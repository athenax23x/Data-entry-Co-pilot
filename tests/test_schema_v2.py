"""M0: schema_v2.json, the v1 -> v2 migration, and the Paykings column map. Fake data only."""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from merchant_notebook import migrate, paykings_map as PM, record as R
from merchant_notebook.fields import spec_keys

ROOT = Path(__file__).resolve().parent.parent
V2 = json.loads((ROOT / "schema_v2.json").read_text(encoding="utf-8"))
LAYOUT = json.loads((ROOT / "preview_tool" / "paykings_layout.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((ROOT / "tests" / "fixtures" / "sample_record.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(V2, format_checker=jsonschema.FormatChecker())


def problems(rec):
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in VALIDATOR.iter_errors(rec)]


def blank_v1():
    return R.new_record("MCN-20261118-001", "2026-11-18T10:00:00Z")


def test_schema_v2_is_itself_valid():
    jsonschema.Draft202012Validator.check_schema(V2)
    assert V2["properties"]["schema_version"]["const"] == 2


def test_blank_and_sample_v1_records_migrate_to_valid_v2():
    assert problems(migrate.migrate_record(blank_v1())) == []
    assert problems(migrate.migrate_record(SAMPLE)) == []


def test_v1_records_are_not_valid_v2_until_migrated():
    assert problems(blank_v1())


def test_migration_does_not_modify_its_input_and_is_idempotent():
    before = copy.deepcopy(SAMPLE)
    once = migrate.migrate_record(SAMPLE)
    assert SAMPLE == before
    assert migrate.migrate_record(once) == once


def test_migration_keeps_every_existing_value_status_source_and_history():
    out = migrate.migrate_record(SAMPLE)

    def walk(a, b):
        if isinstance(a, dict):
            for k, v in a.items():
                if k == "schema_version":
                    continue
                assert k in b, k
                walk(v, b[k])
        elif isinstance(a, list):
            assert len(a) == len(b)
            for x, y in zip(a, b):
                walk(x, y)
        else:
            assert a == b
    walk(SAMPLE, out)


def test_migration_adds_only_empty_missing_fields():
    out = migrate.migrate_record(SAMPLE)
    for spec in ("business_address.suite", "banking_information.account_number", "tax_id_type", "notes",
                 "personal_information.owners[].ssn", "personal_information.owners[].driver_license_number"):
        f = R.get_field(out, spec_keys(spec))
        assert f["value"] is None and f["status"] == "missing"


def test_unknown_schema_version_is_refused():
    for bad in (0, 3, None):
        rec = blank_v1()
        rec["schema_version"] = bad
        with pytest.raises(migrate.MigrationError):
            migrate.migrate_record(rec)


def test_every_paykings_column_has_a_home_and_nothing_extra_is_mapped():
    layout_cols = {c for step in LAYOUT["steps"] for c in step["columns"]}
    assert set(PM.COLUMN_TO_SPEC) == layout_cols
    assert len(layout_cols) == 68                      # 68 form columns + merchant_id + Status = 70 CSV columns
    assert set(PM.RECORD_COLUMNS) == {LAYOUT["id_column"], LAYOUT["status_column"]}


def test_every_mapped_path_exists_in_a_blank_v2_record():
    rec = migrate.migrate_record(blank_v1())
    for col, spec in PM.COLUMN_TO_SPEC.items():
        f = R.get_field(rec, spec_keys(spec))
        assert set(f) >= {"value", "status", "source_context", "source_document"}, col


def test_no_two_columns_share_a_field():
    specs = list(PM.COLUMN_TO_SPEC.values())
    assert len(specs) == len(set(specs))


def test_sensitive_columns_agree_with_the_layout_and_the_schema_annotations():
    mapped = {PM.COLUMN_TO_SPEC[c] for c in LAYOUT["sensitive_columns"]}
    assert mapped <= PM.SENSITIVE_SPECS
    annotated = set()

    def find(node, path):
        if isinstance(node, dict):
            if node.get("x-sensitive"):
                annotated.add(tuple(path))
            for k, v in node.items():
                find(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                find(v, path + [i])
    find(V2, [])
    names = {p[-1] for p in annotated}   # path ends at the property name
    assert names == {"ssn", "driver_license_number", "passport_number", "account_number"}


@pytest.mark.parametrize("path,value,ok", [
    (("personal_information", "owners", 0, "ssn"), "123456789", True),
    (("personal_information", "owners", 0, "ssn"), "123-45-6789", False),
    (("banking_information", "account_number"), "12345678", True),
    (("banking_information", "account_number"), "12ab", False),
    (("fulfillment_information", "service_only_business"), "Yes", True),
    (("fulfillment_information", "service_only_business"), "Maybe", False),
    (("processing_information", "public_sales_percentage"), 101, False),
    (("personal_information", "owners", 0, "driver_license_expiration"), "01/15/2030", True),
    (("personal_information", "owners", 0, "driver_license_expiration"), "2030-01-15", False),
])
def test_new_fields_validate_their_values(path, value, ok):
    rec = migrate.migrate_record(blank_v1())
    node = R.get_field(rec, path)
    node.update(value=value, status="inferred")
    assert (problems(rec) == []) is ok


def test_v1_schema_and_code_are_untouched():
    v1 = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
    assert v1["properties"]["schema_version"]["const"] == 1
