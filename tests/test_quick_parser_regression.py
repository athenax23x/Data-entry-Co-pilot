"""Regression: the Quick Parser section (Mode 1) must stay exactly the original 11-column prompt.

If you change Quick Parser on purpose, update EXPECTED_SHA256 in the same commit.
"""
import hashlib
import re
from pathlib import Path

INSTRUCTIONS = (Path(__file__).resolve().parent.parent / "instructions.md").read_text(encoding="utf-8")

EXPECTED_COLUMNS = ["First Name", "Last Name", "Business Name", "Street Address", "City", "State", "ZIP",
                    "Email", "Phone", "EIN / Notes", "Status"]
# sha256 of the committed Quick Parser text (from "## Parsing & Auto-Mapping Rules" to the end of its example)
EXPECTED_SHA256 = "440b20bddae12cd3024a0b6bfd7a21edd091c5a9b82f943460802edcaf33c9ec"


def quick_parser_block() -> str:
    start = INSTRUCTIONS.index("## Parsing & Auto-Mapping Rules\n")
    end = INSTRUCTIONS.index("\n---\n\n## Mode 2: Merchant Notebook")
    return INSTRUCTIONS[start:end]


def cells(line: str):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def test_quick_parser_text_is_byte_identical_to_the_committed_version():
    assert hashlib.sha256(quick_parser_block().encode("utf-8")).hexdigest() == EXPECTED_SHA256


def test_quick_parser_outputs_exactly_the_eleven_columns_in_order():
    block = quick_parser_block()
    headers = [cells(l) for l in block.splitlines() if l.startswith("| First Name |")]
    assert len(headers) == 2                                   # the Output Format table and the example table
    for h in headers:
        assert h == EXPECTED_COLUMNS


def test_every_example_row_has_eleven_cells():
    rows = [cells(l) for l in quick_parser_block().splitlines()
            if l.startswith("|") and not l.startswith("|---")]
    assert rows and all(len(r) == 11 for r in rows)


def test_quick_parser_keeps_its_rules():
    block = quick_parser_block()
    assert "mark that cell `[MISSING]`" in block
    assert "put each entry in its own row" in block
    assert "Output **only** a copy-paste-ready Markdown table" in block
    assert re.search(r"\+1 \(XXX\) XXX-XXXX", block)


def test_quick_parser_knows_nothing_about_the_notebook():
    block = quick_parser_block()
    assert "schema.json" not in block and "Notebook" not in block and "merchant_id" not in block
