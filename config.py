"""Central configuration for the OEM Award Tracker.

Nothing here is time-sensitive at import: CURRENT_DATE is computed at runtime
via current_date() so the daily refresh always knows "today" in ET.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9 fallback
    ZoneInfo = None  # type: ignore

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REGISTRY_DIR = DATA_DIR / "registry"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"

for _d in (REGISTRY_DIR, RAW_DIR, PROCESSED_DIR, EXPORTS_DIR, LOGS_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

REGISTRY_CSV = REGISTRY_DIR / "oem_registry.csv"
RAW_JSON = RAW_DIR / "all_awards_raw.json"
PROCESSED_CSV = PROCESSED_DIR / "all_awards_processed.csv"
PROCESSED_PARQUET = PROCESSED_DIR / "all_awards_processed.parquet"
UNMAPPED_CSV = PROCESSED_DIR / "unmapped_candidates.csv"
REJECTED_CSV = PROCESSED_DIR / "rejected_records.csv"
REFRESH_LOG = LOGS_DIR / "refresh_log.csv"
SUMMARY_JSON = PROCESSED_DIR / "data_quality.json"

# --------------------------------------------------------------------------- #
# Dates / timezone
# --------------------------------------------------------------------------- #
TZ_NAME = "America/New_York"
MIN_DATE = date(2023, 1, 1)
REFRESH_HOUR_ET = 7  # 7:00 AM ET recommended refresh

# Toggle: include awards that started before 2023 but remain active today.
# Default OFF per spec — the user wants awards awarded/started no sooner than 2023.
INCLUDE_LEGACY_ACTIVE_AWARDS = os.getenv("INCLUDE_LEGACY_ACTIVE_AWARDS", "false").lower() == "true"


def _tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(TZ_NAME)
        except Exception:
            return None
    return None


def now_et() -> datetime:
    """Current datetime in America/New_York (falls back to naive local)."""
    tz = _tz()
    return datetime.now(tz) if tz else datetime.now()


def current_date() -> date:
    """Today's date in ET, computed at call time (never hardcoded)."""
    return now_et().date()


def refresh_timestamp() -> str:
    """Human-readable 'Last refreshed' string."""
    return now_et().strftime("%Y-%m-%d %H:%M ET")


# --------------------------------------------------------------------------- #
# Parent companies (canonical order used across the UI)
# --------------------------------------------------------------------------- #
PARENT_COMPANIES = [
    "Northrop Grumman",
    "Lockheed Martin",
    "RTX / Raytheon",
    "General Dynamics",
    "Boeing",
    "Airbus",
    "SpaceX",
]

DATA_SOURCE_LABEL = "USAspending.gov API"

# --------------------------------------------------------------------------- #
# Award type codes (procurement / contract & IDV only).
# Confirmed against /api/v2/references/award_types/ — see award_type_mapper.
# Grants/loans/direct payments/other financial assistance are excluded.
# --------------------------------------------------------------------------- #
CONTRACT_AWARD_TYPE_CODES = ["A", "B", "C", "D"]          # definitive/PO/DO/task etc.
IDV_AWARD_TYPE_CODES = ["IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C",
                        "IDV_C", "IDV_D", "IDV_E"]
ALL_CONTRACT_TYPE_CODES = CONTRACT_AWARD_TYPE_CODES + IDV_AWARD_TYPE_CODES

# Base USAspending API
API_BASE = "https://api.usaspending.gov"
USASPENDING_AWARD_URL = "https://www.usaspending.gov/award/{award_id}"
