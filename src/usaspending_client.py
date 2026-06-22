"""USAspending.gov API client.

Strategy:
  1. spending_by_award/  -> enumerate contract+IDV awards per recipient (paginated),
     getting generated_internal_id and the bulk of display fields.
  2. awards/<id>/        -> enrich each award with potential value
     (base_and_all_options), POP potential_end_date, full place-of-performance
     names, PSC/NAICS, and category/type — fields the search endpoint omits.

Award detail responses are cached on disk so repeat refreshes are cheap and the
app never hammers the API.
"""
from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

import config
from logger import get_logger

log = get_logger(__name__)

SEARCH_URL = f"{config.API_BASE}/api/v2/search/spending_by_award/"
AWARD_URL = f"{config.API_BASE}/api/v2/awards/{{award_id}}/"

# Fields requested from spending_by_award (display names supported by the API)
SEARCH_FIELDS = [
    "Award ID", "Recipient Name", "Recipient UEI",
    "Awarding Agency", "Awarding Sub Agency", "Awarding Office",
    "Funding Agency", "Funding Sub Agency",
    "Start Date", "End Date", "Last Date to Order", "Base Obligation Date",
    "Award Amount", "Total Outlays", "Description",
    "Contract Award Type", "Award Type", "NAICS", "PSC",
    "Place of Performance City Code", "Place of Performance State Code",
    "Place of Performance Country Code", "Place of Performance Zip5",
    "recipient_id", "prime_award_recipient_id", "def_codes",
]


class USASpendingClient:
    def __init__(self, cache_dir: Path = config.CACHE_DIR, min_interval: float = 0.3,
                 cache_ttl_hours: float = 24.0):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json",
                                     "User-Agent": "OEM-Award-Tracker/1.0",
                                     # USAspending occasionally drops keep-alive
                                     # connections; close after each request.
                                     "Connection": "close"})
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.cache_ttl = cache_ttl_hours * 3600
        self._last_call = 0.0

    # ----- low level ----- #
    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()

    def _post(self, url: str, payload: dict, retries: int = 6) -> dict:
        # USAspending intermittently returns 429/503/502 under load. Back off
        # generously and retry; raise only after exhausting all attempts.
        last_err = "unknown"
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.post(url, data=json.dumps(payload), timeout=90)
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(30, 2 ** attempt + 1)
                    last_err = f"HTTP {resp.status_code}"
                    log.warning("%s from search; backing off %ss (attempt %d/%d)",
                                last_err, wait, attempt + 1, retries)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                last_err = str(e)
                log.warning("POST %s failed (attempt %d/%d): %s", url, attempt + 1, retries, e)
                time.sleep(min(20, 2 * (attempt + 1)))
        raise RuntimeError(f"POST {url} failed after {retries} retries ({last_err})")

    def _get(self, url: str, retries: int = 2, throttle: bool = True) -> Optional[dict]:
        # Award-detail enrichment is best-effort: USAspending intermittently
        # drops connections / 500s on some IDV detail calls. Failures fall back
        # to search-row values, so we keep retries cheap rather than blocking.
        for attempt in range(retries):
            if throttle:
                self._throttle()
            try:
                # Separate session per thread keeps concurrent GETs thread-safe.
                getter = requests.get if not throttle else self.session.get
                resp = getter(url, timeout=45, headers={"User-Agent": "OEM-Award-Tracker/1.0",
                                                         "Connection": "close"})
                if resp.status_code in (404, 500, 502, 503):
                    return None
                if resp.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                log.debug("GET %s failed (attempt %d): %s", url, attempt + 1, e)
                time.sleep(0.6 * (attempt + 1))
        return None

    # ----- search ----- #
    def search_awards(
        self,
        recipient_names: List[str],
        award_type_codes: Optional[List[str]] = None,
        start_date: str = "2023-01-01",
        end_date: Optional[str] = None,
        page_limit: int = 100,
        max_pages: int = 5,
        sorts: Optional[List[str]] = None,
    ) -> List[dict]:
        """Enumerate awards for a list of recipient legal names.

        Two sort passes per recipient so both dashboard sections are covered:
          - "Start Date" desc  -> the most RECENT contracts (POP start ≈ signed)
          - "Award Amount" desc -> the LARGEST awards (for largest-active section)
        The genuine "10 most recent" is re-sorted by signed date downstream.

        Each recipient term is queried separately: a multi-term
        recipient_search_text OR-query combined with the full field set is
        expensive enough that USAspending returns 503. Per-term queries are
        cheap and reliable; duplicates are removed by the caller.
        """
        award_type_codes = award_type_codes or config.ALL_CONTRACT_TYPE_CODES
        end_date = end_date or config.current_date().isoformat()
        sorts = sorts or ["Start Date", "Award Amount"]
        results: List[dict] = []

        for name in recipient_names:
          for sort_field in sorts:
            # The API splits contracts vs IDVs by award_type group; request both
            for code_group in (config.CONTRACT_AWARD_TYPE_CODES, config.IDV_AWARD_TYPE_CODES):
                group = [c for c in code_group if c in award_type_codes]
                if not group:
                    continue
                page = 1
                while page <= max_pages:
                    payload = {
                        "filters": {
                            "award_type_codes": group,
                            "recipient_search_text": [name],
                            "time_period": [{"start_date": start_date, "end_date": end_date}],
                        },
                        "fields": SEARCH_FIELDS,
                        "page": page,
                        "limit": page_limit,
                        "sort": sort_field,
                        "order": "desc",
                        "subawards": False,
                    }
                    try:
                        data = self._post(SEARCH_URL, payload)
                    except RuntimeError as e:
                        log.error("Search '%s' (%s) page %d failed, skipping rest: %s",
                                  name, sort_field, page, e)
                        break
                    batch = data.get("results", [])
                    results.extend(batch)
                    meta = data.get("page_metadata", {})
                    if not meta.get("hasNext") or not batch:
                        break
                    page += 1
        return results

    # ----- detail (cached) ----- #
    def _cache_path(self, award_id: str) -> Path:
        h = hashlib.md5(award_id.encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    def get_award_detail(self, generated_internal_id: str, use_cache: bool = True,
                         throttle: bool = False) -> Optional[dict]:
        cache_file = self._cache_path(generated_internal_id)
        if use_cache and cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < self.cache_ttl:
                try:
                    return json.loads(cache_file.read_text())
                except json.JSONDecodeError:
                    pass
        data = self._get(AWARD_URL.format(award_id=generated_internal_id), throttle=throttle)
        if data is not None:
            cache_file.write_text(json.dumps(data))
        return data

    def get_award_details_bulk(self, gids: List[str], workers: int = 6,
                               progress=None) -> Dict[str, Optional[dict]]:
        """Fetch many award details concurrently (cache-aware). Returns gid->detail.

        Concurrency (not the per-call throttle) is the rate limiter here, so a
        few hundred enrichment calls finish in a couple of minutes instead of
        tens of minutes. Cached entries cost no network call.
        """
        results: Dict[str, Optional[dict]] = {}
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.get_award_detail, g): g for g in gids}
            for fut in as_completed(futures):
                g = futures[fut]
                try:
                    results[g] = fut.result()
                except Exception:  # noqa: BLE001 - best-effort enrichment
                    results[g] = None
                done += 1
                if progress and done % 200 == 0:
                    progress(done, len(gids))
        return results

    def award_types_reference(self) -> dict:
        return self._get(f"{config.API_BASE}/api/v2/references/award_types/") or {}
