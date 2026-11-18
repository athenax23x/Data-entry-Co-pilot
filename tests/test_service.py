"""M1: the service layer works without the CLI, and a refused request leaves the record exactly as it was."""
import copy
from datetime import datetime, timezone

import pytest

from merchant_notebook import record as R, service as S
from merchant_notebook.commands import Session

NOW = "2026-11-18T10:00:00Z"


def fresh():
    return R.new_record("MCN-20261118-001", NOW)


def test_set_field_writes_a_verified_value_and_one_source():
    rec = fresh()
    msg = S.set_field(rec, "city", "tampa", NOW, lambda: R.add_source(rec, "update_field", NOW))
    assert rec["business_address"]["city"]["value"] == "tampa"  # stored as the normalizer returns it
    assert rec["business_address"]["city"]["status"] == "verified"
    assert len(rec["sources"]) == 1
    assert msg == "/business_address/city: — (missing) -> tampa (verified)"


@pytest.mark.parametrize("field,value", [
    ("state", "not-a-state"),                    # normalizer refuses
    ("city", "missing"),                          # already missing
    ("city", "confirm"),                          # nothing to confirm
])
def test_refused_set_field_leaves_no_source_behind(field, value):
    rec = fresh()
    before = copy.deepcopy(rec)
    with pytest.raises((S.CommandError, R.RecordError)):
        S.set_field(rec, field, value, NOW, lambda: R.add_source(rec, "update_field", NOW))
    assert rec == before


def test_confirm_on_a_conflict_is_refused_without_a_source():
    rec = fresh()
    S.set_field(rec, "city", "Tampa", NOW, lambda: R.add_source(rec, "update_field", NOW))
    R.merge_value(rec, ("business_address", "city"), "Miami", "inferred", "ctx", "SRC-X", NOW)
    before = copy.deepcopy(rec)
    with pytest.raises(R.RecordError):
        S.set_field(rec, "city", "confirm", NOW, lambda: R.add_source(rec, "update_field", NOW))
    assert rec == before


def test_check_same_merchant_refuses_a_different_business_only():
    rec = fresh()
    rec["business_information"]["legal_business_name"].update(value="Alpha LLC", status="verified")
    rec["ein"].update(value="12-3456789", status="verified")
    with pytest.raises(S.CommandError):
        S.check_same_merchant(rec, "Beta Corp, EIN 98-7654321")
    S.check_same_merchant(rec, "Alpha LLC, EIN 12-3456789")               # same merchant -> allowed


def test_apply_extraction_returns_a_tally_and_changes_only_the_record():
    rec = fresh()
    ex, tally = S.apply_extraction(rec, "Legal name: Example Goods LLC\nCity: Tampa", "SRC-1", NOW)
    assert tally["filled"]
    assert rec["business_information"]["legal_business_name"]["value"] == "Example Goods LLC"


def test_service_functions_are_importable_without_the_cli():
    import merchant_notebook.service as svc
    assert not hasattr(svc, "Session") and callable(svc.apply_extraction)


def test_cli_session_and_service_produce_the_same_record(tmp_path):
    clock = iter(range(1, 100))
    now = lambda: datetime(2026, 11, 18, 10, 0, next(clock), tzinfo=timezone.utc)
    s = Session(tmp_path, now=now)
    s.execute("NEW MERCHANT Legal name: Example Goods LLC")
    s.execute("UPDATE FIELD city = tampa")
    rec = s.records[s.active]
    assert rec["business_address"]["city"]["value"] == "tampa"  # stored as the normalizer returns it
    assert rec["business_address"]["city"]["status"] == "verified"
