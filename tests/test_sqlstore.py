"""M2: SQLite storage of v2 records, field encryption, isolation, optimistic locking, import. Fake data only."""
import copy
import hashlib
import json
import os
import sqlite3
import sys

import pytest

from merchant_notebook import migrate, paykings_map as PM, record as R, sqlstore as SQ
from merchant_notebook.keys import DpapiKeyProvider, KeyUnavailable, StaticKeyProvider

NOW = "2026-11-18T10:00:00Z"
KEY = StaticKeyProvider(os.urandom(32))
SSN, ACCOUNT, DL, PASSPORT, LAST4 = "123456789", "12345678", "D0000001", "P0000002", "6789"


def v2_record(mid="MCN-20261118-001", name="Example Goods LLC"):
    rec = migrate.migrate_record(R.new_record(mid, NOW))
    rec["business_information"]["legal_business_name"].update(value=name, status="verified")
    rec["business_entity_type"].update(value="llc", status="verified")
    o = rec["personal_information"]["owners"][0]
    o["first_name"].update(value="Pat", status="verified")
    o["last_name"].update(value="Example", status="verified")
    o["ssn"].update(value=SSN, status="verified")
    o["ssn_last4"].update(value=LAST4, status="verified")
    o["driver_license_number"].update(value=DL, status="verified")
    o["passport_number"].update(value=PASSPORT, status="verified")
    o["date_of_birth"].update(value="01/15/1980", status="verified")
    rec["banking_information"]["account_number"].update(value=ACCOUNT, status="verified")
    rec["record_status"] = "Complete"
    return rec


@pytest.fixture
def db(tmp_path):
    s = SQ.SqliteMerchantStore(tmp_path / "merchants.db", KEY)
    yield s
    s.close()


def test_round_trip_returns_the_same_record(db):
    rec = v2_record()
    v = db.save(rec, expected_version=None)
    loaded, version = db.load(rec["merchant_id"])
    assert loaded == rec and version == v == 1


def test_sensitive_values_are_not_in_the_database_file(db, tmp_path):
    db.save(v2_record(), expected_version=None)
    db.close()
    raw = (tmp_path / "merchants.db").read_bytes()
    for secret in (SSN.encode(), ACCOUNT.encode(), DL.encode(), PASSPORT.encode()):
        assert secret not in raw
    # the non-sensitive name is stored (it is the search column) but the SSN is not anywhere in it
    assert b"Example Goods LLC" in raw


def test_sensitive_values_are_encrypted_but_other_values_are_plain_json(db, tmp_path):
    db.save(v2_record(), expected_version=None)
    doc = json.loads(sqlite3.connect(tmp_path / "merchants.db").execute("SELECT document FROM merchants").fetchone()[0])
    assert doc["personal_information"]["owners"][0]["ssn"]["value"].startswith(SQ.TOKEN_PREFIX)
    assert doc["banking_information"]["account_number"]["value"].startswith(SQ.TOKEN_PREFIX)
    assert doc["personal_information"]["owners"][0]["first_name"]["value"] == "Pat"


def test_a_token_moved_to_another_field_does_not_open(db, tmp_path):
    db.save(v2_record(), expected_version=None)
    con = sqlite3.connect(tmp_path / "merchants.db")
    doc = json.loads(con.execute("SELECT document FROM merchants").fetchone()[0])
    doc["banking_information"]["account_number"]["value"] = doc["personal_information"]["owners"][0]["ssn"]["value"]
    con.execute("UPDATE merchants SET document=?", (json.dumps(doc),))
    con.commit()
    con.close()
    with pytest.raises(SQ.CorruptRecordError):
        db.load("MCN-20261118-001")


def test_a_record_copied_to_another_merchant_does_not_open(db, tmp_path):
    db.save(v2_record("MCN-20261118-001"), expected_version=None)
    db.save(v2_record("MCN-20261118-002", name="Other Co"), expected_version=None)
    con = sqlite3.connect(tmp_path / "merchants.db")
    doc = con.execute("SELECT document FROM merchants WHERE merchant_id='MCN-20261118-001'").fetchone()[0]
    con.execute("UPDATE merchants SET document=? WHERE merchant_id='MCN-20261118-002'", (doc,))
    con.commit()
    con.close()
    with pytest.raises(SQ.CorruptRecordError):
        db.load("MCN-20261118-002")


def test_wrong_key_cannot_open_the_data(tmp_path):
    path = tmp_path / "m.db"
    with SQ.SqliteMerchantStore(path, KEY) as s:
        s.save(v2_record(), expected_version=None)
    with SQ.SqliteMerchantStore(path, StaticKeyProvider(os.urandom(32))) as other:
        with pytest.raises(SQ.CorruptRecordError):
            other.load("MCN-20261118-001")


def test_invalid_record_is_refused_and_nothing_is_written(db):
    rec = v2_record()
    rec["personal_information"]["owners"][0]["ssn"]["value"] = "123-45-6789"   # full SSN with dashes
    with pytest.raises(SQ.RefusedRecord) as e:
        db.save(rec, expected_version=None)
    assert SSN not in str(e.value) and "123-45-6789" not in str(e.value)       # the value is never echoed
    assert db.list() == []


def test_a_bad_date_of_birth_is_refused_without_echoing_it(db):
    rec = v2_record()
    rec["personal_information"]["owners"][0]["date_of_birth"]["value"] = "02/30/1980"
    with pytest.raises(SQ.RefusedRecord) as e:
        db.save(rec, expected_version=None)
    assert "02/30/1980" not in str(e.value)


