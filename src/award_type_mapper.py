"""Maps USAspending award type codes/descriptions to normalized contract types
and classifies actions as new awards vs modifications.

Code reference (confirmed against /api/v2/references/award_types/):
  contracts: A=BPA Call, B=Purchase Order, C=Delivery Order, D=Definitive Contract
  idvs:      IDV_A=GWAC, IDV_B*=IDC, IDV_C=FSS, IDV_D=BOA, IDV_E=BPA
Grants / loans / other financial assistance are excluded upstream.
"""
from __future__ import annotations

import re
from typing import Optional

# Normalized contract-type buckets
CONTRACT_TYPE_BY_CODE = {
    "A": "BPA / BOA",            # BPA Call
    "B": "Purchase Order",
    "C": "Delivery Order",
    "D": "Definitive Contract",
    "IDV_A": "IDIQ / IDV",
    "IDV_B": "IDIQ / IDV",
    "IDV_B_A": "IDIQ / IDV",
    "IDV_B_B": "IDIQ / IDV",
    "IDV_B_C": "IDIQ / IDV",
    "IDV_C": "IDIQ / IDV",
    "IDV_D": "BPA / BOA",        # BOA
    "IDV_E": "BPA / BOA",        # BPA
}

# Codes considered procurement/contract awards (include set)
CONTRACT_CODES = set(CONTRACT_TYPE_BY_CODE.keys())
NON_CONTRACT_CODES = {
    "02", "03", "04", "05", "F001", "F002",            # grants
    "07", "08", "F003", "F004",                        # loans
    "09", "F005", "11", "-1", "F008", "F009", "F010",  # other FA
}


def is_contract_award(award_type_code: Optional[str], category: Optional[str] = None) -> bool:
    if award_type_code and award_type_code in CONTRACT_CODES:
        return True
    if award_type_code and award_type_code in NON_CONTRACT_CODES:
        return False
    # Fall back to category from award detail endpoint
    if category:
        return category.lower() in ("contract", "idv")
    return False


def map_contract_type(award_type_code: Optional[str], type_description: Optional[str] = None) -> str:
    if award_type_code and award_type_code in CONTRACT_TYPE_BY_CODE:
        return CONTRACT_TYPE_BY_CODE[award_type_code]
    desc = (type_description or "").lower()
    if "definitive" in desc:
        return "Definitive Contract"
    if "purchase order" in desc:
        return "Purchase Order"
    if "delivery order" in desc:
        return "Delivery Order"
    if "task order" in desc:
        return "Task Order"
    if "bpa" in desc or "blanket" in desc or "ordering agreement" in desc or "boa" in desc:
        return "BPA / BOA"
    if "idc" in desc or "idiq" in desc or "indefinite" in desc or "gwac" in desc or "schedule" in desc:
        return "IDIQ / IDV"
    if desc:
        return "Other Contract"
    return "Needs Review"


# --- New award vs modification classification (Action Classification) --- #
_MOD_KEYWORDS = re.compile(
    r"\b(modification|admin(istrative)?\s+change|funding\s+(action|change|only)|"
    r"option\s+(year|exercise|period)|exercise\s+option|incremental\s+funding|"
    r"deobligat|de-obligat|reprice|novation|close ?out|closeout)\b",
    re.IGNORECASE,
)


def classify_action(
    contract_type: str,
    modification_number: Optional[str] = None,
    description: Optional[str] = None,
    obligated_amount: Optional[float] = None,
) -> str:
    """Distinguish a new award/order/vehicle from a modification/funding action."""
    mod_num = (modification_number or "").strip().upper()
    desc = description or ""

    # Negative obligation => deobligation
    if obligated_amount is not None and obligated_amount < 0:
        return "Deobligation / Negative Action"

    if _MOD_KEYWORDS.search(desc):
        if "deobligat" in desc.lower() or "de-obligat" in desc.lower():
            return "Deobligation / Negative Action"
        if "option" in desc.lower() or "funding" in desc.lower() or "incremental" in desc.lower():
            return "Option / Funding Action"
        return "Modification"

    # A non-zero, non-"0"/"P00000" modification number signals a mod
    base_mod = mod_num in ("", "0", "00", "000", "0000", "P00000", "A00000", "M00000")
    if not base_mod:
        return "Modification"

    # Base action => a new award/order/vehicle, typed by contract type
    if contract_type == "IDIQ / IDV":
        return "New IDIQ / Vehicle"
    if contract_type == "Delivery Order":
        return "New Delivery Order"
    if contract_type == "Task Order":
        return "New Task Order"
    if contract_type in ("Definitive Contract", "Purchase Order", "BPA / BOA"):
        return "New Award"
    return "Needs Review"
