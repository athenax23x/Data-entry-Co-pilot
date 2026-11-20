"""M21/M22: list progress, duplicate, archive and delete. Fake data only."""
from tests.test_api import TEXT, client, db_path  # noqa: F401  (fixtures)

from merchant_notebook import paykings_export as PE


def _new(client, text=TEXT):
    r = client.post("/api/merchants", json={"text": text})
    assert r.status_code == 201, r.text
    return r.json()


def test_list_shows_form_progress_and_open_conflicts_without_values(client):
    rec = _new(client)
    row = client.get("/api/merchants").json()["merchants"][0]
    filled, total = PE.form_progress(rec["record"])
    assert (row["filled"], row["total"]) == (filled, total) and 0 < filled < total
    assert row["open_conflicts"] == 0 and row["archived"] is False
    assert "Example Goods LLC" not in str({k: v for k, v in row.items() if k != "legal_name"})


def test_duplicate_makes_a_new_merchant_with_the_same_values(client):
    src = _new(client)
    r = client.post(f"/api/merchants/{src['merchant_id']}/duplicate")
    assert r.status_code == 201, r.text
    dup = r.json()
    assert dup["merchant_id"] != src["merchant_id"] and dup["version"] == 1
    assert dup["record"]["contact_information"]["email"]["value"] == src["record"]["contact_information"]["email"]["value"]
    assert dup["record"]["sources"][-1]["label"] == f"Duplikat dari {src['merchant_id']}"
    assert len(client.get("/api/merchants").json()["merchants"]) == 2


def test_archive_hides_restore_shows_and_only_archived_can_be_deleted(client):
    a, b = _new(client), _new(client, "Other Example LLC; other@example.com")
    mid = a["merchant_id"]
    assert client.delete(f"/api/merchants/{mid}", params={"expected_version": 1}).status_code == 422   # not archived
    assert client.post(f"/api/merchants/{mid}/archive", json={"archived": True}).status_code == 200
    ids = [m["merchant_id"] for m in client.get("/api/merchants").json()["merchants"]]
    assert ids == [b["merchant_id"]]
    assert [m["merchant_id"] for m in client.get("/api/merchants", params={"archived": "true"}).json()["merchants"]] == [mid]
    # the "all merchants" CSV leaves archived ones out
    assert "Example Goods LLC" not in client.get("/api/export/paykings.csv").text
    # restore, archive again, then delete at the wrong and the right version
    client.post(f"/api/merchants/{mid}/archive", json={"archived": False})
    assert len(client.get("/api/merchants").json()["merchants"]) == 2
    client.post(f"/api/merchants/{mid}/archive", json={})
    assert client.delete(f"/api/merchants/{mid}", params={"expected_version": 7}).status_code == 409
    assert client.delete(f"/api/merchants/{mid}", params={"expected_version": 1}).status_code == 200
    assert client.get(f"/api/merchants/{mid}").status_code == 404
    assert client.get("/api/merchants", params={"archived": "true"}).json()["merchants"] == []


def test_archive_and_delete_of_an_unknown_merchant_is_404(client):
    assert client.post("/api/merchants/MCN-20261120-099/archive", json={}).status_code == 404
    assert client.delete("/api/merchants/MCN-20261120-099", params={"expected_version": 1}).status_code == 404
    assert client.post("/api/merchants/MCN-20261120-099/duplicate").status_code == 404
