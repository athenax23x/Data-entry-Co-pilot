"""Confirmed (verified) values are never overwritten; conflicts are recorded instead."""
from conftest import active


def test_verified_value_survives_conflicting_add_context(session):
    session.execute("NEW MERCHANT Alex Sample, alex@example.com")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    out = session.execute("ADD CONTEXT call him at 555-010-0199")
    f = active(session)["contact_information"]["phone"]
    assert f["value"] == "+1 (555) 010-0187"          # the verified value is still there
    assert f["status"] == "conflict"
    (c,) = active(session)["conflicts"]
    assert c["field_path"] == "/contact_information/phone"
    assert c["current_value"] == "+1 (555) 010-0187"
    assert c["current_status"] == "verified"
    assert c["resolution"] == {"state": "open"}
    (cand,) = c["candidates"]
    assert cand["value"] == "+1 (555) 010-0199"
    assert "555-010-0199" in cand["source_context"] and cand["source_document"] == "SRC-003"
    assert "CONFLICT" in out


def test_same_value_in_another_format_is_not_a_conflict(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    session.execute("ADD CONTEXT phone is (555) 010-0187")
    f = active(session)["contact_information"]["phone"]
    assert f["status"] == "verified" and active(session)["conflicts"] == []


def test_verified_entity_type_is_not_replaced(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD business_entity_type = llc")
    session.execute("ADD CONTEXT actually a sole proprietor")
    f = active(session)["business_entity_type"]
    assert f["value"] == "llc" and f["status"] == "conflict"
    assert active(session)["conflicts"][0]["candidates"][0]["value"] == "sole_proprietorship"


def test_unclear_text_never_disturbs_a_verified_value(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD ein = 12-3456789")
    session.execute("ADD CONTEXT reference number 987654321")      # 9 digits: EIN or routing? unclear
    f = active(session)["ein"]
    assert f["value"] == "12-3456789" and f["status"] == "verified"


def test_extra_candidates_attach_to_the_same_open_conflict(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    session.execute("ADD CONTEXT 555-010-0199")
    session.execute("ADD CONTEXT 555-010-0123")
    session.execute("ADD CONTEXT 555-010-0199")                    # repeat: not added twice
    (c,) = active(session)["conflicts"]
    assert [x["value"] for x in c["candidates"]] == ["+1 (555) 010-0199", "+1 (555) 010-0123"]


def test_only_update_field_changes_a_verified_value_and_it_shows_old_and_new(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    session.execute("ADD CONTEXT 555-010-0199")
    out = session.execute("UPDATE FIELD phone = 555-010-0199")
    f = active(session)["contact_information"]["phone"]
    assert f["value"] == "+1 (555) 010-0199" and f["status"] == "verified"
    assert "+1 (555) 010-0187" in out and "+1 (555) 010-0199" in out       # old and new are shown
    assert f["history"][-1]["value"] == "+1 (555) 010-0187"                 # nothing is lost
    (c,) = active(session)["conflicts"]
    assert c["resolution"]["state"] == "resolved" and c["resolution"]["resolved_value"] == "+1 (555) 010-0199"


def test_load_does_not_silently_replace_a_session_record(session, make_session, data_dir):
    declined = []
    s = make_session(confirm=lambda q: declined.append(q) or False)
    s.execute("NEW MERCHANT x")
    s.execute("SAVE MERCHANT")
    s.execute("UPDATE FIELD phone = 555.010.0187")                 # unsaved verified value
    out = s.execute(f"LOAD MERCHANT {s.active}")
    assert declined and "unsaved changes" in declined[0]
    assert out.startswith("NOT loaded")
    assert active(s)["contact_information"]["phone"]["value"] == "+1 (555) 010-0187"


def test_different_merchant_is_not_merged(session):
    session.execute("NEW MERCHANT business: Alpha Plumbing LLC; ein: 12-3456789")
    out = session.execute("ADD CONTEXT business: Beta Roofing Inc; ein: 98-7654321")
    assert "different merchant" in out
    assert active(session)["business_information"]["legal_business_name"]["value"] == "Alpha Plumbing LLC"
    assert active(session)["conflicts"] == [] and len(active(session)["sources"]) == 1
