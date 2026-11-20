"""M5 endpoints: prepare, preview, apply. Fake data only."""
import json
import logging

from merchant_notebook.api.security import TOKEN_HEADER
from tests.test_api import TOKEN, client, create, db_path  # noqa: F401  (fixtures)
from tests.test_bridge import ACCOUNT, DL, PASSPORT, SECRETS, SOURCE, SSN, answer, cand

PHONE = cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187")
SERVICE = cand("business_information.business_description", "Service only", "Service only: yes")
FAKE = cand("business_information.legal_business_name", "Fake Inc", "Fake Inc is the company")
DOB = cand("personal_information.owners[0].date_of_birth", "06/02/2004", "Born 06/02/2004")


def body(version, cands, **kw):
    return {"expected_version": version, "answer": answer(*cands), "source_text": SOURCE, **kw}


def test_prepare_masks_builds_the_prompt_and_stores_nothing(client, db_path):
    r = client.post("/api/bridge/prepare", json={"text": SOURCE})
    assert r.status_code == 200
    data = r.json()
    for secret in SECRETS:
        assert secret not in data["masked_text"] and secret not in data["prompt"], secret
    assert "[DISAMARKAN]" in data["masked_text"] and data["masked_text"] in data["prompt"]
    assert "bank account number" in data["hidden"]
    assert client.get("/api/merchants").json() == {"merchants": []}
    assert b"Example Goods" not in db_path.read_bytes()


def test_preview_lists_every_proposal_with_its_check_and_stores_nothing(client):
    mid = create(client)["merchant_id"]
    r = client.post(f"/api/merchants/{mid}/bridge/preview", json=body(1, [PHONE, FAKE, DOB, SERVICE]))
    assert r.status_code == 200
    ps = r.json()["proposals"]
    assert [p["ok"] for p in ps] == [True, False, True, True]
    assert ps[1]["reason"].startswith("Bukti") and ps[2]["status"] == "needs_review"
    assert client.get(f"/api/merchants/{mid}").json()["version"] == 1


def test_apply_stores_the_chosen_proposals_as_inferred_and_needs_review(client):
    mid = create(client, "")["merchant_id"]
    r = client.post(f"/api/merchants/{mid}/bridge/apply", json=body(1, [PHONE, FAKE, DOB, SERVICE], accept=[0, 2, 3]))
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert r.json()["version"] == 2 and r.json()["changed"] is True
    phone = rec["contact_information"]["phone"]
    assert (phone["value"], phone["status"], phone["source_context"]) == ("+1 (555) 010-0187", "inferred", "Phone 555-010-0187")
    assert rec["personal_information"]["owners"][0]["date_of_birth"]["status"] == "needs_review"
    assert rec["business_information"]["business_description"]["value"] == "Service only"
    assert rec["business_information"]["legal_business_name"]["value"] is None            # not chosen
    assert SOURCE not in json.dumps(rec) and "Fake Inc" not in json.dumps(rec)             # no source text stored


def test_apply_checks_again_on_the_server_and_refuses_a_bad_proposal_the_browser_chose(client):
    mid = create(client, "")["merchant_id"]
    r = client.post(f"/api/merchants/{mid}/bridge/apply", json=body(1, [PHONE, FAKE], accept=[1]))
    assert r.status_code == 400
    r = client.post(f"/api/merchants/{mid}/bridge/apply", json=body(1, [PHONE], accept=[0]) | {"source_text": "other text"})
    assert r.status_code == 400                                       # evidence is not in the text that was sent
    sensitive = cand("personal_information.owners[0].ssn", "123456789", "SSN")
    assert client.post(f"/api/merchants/{mid}/bridge/apply", json=body(1, [sensitive], accept=[0])).status_code == 400
    assert client.get(f"/api/merchants/{mid}").json()["version"] == 1


def test_applying_the_same_answer_twice_makes_no_duplicates_and_no_new_version(client):
    mid = create(client, "")["merchant_id"]
    assert client.post(f"/api/merchants/{mid}/bridge/apply", json=body(1, [PHONE], accept=[0])).json()["version"] == 2
    again = client.post(f"/api/merchants/{mid}/bridge/apply", json=body(2, [PHONE], accept=[0]))
    assert again.status_code == 200 and again.json()["version"] == 2 and again.json()["changed"] is False
    assert len(client.get(f"/api/merchants/{mid}").json()["record"]["sources"]) == 2     # new merchant + one bridge


