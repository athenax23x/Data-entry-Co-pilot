"""tests/fixtures: clearly fake data only, not hidden by .gitignore, and still in sync with the app."""
import shutil
import subprocess
from pathlib import Path

import pytest

import fake_data_scan as S
from merchant_notebook import csv_export, store

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------- the scanner itself
@pytest.mark.parametrize("name,body,needle", [
    ("bad.py", 'EMAIL = "jane.doe@gmail.com"\n', "email outside"),
    ("bad.json", '{"phone": "(415) 867-5309"}\n', "phone number outside"),
    ("bad.txt", "ssn 123-45-6789\n", "Social Security number pattern"),
    ("bad.csv", "id,card\n1,4111 1111 1111 1111\n", "card-number pattern"),
    ("README.md", "Contact: owner@company.io\n", "email outside"),
    ("bad2.json", '{"ein": "47-1234567"}\n', "EIN that is not a known fake"),
    ("bad3.txt", "routing 021000021\n", "9-digit number that is not a known fake"),
])
def test_the_scanner_flags_real_looking_data_in_every_fixture_file_type(tmp_path, name, body, needle):
    folder = tmp_path / "fixtures"
    folder.mkdir()
    (folder / name).write_text(body, encoding="utf-8")
    found = S.scan_fixture_folder(folder)
    assert list(found) == [str(folder / name)]
    assert any(needle in p for p in found[str(folder / name)]), found


def test_the_scanner_reaches_files_in_subfolders_and_rejects_binary_files(tmp_path):
    folder = tmp_path / "fixtures"
    (folder / "deep" / "er").mkdir(parents=True)
    (folder / "deep" / "er" / "x.txt").write_text("a@gmail.com", encoding="utf-8")
    (folder / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    found = S.scan_fixture_folder(folder)
    assert set(found) == {str(folder / "deep" / "er" / "x.txt"), str(folder / "blob.bin")}


def test_the_scanner_accepts_obviously_fake_data(tmp_path):
    folder = tmp_path / "fixtures"
    folder.mkdir()
    (folder / "ok.txt").write_text("alex@example.com (813) 555-0144 +1 (555) 010-0187 12-3456789 123456789 "
                                   "MCN-20261117-001 2026-11-17T14:30:00Z 01/15/1980 ssn_last4 6789\n",
                                   encoding="utf-8")
    assert S.scan_fixture_folder(folder) == {}


# ---------------------------------------------------------------- the real fixtures
def test_fixtures_folder_has_every_file_type_the_scanner_must_cover():
    suffixes = {p.suffix.lower() for p in S.fixture_files(FIXTURES)}
    assert {".json", ".csv", ".txt", ".md"} <= suffixes
    assert (FIXTURES / "README.md").is_file()


def test_every_file_in_tests_fixtures_contains_only_clearly_fake_data():
    assert S.scan_fixture_folder(FIXTURES) == {}


def test_test_fixtures_py_itself_only_contains_the_deliberate_bad_samples():
    """test_fixtures.py is excluded from the code scan because it holds bad samples on purpose. Pin exactly which
    non-fake values it may contain, so nothing else can hide in it."""
    body = (ROOT / "tests" / "test_fixtures.py").read_text(encoding="utf-8")
    emails = {m.group(0) for m in S._EMAIL.finditer(body) if m.group(1).lower() not in S.ALLOWED_DOMAINS}
    assert emails == {"jane.doe@gmail.com", "a@gmail.com", "owner@company.io"}
    phones = {m.group(0) for m in S._PHONE.finditer(body) if "555" not in (m.group(1), m.group(2))}
    assert phones == {"(415) 867-5309"}


def test_sample_record_is_a_valid_record_and_the_csv_is_its_exact_export():
    rec, _ = store.load_record(str(FIXTURES / "sample_record.json"), FIXTURES)        # validated on load
    expected = (FIXTURES / "sample_export.csv").read_bytes().decode("utf-8")
    assert csv_export.render_csv([rec]) == expected
    header = expected.splitlines()[0].split(",")
    assert header == csv_export.FIXED_COLUMNS                      # fixture follows the app's current columns
    assert rec["conflicts"] and rec["conflicts"][0]["current_status"] == "verified"


def test_every_sample_input_line_becomes_a_schema_valid_record(session):
    lines = (FIXTURES / "sample_input.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    entity = {}
    for line in lines:
        out = session.execute("NEW MERCHANT " + line)
        assert "Created MCN-" in out
        rec = session.records[session.active]
        assert store.validate_record(rec) == []
        entity[line.split()[0].lower()] = rec["business_entity_type"]["value"]
    assert entity == {"john": "llc", "maria": None, "dave": "sole_proprietorship", "priya": "sole_proprietorship"}


# ---------------------------------------------------------------- .gitignore behaviour
def ignored(path: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    assert r.returncode in (0, 1), f"git check-ignore failed for {path}"
    return r.returncode == 0


needs_git = pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(),
                               reason="needs a git checkout")


@needs_git
@pytest.mark.parametrize("path", [
    "tests/fixtures/sample_export.csv", "tests/fixtures/new_fixture.csv",
    "tests/fixtures/sample_record.json", "tests/fixtures/sample_input.txt", "tests/fixtures/README.md",
    "tests/fixtures/fake_inputs.py", "schema.json", "instructions.md",
])
def test_fixtures_and_project_files_are_not_ignored(path):
    assert not ignored(path), path


@needs_git
@pytest.mark.parametrize("path", [
    "export.csv", "tests/other.csv", "merchant_data/exports/merchants_20261117-150000.csv",
    "tests/fixtures/sub/nested.csv",                      # only tests/fixtures/*.csv is re-included
    "a.merchants.json", "tests/fixtures/a.merchants.json", "merchant_data/MCN-20261117-001.json",
    "data/a.json", "src/data/x.json", "tests/fixtures/data/a.csv", "tests/fixtures/data/a.json",
    "merchants/x.json",
])
def test_real_data_locations_stay_ignored(path):
    assert ignored(path), path
