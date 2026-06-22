"""Subsidiary / recipient matching.

Two responsibilities:
  1. map_recipient() — authoritative mapping via the curated registry.
  2. fuzzy_candidate() — flag *unmapped* recipients that look like a tracked OEM
     so they land in unmapped_candidates.csv for human review. Fuzzy matches are
     NEVER auto-added to the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz

from company_registry import Registry, RegistryEntry, normalize_name

# Distinctive tokens per parent used as a cheap pre-filter for fuzzy candidates.
PARENT_TOKENS = {
    "Northrop Grumman": ["northrop", "grumman"],
    "Lockheed Martin": ["lockheed", "sikorsky"],
    "RTX / Raytheon": ["raytheon", "rtx", "pratt", "whitney", "collins aerospace", "rockwell collins"],
    "General Dynamics": ["general dynamics", "electric boat", "bath iron works", "gulfstream"],
    "Boeing": ["boeing"],
    "Airbus": ["airbus"],
    "SpaceX": ["space exploration technologies", "spacex"],
}

FUZZY_THRESHOLD = 88  # token_set_ratio cutoff for "looks like" a tracked entity


@dataclass
class MappingResult:
    parent_company: Optional[str]
    confidence: str           # High | Medium | Low | (unmapped -> None parent)
    matched_legal_name: str
    method: str               # uei | exact-name | parent-name | unmapped | excluded


def map_recipient(
    registry: Registry,
    recipient_name: str,
    uei: str = "",
    parent_name: str = "",
) -> MappingResult:
    if registry.is_excluded(recipient_name):
        return MappingResult(None, "Exclude", recipient_name, "excluded")
    entry: Optional[RegistryEntry] = registry.match(recipient_name, uei=uei, parent_name=parent_name)
    if entry is None:
        return MappingResult(None, "Unmapped", "", "unmapped")
    method = "uei" if (uei and uei.strip().upper() == entry.uei.strip().upper() and entry.uei) else "exact-name"
    return MappingResult(entry.parent_company, entry.confidence, entry.legal_name, method)


@dataclass
class FuzzyResult:
    possible_parent: Optional[str]
    score: float
    recommended_action: str   # Add to registry | Needs manual review | Exclude


def fuzzy_candidate(registry: Registry, recipient_name: str) -> Optional[FuzzyResult]:
    """If an unmapped recipient resembles a tracked OEM, return a review candidate."""
    if not recipient_name:
        return None
    norm = normalize_name(recipient_name)
    lower = recipient_name.lower()

    best_parent = None
    best_score = 0.0
    # token pre-filter
    candidate_parents = [p for p, toks in PARENT_TOKENS.items()
                         if any(t in lower for t in toks)]
    if not candidate_parents:
        return None

    for parent in candidate_parents:
        for entry in registry.all_include_entries():
            if entry.parent_company != parent:
                continue
            for known in [entry.legal_name] + entry.variants:
                score = fuzz.token_set_ratio(norm, normalize_name(known))
                if score > best_score:
                    best_score, best_parent = score, parent

    if best_score >= FUZZY_THRESHOLD:
        action = "Add to registry"
    elif best_score >= 70:
        action = "Needs manual review"
    else:
        # token matched but very low similarity -> likely false positive
        action = "Needs manual review"
    return FuzzyResult(best_parent, round(best_score, 1), action)
