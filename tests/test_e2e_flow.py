"""One whole run with US-style fake data: paste text -> mask -> Claude's answer -> preview -> apply -> CSV export.

Nothing sensitive may reach the prompt, the stored sources, or the default CSV. Fake data only."""
import csv
import io
import json

from tests.test_api import TOKEN, client, db_path  # noqa: F401  (fixtures)
from tests.test_bridge import answer, cand

SSN, ACCOUNT, CARD = "123-45-6789", "87654321", "4111 1111 1111 1111"
TEXT = (f"Example Goods LLC. Owner: Pat Example, phone 555-010-0187. Email: contact@example.com. "
        f"Address: 123 Example Ave, Tampa, FL 33602. Bank: Example Bank N.A., account number {ACCOUNT}. "
        f"SSN {SSN}. Card {CARD} cvv 321. Routing 021000021. Started 06/02/2004. EIN 12-3456789.")
SECRETS = [SSN, "123456789", ACCOUNT, CARD, "cvv 321"]


def test_whole_flow_keeps_sensitive_data_out_of_the_prompt_the_sources_and_the_default_csv(client):
    # 1. mask + prompt
    prep = client.post("/api/bridge/prepare", json={"text": TEXT}).json()
    for s in SECRETS:
        assert s not in prep["masked_text"] and s not in prep["prompt"], s
    assert "Example Goods LLC" in prep["prompt"] and "FIELD LIST" in prep["prompt"]
    assert "021000021" in prep["masked_text"]                                      # a routing number is public

    # 2. a new empty merchant, then Claude's answer (written by hand, as Claude would return it)
    rec = client.post("/api/merchants", json={"text": ""}).json()
    mid, version = rec["merchant_id"], rec["version"]
    good = [cand("business_information.legal_business_name", "Example Goods LLC", "Example Goods LLC"),
            cand("business_entity_type", "llc", "Example Goods LLC"),
            cand("personal_information.owners[0].first_name", "Pat", "Owner: Pat Example"),
            cand("personal_information.owners[0].last_name", "Example", "Owner: Pat Example"),
            cand("contact_information.email", "contact@example.com", "Email: contact@example.com"),
            cand("business_address.street_address", "123 Example Ave", "Address: 123 Example Ave, Tampa, FL 33602"),
            cand("business_address.city", "Tampa", "Address: 123 Example Ave, Tampa, FL 33602"),
            cand("business_address.state", "FL", "Address: 123 Example Ave, Tampa, FL 33602"),
            cand("business_address.zip", "33602", "Address: 123 Example Ave, Tampa, FL 33602"),
            cand("banking_information.bank_name", "Example Bank N.A.", "Bank: Example Bank N.A.")]
    bad = [cand("business_information.business_description", "Sells goods", "this quote is not in the text"),
           cand("banking_information.account_number", ACCOUNT, f"account number {ACCOUNT}"),      # sensitive: never allowed
           cand("fulfillment_information.inventory_storage", "Warehouse", "Warehouse")]            # skipped column
    body = {"expected_version": version, "answer": answer(*good, *bad), "source_text": TEXT}

    # 3. preview: only the good ones pass
    ps = client.post(f"/api/merchants/{mid}/bridge/preview", json=body).json()["proposals"]
    assert [p["ok"] for p in ps] == [True] * len(good) + [False] * len(bad)

    # 4. apply the good ones: stored as inferred, no source text kept
    done = client.post(f"/api/merchants/{mid}/bridge/apply", json=body | {"accept": list(range(len(good)))})
    assert done.status_code == 200, done.text
    stored = done.json()["record"]
    assert stored["business_address"]["city"]["status"] == "inferred"
    assert TEXT not in json.dumps(stored) and ACCOUNT not in json.dumps(stored)

    # 5. a refused proposal cannot be applied even if the browser chose it
    assert client.post(f"/api/merchants/{mid}/bridge/apply",
                       json=body | {"expected_version": done.json()["version"], "accept": [len(good) + 1]}).status_code == 400

    # 6. CSV: the Paykings row has the data, and no sensitive value by default
    res = client.get("/api/export/paykings.csv", params={"merchant_id": mid})
    row = list(csv.DictReader(io.StringIO(res.text)))[0]
    assert row["Legal Business Name"] == "Example Goods LLC" and row["Business City"] == "Tampa"
    assert row["Business State"] == "FL" and row["Owner Title"] == "Owner" and row["Bank Name"] == "Example Bank N.A."
    assert ACCOUNT not in res.text and row["Bank Account Number"] == "" and row["Building Type"] == ""
