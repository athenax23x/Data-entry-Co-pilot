"""M3: the local HTTP API. TestClient, fake data only."""
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from merchant_notebook import sqlstore as SQ
from merchant_notebook.api import __main__ as api_main
from merchant_notebook.api.app import create_app
from merchant_notebook.api.security import ALLOWED_HOSTS, TOKEN_HEADER
from merchant_notebook.keys import StaticKeyProvider

BASE = "http://127.0.0.1:8765"
TOKEN = "test-token-not-a-real-secret"
KEY = StaticKeyProvider(os.urandom(32))
SSN, SSN2, ACCOUNT = "123456789", "987654321", "12345678"
TEXT = "Example Goods LLC; 88 Pine Rd Tampa FL 33602; owner@example.com; 555-010-0187"


class Clock:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return datetime(2026, 11, 18, 10, 0, self.n, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "merchants.db"


@pytest.fixture
def client(db_path):
    app = create_app(lambda: SQ.SqliteMerchantStore(db_path, KEY), token=TOKEN, clock=Clock())
    with TestClient(app, base_url=BASE, raise_server_exceptions=False, headers={TOKEN_HEADER: TOKEN}) as c:
        yield c


def create(client, text=TEXT):
    r = client.post("/api/merchants", json={"text": text})
    assert r.status_code == 201, r.text
    return r.json()


def patch(client, mid, path, version, **body):
    return client.patch(f"/api/merchants/{mid}/fields/{path}", json={"expected_version": version, **body})


# ------------------------------------------------------------------ host, origin, token, bind
def test_foreign_host_is_refused_with_400(client):
    for host in ("evil.example", "127.0.0.1:9999", "127.0.0.1", "localhost:80"):
        assert client.get("/api/health", headers={"Host": host}).status_code == 400
    for host in ALLOWED_HOSTS:
        assert client.get("/api/health", headers={"Host": host}).status_code == 200


def test_the_server_binds_to_loopback_only(monkeypatch):
    seen = {}
    monkeypatch.setattr(api_main.uvicorn, "run", lambda app, **kw: seen.update(kw))
    api_main.serve(lambda: None)
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8765 and seen["access_log"] is False
    package = Path(api_main.__file__).parent
    for f in package.glob("*.py"):
        assert "0.0.0.0" not in f.read_text(encoding="utf-8"), f.name


@pytest.mark.parametrize("method", ["post", "patch"])
def test_foreign_origin_is_refused_with_403_on_writes(client, method):
    m = create(client)
    bad = {"Origin": "https://evil.example"}
    if method == "post":
        r = client.post("/api/merchants", json={}, headers=bad)
    else:
        r = client.patch(f"/api/merchants/{m['merchant_id']}/fields/phone", headers=bad,
                         json={"expected_version": 1, "value": "555-010-0188"})
    assert r.status_code == 403
    assert client.post("/api/merchants", json={}, headers={"Origin": "null"}).status_code == 403
    assert len(client.get("/api/merchants").json()["merchants"]) == 1            # nothing was created


def test_same_origin_and_no_origin_are_accepted(client):
    assert client.post("/api/merchants", json={}, headers={"Origin": BASE}).status_code == 201
    assert client.post("/api/merchants", json={}).status_code == 201


def test_missing_or_wrong_token_is_401(client):
    for headers in ({TOKEN_HEADER: ""}, {TOKEN_HEADER: "wrong"}, {TOKEN_HEADER: TOKEN + "x"}):
        assert client.get("/api/health", headers=headers).status_code == 401
        assert client.post("/api/merchants", json={}, headers=headers).status_code == 401
    bare = TestClient(client.app, base_url=BASE)
    assert bare.get("/api/merchants").status_code == 401


def test_the_page_carries_the_token_and_there_are_no_cors_headers(client):
    r = client.get("/", headers={TOKEN_HEADER: ""})
    assert r.status_code == 200 and f'content="{TOKEN}"' in r.text
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert not any(h.lower().startswith("access-control-") for h in r.headers)
    assert r.headers["cache-control"] == "no-store"


def test_a_new_token_is_made_for_each_server_run():
    a = create_app(lambda: None)
    b = create_app(lambda: None)
    assert a.state.token != b.state.token and len(a.state.token) >= 32


# ------------------------------------------------------------------ endpoints
def test_create_list_search_and_get(client):
    m = create(client)
    assert m["version"] == 1 and m["record"]["schema_version"] == 2
    assert m["record"]["business_information"]["legal_business_name"]["value"] == "Example Goods LLC"
    create(client, "Other Shop Inc")
    assert len(client.get("/api/merchants").json()["merchants"]) == 2
    found = client.get("/api/merchants", params={"q": "example goods"}).json()["merchants"]
    assert [x["merchant_id"] for x in found] == [m["merchant_id"]]
    got = client.get(f"/api/merchants/{m['merchant_id']}").json()
    assert got["version"] == 1 and got["record"] == m["record"]
    assert client.get("/api/merchants/MCN-20990101-001").status_code == 404


def test_new_merchants_get_distinct_ids(client):
    ids = {create(client, "")["merchant_id"] for _ in range(3)}
    assert len(ids) == 3


def test_get_shows_the_full_sensitive_values(client):
    m = create(client)
    mid = m["merchant_id"]
    assert patch(client, mid, "owners[0].ssn", 1, value=SSN).status_code == 200
    assert patch(client, mid, "banking_information.account_number", 2, value=ACCOUNT).status_code == 200
    rec = client.get(f"/api/merchants/{mid}").json()["record"]
    assert rec["personal_information"]["owners"][0]["ssn"]["value"] == SSN
    assert rec["banking_information"]["account_number"]["value"] == ACCOUNT


def test_update_field_set_confirm_and_missing(client):
    mid = create(client)["merchant_id"]
    r = patch(client, mid, "phone", 1, value="555.010.0199")
    assert r.status_code == 200 and r.json()["version"] == 2
    assert r.json()["record"]["contact_information"]["phone"]["value"] == "+1 (555) 010-0199"
    r = patch(client, mid, "email", 2, action="confirm")
    assert r.json()["record"]["contact_information"]["email"]["status"] == "verified"
    r = patch(client, mid, "phone", 3, action="missing")
    assert r.json()["record"]["contact_information"]["phone"]["value"] is None


def test_v2_field_service_only_business_can_be_updated(client):
    mid = create(client)["merchant_id"]
    r = patch(client, mid, "fulfillment_information.service_only_business", 1, value="yes")
    assert r.status_code == 200
    f = r.json()["record"]["fulfillment_information"]["service_only_business"]
    assert (f["value"], f["status"]) == ("Yes", "verified")


def test_a_second_owner_can_be_added_with_v2_owner_fields(client):
    mid = create(client)["merchant_id"]
    assert patch(client, mid, "owners[1].email", 1, value="second@example.com").status_code == 200
    assert patch(client, mid, "owners[1].passport_expiration", 2, value="05/06/2032").status_code == 200


def test_bad_requests_are_400(client):
    mid = create(client)["merchant_id"]
    assert patch(client, mid, "no_such_field", 1, value="x").status_code == 400
    assert patch(client, mid, "phone", 1, value="not a phone").status_code == 400
    assert patch(client, mid, "phone", 1).status_code == 400                         # set without a value
    assert patch(client, mid, "notes", 1, value="confirm").status_code == 400        # reserved word as a value
    assert patch(client, mid, "notes", 1, value="card 4111 1111 1111 1111").status_code == 400
    assert patch(client, mid, "notes", 1, action="confirm").status_code == 400       # nothing to confirm
    assert client.get(f"/api/merchants/{mid}").json()["version"] == 1                # nothing changed


def test_add_context_merges_and_reports_conflicts(client):
    mid = create(client)["merchant_id"]
    r = client.post(f"/api/merchants/{mid}/context", json={"expected_version": 1, "text": "call 555-010-0111"})
    assert r.status_code == 200 and r.json()["version"] == 2
    assert r.json()["record"]["contact_information"]["phone"]["status"] == "conflict"
    r = client.post(f"/api/merchants/{mid}/context", json={"expected_version": 1, "text": "x"})
    assert r.status_code == 409


def test_resolve_a_conflict(client):
    mid = create(client)["merchant_id"]
    r = client.post(f"/api/merchants/{mid}/context", json={"expected_version": 1, "text": "call 555-010-0111"})
    conflict = r.json()["record"]["conflicts"][0]
    cid = conflict["conflict_id"]
    url = f"/api/merchants/{mid}/conflicts/{cid}/resolve"
    assert client.post(url, json={"expected_version": 2, "value": "+1 (555) 999-9999"}).status_code == 400
    r = client.post(url, json={"expected_version": 2, "value": conflict["candidates"][0]["value"]})
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["contact_information"]["phone"]["value"] == "+1 (555) 010-0111"
    assert rec["contact_information"]["phone"]["status"] == "verified"
    assert rec["conflicts"][0]["resolution"]["state"] == "resolved"
    again = client.post(url, json={"expected_version": 3, "value": "+1 (555) 010-0111"})
    assert again.status_code == 400
    assert client.post(f"/api/merchants/{mid}/conflicts/CNF-099/resolve",
                       json={"expected_version": 3, "value": "x"}).status_code == 404


# ------------------------------------------------------------------ concurrency and isolation
def test_two_patches_with_the_same_version_second_is_409(client):
    mid = create(client)["merchant_id"]
    assert patch(client, mid, "phone", 1, value="555-010-0101").status_code == 200
    second = patch(client, mid, "phone", 1, value="555-010-0102")
    assert second.status_code == 409 and "Reload" in second.json()["detail"]
    got = client.get(f"/api/merchants/{mid}").json()
    assert got["version"] == 2 and got["record"]["contact_information"]["phone"]["value"] == "+1 (555) 010-0101"


def test_patch_to_merchant_a_does_not_change_merchant_b(client):
    a, b = create(client)["merchant_id"], create(client, "Other Shop Inc")["merchant_id"]
    before = client.get(f"/api/merchants/{b}").json()
    assert patch(client, a, "notes", 1, value="only for A").status_code == 200
    assert client.get(f"/api/merchants/{b}").json() == before
    assert patch(client, "MCN-20990101-001", "notes", 1, value="x").status_code == 404


# ------------------------------------------------------------------ errors and logs
def test_422_messages_never_contain_the_input(client, caplog):
    mid = create(client)["merchant_id"]
    secret = "SECRET-INPUT-VALUE-" + SSN
    caplog.set_level(logging.DEBUG)
    for r in (
        client.patch(f"/api/merchants/{mid}/fields/ssn", json={"expected_version": secret, "value": secret}),
        client.patch(f"/api/merchants/{mid}/fields/ssn", json={"expected_version": 1, "bogus": secret}),
        client.post(f"/api/merchants/{mid}/context", json={"expected_version": 1, "text": 5, "x": secret}),
        client.post("/api/merchants", content=secret, headers={"Content-Type": "application/json"}),
    ):
        assert r.status_code == 422
        assert secret not in r.text and SSN not in r.text
        assert r.json()["fields"]
    assert secret not in caplog.text


def test_sensitive_values_are_not_in_errors_logs_or_the_database_file(client, caplog, capfd, db_path):
    mid = create(client)["merchant_id"]
    caplog.set_level(logging.DEBUG)
    r = patch(client, mid, "owners[0].ssn", 1, value=SSN)
    assert r.status_code == 200 and SSN not in r.json()["message"]
    bad = patch(client, mid, "owners[0].ssn", 2, value="12-34")
    assert bad.status_code == 400 and "12-34" not in bad.text
    assert patch(client, mid, "owners[0].ssn", 2, value=SSN2).status_code == 200            # SSN is now in history
    client.get(f"/api/merchants/{mid}")
    client.get("/api/merchants", params={"q": "Example"})
    out = capfd.readouterr()
    assert SSN not in caplog.text and SSN2 not in caplog.text
    assert SSN not in out.out + out.err and SSN2 not in out.out + out.err
    rec = client.get(f"/api/merchants/{mid}").json()["record"]
    ssn = rec["personal_information"]["owners"][0]["ssn"]
    assert ssn["value"] == SSN2 and ssn["history"][0]["value"] == SSN
    assert SSN not in ssn["source_context"] and SSN2 not in ssn["source_context"]
    raw = db_path.read_bytes()
    assert SSN.encode() not in raw and SSN2.encode() not in raw


def test_server_errors_are_generic_and_do_not_leak_details(client, monkeypatch, caplog):
    mid = create(client)["merchant_id"]
    caplog.set_level(logging.DEBUG)

    def corrupt(_):
        raise SQ.CorruptRecordError(f"detail with {SSN}")

    monkeypatch.setattr(client.app.state.store, "load", corrupt)
    r = client.get(f"/api/merchants/{mid}")
    assert r.status_code == 500 and SSN not in r.text
    monkeypatch.setattr(client.app.state.store, "load", lambda _: (_ for _ in ()).throw(RuntimeError(SSN)))
    r = client.get(f"/api/merchants/{mid}")
    assert r.status_code == 500 and SSN not in r.text and SSN not in caplog.text


def test_a_refused_record_is_422_and_nothing_is_written(client, monkeypatch):
    mid = create(client)["merchant_id"]

    def refuse(rec, expected_version):
        raise SQ.RefusedRecord("the record does not match schema_v2.json:\n  /x: problem")

    monkeypatch.setattr(client.app.state.store, "save", refuse)
    assert patch(client, mid, "notes", 1, value="x").status_code == 422
    monkeypatch.undo()
    assert client.get(f"/api/merchants/{mid}").json()["version"] == 1


# ------------------------------------------------------------------ Paykings CSV export (M10)
def _csv_rows(text):
    import csv, io
    return list(csv.DictReader(io.StringIO(text)))


def test_export_has_the_70_paykings_columns_and_hides_sensitive_values_by_default(client):
    m = create(client)
    mid = m["merchant_id"]
    r = patch(client, mid, "personal_information.owners[0].ssn", 1, action="set", value="123-45-6789")
    assert r.status_code == 200
    res = client.get("/api/export/paykings.csv", params={"merchant_id": mid})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"] and res.headers["cache-control"] == "no-store"
    rows = _csv_rows(res.text)
    assert len(rows) == 1 and len(rows[0]) == 70 and rows[0]["merchant_id"] == mid
    assert rows[0]["Legal Business Name"] == "Example Goods LLC" and rows[0]["Business Email"] == "owner@example.com"
    assert "123456789" not in res.text and rows[0]["SSN"] == ""
    assert rows[0]["Owner Title"] == "Owner"
    assert rows[0]["Building Type"] == "" and rows[0]["MCC Code"] == ""              # skipped columns stay blank


def test_export_includes_sensitive_values_only_when_asked_and_covers_all_merchants(client):
    a = create(client)["merchant_id"]
    create(client, "Second Shop LLC; 5 Oak St Tampa FL 33602")
    patch(client, a, "personal_information.owners[0].ssn", 1, action="set", value="123-45-6789")
    plain = _csv_rows(client.get("/api/export/paykings.csv").text)
    assert len(plain) == 2
    with_secret = client.get("/api/export/paykings.csv", params={"merchant_id": a, "include_sensitive": "true"})
    assert _csv_rows(with_secret.text)[0]["SSN"] == "123456789"
    assert "with-sensitive" in with_secret.headers["content-disposition"]


def test_export_needs_the_token_and_refuses_an_unknown_merchant(client):
    assert client.get("/api/export/paykings.csv", headers={TOKEN_HEADER: "wrong"}).status_code == 401
    assert client.get("/api/export/paykings.csv", params={"merchant_id": "MCN-00000000-999"}).status_code == 404


def test_export_refuses_an_id_that_is_not_a_merchant_id(client):
    for bad in ('x"; filename="evil', "MCN-1", "../etc/passwd"):
        assert client.get("/api/export/paykings.csv", params={"merchant_id": bad}).status_code == 404
