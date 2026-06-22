from value_normalizer import normalize_value


def test_potential_value_preferred():
    v = normalize_value(base_and_all_options=500, total_obligation=100)
    assert v.potential_value == 500
    assert v.ranking_value == 500
    assert v.value_basis == "Base and All Options"


def test_falls_back_to_obligated_when_potential_missing():
    v = normalize_value(base_and_all_options=None, total_obligation=250)
    assert v.potential_value is None
    assert v.ranking_value == 250
    assert v.value_basis == "Obligated Amount"


def test_does_not_rank_by_obligated_if_potential_larger():
    # potential present and larger -> ranking uses potential, not obligated
    v = normalize_value(base_and_all_options=1000, total_obligation=999999)
    assert v.ranking_value == 1000  # potential wins regardless of obligated size
    assert v.value_basis == "Base and All Options"


def test_needs_review_when_all_missing():
    v = normalize_value()
    assert v.ranking_value is None
    assert v.value_basis == "Needs Review"


def test_placeholder_ceiling_not_ranked():
    # OASIS+ style $999,999,999,999 ceiling with tiny obligated amount
    v = normalize_value(base_and_all_options=999_999_999_999, total_obligation=2500)
    assert v.placeholder_ceiling is True
    assert v.potential_value is None            # fake ceiling hidden
    assert v.ranking_value == 2500              # ranked by real obligated $
    assert "placeholder" in v.value_basis.lower()


def test_nine_digit_all_nines_is_placeholder():
    from value_normalizer import is_placeholder_amount
    assert is_placeholder_amount(999_999_999)
    assert is_placeholder_amount(999_999_999_999)
    assert not is_placeholder_amount(1_379_097_000)   # real $1.38B contract
    assert not is_placeholder_amount(151_000_000_000)
