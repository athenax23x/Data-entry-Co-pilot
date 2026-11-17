"""Owner date of birth (US format), refund policy, and the removed current_processor field."""
import copy
import json
import re
from pathlib import Path

import pytest

from conftest import active
from merchant_notebook import csv_export as C, normalize, record as R, store

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_TEXT = (ROOT / "schema.json").read_text(encoding="utf-8")
INSTRUCTIONS = (ROOT / "instructions.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("given,stored", [
    ("01/15/1980", "01/15/1980"),
    ("1/5/1980", "01/05/1980"),
    ("1980-01-15", "01/15/1980"),
    ("02/29/2000", "02/29/2000"),
])
def test_dob_is_stored_in_us_format(given, stored):
    assert normalize.us_date(given) == stored


@pytest.mark.parametrize("bad", ["02/30/1980", "13/01/1980", "15/01/1980", "01/15/1850", "01/15/2999",
                                 "02/29/2001", "1980/01/15", "Jan 15 1980", "01-15-1980", "", "tomorrow"])
def test_dob_rejects_non_us_formats_impossible_and_out_of_range_dates(bad):
    assert normalize.us_date(bad) is None


def test_update_field_sets_the_dob_as_verified_in_us_format(session):
    session.execute("NEW MERCHANT name: Alex Sample")
    out = session.execute("UPDATE FIELD date_of_birth = 1/5/1980")
    f = active(session)["personal_information"]["owners"][0]["date_of_birth"]
    assert (f["value"], f["status"]) == ("01/05/1980", "verified") and "01/05/1980" in out
    bad = session.execute("UPDATE FIELD dob = 02/30/1980")
    assert bad.startswith("Error: Unknown field")                       # only the schema name is a field name
    bad = session.execute("UPDATE FIELD date_of_birth = 02/30/1980")
    assert bad.startswith("Error") and "nothing was changed" in bad
    assert f["value"] == "01/05/1980"


def test_dob_can_be_set_per_owner_and_is_not_exported_for_other_owners(session):
    session.execute("NEW MERCHANT name: Alex Sample; dob: 01/15/1980")
    session.execute("UPDATE FIELD owners[1].first_name = Pat")
    session.execute("UPDATE FIELD owners[1].date_of_birth = 03/04/1975")
    owners = active(session)["personal_information"]["owners"]
    assert owners[0]["date_of_birth"]["value"] == "01/15/1980" and owners[0]["date_of_birth"]["status"] == "inferred"
    assert owners[1]["date_of_birth"]["value"] == "03/04/1975"
    import csv, io
    rows = list(csv.DictReader(io.StringIO(C.render_csv([active(session)]), newline="")))
    assert rows[0]["date_of_birth"] == "01/15/1980"                       # primary owner only
    assert "03/04/1975" not in str(rows[0])


def test_a_verified_dob_is_protected_like_any_other_value(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD date_of_birth = 01/15/1980")
    session.execute("ADD CONTEXT dob: 02/20/1981")
    f = active(session)["personal_information"]["owners"][0]["date_of_birth"]
    assert f["value"] == "01/15/1980" and f["status"] == "conflict"
    assert active(session)["conflicts"][0]["candidates"][0]["value"] == "02/20/1981"


def test_schema_rejects_wrong_dob_formats_and_the_app_rejects_impossible_dates(session, data_dir):
    session.execute("NEW MERCHANT x")
    rec = active(session)
    dob = rec["personal_information"]["owners"][0]["date_of_birth"]
    for value in ("1980-01-15", "13/01/1980", "1/5/1980"):
        dob.update(value=value, status="inferred")
        assert any("does not match" in p for p in store.validate_record(rec)), value
    dob.update(value="02/30/1980", status="inferred")                    # matches the pattern, not a real date
    problems = store.validate_record(rec)
    assert problems == ["personal_information/owners/0/date_of_birth/value: '02/30/1980' is not a real date"]
    assert session.execute("SAVE MERCHANT").startswith("NOT saved")
    assert not data_dir.exists() or list(data_dir.iterdir()) == []
    dob.update(value="01/15/1980")
    assert store.validate_record(rec) == []


def test_refund_policy_is_a_business_text_field(session):
    session.execute("NEW MERCHANT business: Sample Services LLC; refund policy: 30 days, full refund if unused")
    f = active(session)["business_information"]["refund_policy"]
    assert (f["value"], f["status"]) == ("30 days, full refund if unused", "inferred")
    session.execute("UPDATE FIELD refund_policy = No refunds after delivery")
    f = active(session)["business_information"]["refund_policy"]
    assert (f["value"], f["status"]) == ("No refunds after delivery", "verified")
    assert f["history"][-1]["value"] == "30 days, full refund if unused"
    assert "business_information.refund_policy" in session.execute("SHOW MERCHANT")
    import csv, io
    (row,) = csv.DictReader(io.StringIO(C.render_csv([active(session)]), newline=""))
    assert row["refund_policy"] == "No refunds after delivery"
    assert store.validate_record(active(session)) == []


def test_refund_policy_is_in_schema_app_and_instructions():
    schema = json.loads(SCHEMA_TEXT)
    assert "refund_policy" in schema["properties"]["business_information"]["required"]
    assert "refund_policy" in R.new_record("MCN-20261117-001", "2026-11-17T14:30:00Z")["business_information"]
    assert "`business_information.refund_policy`" in INSTRUCTIONS


def test_current_processor_is_gone_everywhere(session):
    assert "current_processor" not in SCHEMA_TEXT
    assert "current_processor" not in INSTRUCTIONS
    assert "current_processor" not in C.FIXED_COLUMNS
    rec = R.new_record("MCN-20261117-001", "2026-11-17T14:30:00Z")
    assert "current_processor" not in rec["processing_information"]
    session.execute("NEW MERCHANT processor: Example Payments")                # no longer a recognized label
    assert session.execute("UPDATE FIELD current_processor = X").startswith("Error: Unknown field")
    assert "current_processor" not in json.dumps(session.records)
    for p in (ROOT / "merchant_notebook").glob("*.py"):
        assert "current_processor" not in p.read_text(encoding="utf-8"), p.name
    assert "current_processor" not in (ROOT / "README.md").read_text(encoding="utf-8")


def test_a_record_with_the_removed_field_is_rejected(session):
    session.execute("NEW MERCHANT x")
    rec = copy.deepcopy(active(session))
    rec["processing_information"]["current_processor"] = R.empty_field()
    rec["processing_information"]["current_processor"].update(value="Example Payments", status="inferred")
    # extra fields in a section are allowed by the schema (extension point) as long as they are field objects
    assert store.validate_record(rec) == []
    rec["processing_information"]["current_processor"] = "Example Payments"
    assert store.validate_record(rec) != []                                  # but a bare value is not a field object
