"""Saving happens only on request, and a failed save is always reported as a failure."""
import errno
import json
import stat

import pytest

from conftest import active
from merchant_notebook import store


def test_nothing_is_written_unless_a_save_command_runs(session, data_dir, tmp_path):
    session.execute("NEW MERCHANT Alex Sample, sole proprietor, alex@example.com")
    session.execute("ADD CONTEXT phone 555.010.0187")
    session.execute("UPDATE FIELD city = Tampa")
    session.execute("SHOW MERCHANT")
    session.execute("SHOW MISSING FIELDS")
    session.execute("NEW MERCHANT second one")
    assert not data_dir.exists()
    assert list(tmp_path.iterdir()) == []
    assert session.dirty == set(session.records)          # everything is still unsaved


def test_save_writes_exactly_one_valid_file_for_the_requested_merchant(session, data_dir):
    session.execute("NEW MERCHANT Alex Sample, alex@example.com")
    first = session.active
    session.execute("NEW MERCHANT other merchant")
    out = session.execute(f"SAVE MERCHANT {first}")
    files = sorted(p.name for p in data_dir.iterdir())
    assert files == [f"{first}.json"]
    assert out.startswith(f"Saved {first} to ") and str(data_dir / f"{first}.json") in out
    saved = json.loads((data_dir / f"{first}.json").read_text(encoding="utf-8"))
    assert saved == session.records[first]
    assert store.validate_record(saved) == []
    assert stat.S_IMODE((data_dir / f"{first}.json").stat().st_mode) == 0o600
    assert first not in session.dirty and session.active in session.dirty


def test_overwrite_needs_confirmation(make_session, data_dir):
    asked = []
    s = make_session(confirm=lambda q: asked.append(q) or False)
    s.execute("NEW MERCHANT x")
    s.execute("SAVE MERCHANT")
    path = data_dir / f"{s.active}.json"
    before = path.read_bytes()
    s.execute("UPDATE FIELD city = Tampa")
    out = s.execute("SAVE MERCHANT")
    assert asked and out.startswith("NOT saved") and path.read_bytes() == before
    s.confirm = lambda q: True
    assert s.execute("SAVE MERCHANT").startswith("Saved")
    assert json.loads(path.read_text())["business_address"]["city"]["value"] == "Tampa"


def test_failed_save_is_reported_as_failure_when_the_folder_cannot_be_created(make_session, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder")
    s = make_session(directory=blocker / "merchant_data")
    s.execute("NEW MERCHANT x")
    out = s.execute("SAVE MERCHANT")
    assert out.startswith("NOT saved")
    assert "Saved" not in out
    assert s.active in s.dirty                             # still unsaved, and the app knows it
    assert list(tmp_path.iterdir()) == [blocker]


def test_failed_save_is_reported_when_the_final_rename_fails(session, data_dir, monkeypatch):
    session.execute("NEW MERCHANT x")

    def boom(*a, **k):
        raise OSError(errno.EIO, "disk exploded")

    monkeypatch.setattr(store.os, "replace", boom)
    out = session.execute("SAVE MERCHANT")
    assert out.startswith("NOT saved") and "disk exploded" in out and "Saved" not in out
    assert list(data_dir.iterdir()) == []                   # no final file and no leftover temp file
    assert session.active in session.dirty


def test_save_refuses_a_record_that_breaks_the_schema(session, data_dir):
    session.execute("NEW MERCHANT x")
    active(session)["business_address"]["zip"].update(value="not-a-zip", status="inferred")
    out = session.execute("SAVE MERCHANT")
    assert out.startswith("NOT saved") and "schema.json" in out and "zip" in out
    assert not data_dir.exists() or list(data_dir.iterdir()) == []


def test_save_load_round_trip_is_exact(make_session, data_dir):
    s = make_session(confirm=lambda q: True)
    s.execute("NEW MERCHANT Alex Sample, sole proprietor, alex@example.com")
    s.execute("UPDATE FIELD phone = 555.010.0187")
    s.execute("ADD CONTEXT 555-010-0199")
    original = json.loads(json.dumps(active(s)))
    mid = s.active
    s.execute("SAVE MERCHANT")
    assert s.execute("CLEAR SESSION").startswith("Session cleared")
    assert s.records == {} and s.active is None
    out = s.execute(f"LOAD MERCHANT {mid}")
    assert out.startswith(f"Loaded {mid}") and s.records[mid] == original


def test_clear_session_asks_first_and_never_deletes_files(make_session, data_dir):
    asked = []
    s = make_session(confirm=lambda q: asked.append(q) or False)
    s.execute("NEW MERCHANT x")
    s.execute("SAVE MERCHANT")
    s.execute("NEW MERCHANT y")                              # unsaved
    assert s.execute("CLEAR SESSION") == "Session not cleared."
    assert asked and s.records
    s.confirm = lambda q: True
    out = s.execute("CLEAR SESSION")
    assert "No files were deleted" in out and len(list(data_dir.glob("*.json"))) == 1


def test_load_rejects_invalid_files_and_adds_nothing(session, data_dir, tmp_path):
    session.execute("NEW MERCHANT x")
    session.execute("SAVE MERCHANT")
    path = data_dir / f"{session.active}.json"
    bad = json.loads(path.read_text())
    bad["contact_information"]["email"].update(value="not-an-email", status="inferred")
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(bad))
    not_json = tmp_path / "nope.json"
    not_json.write_text("{ this is not json")
    session.execute("CLEAR SESSION")
    for target in (broken, not_json, tmp_path / "missing.json"):
        out = session.execute(f"LOAD MERCHANT {target}")
        assert out.startswith("NOT loaded"), out
    assert session.records == {} and session.active is None


def test_failed_export_is_reported_as_failure(make_session, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    s = make_session(directory=blocker / "md")
    s.execute("NEW MERCHANT x")
    out = s.execute("EXPORT CSV")
    assert out.startswith("NOT exported") and "Exported" not in out


def test_merchant_id_cannot_escape_the_data_folder(data_dir):
    with pytest.raises(store.StoreError):
        store.record_path(data_dir, "../../etc/passwd")
