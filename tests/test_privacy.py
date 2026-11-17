"""Privacy: no sensitive data stored, no mixing of merchants, no real data in the repo."""
import json
import re
from pathlib import Path

from conftest import active
from merchant_notebook.commands import PRIVACY_NOTICE

ROOT = Path(__file__).resolve().parent.parent
FAKE_CARD = "4111 1111 1111 1111"          # a well-known test number, not a real card


def test_card_numbers_and_security_codes_are_discarded_and_reported(session):
    out = session.execute(f"NEW MERCHANT alex@example.com card {FAKE_CARD} cvv 123 exp 12/30")
    dump = json.dumps(session.records)
    assert "4111" not in dump and "1111" not in dump and "cvv" not in dump.lower() and "123" not in dump
    assert "Discarded and NOT stored: payment card number, card security code" in out
    assert active(session)["contact_information"]["email"]["value"] == "alex@example.com"


def test_passwords_and_one_time_codes_are_discarded(session):
    session.execute("NEW MERCHANT alex@example.com")
    out = session.execute("ADD CONTEXT password: hunter2xyz and OTP 482913")
    dump = json.dumps(session.records)
    assert "hunter2xyz" not in dump and "482913" not in dump
    assert "password" in out and "one-time code" in out


def test_update_field_refuses_sensitive_values(session):
    session.execute("NEW MERCHANT x")
    out = session.execute(f"UPDATE FIELD business_description = {FAKE_CARD}")
    assert out.startswith("Error") and "sensitive" in out
    assert active(session)["business_information"]["business_description"]["value"] is None
    assert "4111" not in json.dumps(session.records)


def test_phone_and_ein_next_to_each_other_are_not_mistaken_for_a_card(session):
    session.execute("NEW MERCHANT 512-555-0187 12-3456789")
    rec = active(session)
    assert rec["contact_information"]["phone"]["value"] == "+1 (512) 555-0187"
    assert rec["ein"]["value"] == "12-3456789"


def test_one_merchant_never_shows_another_merchants_data(session):
    session.execute("NEW MERCHANT name: Alex Sample; alex@example.com; ein: 12-3456789")
    a = session.active
    session.execute("NEW MERCHANT name: Blake Demo; blake@example.org; ein: 98-7654321")
    b = session.active
    out_b = session.execute(f"SHOW MERCHANT {b}")
    out_a = session.execute(f"SHOW MERCHANT {a}")
    assert "blake@example.org" in out_b and "alex@example.com" not in out_b and "12-3456789" not in out_b
    assert "alex@example.com" in out_a and "blake@example.org" not in out_a and "98-7654321" not in out_a
    session.execute(f"UPDATE FIELD {a} city = Tampa")
    assert active(session) is session.records[b] and session.records[b]["business_address"]["city"]["value"] is None


def test_each_new_merchant_gets_its_own_unique_id_and_independent_record(session):
    session.execute("NEW MERCHANT one")
    first = session.active
    session.execute("NEW MERCHANT two")
    second = session.active
    assert first != second and first.endswith("-001") and second.endswith("-002")
    assert session.records[first]["sources"] is not session.records[second]["sources"]
    assert session.records[first]["conflicts"] is not session.records[second]["conflicts"]


def test_cloud_notice_is_shown_once_and_matches_instructions(session):
    text = (ROOT / "instructions.md").read_text(encoding="utf-8")
    assert "> " + PRIVACY_NOTICE in text.replace("\n   > ", "\n> ") or PRIVACY_NOTICE in text
    first = session.execute("NEW MERCHANT one")
    second = session.execute("NEW MERCHANT two")
    assert PRIVACY_NOTICE in first and PRIVACY_NOTICE not in second


def test_repo_code_and_tests_contain_only_clearly_fake_contact_data():
    """Code, tests and README: fake emails and 555 phones only. (tests/fixtures is scanned more strictly in
    test_fixtures.py; test_fixtures.py itself holds deliberate bad samples and is checked there.)"""
    import fake_data_scan as S
    files = [p for d in ("merchant_notebook", "tests") for p in (ROOT / d).rglob("*.py")] + [ROOT / "README.md"]
    files = [p for p in files if p.name != "test_fixtures.py" and "fixtures" not in p.parts]
    assert files
    for p in files:
        assert S.scan_code(p.read_text(encoding="utf-8")) == [], p.name
