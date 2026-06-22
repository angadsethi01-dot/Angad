"""Rule-based work-type categorization (the core accuracy piece).

Assigns every award a standardized Award Category based on description keywords,
PSC code/description, and NAICS code/description — NOT by company/agency/size/
location. Returns (category, confidence, reason).

Confidence:
  High   -> a strong PSC/keyword signal clearly identifies the work type
  Medium -> signals point to a related category, or only one weak signal
  Low / Needs Review -> vague/generic description and no code signal
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Canonical category list (must stay uniform across all OEMs)
CATEGORIES = [
    "Aircraft / Aviation Systems",
    "Aircraft Maintenance / Sustainment",
    "Space / Satellite Systems",
    "Launch / Space Transportation",
    "Missiles / Weapons / Ordnance",
    "Sensors / Radar / Electronic Warfare",
    "Communications / RF Systems",
    "Shipboard / Maritime Systems",
    "Ground Vehicles / Land Systems",
    "Propulsion / Engines / Power Systems",
    "Electronics / Electrical Components",
    "Fluid Systems / Mechanical",
    "Mechanical Hardware / Parts",
    "Software / IT / Cyber",
    "Cybersecurity / Information Assurance",
    "Engineering / Technical Services",
    "Manufacturing / Production",
    "R&D / Prototype / Advanced Development",
    "Semiconductor R&D / Testing",
    "Logistics / Supply Support",
    "Testing / Quality / Inspection",
    "Training / Simulation",
    "Professional / Program Support",
    "Facilities / Construction",
    "Commodities / Parts",
    "General Contract Support",
    "Other / Needs Review",
]


@dataclass
class Rule:
    category: str
    kw: Optional[re.Pattern]            # description keyword pattern
    psc_prefixes: Tuple[str, ...] = ()  # PSC code prefixes
    naics_prefixes: Tuple[str, ...] = ()
    priority: int = 50                  # lower = evaluated first


def _kw(*words: str) -> re.Pattern:
    return re.compile(r"(?i)\b(" + "|".join(words) + r")\b")


# Rules ordered by specificity/priority. Platform/program names are deliberately
# high priority so e.g. "F-35 sustainment" lands on sustainment, "B-21" on aircraft.
RULES: List[Rule] = [
    # --- Maintenance / sustainment (check before generic aircraft) --- #
    Rule("Aircraft Maintenance / Sustainment",
         _kw("sustainment", "depot", "overhaul", "repair", "maintenance", "spares",
             "aircraft component", "aircraft accessor", "aircraft parts", "mro",
             "field service", "logistics support.*aircraft"),
         psc_prefixes=("J0", "J15", "J16", "J17", "J28"), priority=20),

    # --- Launch / space transportation --- #
    Rule("Launch / Space Transportation",
         _kw("launch service", "launch vehicle", "space transportation", "rideshare",
             "falcon", "starship", "national security space launch", "nssl", "rocket"),
         psc_prefixes=("AR3", "V1"), priority=15),

    # --- Space / satellite --- #
    Rule("Space / Satellite Systems",
         _kw("satellite", "spacecraft", "payload", "on-orbit", "orbital",
             "space vehicle", "ground station", "gps iii", "sbirs", "next-gen opir",
             "space domain", "constellation"),
         psc_prefixes=("18", "AR1", "AR2", "AR4", "AR9"), priority=22),

    # --- Missiles / weapons / ordnance --- #
    Rule("Missiles / Weapons / Ordnance",
         _kw("missile", "interceptor", "munition", "ordnance", "warhead", "rocket motor",
             "javelin", "tomahawk", "amraam", "patriot", "gmlrs", "hypersonic",
             "stand-in attack weapon", "siaw", "ngi", "sentinel", "bomb", "torpedo",
             "ammunition", "projectile"),
         psc_prefixes=("14", "13", "10", "11", "12"), priority=18),

    # --- Sensors / radar / EW --- #
    Rule("Sensors / Radar / Electronic Warfare",
         _kw("radar", "g/ator", "gator", "sensor", "electronic warfare", "ew suite",
             "electro-optic", "infrared", "eo/ir", "surveillance", "seeker",
             "signals intelligence", "sigint", "jammer", "deep space advanced radar",
             "dsarc", "targeting pod", "aesa"),
         psc_prefixes=("58", "59", "AS"), priority=24),

    # --- Communications / RF --- #
    Rule("Communications / RF Systems",
         _kw("communication", "comms", "rf system", "radio", "antenna", "satcom",
             "data link", "transceiver", "waveform", "tactical network"),
         psc_prefixes=("58",), priority=40),

    # --- Shipboard / maritime --- #
    Rule("Shipboard / Maritime Systems",
         _kw("submarine", "shipboard", "naval", "ship", "frigate", "destroyer",
             "combat system", "gyro compass", "navigation equipment", "hull",
             "shipyard", "sonar", "virginia class", "columbia class", "ddg",
             "maritime", "marine propulsion"),
         psc_prefixes=("19", "20", "J19", "J20"), priority=23),

    # --- Ground vehicles / land --- #
    Rule("Ground Vehicles / Land Systems",
         _kw("abrams", "tank", "stryker", "armored vehicle", "ground vehicle",
             "combat vehicle", "tactical vehicle", "hmmwv", "land systems",
             "fighting vehicle", "mrap"),
         psc_prefixes=("23", "24", "25"), priority=23),

    # --- Propulsion / engines --- #
    Rule("Propulsion / Engines / Power Systems",
         _kw("engine", "propulsion", "turbine", "f135", "f119", "gas turbine",
             "power system", "generator", "auxiliary power", "rocket engine"),
         psc_prefixes=("28", "29", "61"), priority=30),

    # --- Aircraft / aviation (generic, after sustainment/missile/space) --- #
    Rule("Aircraft / Aviation Systems",
         _kw("aircraft", "airframe", "fixed wing", "rotary wing", "helicopter",
             "f-35", "f-22", "b-21", "kc-46", "e-130j", "e-2", "p-8", "ch-53",
             "uh-60", "v-22", "fighter", "bomber", "drone", "unmanned aircraft",
             "uas", "global hawk", "triton"),
         psc_prefixes=("15", "16", "17"), priority=35),

    # --- Cybersecurity --- #
    Rule("Cybersecurity / Information Assurance",
         _kw("cybersecurity", "information assurance", "cyber defense", "zero trust",
             "security operations", "vulnerability", "accreditation", "risk management framework"),
         priority=26),

    # --- Software / IT --- #
    Rule("Software / IT / Cyber",
         _kw("software", "cloud", "information technology", "it services", "data center",
             "enterprise system", "application development", "it modernization",
             "help desk", "network operations", "devsecops"),
         psc_prefixes=("70", "DA", "DB", "DC", "DD", "DE", "DF", "DG", "DH", "DJ"),
         naics_prefixes=("5415", "5182"), priority=28),

    # --- Semiconductor R&D --- #
    Rule("Semiconductor R&D / Testing",
         _kw("semiconductor", "microelectronic", "foundry", "wafer", "asic", "fpga",
             "integrated circuit", "chip fabrication"),
         priority=19),

    # --- R&D / prototype --- #
    Rule("R&D / Prototype / Advanced Development",
         _kw("research and development", "r&d", "prototype", "advanced development",
             "technology maturation", "experimental", "demonstration", "ota",
             "other transaction", "applied research", "basic research"),
         psc_prefixes=("A",), priority=33),

    # --- Training / simulation --- #
    Rule("Training / Simulation",
         _kw("training", "simulator", "simulation", "trainer", "courseware",
             "instruction", "war ?game"),
         psc_prefixes=("69",), priority=27),

    # --- Testing / quality --- #
    Rule("Testing / Quality / Inspection",
         _kw("test fixture", "test equipment", "testing", "evaluation", "calibration",
             "inspection", "quality assurance", "test and evaluation"),
         psc_prefixes=("66",), priority=34),

    # --- Logistics / supply --- #
    Rule("Logistics / Supply Support",
         _kw("logistics", "supply support", "supply chain", "warehous", "distribution",
             "transportation services", "freight", "material support"),
         psc_prefixes=("V", "R7"), priority=42),

    # --- Engineering / technical services --- #
    Rule("Engineering / Technical Services",
         _kw("engineering", "technical service", "systems engineering", "integration",
             "technical support", "design support", "analysis"),
         psc_prefixes=("R4", "AR", "B5"), priority=45),

    # --- Manufacturing / production --- #
    Rule("Manufacturing / Production",
         _kw("manufactur", "production", "fabrication", "low rate initial production",
             "lrip", "full rate production", "assembly"),
         priority=44),

    # --- Propulsion fluid/mechanical --- #
    Rule("Fluid Systems / Mechanical",
         _kw("hydraulic", "pneumatic", "valve", "pump", "actuator", "fluid system"),
         psc_prefixes=("47", "43"), priority=46),

    Rule("Mechanical Hardware / Parts",
         _kw("bearing", "fastener", "gear", "bracket", "mechanical hardware", "structural part"),
         psc_prefixes=("30", "31", "53"), priority=47),

    Rule("Electronics / Electrical Components",
         _kw("electronic component", "circuit card", "printed circuit", "connector",
             "electrical component", "wiring harness", "power supply"),
         psc_prefixes=("59", "61"), priority=48),

    # --- Facilities / construction --- #
    Rule("Facilities / Construction",
         _kw("construction", "facility", "facilities", "building", "renovation",
             "military construction", "milcon"),
         psc_prefixes=("Y", "Z"), priority=43),

    # --- Professional / program support --- #
    Rule("Professional / Program Support",
         _kw("program support", "program management", "administrative support",
             "professional service", "advisory", "consulting", "acquisition support"),
         psc_prefixes=("R6", "R1", "R2"), priority=49),

    # --- Commodities / parts --- #
    Rule("Commodities / Parts",
         _kw("parts", "components", "spare parts", "supplies", "hardware kit"),
         priority=52),
]


def _psc_matches(psc: str, prefixes: Tuple[str, ...]) -> bool:
    if not psc or not prefixes:
        return False
    psc = psc.upper()
    return any(psc.startswith(p) for p in prefixes)


def _naics_matches(naics: str, prefixes: Tuple[str, ...]) -> bool:
    if not naics or not prefixes:
        return False
    return any(str(naics).startswith(p) for p in prefixes)


def categorize(
    description: Optional[str],
    psc_code: Optional[str] = None,
    psc_description: Optional[str] = None,
    naics_code: Optional[str] = None,
    naics_description: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Return (Award Category, Category Confidence, Category Reason)."""
    text = " ".join(filter(None, [description, psc_description, naics_description]))
    psc = (psc_code or "").upper()
    naics = naics_code or ""

    kw_hits: List[Tuple[Rule, str]] = []
    code_hits: List[Tuple[Rule, str]] = []

    for rule in sorted(RULES, key=lambda r: r.priority):
        kw_match = rule.kw.search(text) if (rule.kw and text) else None
        psc_match = _psc_matches(psc, rule.psc_prefixes)
        naics_match = _naics_matches(naics, rule.naics_prefixes)
        if kw_match:
            kw_hits.append((rule, f"keyword '{kw_match.group(0)}'"))
        if psc_match:
            code_hits.append((rule, f"PSC {psc}"))
        elif naics_match:
            code_hits.append((rule, f"NAICS {naics}"))

    # Decision logic
    if kw_hits:
        rule, kw_reason = kw_hits[0]
        # Confidence: high if a code signal also points to the same category
        same_code = next((c for c in code_hits if c[0].category == rule.category), None)
        if same_code:
            return rule.category, "High", f"{kw_reason} + {same_code[1]} → {rule.category}"
        # If a different code points elsewhere -> medium
        if code_hits:
            return rule.category, "Medium", f"{kw_reason}; PSC/NAICS suggested related work → {rule.category}"
        # keyword only
        conf = "High" if rule.priority <= 25 else "Medium"
        return rule.category, conf, f"{kw_reason} → {rule.category}"

    if code_hits:
        rule, code_reason = code_hits[0]
        return rule.category, "Medium", f"{code_reason} → {rule.category} (no keyword signal)"

    if text.strip():
        return "General Contract Support", "Low / Needs Review", "No specific work-type signal in description/PSC/NAICS"
    return "Other / Needs Review", "Low / Needs Review", "No description or code data available"
