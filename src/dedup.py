"""Deduplication helpers (spec §27).

Primary key: generated_unique_award_id. Fallback composite key:
award_id/PIID + recipient UEI + action date + potential value.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def award_key(row: dict) -> Tuple:
    gid = row.get("generated_internal_id") or row.get("Generated Award ID") or row.get("generated_unique_award_id")
    if gid:
        return ("gid", gid)
    return (
        "composite",
        row.get("Award ID") or row.get("Award ID / PIID"),
        row.get("Recipient UEI"),
        str(row.get("Base Obligation Date") or row.get("Award Date")),
        str(row.get("Award Amount") or row.get("Potential Value")),
    )


def deduplicate(rows: List[dict]) -> List[dict]:
    """Return rows with duplicates removed, keeping first occurrence."""
    seen = set()
    out = []
    for r in rows:
        k = award_key(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out
