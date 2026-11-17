"""The CSV preview tool: one card per row, safe escaping, empty columns hidden, read-only."""
import csv
import re
import subprocess
import sys
from pathlib import Path

import pytest

from preview_tool import preview_csv

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "sample_export.csv"


def cards(page: str) -> list:
    return re.findall(r'<article class="card">', page)


def make_csv(path: Path, rows: list) -> Path:
    fields = list(rows[0])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


@pytest.fixture
def page(tmp_path):
    out = tmp_path / "out.html"
    assert preview_csv.main([str(FIXTURE), "--out", str(out)]) == 0
    return out.read_text(encoding="utf-8")


def test_html_is_created_with_one_card_for_the_fixture_row(page):
    assert page.startswith("<!DOCTYPE html>")
    assert len(cards(page)) == 1
    assert "Alex Sample" in page and "MCN-20261117-001" in page and "Tampa" in page


def test_every_row_becomes_one_card(tmp_path):
    rows = [{"merchant_id": f"M{i}", "First Name": f"Name{i}", "Status": "Complete"} for i in range(5)]
    out = tmp_path / "many.html"
    assert preview_csv.main([str(make_csv(tmp_path / "many.csv", rows)), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert len(cards(text)) == 5
    assert "5 merchants" in text


def test_script_text_is_escaped(tmp_path):
    evil = '<script>alert(1)</script>'
    rows = [{"merchant_id": "M1", "First Name": evil, "Business Name": '"><img src=x onerror=alert(1)>',
             "Status": "<b>x</b>"}]
    out = tmp_path / "evil.html"
    preview_csv.main([str(make_csv(tmp_path / "evil.csv", rows)), "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    assert "<script" not in text.lower()
    assert "<img" not in text.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text


def test_empty_columns_are_not_shown(page):
    assert "Website" not in page
    assert "Business description" not in page
    assert "Routing number" in page                    # a filled extra column does appear


def test_status_columns_become_badges_not_rows(page):
    assert "first_name_status" not in page and "ein_status" not in page
    assert 'class="badge b-inferred"' in page and 'class="badge b-conflict"' in page
    assert "Needs Review" in page


def test_missing_value_is_highlighted(page):
    assert 'class="value missing-value">[MISSING]' in page


def test_page_has_no_external_resources(page):
    lowered = page.lower()
    for token in ("http://", "https://", "<script", "<link", "src=", "@import", "url("):
        assert token not in lowered


def test_default_output_goes_to_merchant_data_previews(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert preview_csv.main([str(FIXTURE)]) == 0
    assert (tmp_path / "merchant_data" / "previews" / "sample_export.html").is_file()


def test_input_is_not_modified_and_bad_output_is_refused(tmp_path):
    csv_copy = tmp_path / "in.csv"
    csv_copy.write_bytes(FIXTURE.read_bytes())
    before = csv_copy.read_bytes()
    assert preview_csv.main([str(csv_copy), "--out", str(csv_copy)]) == 2
    assert preview_csv.main([str(csv_copy), "--out", str(tmp_path / "x.json")]) == 2
    assert csv_copy.read_bytes() == before
    assert preview_csv.main([str(tmp_path / "missing.csv")]) == 2


def test_module_entry_point(tmp_path):
    out = tmp_path / "m.html"
    r = subprocess.run([sys.executable, "-m", "preview_tool", str(FIXTURE), "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.is_file()
