"""Award value normalization + 'Value Basis' assignment.

Largest awards are ranked by POTENTIAL value (base + all options). When that is
missing we fall back to obligated amount and clearly mark the Value Basis so the
UI never silently ranks by the smaller number.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return f
    except (ValueError, TypeError):
        return None


def is_placeholder_amount(v) -> bool:
    """True for USAspending data-entry 'ceiling' sentinels that are not real
    award values — e.g. 999,999,999 / 999,999,999,999 (all-nines) and round
    trillion ceilings used on governmentwide IDV vehicles (OASIS+, GSA MAS…).
    """
    f = _to_float(v)
    if f is None or f <= 0:
        return False
    iv = int(round(f))
    s = str(iv)
    if len(s) >= 9 and set(s) == {"9"}:          # 999999999, 999999999999, …
        return True
    if iv in (1_000_000_000_000, 100_000_000_000, 10_000_000_000_000):
        return True
    return False


@dataclass
class ValueResult:
    potential_value: Optional[float]
    obligated_amount: Optional[float]
    ranking_value: Optional[float]   # value used for "largest" sorting
    value_basis: str                 # Base and All Options | Potential Value | Obligated Amount | Award Amount | IDV Ceiling (placeholder) | Needs Review
    placeholder_ceiling: bool = False


def normalize_value(
    base_and_all_options=None,
    total_potential_value=None,
    potential_award_amount=None,
    current_total_value=None,   # "Award Amount" from spending_by_award
    total_obligation=None,
) -> ValueResult:
    """Pick the best potential value, else fall back; tag the basis used.

    If the potential value is a placeholder ceiling sentinel, it is NOT used to
    rank "largest" awards — we fall back to the obligated amount and flag it,
    so a $1T governmentwide-vehicle ceiling never masquerades as a real award.
    """
    bao = _to_float(base_and_all_options)
    tpv = _to_float(total_potential_value)
    paa = _to_float(potential_award_amount)
    cur = _to_float(current_total_value)
    obl = _to_float(total_obligation)

    potential = None
    pot_basis = "Needs Review"
    if bao is not None and bao > 0:
        potential, pot_basis = bao, "Base and All Options"
    elif tpv is not None and tpv > 0:
        potential, pot_basis = tpv, "Potential Value"
    elif paa is not None and paa > 0:
        potential, pot_basis = paa, "Potential Value"

    placeholder = is_placeholder_amount(potential)

    if potential is not None and not placeholder:
        ranking, basis = potential, pot_basis
    elif obl is not None and obl != 0:
        ranking = obl
        basis = "IDV Ceiling (placeholder); ranked by obligated" if placeholder else "Obligated Amount"
    elif cur is not None and cur != 0 and not is_placeholder_amount(cur):
        ranking, basis = cur, "Award Amount"
    else:
        ranking, basis = (None, "IDV Ceiling (placeholder)") if placeholder else (None, "Needs Review")

    return ValueResult(
        potential_value=(None if placeholder else potential),
        obligated_amount=obl,
        ranking_value=ranking,
        value_basis=basis,
        placeholder_ceiling=placeholder,
    )


def format_currency(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"${v:,.0f}"
