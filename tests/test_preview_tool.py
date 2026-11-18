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
    assert 'class="badge b-conflict"' in page               # warnings that matter stay visible
    assert 'class="badge b-inferred"' not in page and ">inferred<" not in page   # hidden to keep copying clean
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


VIEWER = ROOT / "preview_tool" / "viewer.html"


def test_standalone_viewer_is_self_contained_and_never_builds_markup_from_data():
    text = VIEWER.read_text(encoding="utf-8")
    for token in ("innerHTML", "insertAdjacentHTML", "document.write", "eval(", "http://", "https://",
                  "<link", "src=", "@import", "url(", "fetch(", "XMLHttpRequest"):
        assert token not in text
    assert "default-src 'none'" in text           # the page cannot make network requests


def test_module_entry_point(tmp_path):
    out = tmp_path / "m.html"
    r = subprocess.run([sys.executable, "-m", "preview_tool", str(FIXTURE), "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.is_file()


# ---------------------------------------------------------------- Paykings form layout
PK_FIXTURE = ROOT / "tests" / "fixtures" / "sample_paykings.csv"


def render(tmp_path, csv_path):
    out = tmp_path / "pk.html"
    assert preview_csv.main([str(csv_path), "--out", str(out)]) == 0
    return out.read_text(encoding="utf-8")


def test_viewer_embeds_the_same_layout_as_the_python_tool():
    import json
    text = VIEWER.read_text(encoding="utf-8")
    block = re.search(r'<script type="application/json" id="paykings-layout">(.*?)</script>', text, re.S).group(1)
    assert json.loads(block) == preview_csv.PAYKINGS


def test_paykings_fixture_uses_the_template_columns():
    with open(PK_FIXTURE, encoding="utf-8", newline="") as fh:
        assert next(csv.reader(fh)) == preview_csv.TEMPLATE_COLUMNS
    assert len(preview_csv.TEMPLATE_COLUMNS) == len(set(preview_csv.TEMPLATE_COLUMNS))


def test_paykings_card_follows_the_form_steps(tmp_path):
    page = render(tmp_path, PK_FIXTURE)
    assert len(cards(page)) == 1
    titles = re.findall(r"<h3>([^<]*)</h3>", page)
    assert titles == [s["title"] for s in preview_csv.PAYKINGS["steps"]]
    assert "<h2>Example Goods LLC</h2>" in page
    assert "form: 15/01/1980" in page                     # date hint for the dd/mm/yyyy picker
    assert "•••• 5678 (show)" in page                       # bank account masked until clicked
    assert 'class="row warn"' not in page                  # fixture totals are valid
    assert "Passport Number" not in page                   # empty columns stay hidden


def test_paykings_checks_totals_and_website(tmp_path):
    row = {c: "" for c in preview_csv.TEMPLATE_COLUMNS}
    row.update({"Legal Business Name": "<script>x</script>", "Public Sales %": "80", "B2B Sales %": "10",
                "Card Swipe %": "abc", "Card Internet %": "50", "Website": "[MISSING]"})
    page = render(tmp_path, make_csv(tmp_path / "pk.csv", [row]))
    assert "Public + B2B = 90% (must total 100%)" in page
    assert "Swipe + Keyed + Internet: a value is not a number" in page
    assert "Website is required when Card Internet % is above 0" in page
    assert "National + International" not in page          # untouched group is not checked
    assert "<script" not in page and "&lt;script&gt;x&lt;/script&gt;" in page
