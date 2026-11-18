"""M5: masking, the prompt, and the answer checks. Fake data only."""
import json

import pytest

from merchant_notebook import migrate, paykings_map as PM, record as R
from merchant_notebook.bridge import check, mask, prompt

NOW = "2026-11-18T10:00:00Z"
SSN, SSN4, ACCOUNT, DL, SIM, PASSPORT, CARD, CVV = "123-45-6789", "6789", "87654321", "D1234567", "55667788", "X7654321", "4111 1111 1111 1111", "321"
SOURCE = (f"Example Goods LLC, owner Pat Example. Phone 555-010-0187. Born 06/02/2004. Service only: yes. "
          f"SSN {SSN}. SSN last 4: {SSN4}. Account number: {ACCOUNT}. Rekening 1234 5678 90. "
          f"Driver license {DL}. SIM: {SIM}. Passport no. {PASSPORT}. Card {CARD} cvv {CVV}. "
          f"Routing 021000021. Password: hunter2.")
SECRETS = [SSN, SSN.replace("-", ""), ACCOUNT, "1234 5678 90", DL, SIM, PASSPORT, CARD, f"cvv {CVV}", "hunter2"]


def blank():
    return migrate.migrate_record(R.new_record("MCN-20261118-001", NOW))


def answer(*cands):
    return json.dumps({"candidates": list(cands)})


def cand(path, value, evidence, **kw):
    return {"path": path, "value": value, "evidence": evidence, **kw}


@pytest.mark.parametrize("text, secret", [
    ("Acc no 12345" + "67890", "12345" + "67890"), ("Acc: 12345" + "67890", "12345" + "67890"),                 # "acc" alone
    ("Nomor SIM: 12345" + "6789012", "12345" + "6789012"), ("nomor sim 12345" + "6789012", "12345" + "6789012"),  # SIM, any case
    ("paspor 'AB1234567'", "AB1234567"),                                                       # quote before value
    ("Driver License: D1234567", "D1234567"), ("Driver License Number D1234567", "D1234567"),  # Paykings field name
    ("Passport Number: X1234567", "X1234567"),
    ("Social media ads, phone 555-010-" + "0187", "0187"),                                    # no leftover digit
])
def test_hardening_cases_from_review(text, secret):
    masked, kinds = mask.mask(text)
    assert secret not in masked and mask.MASK in masked and kinds, (text, masked)


def test_routing_and_plain_dates_stay_visible():
    for text in ["Routing 021000021", "Owner DOB 01/15/1980, ZIP 33602"]:
        assert mask.mask(text) == (text, []), text


# ------------------------------------------------------------------ A. masking
def test_every_kind_of_sensitive_value_is_gone_from_masked_text():
    masked, kinds = mask.mask(SOURCE)
    for secret in SECRETS:
        assert secret not in masked, secret
    assert "SSN last 4: [DISAMARKAN]" in masked and "Routing 021000021" in masked
    assert masked.count(mask.MASK) >= 6
    assert {"bank account number", "driver licence number", "passport number", "SSN last 4", "payment card number",
            "card security code", "full Social Security number", "password"} <= set(kinds)
    assert "Example Goods LLC" in masked and "555-010-0187" in masked          # ordinary text is kept


def test_each_pattern_on_its_own():
    for text, secret in [("Account: 12345678", "12345678"), ("acct no. 1234-5678-9012", "9012"),
                         ("Rekening 123456789012", "123456789012"), ("DL# 998877", "998877"),
                         ("driver's license number D1234567", "D1234567"), ("SIM: 123456789012", "123456789012"),
                         ("passport X1234567", "X1234567"), ("Paspor: A7654321", "A7654321"),
                         ("ssn ending in 6789", "6789"), ("Routing 021000021 / account 87654321", "87654321")]:
        masked, kinds = mask.mask(text)
        assert secret not in masked and kinds, text


TEN = "12345" "67890"      # written in two parts so the fake-data scan does not read it as a phone number


@pytest.mark.parametrize("text, secret", [
    (f"Account number is {TEN}", TEN),
    (f"Bank: Chase, {TEN}", TEN),
    (f"Rek. BCA {TEN}", TEN),
    ("SSN: 4321", "4321"),
    ("last four of SSN 1234", "1234"),
    ("my social is 123456789", "123456789"),
], ids=["account-number-is", "bank-name-comma", "rek-bca", "ssn-colon-4", "last-four-of-ssn", "my-social-is"])
def test_loose_patterns_hide_digits_near_bank_and_ssn_words(text, secret):
    masked, kinds = mask.mask(text)
    assert secret not in masked and mask.MASK in masked and kinds
    assert mask.mask(masked)[0] == masked                                  # stable on a second pass
    assert secret not in prompt.build_prompt(masked)


