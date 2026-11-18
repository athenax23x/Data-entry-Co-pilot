"""SSN: only the last 4 digits can ever be stored. A full SSN is discarded, never truncated."""
import csv
import io
import json

import pytest

from conftest import active
from merchant_notebook import csv_export as C, normalize, store

FULL = ["123-45-6789", "123 45 6789", "ssn: 123456789", "SSN 123456789", "social security number 123456789",
        "Social Security # 123-45-6789"]


def owner(session, i=0):
    return active(session)["personal_information"]["owners"][i]


def test_last4_accepts_exactly_four_digits_and_never_truncates():
    assert normalize.last4("1234") == "1234" and normalize.last4(" 0042 ") == "0042"
    for bad in ("123", "12345", "123456789", "123-45-6789", "12a4", "", "xxxx"):
        assert normalize.last4(bad) is None, bad


def test_update_field_stores_last4_as_verified(session):
    session.execute("NEW MERCHANT name: Alex Sample")
    out = session.execute("UPDATE FIELD ssn_last4 = 6789")
    f = owner(session)["ssn_last4"]
    assert (f["value"], f["status"]) == ("6789", "verified") and "6789" in out
    session.execute("UPDATE FIELD owners[1].ssn_last4 = 0042")
    assert owner(session, 1)["ssn_last4"]["value"] == "0042"
    assert store.validate_record(active(session)) == []


@pytest.mark.parametrize("bad", ["123", "12345", "abcd"])
def test_update_field_rejects_anything_but_four_digits(session, bad):
    session.execute("NEW MERCHANT x")
    out = session.execute(f"UPDATE FIELD ssn_last4 = {bad}")
    assert out.startswith("Error") and "nothing was changed" in out
    assert owner(session)["ssn_last4"]["value"] is None


@pytest.mark.parametrize("full", ["123-45-6789", "123 45 6789", "123456789"])
def test_update_field_refuses_a_full_ssn_and_points_to_last4(session, full):
    session.execute("NEW MERCHANT x")
    out = session.execute(f"UPDATE FIELD ssn_last4 = {full}")
    assert out.startswith("Error")
    assert owner(session)["ssn_last4"]["value"] is None
    assert "6789" not in json.dumps(session.records) and "123-45" not in json.dumps(session.records)
    if "-" in full or " " in full:
        assert "last 4 digits" in out                        # recognized as an SSN and explained


@pytest.mark.parametrize("text", FULL)
def test_a_full_ssn_in_new_merchant_or_add_context_is_discarded_completely(session, text):
    out = session.execute(f"NEW MERCHANT name: Alex Sample; {text}; alex@example.com")
    out2 = session.execute(f"ADD CONTEXT owner note {text}")
    dump = json.dumps(session.records)
    assert "Discarded and NOT stored: full Social Security number" in out
    assert "Discarded and NOT stored: full Social Security number" in out2
    for fragment in ("123-45-6789", "123456789", "123 45 6789", "6789", "123-45"):
        assert fragment not in dump, fragment                  # not even the last 4 or a partial
    assert owner(session)["ssn_last4"]["value"] is None
    assert active(session)["contact_information"]["email"]["value"] == "alex@example.com"
    assert store.validate_record(active(session)) == []


def test_last4_can_be_given_with_a_label(session):
    session.execute("NEW MERCHANT name: Alex Sample; ssn last 4: 6789")
    f = owner(session)["ssn_last4"]
    assert (f["value"], f["status"]) == ("6789", "inferred")
    session.execute("NEW MERCHANT name: Blake Demo; ssn: 4321")
    assert owner(session)["ssn_last4"]["value"] == "4321"


def test_a_verified_last4_is_protected_like_any_other_value(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD ssn_last4 = 6789")
    session.execute("ADD CONTEXT ssn last 4: 1111")
    f = owner(session)["ssn_last4"]
    assert f["value"] == "6789" and f["status"] == "conflict"


@pytest.mark.parametrize("bad", ["123456789", "12345", "123", "12-34", "abcd", "123-45-6789", " 1234"])
def test_the_schema_itself_only_accepts_exactly_four_digits(session, bad):
    # The schema is the last line of defence for files that come from outside the app: a full SSN written
    # without dashes must be rejected by the schema pattern, not only by the app's normalizer.
    session.execute("NEW MERCHANT x")
    rec = active(session)
    rec["personal_information"]["owners"][0]["ssn_last4"].update(value=bad, status="inferred")
    assert any("does not match" in p for p in store.validate_record(rec)), bad
    rec["personal_information"]["owners"][0]["ssn_last4"].update(value="6789")
    assert store.validate_record(rec) == []


def test_a_full_ssn_in_a_file_is_rejected_on_load_and_save(session, data_dir, tmp_path):
    session.execute("NEW MERCHANT x")
    rec = active(session)
    rec["personal_information"]["owners"][0]["ssn_last4"].update(value="123-45-6789", status="inferred")
    assert store.validate_record(rec) != []
    assert session.execute("SAVE MERCHANT").startswith("NOT saved")
    assert not data_dir.exists() or list(data_dir.iterdir()) == []
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(rec))
    session.execute("CLEAR SESSION")
    assert session.execute(f"LOAD MERCHANT {bad}").startswith("NOT loaded")


def test_csv_exports_only_the_primary_owners_last4(session):
    session.execute("NEW MERCHANT name: Alex Sample; ssn last 4: 6789")
    session.execute("UPDATE FIELD owners[1].first_name = Pat")
    session.execute("UPDATE FIELD owners[1].ssn_last4 = 0042")
    (row,) = csv.DictReader(io.StringIO(C.render_csv([active(session)]), newline=""))
    assert row["ssn_last4"] == "6789" and "0042" not in str(row)
    assert "ssn_last4" in C.FIXED_COLUMNS


def test_no_full_ssn_field_exists_anywhere():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
    names = json.dumps(schema).lower()
    assert "ssn_last4" in names and '"ssn"' not in names and "social_security" not in names
    assert "last 4 digits only" in (root / "instructions.md").read_text(encoding="utf-8")
