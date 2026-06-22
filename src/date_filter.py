"""Date logic, split into two independent concepts.

1. RECENT CONTRACT (dataset inclusion): the contract was awarded on/after
   2023-01-01. This is what populates "10 Most Recent Contracts Awarded" and
   every supporting table. Expired performance does NOT exclude it.

2. CURRENTLY ACTIVE (used only for "10 Largest Active Awards"): the period of
   performance current end date is today or later. Falls back to the potential
   end date with lower confidence. This is where the current-date tracker
   matters — CURRENT_DATE is computed at runtime in ET, never hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from dateutil import parser as dtparse

import config


def parse_date(value) -> Optional[date]:
    """Parse a USAspending date string/datetime to a date, tolerant of None."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return dtparse.parse(str(value)).date()
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass
class RecentDecision:
    include: bool
    rejection_reason: str = ""


def is_recent_contract(
    action_date,
    current_date: Optional[date] = None,  # accepted for symmetry; unused
    include_legacy: Optional[bool] = None,
) -> RecentDecision:
    """Dataset inclusion: keep contracts awarded on/after MIN_DATE (2023)."""
    legacy = config.INCLUDE_LEGACY_ACTIVE_AWARDS if include_legacy is None else include_legacy
    ad = parse_date(action_date)
    if ad is None:
        return RecentDecision(False, "Missing award date")
    if not legacy and ad < config.MIN_DATE:
        return RecentDecision(False, "Award date before 2023")
    return RecentDecision(True, "")


@dataclass
class ActiveDecision:
    is_active: bool
    active_status: str        # Active | Inactive (performance ended) |
                              # Potentially Active — current end date missing | End date unknown
    date_confidence: str      # High | Needs Review


def active_status(
    pop_current_end,
    pop_potential_end=None,
    current_date: Optional[date] = None,
) -> ActiveDecision:
    """Is the contract's performance period still open as of today (ET)?"""
    cd = current_date or config.current_date()
    ce = parse_date(pop_current_end)
    pe = parse_date(pop_potential_end)

    if ce is not None:
        if ce >= cd:
            return ActiveDecision(True, "Active", "High")
        return ActiveDecision(False, "Inactive (performance ended)", "High")
    if pe is not None:
        if pe >= cd:
            return ActiveDecision(True, "Potentially Active — current end date missing", "Needs Review")
        return ActiveDecision(False, "Inactive (performance ended)", "Needs Review")
    return ActiveDecision(False, "End date unknown", "Needs Review")
