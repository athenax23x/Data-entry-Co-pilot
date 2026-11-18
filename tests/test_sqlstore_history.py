"""Old values copied into history and conflicts are protected like the field value itself. Fake data only."""
import os

from merchant_notebook import record as R, sqlstore as SQ
from merchant_notebook.keys import StaticKeyProvider
from tests.test_sqlstore import NOW, v2_record

OLD, NEW = "111223333", "444556666"


def test_replaced_sensitive_values_are_not_readable_in_the_database_file(tmp_path):
    with SQ.SqliteMerchantStore(tmp_path / "m.db", StaticKeyProvider(os.urandom(32))) as db:
        rec = v2_record()
        ssn = rec["personal_information"]["owners"][0]["ssn"]
        R.user_set(rec, ("personal_information", "owners", 0, "ssn"), OLD, "ctx", "SRC-001", NOW)
        R.user_set(rec, ("personal_information", "owners", 0, "ssn"), NEW, "ctx", "SRC-002", NOW)
        assert ssn["history"][-1]["value"] == OLD
        v = db.save(rec, None)
        loaded, version = db.load(rec["merchant_id"])
        assert loaded == rec and version == v
    raw = (tmp_path / "m.db").read_bytes()
    assert OLD.encode() not in raw and NEW.encode() not in raw


def test_plain_history_from_the_first_m2_version_still_loads(tmp_path):
    with SQ.SqliteMerchantStore(tmp_path / "m.db", StaticKeyProvider(os.urandom(32))) as db:
        rec = v2_record()
        rec["personal_information"]["owners"][0]["ssn"]["history"] = [
            {"value": OLD, "status": "verified", "source_context": None, "source_document": None, "replaced_at": NOW}]
        doc = SQ._encrypt_doc(rec, db._cipher)
        doc["personal_information"]["owners"][0]["ssn"]["history"][0]["value"] = OLD     # as M2 stored it
        assert SQ._decrypt_doc(doc, db._cipher) == rec
