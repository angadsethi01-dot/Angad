"""OEM registry loader + name normalization utilities.

The registry (data/registry/oem_registry.csv) is the single source of truth for
mapping recipient legal entities to parent OEMs. Matching is done on *normalized
exact legal names* (plus declared variants and UEIs) — never naive substring
search — because USAspending contains deceptive near-matches like
"SPACEX FIREWORKS LLC" or "SANTA BARBARA AIRBUS".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

import pandas as pd

import config

# Suffixes stripped during normalization so "CORP" == "CORPORATION", etc.
_SUFFIX_MAP = {
    "incorporated": "inc",
    "corporation": "corp",
    "company": "co",
    "limited": "ltd",
    "l l c": "llc",
}
_PUNCT_RE = re.compile(r"[.,/&]+")
_WS_RE = re.compile(r"\s+")


def normalize_name(name: Optional[str]) -> str:
    """Uppercase, strip punctuation, collapse whitespace, unify common suffixes."""
    if not name:
        return ""
    s = str(name).lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    for long, short in _SUFFIX_MAP.items():
        s = re.sub(rf"\b{long}\b", short, s)
    s = _WS_RE.sub(" ", s).strip()
    return s.upper()


@dataclass
class RegistryEntry:
    parent_company: str
    legal_name: str
    variants: List[str]
    uei: str
    parent_recipient_name: str
    include: bool
    confidence: str
    source: str
    notes: str

    @property
    def normalized_names(self) -> List[str]:
        names = [self.legal_name] + self.variants
        return [normalize_name(n) for n in names if n]


@dataclass
class Registry:
    entries: List[RegistryEntry]
    # normalized name -> entry (Include only)
    _by_name: Dict[str, RegistryEntry] = field(default_factory=dict)
    _by_uei: Dict[str, RegistryEntry] = field(default_factory=dict)
    _excluded_names: Dict[str, RegistryEntry] = field(default_factory=dict)

    def build_index(self) -> "Registry":
        for e in self.entries:
            target = self._by_name if e.include else self._excluded_names
            for n in e.normalized_names:
                target.setdefault(n, e)
            if e.include and e.uei:
                self._by_uei[e.uei.strip().upper()] = e
        return self

    # ----- lookups ----- #
    def match(self, recipient_name: str, uei: str = "", parent_name: str = "") -> Optional[RegistryEntry]:
        """Return the registry entry for a recipient, or None if unmapped/excluded."""
        if uei:
            hit = self._by_uei.get(uei.strip().upper())
            if hit:
                return hit
        norm = normalize_name(recipient_name)
        if norm in self._excluded_names:
            return None  # explicitly excluded false-positive
        if norm in self._by_name:
            return self._by_name[norm]
        # Fall back to parent recipient name exact match (e.g. divisions rolled up)
        pnorm = normalize_name(parent_name)
        if pnorm and pnorm in self._by_name:
            return self._by_name[pnorm]
        return None

    def is_excluded(self, recipient_name: str) -> bool:
        return normalize_name(recipient_name) in self._excluded_names

    def include_names_by_company(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {c: [] for c in config.PARENT_COMPANIES}
        for e in self.entries:
            if e.include:
                out.setdefault(e.parent_company, []).append(e.legal_name)
        return out

    def search_terms(self, parent_company: str) -> List[str]:
        """Legal names to feed to USAspending recipient_search_text for a company."""
        terms = []
        for e in self.entries:
            if e.include and e.parent_company == parent_company:
                terms.append(e.legal_name)
        return terms

    def all_include_entries(self) -> List[RegistryEntry]:
        return [e for e in self.entries if e.include]


def _split_variants(raw: str) -> List[str]:
    if not raw or pd.isna(raw):
        return []
    return [v.strip() for v in str(raw).split(";") if v.strip()]


@lru_cache(maxsize=1)
def load_registry(path: str = str(config.REGISTRY_CSV)) -> Registry:
    df = pd.read_csv(path, dtype=str).fillna("")
    entries: List[RegistryEntry] = []
    for _, r in df.iterrows():
        include = str(r.get("Include / Exclude", "")).strip().lower() == "include"
        entries.append(
            RegistryEntry(
                parent_company=r.get("Parent Company", "").strip(),
                legal_name=r.get("Recipient Legal Name", "").strip(),
                variants=_split_variants(r.get("Known Name Variant", "")),
                uei=r.get("Recipient UEI", "").strip(),
                parent_recipient_name=r.get("Parent Recipient Name", "").strip(),
                include=include,
                confidence=r.get("Mapping Confidence", "").strip() or "Medium",
                source=r.get("Source", "").strip(),
                notes=r.get("Notes", "").strip(),
            )
        )
    return Registry(entries=entries).build_index()
