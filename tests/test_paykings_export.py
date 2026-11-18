"""The Paykings CSV row writer: columns, blanks, and spreadsheet-formula safety. Fake data only."""
import csv
import io

from merchant_notebook import migrate, paykings_export as PE, paykings_map as PM, record as R

NOW = "2026-11-18T10:00:00Z"


def blank():
    return migrate.migrate_record(R.new_record("MCN-20261118-001", NOW))


def test_columns_are_the_layout_in_order_and_every_one_is_present():
    row = PE.row_for(blank())
    assert list(row) == PE.TEMPLATE_COLUMNS and len(row) == 70
    assert set(PM.COLUMN_TO_SPEC) <= set(row)


def test_cells_that_a_spreadsheet_would_run_as_a_formula_are_defused():
    rec = blank()
    rec["business_information"]["business_description"] = {"value": "=HYPERLINK(\"x\")", "status": "verified",
                                                           "source_context": "t", "source_document": None}
    rec["contact_information"]["phone"] = {"value": "+1 (555) 010-0187", "status": "verified",
                                            "source_context": "t", "source_document": None}
    row = PE.row_for(rec)
    assert row["Business Description"].startswith("'=")
    assert row["Business Phone"] == "+1 (555) 010-0187"                          # a plain phone is not changed


def test_render_roundtrips_through_a_csv_reader():
    text = PE.render_csv([blank(), blank()])
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 2 and list(rows[0]) == PE.TEMPLATE_COLUMNS
