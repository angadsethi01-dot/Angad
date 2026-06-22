# OEM Contract Awards Tracker

A refreshed-daily dashboard tracking **active, current** U.S. government contract
awards to major aerospace & defense OEM families and their real subsidiaries,
using the official [USAspending.gov API](https://api.usaspending.gov/).

Tracked parents: **Northrop Grumman · Lockheed Martin · RTX / Raytheon ·
General Dynamics · Boeing · Airbus · SpaceX**.

It works like an automated, multi-company version of the Northrop "Awards
Summary" tab: per-company KPIs, 10 most recent current awards, 10 largest by
**potential value**, award-category tallies, performance-location counts,
subsidiary breakdown, and a full searchable/exportable award table.

---

## Run it as a local website (easiest)

**Double-click `Start OEM Tracker.command`** in Finder.
(First time only: right-click → Open to approve it past macOS Gatekeeper.)

It creates the environment, installs dependencies, pulls data on first run, and
opens the site in your browser. Or from a terminal:

```bash
cd oem_award_tracker
./run.sh
```

Then open it:
- **On this Mac:** http://localhost:8501
- **From your phone / another device:** use the **Network URL** the launcher
  prints (e.g. `http://192.168.x.x:8501`). The device must be on the same WiFi,
  and you may need to approve the macOS firewall prompt the first time.

To stop the site, press `Ctrl+C` in the terminal (or close the window the
`.command` opened).

## Manual / developer start

```bash
cd oem_award_tracker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Pull + process data (writes data/processed/*)
python refresh.py                 # full pull
python refresh.py --limit 1       # quick test: 1 recipient/company
python refresh.py --no-enrich     # skip per-award detail (faster, no potential value)

# 2. Launch the dashboard
streamlit run app.py
```

The app reads the **processed** dataset only — it never pulls the full API on
page load. Run `refresh.py` on a schedule; the app displays the latest results.

---

## How it works

| Stage | Module | Notes |
|-------|--------|-------|
| API access | `src/usaspending_client.py` | `spending_by_award/` to enumerate contracts+IDVs per recipient, then `awards/<id>/` to enrich with potential value, POP dates, place-of-performance names, PSC/NAICS. Disk-cached, rate-limited. |
| Company mapping | `data/registry/oem_registry.csv` + `src/company_registry.py` + `src/subsidiary_matcher.py` | Authoritative mapping by **normalized exact legal name / UEI**, never naive substring search. Includes explicit *Exclude* rows for deceptive lookalikes (e.g. `SPACEX FIREWORKS LLC`, `SANTA BARBARA AIRBUS`). |
| Date logic | `src/date_filter.py` | Two separate ideas: **(1) recent contract** = awarded on/after 2023-01-01 → this is the dataset behind every page. **(2) currently active** = POP current end ≥ today (ET), used only to filter the "10 Largest Active Awards" section. Missing current-end falls back to potential-end → *Needs Review*. CURRENT_DATE is computed at runtime in ET. `INCLUDE_LEGACY_ACTIVE_AWARDS=true` env toggle (default off). |
| Value | `src/value_normalizer.py` | Ranks by potential value (base + all options); falls back to obligated amount with a `Value Basis` flag. |
| Categorization | `src/category_mapper.py` | Rule-based work-type classification over description + PSC + NAICS → `Award Category`, `Category Confidence`, `Category Reason`. Uniform categories across all OEMs. |
| Award type / action | `src/award_type_mapper.py` | Maps award-type codes to contract types and classifies New Award vs Modification/Funding action. |
| Locations | `src/location_normalizer.py` | Place of performance (not recipient HQ). |
| Aggregation | `src/dashboard_tables.py` | KPIs, latest/largest, category/location tallies, subsidiary & company rollups. |
| UI | `app.py`, `src/charts.py`, `src/exporter.py` | Streamlit pages + Plotly bars + CSV/Excel export. |

The two most accuracy-critical pieces are **`oem_registry.csv`** (correct parent
assignment) and **`category_mapper.py`** (correct work-type assignment).

---

## Daily refresh (7:00 AM ET recommended)

**cron** (local):
```cron
0 7 * * *  cd /path/to/oem_award_tracker && .venv/bin/python refresh.py >> data/logs/cron.log 2>&1
```

**GitHub Actions**: schedule a workflow `cron: '0 11 * * *'` (11:00 UTC ≈ 7:00
ET) running `python refresh.py`, committing/uploading `data/processed/`.

Data is labeled **"refreshed daily"** (not "live") — USAspending has reporting
delays and later corrections.

---

## Data outputs (`data/`)

```
registry/oem_registry.csv        curated parent ↔ recipient mapping (editable)
processed/all_awards_processed.csv|.parquet   accepted, normalized awards
processed/rejected_records.csv    rejected awards + reason
processed/unmapped_candidates.csv fuzzy lookalikes for human review
processed/data_quality.json       refresh summary / DQ counters
logs/refresh_log.csv              one row per refresh
raw/all_awards_raw.json           raw search rows
cache/                            cached award-detail responses (24h TTL)
```

## Extending the registry

1. Find candidates on the **Registry Review** page (`unmapped_candidates.csv`).
2. Verify via USAspending recipient profile / UEI / parent-recipient data.
3. Add a row to `oem_registry.csv` with `Include / High` (or `Medium`).
4. Re-run `python refresh.py`. Fuzzy matches are **never** auto-included.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

Covers date filtering, pre-2023 exclusion, registry/subsidiary mapping,
category mapping, potential-value sorting, location normalization, and dedup.
