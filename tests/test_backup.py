"""M6: backups. Fake data only. DPAPI is Windows-only, so a plain-file key provider stands in for it here."""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from merchant_notebook import backup as B, sqlstore as SQ
from merchant_notebook.keys import KEY_BYTES, KeyProvider, KeyUnavailable
from tests.test_sqlstore import ACCOUNT, DL, PASSPORT, SSN, v2_record

T0 = datetime(2026, 11, 18, 10, 0, 0, tzinfo=timezone.utc)
PASS = "correct horse battery"
OTHER = b"OTHER-ACCOUNT:"                                       # marks a key file this "account" cannot open


class PlainFileProvider(KeyProvider):
    """Stand-in for DpapiKeyProvider: the key file holds the raw key, and a file starting with OTHER is 'another account'."""

    def __init__(self, key_file):
        self.key_file = key_file

    def key(self):
        if self.key_file.exists():
            raw = self.key_file.read_bytes()
            if raw.startswith(OTHER):
                raise KeyUnavailable("another account")
            return raw
        key = os.urandom(KEY_BYTES)
        self.install(key)
        return key

    def install(self, key):
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self.key_file.write_bytes(key)


@pytest.fixture(autouse=True)
def fake_dpapi(monkeypatch):
    monkeypatch.setattr(B, "_provider", lambda f: PlainFileProvider(f))


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "merchant_data"
    with SQ.SqliteMerchantStore(d / "merchants.db", PlainFileProvider(d / "mcn.key")) as s:
        s.save(v2_record("MCN-20261118-001", "Example Goods LLC"), None)
        s.save(v2_record("MCN-20261118-002", "Sample Shop LLC"), None)
    return d


def stamp(n):
    return T0 + timedelta(seconds=n)


def load_all(d):
    with SQ.SqliteMerchantStore(d / "merchants.db", PlainFileProvider(d / "mcn.key")) as s:
        return {r["merchant_id"]: s.load(r["merchant_id"])[0] for r in s.list()}


# ---------------------------------------------------------------- create
def test_backup_has_expected_files_and_no_plain_secrets(data):
    b = B.create_backup(data, now=T0)
    assert b.name == "mcn-backup-20261118-100000"
    assert {p.name for p in b.iterdir()} == {"merchants.db", "mcn.key", "manifest.json"}
    raw = (b / "merchants.db").read_bytes()
    for secret in (SSN, ACCOUNT, DL, PASSPORT):
        assert secret.encode() not in raw
    m = json.loads((b / "manifest.json").read_text())
    assert m["merchant_count"] == 2 and m["has_recovery_key"] is False
    text = (b / "manifest.json").read_text()
    assert "Example" not in text and "MCN-" not in text           # no names or ids in the manifest


def test_backup_of_missing_database_is_refused(tmp_path):
    with pytest.raises(B.BackupError, match="Belum ada database"):
        B.create_backup(tmp_path / "empty")


def test_backup_is_consistent_while_a_writer_holds_the_database(data):
    con = sqlite3.connect(data / "merchants.db", isolation_level=None)
    con.execute("BEGIN IMMEDIATE")                               # an uncommitted write in progress
    con.execute("UPDATE merchants SET legal_name='half done'")
    try:
        b = B.create_backup(data, now=T0)                        # reads the committed state, does not fail
    finally:
        con.execute("ROLLBACK")
        con.close()
    assert B.verify_backup(b)["merchants"] == 2
    names = [r[0] for r in sqlite3.connect(b / "merchants.db").execute("SELECT legal_name FROM merchants")]
    assert "half done" not in names


def test_same_second_does_not_overwrite(data):
    a, b = B.create_backup(data, now=T0), B.create_backup(data, now=T0)
    assert a != b and a.exists() and b.exists()


