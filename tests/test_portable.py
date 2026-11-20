"""Password-protected portable export/import. Fake data only; a different key on each side proves the move works."""
import json
import os

import pytest

from merchant_notebook import migrate, portable as PT, record as R, sqlstore as SQ
from merchant_notebook.keys import StaticKeyProvider

NOW = "2026-11-18T10:00:00Z"
PW = "correct horse battery"
SSN = "123456" + "789"                      # stored as 9 digits, no dashes


def _store(tmp_path, name):
    return SQ.SqliteMerchantStore(tmp_path / name, StaticKeyProvider(os.urandom(32)))


def _filled(store, n=1):
    for i in range(n):
        rec = migrate.migrate_record(R.new_record(f"MCN-20261118-{i + 1:03d}", NOW))
        owner = rec["personal_information"]["owners"][0]
        owner["ssn"] = {"value": SSN, "status": "verified", "source_context": "t", "source_document": None}
        store.save(rec, expected_version=None)


def test_a_record_moves_to_a_store_with_a_different_key(tmp_path):
    a, b = _store(tmp_path, "a.db"), _store(tmp_path, "b.db")
    _filled(a, 2)
    f = tmp_path / "m.mcnx"
    assert PT.export_store(a, f, PW) == 2
    assert PT.import_into_store(b, f, PW) == {"imported": 2, "skipped": 0, "failed": 0}
    assert b.load("MCN-20261118-001")[0]["personal_information"]["owners"][0]["ssn"]["value"] == SSN
    assert PT.import_into_store(b, f, PW)["skipped"] == 2                        # never overwrites


def test_the_file_shows_no_merchant_data_and_needs_the_right_password(tmp_path):
    a = _store(tmp_path, "a.db")
    _filled(a)
    f = tmp_path / "m.mcnx"
    PT.export_store(a, f, PW)
    raw = f.read_bytes()
    assert SSN.encode() not in raw and b"MCN-20261118" not in raw and b"Example" not in raw
    with pytest.raises(PT.PortableError, match="Wrong password"):
        PT.read_records(raw, "another long password")


def test_a_changed_or_foreign_file_is_refused_without_leaking_anything(tmp_path):
    blob = PT.export_records([], PW)
    doc = json.loads(blob)
    doc["ciphertext"] = doc["ciphertext"][:-4] + "AAAA"
    for bad in (json.dumps(doc).encode(), b"not json", b'{"format":"other"}'):
        with pytest.raises(PT.PortableError) as e:
            PT.read_records(bad, PW)
        assert PW not in str(e.value)


def test_a_short_password_is_refused():
    with pytest.raises(PT.PortableError, match="at least 12"):
        PT.export_records([], "short")
