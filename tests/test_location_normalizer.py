from location_normalizer import normalize_location


def test_us_city_state():
    r = normalize_location(city="Hawthorne", state="California", country="UNITED STATES")
    assert r.full_location == "HAWTHORNE, CALIFORNIA, UNITED STATES"
    assert r.country == "UNITED STATES"


def test_us_state_only():
    r = normalize_location(city=None, state="Virginia", country="UNITED STATES")
    assert r.full_location == "VIRGINIA, UNITED STATES"


def test_foreign_location():
    r = normalize_location(city="Ottawa", state=None, country="CANADA", country_code="CAN")
    assert r.full_location == "OTTAWA, CANADA"


def test_country_code_only_us_default():
    r = normalize_location(city="Bethpage", state_code="NY", country_code="USA")
    assert r.full_location == "BETHPAGE, NY, UNITED STATES"


def test_empty_inputs():
    r = normalize_location()
    assert "UNITED STATES" in r.full_location
