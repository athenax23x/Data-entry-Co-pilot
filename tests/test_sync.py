"""The app, instructions.md and schema.json must describe the same structure."""
import json
import re
from pathlib import Path

from merchant_notebook import fields, normalize, record as R, store
from merchant_notebook.commands import COMMANDS, Session

ROOT = Path(__file__).resolve().parent.parent
INSTRUCTIONS = (ROOT / "instructions.md").read_text(encoding="utf-8")
SCHEMA = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
DEFS = SCHEMA["$defs"]


def section(title):
    m = re.search(rf"^### {re.escape(title)}\n(.*?)(?=^#{{2,3}} )", INSTRUCTIONS, re.S | re.M)
    assert m, title
    return m.group(1)


def table_first_cells(block):
    out = []
    for line in block.splitlines():
        m = re.match(r"^\|\s*(.+?)\s*\|", line)
        if m and not set(m.group(1)) <= set("-: "):
            out.append(m.group(1))
    return out[1:]


def schema_field_paths():
    """Every field path defined by schema.json (owner_id / is_primary_owner are not field objects)."""
    paths = set()
    for key, spec in SCHEMA["properties"].items():
        if key in ("business_entity_type", "ein"):
            paths.add(key)
        elif key == "personal_information":
            for k in ("first_name", "last_name", "date_of_birth", "title", "ownership_percentage"):
                assert k in DEFS["owner"]["properties"]
                paths.add(f"personal_information.owners[].{k}")
        elif spec.get("type") == "object" and "properties" in spec:
            for sub, subspec in spec["properties"].items():
                paths.add(f"{key}.items[]" if sub == "items" else f"{key}.{sub}")
    return paths


def test_the_nine_commands_are_exactly_the_ones_in_instructions():
    rows = table_first_cells(section("Commands"))
    docs = [re.match(r"`([A-Z ]+?)(?: [\[<].*)?`$", r).group(1) for r in rows]
    assert docs == list(COMMANDS) and len(docs) == 9
    assert all(hasattr(Session, "cmd_" + c.lower().replace(" ", "_")) for c in COMMANDS)


def test_app_fields_equal_schema_fields():
    assert set(fields.FIELD_SPECS) == schema_field_paths()


def test_instructions_fields_reference_equals_schema_fields():
    doc = {c.strip("`") for c in table_first_cells(section("Fields Reference"))}
    doc -= {"personal_information.owners[].owner_id", "personal_information.owners[].is_primary_owner"}
    assert doc == schema_field_paths()


def test_entity_types_statuses_and_record_statuses_match_the_schema():
    entity_enum = next(s["properties"]["value"]["enum"] for s in DEFS["entityTypeField"]["allOf"]
                       if "properties" in s)
    assert list(normalize.ENTITY_VALUES) == [v for v in entity_enum if v is not None]
    assert list(R.STATUSES) == DEFS["status"]["enum"]
    doc_entities = [c.strip("`") for c in table_first_cells(section("Entity Type Values"))]
    assert doc_entities == [v for v in entity_enum if v is not None]
    doc_statuses = [c.strip("`") for c in table_first_cells(section("Field Statuses"))]
    assert doc_statuses == DEFS["status"]["enum"]


def test_a_new_record_has_exactly_the_schema_top_level_keys():
    rec = R.new_record("MCN-20261117-001", "2026-11-17T14:30:00Z")
    assert set(rec) == set(SCHEMA["properties"]) - {"custom_fields"}
    assert set(SCHEMA["required"]) == set(rec)
    for sec in ("business_information", "business_address", "contact_information", "processing_information"):
        assert set(rec[sec]) == set(SCHEMA["properties"][sec]["properties"]) == set(SCHEMA["properties"][sec]["required"])
    assert set(rec["personal_information"]["owners"][0]) == set(DEFS["owner"]["required"])


def field_objects(root):
    """Yield every field object in a record (history entries are not field objects)."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if {"value", "status"} <= set(node) and "replaced_at" not in node:
                yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def test_field_objects_use_only_the_schema_keys(session):
    session.execute("NEW MERCHANT name: Alex Sample; alex@example.com")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    session.execute("UPDATE FIELD phone = 555.010.0199")
    allowed = set(DEFS["field"]["properties"])
    nodes = list(field_objects(session.records[session.active]))
    assert nodes and all(set(n) <= allowed for n in nodes)
    assert any("history" in n for n in nodes)
    assert store.validate_record(session.records[session.active]) == []


def test_every_status_the_app_can_produce_is_allowed_by_the_schema(session):
    session.execute("NEW MERCHANT Alex Sample, alex@example.com, sole proprietor LLC, 123456789")
    session.execute("UPDATE FIELD city = Tampa")
    session.execute("UPDATE FIELD phone = 555.010.0187")
    session.execute("ADD CONTEXT 555-010-0199")
    seen = {n["status"] for n in field_objects(session.records[session.active])}
    assert seen <= set(DEFS["status"]["enum"])
    assert seen == set(DEFS["status"]["enum"])