def test_merchant_id_must_be_valid(db):
    rec = v2_record()
    rec["merchant_id"] = "../etc"
    with pytest.raises(SQ.RefusedRecord):
        db.save(rec, expected_version=None)


def test_create_twice_is_refused(db):
    db.save(v2_record(), expected_version=None)
    with pytest.raises(SQ.StaleRecordError, match="already exists"):
        db.save(v2_record(), expected_version=None)


def test_optimistic_lock_second_writer_is_told_to_reload(db):
    db.save(v2_record(), expected_version=None)                       # version 1
    _, v_a = db.load("MCN-20261118-001")
    _, v_b = db.load("MCN-20261118-001")                              # two windows read version 1
    rec_a, _ = db.load("MCN-20261118-001")
    rec_a["business_information"]["dba_name"].update(value="Pat's Shop", status="verified")
    assert db.save(rec_a, expected_version=v_a) == 2                  # first writer wins
    rec_b, _ = db.load("MCN-20261118-001")
    rec_b2 = copy.deepcopy(rec_b)
    rec_b2["business_information"]["website"].update(value="https://example.com", status="verified")
    with pytest.raises(SQ.StaleRecordError, match="changed since it was read"):
        db.save(rec_b2, expected_version=v_b)                         # second writer is refused
    assert db.load("MCN-20261118-001")[0]["business_information"]["dba_name"]["value"] == "Pat's Shop"


def test_merchants_are_isolated(db):
    a, b = v2_record("MCN-20261118-001", "Alpha Co"), v2_record("MCN-20261118-002", "Beta Co")
    b["personal_information"]["owners"][0]["ssn"]["value"] = "987654321"
    db.save(a, None)
    db.save(b, None)
    assert db.load("MCN-20261118-001")[0]["business_information"]["legal_business_name"]["value"] == "Alpha Co"
    assert db.load("MCN-20261118-001")[0]["personal_information"]["owners"][0]["ssn"]["value"] == SSN
    assert db.load("MCN-20261118-002")[0]["personal_information"]["owners"][0]["ssn"]["value"] == "987654321"


def test_load_of_an_unknown_merchant(db):
    with pytest.raises(SQ.NotFound):
        db.load("MCN-20261118-999")


def test_list_and_search_do_not_need_the_key_and_match_names(db):
    db.save(v2_record("MCN-20261118-001", "Alpha Fashion LLC"), None)
    db.save(v2_record("MCN-20261118-002", "Beta Trading Inc"), None)
    assert {r["merchant_id"] for r in db.list()} == {"MCN-20261118-001", "MCN-20261118-002"}
    assert [r["merchant_id"] for r in db.list("fashion")] == ["MCN-20261118-001"]
    assert [r["merchant_id"] for r in db.list("TRADING")] == ["MCN-20261118-002"]
    assert [r["merchant_id"] for r in db.list("20261118-002")] == ["MCN-20261118-002"]
    assert db.list("%") == [] and db.list("_") == []                 # wildcards are literal


def test_import_v1_json_files_once_and_leaves_sources_unchanged(db, tmp_path):
    src = tmp_path / "old"
    src.mkdir()
    v1 = R.new_record("MCN-20261118-001", NOW)
    v1["business_information"]["legal_business_name"].update(value="Old Co", status="verified")
    (src / "MCN-20261118-001.json").write_text(json.dumps(v1), encoding="utf-8")
    before = hashlib.sha256((src / "MCN-20261118-001.json").read_bytes()).hexdigest()

    first = db.import_json_dir(src)
    assert first.imported == ["MCN-20261118-001"] and not first.failed
    rec, _ = db.load("MCN-20261118-001")
    assert rec["schema_version"] == 2 and rec["business_information"]["legal_business_name"]["value"] == "Old Co"

    second = db.import_json_dir(src)
    assert second.skipped == ["MCN-20261118-001"] and not second.imported
    assert hashlib.sha256((src / "MCN-20261118-001.json").read_bytes()).hexdigest() == before


def test_import_reports_bad_files_without_values(db, tmp_path):
    src = tmp_path / "old"
    src.mkdir()
    bad = R.new_record("MCN-20261118-005", NOW)
    bad["personal_information"]["owners"][0]["ssn"] = {"value": "123-45-6789", "status": "verified",
                                                        "source_context": None, "source_document": None}
    (src / "MCN-20261118-005.json").write_text(json.dumps(bad), encoding="utf-8")
    (src / "MCN-20261118-006.json").write_text("{not json", encoding="utf-8")
    report = db.import_json_dir(src)
    assert report.imported == [] and len(report.failed) == 2
    assert all("123-45-6789" not in reason for _, reason in report.failed)
    assert db.list() == []


def test_database_file_is_private_on_posix(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX permissions only")
    path = tmp_path / "m.db"
    with SQ.SqliteMerchantStore(path, KEY):
        pass
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_sensitive_names_match_the_paykings_map():
    spec_names = {s.split(".")[-1] for s in PM.SENSITIVE_SPECS}
    assert set(SQ.SENSITIVE_NAMES) == spec_names


def test_dpapi_provider_refuses_outside_windows(tmp_path):
    if sys.platform == "win32":
        pytest.skip("this checks the non-Windows refusal")
    with pytest.raises(KeyUnavailable, match="needs Windows"):
        DpapiKeyProvider(tmp_path / "k.bin").key()
    assert not (tmp_path / "k.bin").exists()


def test_static_key_must_be_32_bytes():
    with pytest.raises(KeyUnavailable):
        StaticKeyProvider(b"short")
