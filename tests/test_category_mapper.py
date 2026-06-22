from category_mapper import categorize, CATEGORIES


def cat(desc, psc=None, naics=None):
    return categorize(desc, psc_code=psc)[0]


def test_gator_radar():
    assert categorize("G/ATOR radar development")[0] == "Sensors / Radar / Electronic Warfare"


def test_aircraft_component_repair_is_sustainment():
    assert categorize("Aircraft components and accessories repair")[0] == "Aircraft Maintenance / Sustainment"


def test_satellite_payload_is_space():
    assert categorize("Satellite payload integration work")[0] == "Space / Satellite Systems"


def test_launch_services():
    assert categorize("Launch services for national security space launch")[0] == "Launch / Space Transportation"


def test_missile_interceptor():
    assert categorize("Missile interceptor production")[0] == "Missiles / Weapons / Ordnance"


def test_submarine_combat_systems():
    assert categorize("Submarine combat systems support")[0] == "Shipboard / Maritime Systems"


def test_f35_sustainment():
    assert categorize("F-35 sustainment support services")[0] == "Aircraft Maintenance / Sustainment"


def test_vague_description_low_confidence():
    c, conf, _ = categorize("Miscellaneous support services")
    assert conf == "Low / Needs Review"


def test_psc_only_signal():
    c, conf, reason = categorize("", psc_code="1510")
    assert c == "Aircraft / Aviation Systems"
    assert conf == "Medium"


def test_all_categories_valid():
    for desc in ["radar", "satellite", "missile", "software cloud", "training simulator"]:
        assert categorize(desc)[0] in CATEGORIES