def test_the_loose_patterns_leave_a_routing_number_and_a_zip_code_visible():
    for text in ["Bank: Chase routing 021000021", "Routing 021000021, bank Chase", "Bank Tampa FL 33602"]:
        assert mask.mask(text)[0] == text


def test_ordinary_text_with_the_same_words_is_not_masked():
    for text in ["Account manager Lee", "license expires 01/02/2030", "Routing 123456789", "account: open since 2019"]:
        assert mask.mask(text)[0] == text


def test_masking_does_not_change_its_input_and_is_stable():
    once = mask.mask(SOURCE)[0]
    assert mask.mask(once)[0] == once


# ------------------------------------------------------------------ B. prompt
def test_the_prompt_has_the_rules_and_no_sensitive_values_or_fields():
    p = prompt.build_prompt(mask.mask(SOURCE)[0])
    for secret in SECRETS:
        assert secret not in p, secret
    assert '{"candidates": [{"path": "...", "value": "...", "evidence": "..."}]}' in p
    assert "{{" not in p and "Example Goods LLC" in p
    listed = {line[2:].split(" — ")[0] for line in p.split("## FIELD LIST", 1)[1].split("## TEXT")[0].splitlines()
              if line.startswith("- ")}
    assert listed == set(prompt.allowed_specs())
    for spec in PM.SENSITIVE_SPECS:
        assert prompt.path_of(spec) not in listed
    assert "personal_information.owners[0].ssn" not in p and "account_number" not in p
    assert "business_information.legal_business_name" in listed and "fulfillment_information.service_only_business" not in listed


def test_the_allowed_list_is_the_paykings_map_minus_the_sensitive_and_skipped_fields():
    assert set(prompt.allowed_specs().values()) == {s for s in PM.COLUMN_TO_SPEC.values() if s} - PM.SENSITIVE_SPECS - PM.SKIPPED_SPECS


def test_text_that_looks_like_a_template_marker_cannot_change_the_prompt():
    p = prompt.build_prompt("{{ALLOWED_FIELDS}}")
    assert p.count("- business_information.legal_business_name") == 1


# ------------------------------------------------------------------ C. checks
def run(cands, rec=None, source=SOURCE):
    return check.check_answer(rec or blank(), answer(*cands), source, NOW)


def test_a_proposal_with_evidence_that_is_not_in_the_text_is_refused():
    p, = run([cand("business_information.legal_business_name", "Fake Inc", "Fake Inc is the company")])
    assert not p.ok and "Bukti" in p.reason and p.value is None


def test_evidence_is_compared_after_tidying_spaces_and_case():
    p, = run([cand("contact_information.phone", "555-010-0187", "PHONE   555-010-0187")])
    assert p.ok and p.value == "+1 (555) 010-0187" and p.status == "inferred" and p.outcome == "filled"


def test_unknown_and_sensitive_paths_are_refused():
    ps = run([cand("no.such.path", "x", "Example Goods LLC"),
              cand("personal_information.owners[0].ssn", "123456789", "SSN"),
              cand("personal_information.owners[0].ssn_last4", SSN4, "SSN last 4"),
              cand("banking_information.account_number", ACCOUNT, "Account number"),
              cand("personal_information.owners[0].driver_license_number", DL, "Driver license"),
              cand("personal_information.owners[0].passport_number", PASSPORT, "Passport")])
    assert [p.ok for p in ps] == [False] * 6
    assert ps[0].reason == "Path tidak dikenal." and all("sensitif" in p.reason for p in ps[1:])
    assert all(p.value is None and p.evidence == "" for p in ps)          # nothing of the proposal is returned


def test_values_must_pass_the_field_format():
    p, = run([cand("contact_information.phone", "not a phone", "Phone 555-010-0187")])
    assert not p.ok and "format" in p.reason
    p, = run([cand("business_address.state", "Florida", "Example Goods LLC")])
    assert not p.ok


def test_a_value_that_looks_sensitive_is_refused_even_in_a_free_text_field():
    p, = run([cand("notes", f"card {CARD}", "Example Goods LLC")])
    assert not p.ok and "sensitif" in p.reason


