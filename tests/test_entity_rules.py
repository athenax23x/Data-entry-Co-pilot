"""Entity types, sole-proprietorship rules and the owner-name-is-not-a-business-name rule."""
import pytest

from conftest import active
from merchant_notebook.entity import recognize


@pytest.mark.parametrize("text,expected", [
    ("Alex Sample, sole proprietor", "sole_proprietorship"),
    ("a sole proprietorship", "sole_proprietorship"),
    ("sole prop", "sole_proprietorship"),
    ("individual owner", "sole_proprietorship"),
    ("Sample Services LLC", "llc"),
    ("Sample Services L.L.C.", "llc"),
    ("Sample Services Limited Liability Company", "llc"),
    ("Sample Foods Inc.", "corporation"),
    ("Sample Foods Corp", "corporation"),
    ("Sample Foods Incorporated", "corporation"),
    ("Sample Foods S Corp", "s_corporation"),
    ("Sample Foods S-Corporation", "s_corporation"),
    ("Sample Foods C Corp", "c_corporation"),
    ("Sample Foods C Corporation", "c_corporation"),
    ("Sample Partners General Partnership", "general_partnership"),
    ("Sample Partners LP", "limited_partnership"),
    ("Sample Partners L.P.", "limited_partnership"),
    ("Sample Partners Limited Partnership", "limited_partnership"),
    ("Sample Partners LLP", "limited_liability_partnership"),
    ("Sample Partners L.L.P.", "limited_liability_partnership"),
    ("Sample Partners Limited Liability Partnership", "limited_liability_partnership"),
])
def test_all_eight_entity_types_are_recognized(text, expected):
    r = recognize(text)
    assert (r.kind, r.value) == ("one", expected)


def test_the_most_specific_type_wins():
    assert recognize("Sample LLP").value == "limited_liability_partnership"    # not LP
    assert recognize("Sample Inc, S Corp").value == "s_corporation"            # not just corporation
    assert recognize("Sample LLC taxed as an S Corp").value == "llc"           # a tax election is not the entity


def test_unclear_or_contradictory_signals_are_never_guessed():
    assert recognize("Sample Co").kind == "none"
    assert recognize("Sample Ltd").kind == "ambiguous"
    assert recognize("sole proprietor and also an LLC").kind == "ambiguous"
    assert recognize("some partnership").kind == "ambiguous"


def test_sole_proprietor_needs_no_business_suffix(session):
    session.execute("NEW MERCHANT Alex Sample, sole proprietor, alex@example.com")
    f = active(session)["business_entity_type"]
    assert (f["value"], f["status"]) == ("sole_proprietorship", "inferred")
    assert active(session)["business_information"]["legal_business_name"]["value"] is None


def test_owner_name_is_never_copied_into_the_business_name(session):
    session.execute("NEW MERCHANT name: Alex Sample; individual owner; alex@example.com")
    rec = active(session)
    assert rec["personal_information"]["owners"][0]["first_name"]["value"] == "Alex"
    for name in ("legal_business_name", "dba_name"):
        assert rec["business_information"][name]["value"] is None
    assert "Sample" not in str({k: v["value"] for k, v in rec["business_information"].items()})


def test_dba_goes_to_dba_name_not_to_the_legal_name(session):
    session.execute("NEW MERCHANT name: Alex Sample; sole proprietor; dba Sample Mobile Detailing; "
                    "88 Pine Rd Tampa FL 33602; alex@example.com; 813 555 0144")
    rec = active(session)
    assert rec["business_information"]["dba_name"]["value"] == "Sample Mobile Detailing"
    assert rec["business_information"]["legal_business_name"]["value"] is None
    assert rec["record_status"] == "Complete"          # the DBA satisfies the sole proprietor's name need
    assert "legal_business_name" in session.execute("SHOW MISSING FIELDS")


def test_without_any_business_name_a_sole_proprietor_is_incomplete(session):
    session.execute("NEW MERCHANT name: Alex Sample; sole proprietor; 88 Pine Rd Tampa FL 33602; "
                    "alex@example.com; 813 555 0144")
    assert active(session)["record_status"] == "Incomplete"


def test_dba_does_not_satisfy_the_name_need_for_other_entity_types(session):
    session.execute("NEW MERCHANT name: Alex Sample; dba Sample Mobile Detailing; 88 Pine Rd Tampa FL 33602; "
                    "alex@example.com; 813 555 0144")
    assert active(session)["record_status"] == "Incomplete"


def test_contradictory_entity_signals_become_unknown_and_needs_review(session):
    session.execute("NEW MERCHANT sole proprietor, Sample Services LLC")
    f = active(session)["business_entity_type"]
    assert (f["value"], f["status"]) == ("unknown", "needs_review")


def test_entity_suffix_is_recognized_and_stays_in_the_legal_name(session):
    session.execute("NEW MERCHANT business: Sample Services llc")
    rec = active(session)
    assert rec["business_information"]["legal_business_name"]["value"] == "Sample Services LLC"
    assert rec["business_entity_type"]["value"] == "llc"
    assert rec["conflicts"] == []


def test_update_field_normalizes_entity_names_to_schema_values(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD business_entity_type = Sole Proprietorship")
    f = active(session)["business_entity_type"]
    assert (f["value"], f["status"]) == ("sole_proprietorship", "verified")
    out = session.execute("UPDATE FIELD business_entity_type = banana")
    assert out.startswith("Error") and active(session)["business_entity_type"]["value"] == "sole_proprietorship"


def test_owner_name_becomes_the_legal_name_only_when_the_user_says_so(session):
    session.execute("NEW MERCHANT name: Alex Sample; sole proprietor")
    session.execute("UPDATE FIELD legal_business_name = Alex Sample")
    f = active(session)["business_information"]["legal_business_name"]
    assert (f["value"], f["status"]) == ("Alex Sample", "verified")
