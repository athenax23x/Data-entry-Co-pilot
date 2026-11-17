"""CSV export: flat view, RFC 4180, owners and ownership percentages flattened."""
import csv
import io
import re
from pathlib import Path

from conftest import active
from merchant_notebook import csv_export as C, record as R

INSTRUCTIONS = (Path(__file__).resolve().parent.parent / "instructions.md").read_text(encoding="utf-8")


def parse(text):
    rows = list(csv.reader(io.StringIO(text, newline="")))
    return rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]


def two_owner_merchant(s):
    s.execute("NEW MERCHANT name: Alex Sample; sole proprietor; dba Sample Mobile Detailing; "
              "88 Pine Rd Tampa FL 33602; alex@example.com; 813 555 0144; ein: 12-3456789; routing: 123456789; "
              "ownership: 60%; products: car wash, interior detailing")
    s.execute("UPDATE FIELD owners[1].first_name = Pat")
    s.execute("UPDATE FIELD owners[1].last_name = Example")
    s.execute("UPDATE FIELD owners[1].ownership_percentage = 40")
    s.execute("UPDATE FIELD custom_fields.loyalty_tier = gold")
    return active(s)


def test_original_eleven_columns_come_first_in_order():
    assert C.FIXED_COLUMNS[0] == "merchant_id"
    assert C.FIXED_COLUMNS[1:12] == ["First Name", "Last Name", "Business Name", "Street Address", "City", "State",
                                     "ZIP", "Email", "Phone", "EIN / Notes", "Status"]
    assert len(C.FIXED_COLUMNS) == len(set(C.FIXED_COLUMNS))


def test_nested_record_is_flattened_including_owners_and_percentages(session):
    two_owner_merchant(session)
    header, (row,) = parse(C.render_csv([active(session)]))
    assert (row["First Name"], row["Last Name"]) == ("Alex", "Sample")      # primary owner
    assert row["ownership_percentage"] == "60"
    assert row["other_owners"] == "Pat Example (40%)"                       # every other owner
    assert row["products_and_services_items"] == "car wash; interior detailing"
    assert row["EIN / Notes"] == "EIN: 12-3456789; Routing: 123456789"
    assert row["routing_number"] == "123456789"
    assert row["Business Entity Type"] == "sole_proprietorship"
    assert row["custom.loyalty_tier"] == "gold"
    assert row["Status"] == active(session)["record_status"]


def test_values_with_commas_quotes_and_newlines_survive_a_round_trip(session):
    two_owner_merchant(session)
    session.execute('UPDATE FIELD dba_name = Sample, Mobile "Detailing"')
    rec = active(session)
        value='Line one, "quoted"\nline two', status="inferred", source_context="x", source_document="SRC-001")
    text = C.render_csv([rec])
    assert "\r\n" in text
    _, (row,) = parse(text)
    assert row["DBA Name"] == 'Sample, Mobile "Detailing"'
    assert row["business_description"] == 'Line one, "quoted"\nline two'


def test_required_columns_use_missing_but_notes_stays_blank(session):
    session.execute("NEW MERCHANT Alex Sample")
    _, (row,) = parse(C.render_csv([active(session)]))
    for col in C.REQUIRED_COLUMNS[2:]:
        assert row[col] == "[MISSING]", col
    assert row["EIN / Notes"] == "" and row["website"] == ""
    assert row["Business Entity Type"] == "unknown"


def test_a_conflicted_field_exports_the_kept_value_and_the_conflict_status(session):
    session.execute("NEW MERCHANT x")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    session.execute("ADD CONTEXT 555-010-0199")
    _, (row,) = parse(C.render_csv([active(session)]))
    assert row["Phone"] == "+1 (555) 010-0187" and row["phone_status"] == "conflict"
    assert "0199" not in str(row)


def test_export_covers_only_the_requested_merchants_and_writes_under_exports(session, data_dir):
    session.execute("NEW MERCHANT name: Alex Sample; alex@example.com")
    a = session.active
    session.execute("NEW MERCHANT name: Blake Demo; blake@example.org")
    b = session.active
    out = session.execute("EXPORT CSV")                                     # active merchant only
    (path,) = (data_dir / "exports").glob("merchants_*.csv")
    assert re.fullmatch(r"merchants_\d{8}-\d{6}\.csv", path.name) and str(path) in out
    _, rows = parse(path.read_text(encoding="utf-8"))
    assert [r["merchant_id"] for r in rows] == [b]
    assert "alex@example.com" not in path.read_text(encoding="utf-8")
    session.execute(f"EXPORT CSV {a}")
    session.execute("EXPORT CSV ALL")
    sizes = {p.name: [r["merchant_id"] for r in parse(p.read_text(encoding="utf-8"))[1]]
             for p in (data_dir / "exports").glob("*.csv")}
    assert sorted(len(v) for v in sizes.values()) == [1, 1, 2]


def test_every_csv_column_is_documented_in_instructions():
    section = INSTRUCTIONS.split("### CSV Export Format")[1].split("\n---\n")[0]
    for col in C.FIXED_COLUMNS:
        assert col in section, f"{col} is not described in the CSV Export Format section of instructions.md"
