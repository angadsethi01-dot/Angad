from company_registry import load_registry, normalize_name
from subsidiary_matcher import map_recipient, fuzzy_candidate


def reg():
    load_registry.cache_clear()
    return load_registry()


def test_normalize_name_suffixes():
    assert normalize_name("Northrop Grumman Systems Corp.") == normalize_name("NORTHROP GRUMMAN SYSTEMS CORPORATION")


def test_electric_boat_maps_to_gd():
    r = reg()
    m = map_recipient(r, "ELECTRIC BOAT CORPORATION")
    assert m.parent_company == "General Dynamics"


def test_sikorsky_maps_to_lockheed():
    r = reg()
    m = map_recipient(r, "SIKORSKY AIRCRAFT CORPORATION")
    assert m.parent_company == "Lockheed Martin"


def test_spacex_maps():
    r = reg()
    m = map_recipient(r, "Space Exploration Technologies Corp.")
    assert m.parent_company == "SpaceX"


def test_excluded_false_positive_not_mapped():
    r = reg()
    assert map_recipient(r, "SPACEX FIREWORKS LLC").parent_company is None
    assert map_recipient(r, "SANTA BARBARA AIRBUS").parent_company is None


def test_unknown_recipient_unmapped():
    r = reg()
    assert map_recipient(r, "ACME WIDGETS LLC").parent_company is None


def test_fuzzy_candidate_flags_lookalike():
    r = reg()
    fc = fuzzy_candidate(r, "NORTHROP GRUMMAN SPACE SYSTEMS DIVISION")
    assert fc is not None and fc.possible_parent == "Northrop Grumman"
