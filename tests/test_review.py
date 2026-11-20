"""M23/M24/M25: checks before the Paykings form, the missing-info message, work stage. Fake data only."""
from datetime import date

from merchant_notebook import migrate, record as R, review
from tests.test_api import TEXT, client, db_path  # noqa: F401  (fixtures)

O = ("personal_information", "owners", 0)
TODAY = date(2026, 11, 20)


def blank():
    return migrate.migrate_record(R.new_record("MCN-20261120-001", "2026-11-20T00:00:00Z"))


def put(rec, keys, value):
    f = R.get_field(rec, keys)
    f["value"], f["status"] = value, "verified"


def codes(rec):
    return {w["code"] for w in review.checks(rec, TODAY)}


def test_percentages_must_total_100():
    rec = blank()
    P = "processing_information"
    put(rec, (P, "public_sales_percentage"), 80); put(rec, (P, "b2b_sales_percentage"), 10)
    put(rec, (P, "card_present_percentage"), 80); put(rec, (P, "keyed_percentage"), 20); put(rec, (P, "ecommerce_percentage"), 0)
    found = review.checks(rec, TODAY)
    assert {w["code"] for w in found} == {"sales_public_b2b"}
    assert "90%" in found[0]["message"] and found[0]["fields"] == ["Public Sales %", "B2B Sales %"]


def test_tickets_zip_ein_dba_dates_routing():
    rec = blank()
    P = "processing_information"
    put(rec, (P, "average_ticket"), 900); put(rec, (P, "high_ticket"), 600); put(rec, (P, "monthly_card_volume"), 500)
    put(rec, ("business_address", "zip"), "78701"); put(rec, ("business_address", "state"), "FL")
    put(rec, ("business_entity_type",), "llc")
    put(rec, ("business_information", "dba_different_from_legal"), "Yes")
    put(rec, ("business_information", "business_start_date"), "2027-01-01")
    put(rec, O + ("date_of_birth",), "01/01/2012")
    put(rec, O + ("driver_license_expiration",), "01/01/2025")
    put(rec, (P, "routing_number"), "021000022")
    assert codes(rec) >= {"avg_gt_high", "avg_gt_volume", "high_gt_volume", "zip_state_business", "ein_needed",
                          "dba_missing", "start_in_future", "owner_under_18", "driver_expired", "routing_checksum"}


def test_a_clean_record_has_no_findings():
    rec = blank()
    P = "processing_information"
    put(rec, ("business_address", "zip"), "78701"); put(rec, ("business_address", "state"), "TX")
    put(rec, O + ("zip",), "33602"); put(rec, O + ("state",), "FL")
    put(rec, (P, "routing_number"), "021000021")
    put(rec, ("business_entity_type",), "llc"); put(rec, ("ein",), "12-3456789")
    put(rec, (P, "average_ticket"), 85); put(rec, (P, "high_ticket"), 600); put(rec, (P, "monthly_card_volume"), 40000)
    assert review.checks(rec, TODAY) == []


def test_zip_table_and_routing_checksum():
    assert review.zip_matches_state("10001", "NY") and review.zip_matches_state("73301", "TX")
    assert review.zip_matches_state("90210", "TX") is False and review.zip_matches_state("12345", "ZZ") is None
    assert review.routing_checksum_ok("021000021") and not review.routing_checksum_ok("021000022")


def test_missing_message_is_english_grouped_and_asks_for_secure_sharing():
    rec = blank()
    put(rec, ("business_information", "legal_business_name"), "Example Goods LLC")
    put(rec, O + ("first_name",), "Pat")
    put(rec, ("business_information", "dba_different_from_legal"), "No")
    msg = review.missing_message(rec)
    assert msg.startswith("Hi Pat,") and "for Example Goods LLC" in msg
    assert "Business address:" in msg and "- Business ZIP code" in msg
    assert "DBA / trade name" not in msg                                    # DBA = No
    assert msg.count("%, total 100") == 3                                   # percentages asked as 3 groups
    assert "Photo ID" in msg and "securely" in msg
    assert "Legal business name" not in msg


def test_review_endpoint_and_stage(client):
    mid = client.post("/api/merchants", json={"text": TEXT}).json()["merchant_id"]
    r = client.get(f"/api/merchants/{mid}/review").json()
    assert r["stage"] == "baru" and r["message"].startswith("Hi") and r["missing"]
    assert client.post(f"/api/merchants/{mid}/stage", json={"stage": "menunggu_info"}).status_code == 200
    assert client.post(f"/api/merchants/{mid}/stage", json={"stage": "lainnya"}).status_code == 422
    row = client.get("/api/merchants").json()["merchants"][0]
    assert row["stage"] == "menunggu_info" and row["errors"] is not None and row["warnings"] is not None
    assert client.get(f"/api/merchants/{mid}/review").json()["stage"] == "menunggu_info"
    assert client.post("/api/merchants/MCN-20261120-099/stage", json={"stage": "baru"}).status_code == 404


def test_application_status(client):
    mid = client.post("/api/merchants", json={"text": TEXT}).json()["merchant_id"]
    assert client.get(f"/api/merchants/{mid}/review").json()["app_status"] == "no_info"
    assert client.get("/api/merchants").json()["merchants"][0]["app_status"] == "no_info"
    assert client.post(f"/api/merchants/{mid}/stage", json={"stage": "siap_diisi"}).status_code == 200
    r = client.post(f"/api/merchants/{mid}/application-status", json={"app_status": "signed_waiting_underwriting"})
    assert r.status_code == 200
    row = client.get("/api/merchants").json()["merchants"][0]
    assert (row["stage"], row["app_status"]) == ("siap_diisi", "signed_waiting_underwriting")   # independent
    assert client.post(f"/api/merchants/{mid}/application-status", json={"app_status": "pending"}).status_code == 422
    assert client.post(f"/api/merchants/{mid}/stage", json={"stage": "disetujui"}).status_code == 422    # moved to app status
    assert client.post("/api/merchants/MCN-20261120-099/application-status", json={"app_status": "approved"}).status_code == 404


def test_an_m25_database_is_upgraded(tmp_path):
    """A database made by #24 (no app_status column, old stages) opens and maps the old stages."""
    import os
    import sqlite3
    from merchant_notebook import sqlstore as SQ
    from merchant_notebook.keys import StaticKeyProvider
    db = tmp_path / "merchants.db"
    key = StaticKeyProvider(os.urandom(32))
    store = SQ.SqliteMerchantStore(db, key)
    rec = blank()
    R.touch(rec, "2026-11-20T00:00:00Z")
    store.save(rec, None)
    store.close()
    con = sqlite3.connect(db)
    con.execute("DROP TABLE work_status")
    con.execute("CREATE TABLE work_status (merchant_id TEXT PRIMARY KEY, stage TEXT NOT NULL, updated_at TEXT NOT NULL)")
    con.execute("INSERT INTO work_status VALUES ('MCN-20261120-001', 'disetujui', 'x')")
    con.commit(); con.close()
    store = SQ.SqliteMerchantStore(db, key)
    row = store.list()[0]
    assert (row["stage"], row["app_status"]) == ("siap_diisi", "approved")
    store.close()
