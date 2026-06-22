from dedup import deduplicate, award_key


def test_dedup_by_generated_id():
    rows = [
        {"generated_internal_id": "CONT_AWD_1", "Award ID": "X"},
        {"generated_internal_id": "CONT_AWD_1", "Award ID": "X-dup"},
        {"generated_internal_id": "CONT_AWD_2", "Award ID": "Y"},
    ]
    out = deduplicate(rows)
    assert len(out) == 2
    assert out[0]["Award ID"] == "X"  # first kept


def test_composite_key_when_no_gid():
    rows = [
        {"Award ID": "P1", "Recipient UEI": "U1", "Base Obligation Date": "2024-01-01", "Award Amount": 10},
        {"Award ID": "P1", "Recipient UEI": "U1", "Base Obligation Date": "2024-01-01", "Award Amount": 10},
        {"Award ID": "P1", "Recipient UEI": "U2", "Base Obligation Date": "2024-01-01", "Award Amount": 10},
    ]
    out = deduplicate(rows)
    assert len(out) == 2


def test_key_prefers_gid():
    assert award_key({"generated_internal_id": "G"})[0] == "gid"
    assert award_key({"Award ID": "P"})[0] == "composite"
