"""Records are validated against schema.json (with format checking switched on)."""
import copy
import json
import re
from pathlib import Path

import pytest

from merchant_notebook import record as R, store

ROOT = Path(__file__).resolve().parent.parent
INSTRUCTIONS = (ROOT / "instructions.md").read_text(encoding="utf-8")
EXAMPLE = json.loads(re.search(r"### Example Record.*?```json\n(.*?)```", INSTRUCTIONS, re.S).group(1))


def fresh():
    return R.new_record("MCN-20261117-001", "2026-11-17T14:30:00Z")


def test_a_new_record_is_valid():
    assert store.validate_record(fresh()) == []


def test_the_example_record_in_instructions_is_valid():
    assert store.validate_record(EXAMPLE) == []


def _mutate(path, **changes):
    rec = copy.deepcopy(EXAMPLE)
    node = rec
    for p in path:
        node = node[p]
    node.update(changes)
    return rec


@pytest.mark.parametrize("name,rec,needle", [
    ("bad email", _mutate(["contact_information", "email"], value="not-an-email", status="inferred"), "'email'"),
    ("bad date", _mutate(["business_information", "business_start_date"], value="2026-13-45", status="inferred"),
     "'date'"),
    ("bad uri", _mutate(["business_information", "website"], value="not a uri", status="inferred"), "'uri'"),
    ("bad date-time", _mutate([], created_at="yesterday"), "'date-time'"),
    ("unknown status", _mutate(["ein"], status="confirmed"), "is not one of"),
    ("missing but has a value", _mutate(["ein"], value="12-3456789"), "is not of type 'null'"),
    ("verified but null", _mutate(["ein"], status="verified"), "should not be valid under {'type': 'null'}"),
    ("entity type not in the list", _mutate(["business_entity_type"], value="Sole Proprietorship"), "is not one of"),
    ("bad phone format", _mutate(["contact_information", "phone"], value="5550100187"), "does not match"),
    ("percentage over 100", _mutate(["processing_information", "keyed_percentage"], value=101, status="inferred"),
     "maximum"),
    ("extra top-level key", _mutate([], notes="free text"), "Additional properties"),
    ("field without source_document", None, "source_document"),
])
def test_invalid_records_are_rejected(name, rec, needle):
    if rec is None:
        rec = copy.deepcopy(EXAMPLE)
        del rec["ein"]["source_document"]
    problems = store.validate_record(rec)
    assert problems, f"{name}: the record was accepted"
    assert any(needle in p for p in problems), (name, problems)


def test_each_format_is_rejected_for_the_format_and_not_some_other_rule():
    for path, value, fmt in ((["contact_information", "email"], "not-an-email", "email"),
                             (["business_information", "business_start_date"], "2026-13-45", "date"),
                             (["business_information", "website"], "not a uri", "uri")):
        rec = _mutate(path, value=value, status="inferred")
        problems = store.validate_record(rec)
        assert len(problems) == 1 and f"is not a '{fmt}'" in problems[0], problems


def test_a_missing_required_key_is_rejected():
    rec = fresh()
    del rec["sources"]
    assert any("'sources' is a required property" in p for p in store.validate_record(rec))


def test_valid_values_of_each_format_are_accepted():
    rec = fresh()
    rec["contact_information"]["email"].update(value="owner@example.com", status="inferred")
    rec["business_information"]["business_start_date"].update(value="2020-02-29", status="inferred")
    rec["business_information"]["website"].update(value="https://www.example.com/path", status="inferred")
    assert store.validate_record(rec) == []
