"""fields.py must know every v2 field. The field list is generated from paykings_map; these tests keep it honest."""
import pytest

from merchant_notebook import fields, migrate, paykings_map as PM, record as R, service as S

NOW = "2026-11-18T10:00:00Z"


def blank_v2():
    return migrate.migrate_record(R.new_record("MCN-20261118-001", NOW))


def test_field_specs_equal_the_paykings_map_plus_the_v1_only_fields():
    expected = set(PM.COLUMN_TO_SPEC.values()) | set(fields._EXTRA_SPECS)
    assert set(fields.FIELD_SPECS) == expected


def test_every_spec_exists_in_a_blank_v2_record_and_resolves_to_it():
    rec = blank_v2()
    for spec in fields.FIELD_SPECS:
        if spec.endswith("items[]"):
            continue
        keys = fields.resolve_target(spec)
        assert keys == fields.spec_keys(spec)
        if spec == PM.OWNER + "title":                        # every owner starts as Owner
            assert R.get_field(rec, keys)["value"] == "Owner", spec
            continue
        assert R.get_field(rec, keys)["status"] == "missing", spec


def test_owner_fields_are_exactly_the_owner_specs():
    owner_specs = {s.split(".")[-1] for s in fields.FIELD_SPECS if s.startswith(PM.OWNER)}
    assert set(fields.OWNER_FIELDS) == owner_specs
    for name in ("email", "street_address", "ssn", "passport_expiration"):
        assert name in fields.OWNER_FIELDS


def test_every_normalizer_name_exists():
    from merchant_notebook.normalize import NORMALIZERS
    assert set(fields.FIELD_SPECS.values()) <= set(NORMALIZERS)


def test_short_names_keep_meaning_the_business_field_and_owner_fields_need_an_index():
    assert fields.resolve_target("state") == ("business_address", "state")
    assert fields.resolve_target("phone") == ("contact_information", "phone")
    assert fields.resolve_target("owners[0].state") == ("personal_information", "owners", 0, "state")
    assert fields.resolve_target("title") == ("personal_information", "owners", 0, "title")   # owner-only name
    assert fields.resolve_target("service_only_business") == ("fulfillment_information", "service_only_business")


def test_new_normalizers():
    from merchant_notebook import normalize as N
    assert N.yes_no(" yes ") == "Yes" and N.yes_no("N") == "No" and N.yes_no("maybe") is None
    assert N.ssn("123-45-6789") == "123456789" and N.ssn("12345") is None
    assert N.account_number("1234 5678") == "12345678" and N.account_number("12") is None
    assert N.expiry_date("12/31/2031") == "12/31/2031" and N.expiry_date("02/30/2031") is None


@pytest.mark.parametrize("field,value,expected", [
    ("fulfillment_information.service_only_business", "yes", "Yes"),
    ("banking_information.bank_name", "Example Bank", "Example Bank"),
    ("banking_information.account_number", "12345678", "12345678"),
    ("owners[0].street_address", "5 Elm St", "5 Elm St"),
    ("owners[0].passport_expiration", "01/02/2032", "01/02/2032"),
    ("processing_information.public_sales_percentage", "40%", 40),
])
def test_update_field_works_for_v2_fields(field, value, expected):
    rec = blank_v2()
    S.set_field(rec, field, value, NOW, lambda: R.add_source(rec, "update_field", NOW))
    assert R.get_field(rec, fields.resolve_target(field))["value"] == expected


def test_status_uses_paths_that_exist_in_v2():
    rec = blank_v2()
    paths = [p for p, _ in R.needed_fields(rec)]
    for p in paths:
        R.get_field(rec, fields.resolve_target(p))
    assert R.compute_record_status(rec) == "Incomplete"
    for _, f in R.needed_fields(rec):
        f.update(value="x", status="verified")
    assert R.compute_record_status(rec) == "Complete"
    R.needed_fields(rec)[0][1]["status"] = "conflict"
    assert R.compute_record_status(rec) == "Needs Review"


# ---------------------------------------------------------------- user decisions (M7)
def test_skipped_columns_stay_in_the_csv_layout_but_are_not_collected():
    from merchant_notebook.bridge import prompt
    assert PM.SKIPPED_COLUMNS <= set(PM.COLUMN_TO_SPEC)                     # still blank CSV columns
    assert not (set(prompt.allowed_specs().values()) & PM.SKIPPED_SPECS)    # Claude is not asked for them
    assert PM.SKIPPED_SPECS and "fulfillment_information.inventory_storage" in PM.SKIPPED_SPECS


def test_tax_id_type_accepts_only_ein_or_ssn():
    norm = fields.normalizer_for("tax_id_type")
    assert norm("ein") == "EIN" and norm(" SSN ") == "SSN" and norm("TIN") is None


def test_every_new_owner_is_titled_owner():
    rec = blank_v2()
    assert rec["personal_information"]["owners"][0]["title"]["value"] == "Owner"
