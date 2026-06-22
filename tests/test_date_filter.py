from datetime import date

import date_filter as dfm

CD = date(2026, 6, 22)


# --- dataset inclusion: recent contract (awarded >= 2023) --- #
def test_awarded_2022_excluded_from_dataset():
    d = dfm.is_recent_contract("2022-05-01")
    assert not d.include and "before 2023" in d.rejection_reason


def test_awarded_2024_included():
    assert dfm.is_recent_contract("2024-03-01").include


def test_missing_award_date_excluded():
    d = dfm.is_recent_contract(None)
    assert not d.include and d.rejection_reason == "Missing award date"


def test_recent_contract_kept_even_if_performance_ended():
    # A 2024 contract whose performance already ended is still a "recent
    # contract awarded" — it stays in the dataset (just flagged inactive).
    assert dfm.is_recent_contract("2024-03-01").include


def test_legacy_toggle_allows_pre2023():
    assert dfm.is_recent_contract("2021-01-01", include_legacy=True).include


# --- active status (used for the largest-awards filter) --- #
def test_active_when_current_end_future():
    a = dfm.active_status("2027-12-31", None, current_date=CD)
    assert a.is_active and a.active_status == "Active" and a.date_confidence == "High"


def test_inactive_when_current_end_past():
    a = dfm.active_status("2025-06-01", None, current_date=CD)
    assert not a.is_active and "Inactive" in a.active_status


def test_potentially_active_when_current_end_missing():
    a = dfm.active_status(None, "2028-01-01", current_date=CD)
    assert a.is_active and a.date_confidence == "Needs Review"
    assert "Potentially Active" in a.active_status


def test_end_date_unknown():
    a = dfm.active_status(None, None, current_date=CD)
    assert not a.is_active and a.active_status == "End date unknown"