def test_keep_prunes_only_our_oldest_backup_folders(data):
    dest = data / "backups"
    dest.mkdir()
    (dest / "notes.txt").write_text("mine")
    (dest / "mcn-backup-20200101-000000").mkdir()               # looks like ours but has no manifest: untouched
    for i in range(4):
        B.create_backup(data, keep=2, now=stamp(i))
    names = [r["name"] for r in B.list_backups(dest)]
    assert names == ["mcn-backup-20261118-100002", "mcn-backup-20261118-100003"]
    assert (dest / "notes.txt").exists() and (dest / "mcn-backup-20200101-000000").exists()


def test_failed_backup_leaves_no_partial_folder(data, monkeypatch):
    monkeypatch.setattr(B, "_sha256", lambda p: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        B.create_backup(data, now=T0)
    assert list((data / "backups").iterdir()) == []


# ---------------------------------------------------------------- verify
def test_verify_ok_and_with_key(data):
    b = B.create_backup(data, now=T0)
    assert B.verify_backup(b)["decrypt_checked"] is False
    key = PlainFileProvider(data / "mcn.key").key()
    r = B.verify_backup(b, key)
    assert r["decrypt_checked"] is True and r["merchants"] == 2


def test_verify_detects_tampering_and_wrong_key(data):
    b = B.create_backup(data, now=T0)
    with pytest.raises(B.BackupError, match="Kunci tidak bisa membuka"):
        B.verify_backup(b, os.urandom(KEY_BYTES))
    with open(b / "merchants.db", "r+b") as fh:
        fh.seek(2000)
        fh.write(b"\x00\x01\x02")
    with pytest.raises(B.BackupError, match="Checksum"):
        B.verify_backup(b)


def test_verify_rejects_a_folder_that_is_not_a_backup(tmp_path):
    with pytest.raises(B.BackupError, match="bukan folder backup"):
        B.verify_backup(tmp_path)


def test_verify_does_not_modify_the_backup(data):
    b = B.create_backup(data, now=T0)
    before = (b / "merchants.db").read_bytes()
    B.verify_backup(b, PlainFileProvider(data / "mcn.key").key())
    assert (b / "merchants.db").read_bytes() == before and not list(b.glob("*-journal"))


# ---------------------------------------------------------------- restore
def test_restore_same_account_brings_back_the_data_and_keeps_the_old_db(data):
    original = load_all(data)
    b = B.create_backup(data, now=T0)
    with SQ.SqliteMerchantStore(data / "merchants.db", PlainFileProvider(data / "mcn.key")) as s:
        rec, v = s.load("MCN-20261118-001")
        rec["business_information"]["legal_business_name"]["value"] = "Changed After Backup"
        s.save(rec, v)
    r = B.restore_backup(b, data, now=stamp(60), check_app=False)
    assert r["merchants"] == 2 and r["key"] == "keep_current"
    assert load_all(data) == original
    kept = data / r["previous_database"]
    assert kept.exists()
    names = [x[0] for x in sqlite3.connect(kept).execute("SELECT legal_name FROM merchants")]
    assert "Changed After Backup" in names                       # nothing lost: the newer data is still there


def test_restore_refuses_while_the_app_runs(data, monkeypatch):
    b = B.create_backup(data, now=T0)
    monkeypatch.setattr(B, "app_is_running", lambda: True)
    with pytest.raises(B.BackupError, match="sedang berjalan"):
        B.restore_backup(b, data)


def test_restore_on_a_new_account_needs_the_recovery_passphrase(data, tmp_path):
    original = load_all(data)
    b = B.create_backup(data, recovery_passphrase=PASS, now=T0)
    assert (b / "recovery.key").exists()
    new = tmp_path / "new_laptop"
    new.mkdir()
    (new / "mcn.key").write_bytes(OTHER + os.urandom(18))       # a key this account cannot use / does not match
    (b / "mcn.key").write_bytes(OTHER + os.urandom(18))          # the DPAPI copy is useless on the new account
    with pytest.raises(B.BackupError, match="--recovery"):
        B.restore_backup(b, new, check_app=False)
    r = B.restore_backup(b, new, recovery_passphrase=PASS, now=stamp(5), check_app=False)
    assert r["key"] == "install_recovery"
    assert load_all(new) == original
    assert (new / "mcn.key.before-restore-20261118-100005").exists()


def test_wrong_passphrase_changes_nothing(data, tmp_path):
    b = B.create_backup(data, recovery_passphrase=PASS, now=T0)
    new = tmp_path / "other"
    before = (data / "merchants.db").read_bytes()
    with pytest.raises(B.BackupError, match="Frasa pemulihan salah"):
        B.restore_backup(b, data, recovery_passphrase="wrong passphrase!!", check_app=False)
    assert (data / "merchants.db").read_bytes() == before and not list(data.glob("*.before-restore-*"))
    assert not new.exists()


def test_restore_without_any_matching_key_is_refused_and_changes_nothing(data, tmp_path):
    b = B.create_backup(data, now=T0)                            # no recovery key
    new = tmp_path / "fresh"
    new.mkdir()
    (new / "mcn.key").write_bytes(os.urandom(KEY_BYTES))         # a different key
    (b / "mcn.key").write_bytes(OTHER + os.urandom(18))
    with pytest.raises(B.BackupError, match="Tidak ada kunci yang cocok"):
        B.restore_backup(b, new, check_app=False)
    assert not (new / "merchants.db").exists()


def test_restore_removes_a_stale_journal(data):
    b = B.create_backup(data, now=T0)
    (data / "merchants.db-journal").write_bytes(b"stale")
    B.restore_backup(b, data, now=stamp(1), check_app=False)
    assert not (data / "merchants.db-journal").exists()
    assert len(load_all(data)) == 2


# ---------------------------------------------------------------- recovery key
def test_recovery_key_round_trip_and_hides_the_key(tmp_path):
    key = os.urandom(KEY_BYTES)
    f = tmp_path / "recovery.key"
    f.write_text(json.dumps(B.wrap_recovery(key, PASS)))
    assert key.hex().encode() not in f.read_bytes() and key not in f.read_bytes()
    assert B.unwrap_recovery(f, PASS) == key


def test_short_passphrase_is_refused():
    with pytest.raises(B.BackupError, match="minimal"):
        B.wrap_recovery(os.urandom(KEY_BYTES), "short")


# ---------------------------------------------------------------- command line
def test_cli_create_list_verify(data, capsys):
    assert B.main(["create", "--data-dir", str(data)]) == 0
    assert B.main(["list", "--data-dir", str(data)]) == 0
    out = capsys.readouterr().out
    assert "mcn-backup-" in out and "2 merchant" in out
    name = B.list_backups(data / "backups")[0]["name"]
    assert B.main(["verify", str(data / "backups" / name), "--data-dir", str(data), "--check-data"]) == 0
    assert "semua berhasil didekripsi" in capsys.readouterr().out


def test_cli_failure_exits_1_without_a_traceback(tmp_path, capsys):
    assert B.main(["create", "--data-dir", str(tmp_path / "nothing")]) == 1
    assert "Gagal:" in capsys.readouterr().err


# ---------------------------------------------------------------- Windows scripts (cannot be run here; checked for shape)
@pytest.mark.parametrize("name", ["jalankan.bat", "backup.bat", "pulihkan.bat", "jadwal-backup.bat"])
def test_windows_scripts_are_crlf_ascii(name):
    raw = (B.Path(__file__).resolve().parent.parent / name).read_bytes()
    raw.decode("ascii")
    assert raw.count(b"\r\n") == raw.count(b"\n") > 0


def test_run_script_makes_a_backup_before_starting_the_app():
    raw = (B.Path(__file__).resolve().parent.parent / "jalankan.bat").read_text()
    assert raw.index("merchant_notebook.backup create") < raw.index("merchant_notebook.api")