def test_a_different_value_makes_a_conflict_and_a_verified_value_stays(client):
    mid = create(client, "")["merchant_id"]
    client.patch(f"/api/merchants/{mid}/fields/phone", json={"expected_version": 1, "value": "555-010-0199"})
    r = client.post(f"/api/merchants/{mid}/bridge/apply", json=body(2, [PHONE], accept=[0]))
    rec = r.json()["record"]
    assert rec["contact_information"]["phone"]["value"] == "+1 (555) 010-0199"
    assert rec["contact_information"]["phone"]["status"] == "conflict" and len(rec["conflicts"]) == 1


def test_a_stale_version_is_409_for_preview_and_apply(client):
    mid = create(client, "")["merchant_id"]
    client.patch(f"/api/merchants/{mid}/fields/notes", json={"expected_version": 1, "value": "x"})
    assert client.post(f"/api/merchants/{mid}/bridge/preview", json=body(1, [PHONE])).status_code == 409
    assert client.post(f"/api/merchants/{mid}/bridge/apply", json=body(1, [PHONE], accept=[0])).status_code == 409
    assert client.post("/api/merchants/MCN-20990101-001/bridge/preview", json=body(1, [PHONE])).status_code == 404


def test_a_bad_answer_is_400_with_a_general_message(client):
    mid = create(client)["merchant_id"]
    secret = "SECRET-" + SSN
    for bad in ("not json " + secret, "[" + secret + "]", json.dumps({"candidates": secret})):
        r = client.post(f"/api/merchants/{mid}/bridge/preview", json={"expected_version": 1, "answer": bad, "source_text": SOURCE})
        assert r.status_code == 400 and secret not in r.text and "Jawaban tidak bisa dibaca" in r.json()["detail"]


def test_422_and_logs_never_contain_the_texts(client, caplog):
    mid = create(client)["merchant_id"]
    caplog.set_level(logging.DEBUG)
    secret = "SECRET-" + SSN
    for r in (client.post("/api/bridge/prepare", json={"text": 5, "x": secret}),
              client.post(f"/api/merchants/{mid}/bridge/apply", json={"expected_version": 1, "answer": secret, "source_text": secret, "accept": "no"}),
              client.post(f"/api/merchants/{mid}/bridge/preview", json={"expected_version": 1, "answer": secret})):
        assert r.status_code == 422 and secret not in r.text
    client.post("/api/bridge/prepare", json={"text": SOURCE})
    client.post(f"/api/merchants/{mid}/bridge/apply", json=body(1, [PHONE], accept=[0]))
    for s in (SSN, ACCOUNT, DL, PASSPORT, secret):
        assert s not in caplog.text


def test_the_m3_protections_apply_to_the_bridge(client):
    mid = create(client)["merchant_id"]
    urls = ["/api/bridge/prepare", f"/api/merchants/{mid}/bridge/preview", f"/api/merchants/{mid}/bridge/apply"]
    for u in urls:
        assert client.post(u, json={}, headers={TOKEN_HEADER: ""}).status_code == 401
        assert client.post(u, json={}, headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.post(u, json={}, headers={"Host": "evil.example"}).status_code == 400


def test_merchant_b_is_not_changed_by_applying_to_a(client):
    a, b = create(client, "")["merchant_id"], create(client, "Other Shop Inc")["merchant_id"]
    before = client.get(f"/api/merchants/{b}").json()
    client.post(f"/api/merchants/{a}/bridge/apply", json=body(1, [PHONE], accept=[0]))
    assert client.get(f"/api/merchants/{b}").json() == before


def test_numbers_from_claude_are_stored_as_numbers_and_apply_succeeds(client):
    """Percentages and dollar amounts passed the check but failed schema validation on apply (stored as text)."""
    import json as _json
    text = "100% public. 80% card present. Monthly volume about $40,000, average ticket $85."
    rec = client.post("/api/merchants", json={"text": ""}).json()
    ans = _json.dumps({"candidates": [
        {"path": "processing_information.public_sales_percentage", "value": "100", "evidence": "100% public"},
        {"path": "processing_information.card_present_percentage", "value": "80", "evidence": "80% card present"},
        {"path": "processing_information.monthly_card_volume", "value": "40000", "evidence": "Monthly volume about $40,000"},
        {"path": "processing_information.average_ticket", "value": "85", "evidence": "average ticket $85"}]})
    body = {"expected_version": rec["version"], "answer": ans, "source_text": text}
    ps = client.post(f"/api/merchants/{rec['merchant_id']}/bridge/preview", json=body).json()["proposals"]
    assert all(p["ok"] for p in ps) and "stored" not in ps[0]
    done = client.post(f"/api/merchants/{rec['merchant_id']}/bridge/apply", json=body | {"accept": [0, 1, 2, 3]})
    assert done.status_code == 200, done.text
    pi = done.json()["record"]["processing_information"]
    assert pi["public_sales_percentage"]["value"] == 100 and pi["monthly_card_volume"]["value"] == 40000