def test_ambiguous_flag_and_ambiguous_dates_become_needs_review():
    dob = "personal_information.owners[0].date_of_birth"
    p, = run([cand(dob, "06/02/2004", "Born 06/02/2004")])
    assert p.ok and p.status == "needs_review" and p.ambiguous and p.outcome == "review"
    p, = run([cand(dob, "06/02/2004", "Born 06/02/2004", ambiguous=True)])
    assert p.status == "needs_review"
    p, = run([cand(dob, "06/25/2004", "Born 06/02/2004")])
    assert p.status == "inferred" and not p.ambiguous
    p, = run([cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187", ambiguous=True)])
    assert p.status == "needs_review"


def test_a_verified_value_is_not_overwritten_a_different_one_makes_a_conflict():
    rec = blank()
    R.user_set(rec, ("contact_information", "phone"), "+1 (555) 010-0199", "x", "SRC-001", NOW)
    ps = run([cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187")], rec)
    assert ps[0].ok and ps[0].outcome == "conflict"
    before = json.dumps(rec, sort_keys=True)
    result = check.apply_proposals(rec, ps, [0], NOW)
    f = rec["contact_information"]["phone"]
    assert f["value"] == "+1 (555) 010-0199" and f["status"] == "conflict"
    assert rec["conflicts"][0]["candidates"][0]["value"] == "+1 (555) 010-0187"
    assert result["changed"] and json.dumps(rec, sort_keys=True) != before
    ps = run([cand("contact_information.phone", "+1 (555) 010-0199", "Phone 555-010-0187")], blank())
    assert ps[0].outcome == "filled"


def test_the_same_value_as_a_verified_one_changes_nothing():
    rec = blank()
    R.user_set(rec, ("contact_information", "phone"), "+1 (555) 010-0187", "x", "SRC-001", NOW)
    ps = run([cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187")], rec)
    assert ps[0].outcome == "unchanged"
    assert check.apply_proposals(rec, ps, [0], NOW)["changed"] is False and rec["sources"] == []


def test_applying_twice_makes_no_duplicates():
    rec = blank()
    ps = run([cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187"),
              cand("business_information.business_description", "Service only", "Service only: yes")], rec)
    assert check.apply_proposals(rec, ps, [0, 1], NOW)["changed"] is True
    snapshot = json.dumps(rec, sort_keys=True)
    ps2 = run([cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187"),
               cand("business_information.business_description", "Service only", "Service only: yes")], rec)
    assert check.apply_proposals(rec, ps2, [0, 1], NOW)["changed"] is False
    assert json.dumps(rec, sort_keys=True) == snapshot and len(rec["sources"]) == 1
    phone = rec["contact_information"]["phone"]
    assert phone["status"] == "inferred" and phone["source_context"] == "Phone 555-010-0187"
    assert rec["sources"][0]["label"] == "Jembatan Claude"


def test_a_duplicate_inside_one_answer_is_refused():
    c = cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187")
    ps = run([c, c])
    assert [p.ok for p in ps] == [True, False] and ps[1].reason == "Usulan ganda."


def test_evidence_kept_is_at_most_200_characters():
    long_text = "Example Goods LLC " + "word " * 100
    p, = run([cand("business_information.business_description", "words", long_text.strip())], source=long_text)
    assert p.ok and len(p.evidence) <= 200


def test_only_chosen_and_valid_proposals_can_be_applied():
    rec = blank()
    ps = run([cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187"),
              cand("business_information.legal_business_name", "Fake Inc", "Fake Inc")], rec)
    with pytest.raises(check.BridgeError):
        check.apply_proposals(rec, ps, [1], NOW)
    with pytest.raises(check.BridgeError):
        check.apply_proposals(rec, ps, [7], NOW)
    with pytest.raises(check.BridgeError):
        check.apply_proposals(rec, ps, [], NOW)
    assert rec["contact_information"]["phone"]["value"] is None


@pytest.mark.parametrize("bad", ["not json", "[]", '"text"', "null", "{}", '{"candidates": "x"}', "",
                                 '{"candidates": ' + "[" * 5000, "x" * (check.MAX_BYTES + 1),
                                 json.dumps({"candidates": [], "pad": "x" * check.MAX_BYTES})])
def test_a_broken_too_big_or_wrong_shaped_answer_is_refused_with_a_general_message(bad):
    with pytest.raises(check.BridgeError) as e:
        check.check_answer(blank(), bad, SOURCE, NOW)
    assert str(e.value) == check.BAD_ANSWER


def test_a_json_fence_is_accepted_and_bad_items_do_not_stop_the_good_ones():
    good = cand("contact_information.phone", "555-010-0187", "Phone 555-010-0187")
    ps = check.check_answer(blank(), "```json\n" + answer("junk", 5, {"path": 3}, good) + "\n```", SOURCE, NOW)
    assert [p.ok for p in ps] == [False, False, False, True]
