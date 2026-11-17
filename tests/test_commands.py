"""The nine commands: argument forms, errors and bookkeeping."""
from conftest import active


def test_unknown_input_lists_the_nine_commands(session):
    out = session.execute("FROBNICATE")
    assert out.startswith("Not a Notebook command") and "CLEAR SESSION" in out and "EXPORT CSV" in out


def test_commands_are_case_insensitive_and_whitespace_tolerant(session):
    assert "Created MCN-" in session.execute("new   merchant  Alex Sample")
    assert session.active
    assert "record_status" in session.execute("show merchant")


def test_commands_need_an_active_merchant(session):
    for cmd in ("ADD CONTEXT x", "UPDATE FIELD phone = 555.010.0187", "SHOW MERCHANT", "SHOW MISSING FIELDS",
                "SAVE MERCHANT", "EXPORT CSV"):
        assert session.execute(cmd).startswith("Error: No active merchant"), cmd


def test_a_named_merchant_id_must_be_in_the_session(session):
    session.execute("NEW MERCHANT x")
    out = session.execute("SHOW MERCHANT MCN-20990101-001")
    assert out.startswith("Error") and "not in this session" in out


def test_update_field_forms(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD state = fl")                                    # short name, unique
    assert active(session)["business_address"]["state"]["value"] == "FL"
    session.execute("UPDATE FIELD business_information.state_of_formation = tx")  # full path
    assert active(session)["business_information"]["state_of_formation"]["value"] == "TX"
    session.execute("UPDATE FIELD owners[1].last_name = Example")                 # appends a second owner
    owners = active(session)["personal_information"]["owners"]
    assert [o["owner_id"] for o in owners] == ["OWN-1", "OWN-2"] and owners[1]["is_primary_owner"] is False
    assert session.execute("UPDATE FIELD owners[5].last_name = X").startswith("Error")
    session.execute("UPDATE FIELD items[+] = car wash")
    session.execute("UPDATE FIELD items[+] = detailing")
    items = active(session)["products_and_services"]["items"]
    assert [i["value"] for i in items] == ["car wash", "detailing"] and items[0]["status"] == "verified"
    session.execute("UPDATE FIELD custom_fields.loyalty_tier = gold")
    assert active(session)["custom_fields"]["loyalty_tier"]["value"] == "gold"
    assert session.execute("UPDATE FIELD nonsense = 1").startswith("Error: Unknown field")


def test_a_short_name_that_matches_two_fields_is_refused(monkeypatch):
    from merchant_notebook import fields
    monkeypatch.setitem(fields.FIELD_SPECS, "business_information.state", "state")
    try:
        fields.resolve_target("state")
    except fields.FieldError as e:
        assert "ambiguous" in str(e) and "business_address.state" in str(e)
    else:
        raise AssertionError("an ambiguous short name was accepted")


def test_update_field_rejects_values_that_cannot_be_normalized(session):
    session.execute("NEW MERCHANT x")
    for field, bad in (("phone", "12345"), ("email", "nope"), ("zip", "ABCDE"), ("state", "ZZ"),
                       ("business_start_date", "2026-13-45"), ("website", "not a uri"),
                       ("keyed_percentage", "101"), ("mcc", "12"), ("ein", "1-2")):
        out = session.execute(f"UPDATE FIELD {field} = {bad}")
        assert out.startswith("Error") and "nothing was changed" in out, (field, out)
    assert all(f["status"] == "missing" for f in active(session)["contact_information"].values())


def test_confirm_and_missing(session):
    session.execute("NEW MERCHANT alex@example.com")
    assert active(session)["contact_information"]["email"]["status"] == "inferred"
    out = session.execute("UPDATE FIELD email = confirm")
    assert "verified" in out and active(session)["contact_information"]["email"]["status"] == "verified"
    assert session.execute("UPDATE FIELD phone = confirm").startswith("Error: There is no value to confirm")
    session.execute("UPDATE FIELD email = missing")
    f = active(session)["contact_information"]["email"]
    assert f["value"] is None and f["status"] == "missing" and f["history"][-1]["value"] == "alex@example.com"
    assert session.execute("UPDATE FIELD email = missing").startswith("Error")


def test_confirming_a_conflicted_field_asks_which_value_to_keep(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    session.execute("ADD CONTEXT 555-010-0199")
    assert "Choose the value to keep" in session.execute("UPDATE FIELD phone = confirm")


def test_show_missing_fields_lists_what_is_needed(session):
    session.execute("NEW MERCHANT Alex Sample")
    out = session.execute("SHOW MISSING FIELDS")
    for needle in ("legal_business_name", "street_address", "zip", "email", "phone"):
        assert needle in out
    session.execute("UPDATE FIELD phone = 555.010.0187")
    assert "phone" not in session.execute("SHOW MISSING FIELDS")


def test_sources_and_timestamps_are_recorded_for_every_command(session):
    session.execute("NEW MERCHANT alex@example.com")
    session.execute("ADD CONTEXT 555-010-0187")
    session.execute("UPDATE FIELD city = Tampa")
    rec = active(session)
    assert [s["source_id"] for s in rec["sources"]] == ["SRC-001", "SRC-002", "SRC-003"]
    assert [s["source_type"] for s in rec["sources"]] == ["new_merchant", "add_context", "update_field"]
    assert rec["contact_information"]["email"]["source_document"] == "SRC-001"
    assert rec["contact_information"]["phone"]["source_document"] == "SRC-002"
    assert rec["business_address"]["city"]["source_document"] == "SRC-003"
    assert rec["created_at"] < rec["updated_at"]
    assert rec["created_at"].endswith("Z") and rec["merchant_id"].startswith("MCN-20261117-")


def test_missing_values_are_null_and_never_empty_strings(session):
    session.execute("NEW MERCHANT Alex Sample")
    stack = [active(session)]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if {"value", "status"} <= set(node) and node["status"] == "missing":
                assert node["value"] is None
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
