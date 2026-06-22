"""Place-of-performance location normalization.

Primary location is the place of performance (NOT recipient HQ). US locations
render as 'CITY, STATE, UNITED STATES'; state-only as 'STATE, UNITED STATES';
foreign as 'CITY/REGION, COUNTRY'.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class LocationResult:
    city: str
    state: str
    country: str
    full_location: str


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("none", "nan", "null"):
        return ""
    return s


def normalize_location(
    city=None,
    state=None,           # state name preferred, else code
    state_code=None,
    country=None,
    country_code=None,
) -> LocationResult:
    city = _clean(city).upper()
    state = _clean(state).upper()
    state_code = _clean(state_code).upper()
    country = _clean(country).upper()
    country_code = _clean(country_code).upper()

    # Determine if US
    is_us = country in ("UNITED STATES", "UNITED STATES OF AMERICA", "USA") or country_code in ("USA", "US", "")
    state_disp = state or state_code

    if is_us:
        country_disp = "UNITED STATES"
        if city and state_disp:
            full = f"{city}, {state_disp}, UNITED STATES"
        elif state_disp:
            full = f"{state_disp}, UNITED STATES"
        elif city:
            full = f"{city}, UNITED STATES"
        else:
            full = "UNITED STATES (LOCATION UNSPECIFIED)"
    else:
        country_disp = country or country_code or "UNKNOWN COUNTRY"
        region = city or state_disp
        full = f"{region}, {country_disp}" if region else country_disp

    return LocationResult(
        city=city,
        state=state_disp,
        country=country_disp,
        full_location=full,
    )
