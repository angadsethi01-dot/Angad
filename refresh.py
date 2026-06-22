"""Daily refresh pipeline.

Run:  python refresh.py            (full pull from USAspending)
      python refresh.py --limit 5  (cap recipients/company for a quick test)

Steps (spec §32): load registry -> pull contract/IDV awards -> normalize ->
date filter -> company mapping -> categorize -> normalize locations/values ->
dedupe -> save processed / rejected / unmapped / summary / refresh log.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd

import config
from logger import get_logger, append_refresh_log
from company_registry import load_registry
from usaspending_client import USASpendingClient
import date_filter
import value_normalizer
import location_normalizer
import category_mapper
import award_type_mapper
import subsidiary_matcher

log = get_logger("refresh")

PROCESSED_COLUMNS = [
    "Generated Award ID", "Award ID / PIID", "Parent Award ID",
    "Awarding Department", "Awarding Subagency", "Awarding Office",
    "Funding Department", "Funding Subagency",
    "Recipient Legal Name", "Recipient UEI", "Parent Recipient Name",
    "OEM Parent Company", "Award Description", "Award Type", "Award Type Code",
    "Action Classification",
    "Award Date", "Period of Performance Start Date",
    "Period of Performance Current End Date", "Period of Performance Potential End Date",
    "Ordering Period End Date",
    "Potential Value", "Obligated Amount", "Value Basis",
    "NAICS Code", "NAICS Description", "PSC Code", "PSC Description",
    "Performance City", "Performance State", "Performance Country",
    "Full Performance Location", "Recipient Location",
    "Award Category", "Category Confidence", "Category Reason",
    "Currently Active", "Active Status", "Date Confidence", "Mapping Confidence",
    "USAspending Link", "Last Refreshed",
]


def _g(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d.get(k)
    return default


def _detail_value(detail: Optional[dict], path: List[str], default=None):
    cur = detail
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur not in (None, "") else default


def build_record(search_row: dict, detail: Optional[dict], registry, refreshed: str,
                 cd: date) -> Dict:
    """Combine a search row + award detail into one normalized record dict, plus
    return mapping/date decision metadata for routing (accept/reject/unmapped)."""
    detail = detail or {}
    gid = search_row.get("generated_internal_id") or _g(detail, "generated_unique_award_id")
    piid = search_row.get("Award ID") or _g(detail, "piid")

    recipient = search_row.get("Recipient Name") or _detail_value(detail, ["recipient", "recipient_name"], "")
    uei = search_row.get("Recipient UEI") or _detail_value(detail, ["recipient", "recipient_hash"], "") or ""
    parent_name = _detail_value(detail, ["recipient", "parent_recipient_name"], "") or ""

    # ----- company mapping ----- #
    mapping = subsidiary_matcher.map_recipient(registry, recipient, uei=uei, parent_name=parent_name)

    # ----- dates ----- #
    pop = detail.get("period_of_performance", {}) if isinstance(detail.get("period_of_performance"), dict) else {}
    action_date = search_row.get("Base Obligation Date") or _g(detail, "date_signed")
    pop_start = pop.get("start_date") or search_row.get("Start Date")
    pop_cur_end = pop.get("end_date") or search_row.get("End Date")
    pop_pot_end = pop.get("potential_end_date")
    ordering_end = search_row.get("Last Date to Order")

    recent = date_filter.is_recent_contract(action_date)
    active = date_filter.active_status(pop_cur_end, pop_pot_end, current_date=cd)

    # ----- values ----- #
    val = value_normalizer.normalize_value(
        base_and_all_options=_g(detail, "base_and_all_options"),
        current_total_value=search_row.get("Award Amount"),
        total_obligation=_g(detail, "total_obligation", default=search_row.get("Award Amount")),
    )

    # ----- location (prefer place_of_performance from detail) ----- #
    place = detail.get("place_of_performance", {}) if isinstance(detail.get("place_of_performance"), dict) else {}
    loc = location_normalizer.normalize_location(
        city=place.get("city_name"),
        state=place.get("state_name"),
        state_code=place.get("state_code") or search_row.get("Place of Performance State Code"),
        country=place.get("country_name"),
        country_code=place.get("location_country_code") or search_row.get("Place of Performance Country Code"),
    )
    rec_loc = detail.get("recipient", {}).get("location", {}) if isinstance(detail.get("recipient"), dict) else {}
    rec_location = location_normalizer.normalize_location(
        city=rec_loc.get("city_name"), state=rec_loc.get("state_name"),
        state_code=rec_loc.get("state_code"), country=rec_loc.get("country_name"),
        country_code=rec_loc.get("location_country_code"),
    ).full_location

    # ----- codes ----- #
    naics = search_row.get("NAICS") if isinstance(search_row.get("NAICS"), dict) else {}
    psc = search_row.get("PSC") if isinstance(search_row.get("PSC"), dict) else {}
    if not naics:
        nh = detail.get("naics_hierarchy", {})
        naics = nh.get("base_code", {}) if isinstance(nh, dict) else {}
    if not psc:
        ph = detail.get("psc_hierarchy", {})
        psc = ph.get("base_code", {}) if isinstance(ph, dict) else {}

    description = search_row.get("Description") or _g(detail, "description") or ""

    # ----- category ----- #
    cat, cat_conf, cat_reason = category_mapper.categorize(
        description=description,
        psc_code=psc.get("code"), psc_description=psc.get("description"),
        naics_code=naics.get("code"), naics_description=naics.get("description"),
    )

    # ----- award type + action classification ----- #
    type_code = detail.get("type") or search_row.get("Award Type")
    type_desc = detail.get("type_description") or search_row.get("Contract Award Type")
    contract_type = award_type_mapper.map_contract_type(type_code, type_desc)
    mod_number = _detail_value(detail, ["latest_transaction_contract_data", "modification_number"])
    action_class = award_type_mapper.classify_action(
        contract_type, modification_number=mod_number,
        description=description, obligated_amount=val.obligated_amount,
    )

    record = {
        "Generated Award ID": gid,
        "Award ID / PIID": piid,
        "Parent Award ID": _detail_value(detail, ["parent_award", "piid"]),
        "Awarding Department": search_row.get("Awarding Agency"),
        "Awarding Subagency": search_row.get("Awarding Sub Agency"),
        "Awarding Office": search_row.get("Awarding Office") or _detail_value(detail, ["awarding_agency", "office_agency_name"]),
        "Funding Department": search_row.get("Funding Agency"),
        "Funding Subagency": search_row.get("Funding Sub Agency"),
        "Recipient Legal Name": recipient,
        "Recipient UEI": search_row.get("Recipient UEI") or "",
        "Parent Recipient Name": parent_name,
        "OEM Parent Company": mapping.parent_company,
        "Award Description": description,
        "Award Type": contract_type,
        "Award Type Code": type_code,
        "Action Classification": action_class,
        "Award Date": date_filter.parse_date(action_date),
        "Period of Performance Start Date": date_filter.parse_date(pop_start),
        "Period of Performance Current End Date": date_filter.parse_date(pop_cur_end),
        "Period of Performance Potential End Date": date_filter.parse_date(pop_pot_end),
        "Ordering Period End Date": date_filter.parse_date(ordering_end),
        "Potential Value": val.potential_value,
        "Obligated Amount": val.obligated_amount,
        "Value Basis": val.value_basis,
        "NAICS Code": naics.get("code"),
        "NAICS Description": naics.get("description"),
        "PSC Code": psc.get("code"),
        "PSC Description": psc.get("description"),
        "Performance City": loc.city,
        "Performance State": loc.state,
        "Performance Country": loc.country,
        "Full Performance Location": loc.full_location,
        "Recipient Location": rec_location,
        "Award Category": cat,
        "Category Confidence": cat_conf,
        "Category Reason": cat_reason,
        "Currently Active": "Yes" if active.is_active else "No",
        "Active Status": active.active_status,
        "Date Confidence": active.date_confidence,
        "Mapping Confidence": mapping.confidence,
        "USAspending Link": config.USASPENDING_AWARD_URL.format(award_id=gid) if gid else "",
        "Last Refreshed": refreshed,
    }
    return {"record": record, "mapping": mapping, "recent": recent,
            "recipient": recipient, "description": description,
            "ranking_value": val.ranking_value}


def run_refresh(recipient_limit: Optional[int] = None, enrich: bool = True,
                page_limit: int = 100, max_pages: int = 5,
                max_awards: Optional[int] = None) -> dict:
    t0 = time.time()
    cd = config.current_date()
    refreshed = config.refresh_timestamp()
    log.info("Refresh start — CURRENT_DATE=%s", cd)

    registry = load_registry()
    client = USASpendingClient()

    raw_rows: List[dict] = []
    seen_ids = set()
    for company in config.PARENT_COMPANIES:
        terms = registry.search_terms(company)
        if recipient_limit:
            terms = terms[:recipient_limit]
        if not terms:
            continue
        log.info("[%s] searching %d recipient term(s)", company, len(terms))
        rows = client.search_awards(terms, page_limit=page_limit, max_pages=max_pages,
                                    end_date=cd.isoformat())
        for r in rows:
            gid = r.get("generated_internal_id")
            if gid and gid in seen_ids:
                continue
            if gid:
                seen_ids.add(gid)
            raw_rows.append(r)
    log.info("Pulled %d unique raw award rows", len(raw_rows))

    if max_awards and len(raw_rows) > max_awards:
        # Keep the highest-value rows (already sorted desc per group) for bounded runs
        raw_rows = raw_rows[:max_awards]
        log.info("Capped to %d raw rows for this run (--max-awards)", len(raw_rows))

    config.RAW_JSON.write_text(json.dumps(raw_rows)[:50_000_000])  # cap size

    accepted: List[dict] = []
    rejected: List[dict] = []
    unmapped: Dict[str, dict] = {}
    candidates: List[dict] = []   # mapped + recent rows (awaiting enrichment)

    # ---- Pass 1: classify every row with NO API calls (map + recency) ---- #
    for row in raw_rows:
        recipient = row.get("Recipient Name") or ""
        uei = row.get("Recipient UEI") or ""
        mapping = subsidiary_matcher.map_recipient(registry, recipient, uei=uei)
        if mapping.parent_company is None:
            built = build_record(row, None, registry, refreshed, cd)
            rec = built["record"]
            reason = "Recipient explicitly excluded" if mapping.method == "excluded" else "Recipient not mapped to tracked OEM"
            rejected.append({**rec, "Rejection Reason": reason})
            if mapping.method == "unmapped":
                fc = subsidiary_matcher.fuzzy_candidate(registry, recipient)
                if fc and fc.possible_parent:
                    key = recipient.upper()
                    cur = unmapped.get(key)
                    if cur:
                        cur["Award Count"] += 1
                        cur["Total Potential Value"] += (built["ranking_value"] or 0)
                    else:
                        unmapped[key] = {
                            "Candidate Recipient Name": recipient,
                            "Candidate UEI": rec["Recipient UEI"],
                            "Possible Parent Company": fc.possible_parent,
                            "Parent Recipient Name": rec["Parent Recipient Name"],
                            "Award Count": 1,
                            "Total Potential Value": built["ranking_value"] or 0,
                            "Example Award Description": (built["description"] or "")[:160],
                            "Fuzzy Match Score": fc.score,
                            "Recommended Action": fc.recommended_action,
                        }
            continue

        recent = date_filter.is_recent_contract(row.get("Base Obligation Date"))
        if not recent.include:
            built = build_record(row, None, registry, refreshed, cd)
            rejected.append({**built["record"], "Rejection Reason": recent.rejection_reason})
            continue

        row["_company"] = mapping.parent_company
        candidates.append(row)

    # ---- Enrich EVERY candidate (full enrichment) ---- #
    # Fetch the award detail (potential value, POP potential end date, place-of-
    # performance city) for all mapped 2023+ contracts so "Potential Value" is
    # populated everywhere USAspending actually records it. Fetched concurrently
    # and disk-cached. Set OEM_ENRICH_CAP to bound it again if ever needed.
    cap = int(os.getenv("OEM_ENRICH_CAP", "0")) or None
    enrich_gids = set()
    if enrich:
        ordered = candidates
        if cap:
            by_co: Dict[str, List[dict]] = {}
            for row in candidates:
                by_co.setdefault(row["_company"], []).append(row)
            ordered = []
            for rows in by_co.values():
                ordered += sorted(rows, key=lambda r: float(r.get("Award Amount") or 0), reverse=True)[:cap]
        for r in ordered:
            g = r.get("generated_internal_id")
            if g:
                enrich_gids.add(g)
        log.info("Enriching %d of %d candidate awards (concurrent)...", len(enrich_gids), len(candidates))

    details = {}
    if enrich_gids:
        details = client.get_award_details_bulk(
            list(enrich_gids), workers=6,
            progress=lambda d, t: log.info("  enriched %d/%d", d, t))

    # ---- Pass 2: build every candidate record (with detail where fetched) ---- #
    for row in candidates:
        gid = row.get("generated_internal_id")
        built = build_record(row, details.get(gid), registry, refreshed, cd)
        accepted.append(built["record"])

    # ----- save outputs ----- #
    df = pd.DataFrame(accepted, columns=PROCESSED_COLUMNS) if accepted else pd.DataFrame(columns=PROCESSED_COLUMNS)

    # Safeguard: if this run produced nothing (e.g. the API throttled every
    # search call) but a previous good dataset exists, do NOT overwrite it.
    if df.empty and config.PROCESSED_CSV.exists():
        prev = pd.read_csv(config.PROCESSED_CSV)
        if not prev.empty:
            log.error("Refresh produced 0 accepted records (likely API throttling); "
                      "KEEPING the previous dataset of %d awards.", len(prev))
            append_refresh_log({
                "refresh_timestamp": refreshed, "current_date": cd.isoformat(),
                "raw_records": len(raw_rows), "accepted_records": 0,
                "rejected_records": len(rejected), "unmapped_candidates": len(unmapped),
                "companies": 0, "duration_seconds": round(time.time() - t0, 1),
                "status": "aborted-empty", "notes": "kept previous dataset; likely API throttling",
            })
            return {"status": "aborted-empty", "kept_previous": len(prev)}

    df.to_csv(config.PROCESSED_CSV, index=False)
    try:
        df.to_parquet(config.PROCESSED_PARQUET, index=False)
    except Exception as e:  # pyarrow may not be present
        log.warning("Parquet save skipped: %s", e)

    rej_df = pd.DataFrame(rejected)
    rej_df.to_csv(config.REJECTED_CSV, index=False)

    unmapped_rows = sorted(unmapped.values(), key=lambda x: -x["Award Count"])
    unm_df = pd.DataFrame(unmapped_rows)
    unm_df.to_csv(config.UNMAPPED_CSV, index=False)

    summary = build_summary(df, rej_df, unm_df, refreshed, cd, len(raw_rows), time.time() - t0)
    config.SUMMARY_JSON.write_text(json.dumps(summary, indent=2, default=str))

    append_refresh_log({
        "refresh_timestamp": refreshed, "current_date": cd.isoformat(),
        "raw_records": len(raw_rows), "accepted_records": len(df),
        "rejected_records": len(rej_df), "unmapped_candidates": len(unm_df),
        "companies": df["OEM Parent Company"].nunique() if len(df) else 0,
        "duration_seconds": round(time.time() - t0, 1),
        "status": "success",
        "notes": "" if len(df) else "no accepted records",
    })
    log.info("Refresh done: %d accepted, %d rejected, %d unmapped in %.1fs",
             len(df), len(rej_df), len(unm_df), time.time() - t0)
    return summary


def build_summary(df, rej_df, unm_df, refreshed, cd, raw_count, duration) -> dict:
    def safe_int(x):
        return int(x) if x is not None else 0
    return {
        "last_refreshed": refreshed,
        "current_date": cd.isoformat(),
        "data_source": config.DATA_SOURCE_LABEL,
        "raw_records": raw_count,
        "accepted_records": len(df),
        "rejected_records": len(rej_df),
        "unmapped_candidates": len(unm_df),
        "records_missing_potential_value": safe_int((df["Potential Value"].isna()).sum()) if len(df) else 0,
        "records_missing_perf_end": safe_int((df["Period of Performance Current End Date"].isna()).sum()) if len(df) else 0,
        "records_using_obligated_fallback": safe_int((df["Value Basis"].isin(["Obligated Amount", "Award Amount"])).sum()) if len(df) else 0,
        "records_low_category_confidence": safe_int((df["Category Confidence"] == "Low / Needs Review").sum()) if len(df) else 0,
        "records_low_mapping_confidence": safe_int((df["Mapping Confidence"] == "Low").sum()) if len(df) else 0,
        "records_low_date_confidence": safe_int((df["Date Confidence"] == "Needs Review").sum()) if len(df) else 0,
        "duration_seconds": round(duration, 1),
        "by_company": (df.groupby("OEM Parent Company").size().to_dict() if len(df) else {}),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap recipients per company (quick test)")
    ap.add_argument("--no-enrich", action="store_true", help="skip award detail enrichment (faster, no potential value)")
    ap.add_argument("--max-pages", type=int, default=5)
    ap.add_argument("--page-limit", type=int, default=100, help="results per page (lower = faster bounded runs)")
    ap.add_argument("--max-awards", type=int, default=None, help="cap total awards processed (bounded test runs)")
    args = ap.parse_args()
    run_refresh(recipient_limit=args.limit, enrich=not args.no_enrich,
                max_pages=args.max_pages, page_limit=args.page_limit, max_awards=args.max_awards)
