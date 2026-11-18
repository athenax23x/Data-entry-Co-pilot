"""Backups of the local database (M6).  python -m merchant_notebook.backup {create,list,verify,restore} ...

A backup is a folder  mcn-backup-YYYYMMDD-HHMMSS/  with:
  merchants.db   a consistent snapshot (SQLite online backup, safe while the app runs). Sensitive values stay
                 AES-256-GCM tokens, exactly as in the live database. No new plain-text copy is made.
  mcn.key        a copy of the DPAPI-wrapped key file. It only opens on the same Windows account.
  manifest.json  counts and a SHA-256 of merchants.db. No merchant names, ids or values.

The key file is DPAPI-wrapped, so a backup opens only on the Windows account that made it. Without that key the
sensitive values in a backup are lost. Messages never show a stored value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


from . import sqlstore
from .keys import DpapiKeyProvider, KeyProvider, KeyUnavailable, StaticKeyProvider
from .api.security import HOST, PORT

PREFIX = "mcn-backup-"
NAME_RX = re.compile(r"^mcn-backup-\d{8}-\d{6}(-\d+)?$")
DB_NAME, KEY_NAME, MANIFEST = "merchants.db", "mcn.key", "manifest.json"
DEFAULT_KEEP = 14


class BackupError(Exception):
    """The message says what did NOT happen and what to do. It never contains a stored value or key material."""


def _provider(key_file: Path) -> KeyProvider:
    return DpapiKeyProvider(key_file)             # tests replace this


# ---------------------------------------------------------------- helpers
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot(src_db: Path, dst_db: Path) -> None:
    """Consistent copy of a live SQLite file (online backup API; also correct while the app is writing)."""
    src = sqlite3.connect(f"file:{src_db.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(dst_db))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _db_facts(db: Path) -> tuple[int, int]:
    """(merchant count, user_version) of a database file, after an integrity check. Read-only."""
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("Database di backup rusak (integrity_check gagal).")
        return (con.execute("SELECT COUNT(*) FROM merchants").fetchone()[0],
                con.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.DatabaseError:
        raise BackupError("File database di backup tidak bisa dibaca.") from None
    finally:
        con.close()


def _utc_stamp(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")


def _is_backup_dir(p: Path) -> bool:
    return p.is_dir() and NAME_RX.match(p.name) is not None and (p / MANIFEST).is_file()


def backups_in(dest: Path) -> list[Path]:
    """Backup folders in dest, oldest first. Only folders that match our naming and hold a manifest."""
    if not Path(dest).is_dir():
        return []
    return sorted((p for p in Path(dest).iterdir() if _is_backup_dir(p)), key=lambda p: p.name)


# ---------------------------------------------------------------- create / list
def create_backup(data_dir, dest=None, keep: int = DEFAULT_KEEP, now: datetime | None = None) -> Path:
    """Make a backup folder in dest (default <data_dir>/backups). Returns its path. Keeps the newest `keep` backups
    (folders this tool made); nothing else in dest is ever deleted."""
    if keep < 1:
        raise BackupError("--keep minimal 1.")
    data, db = Path(data_dir), Path(data_dir) / DB_NAME
    if not db.is_file():
        raise BackupError(f"Belum ada database di {data}. Tidak ada yang perlu di-backup.")
    dest = Path(dest) if dest else data / "backups"
    dest.mkdir(parents=True, exist_ok=True)

    name = PREFIX + _utc_stamp(now)
    final = dest / name
    n = 1
    while final.exists():
        n += 1
        final = dest / f"{name}-{n}"
    tmp = Path(tempfile.mkdtemp(prefix=".tmp-" + PREFIX, dir=dest))
    try:
        _snapshot(db, tmp / DB_NAME)
        count, user_version = _db_facts(tmp / DB_NAME)
        key_file = data / KEY_NAME
        if key_file.is_file():
            shutil.copy2(key_file, tmp / KEY_NAME)
        manifest = {"format": 1, "created_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "merchant_count": count, "db_user_version": user_version, "db_sha256": _sha256(tmp / DB_NAME),
                    "has_key_file": key_file.is_file()}
        (tmp / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if os.name == "posix":
            for f in tmp.iterdir():
                os.chmod(f, 0o600)
        os.replace(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    for old in backups_in(dest)[:-keep]:
        if old != final:
            shutil.rmtree(old)
    return final


def list_backups(dest) -> list[dict]:
    out = []
    for p in backups_in(Path(dest)):
        try:
            m = json.loads((p / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            m = {}
        out.append({"name": p.name, "created_at": m.get("created_at"), "merchants": m.get("merchant_count"),
                    "size_kb": sum(f.stat().st_size for f in p.iterdir()) // 1024})
    return out


# ---------------------------------------------------------------- verify
def verify_backup(path, key: bytes | None = None) -> dict:
    """Check a backup folder: files, checksum, SQLite integrity, counts. With `key`, also open and decrypt every
    merchant (proves the key fits). Never writes into the backup. Raises BackupError."""
    p = Path(path)
    try:
        m = json.loads((p / MANIFEST).read_text(encoding="utf-8"))
        want = m["db_sha256"]
    except (OSError, ValueError, KeyError):
        raise BackupError("Ini bukan folder backup yang valid (manifest.json tidak ada atau rusak).") from None
    db = p / DB_NAME
    if not db.is_file():
        raise BackupError("File merchants.db tidak ada di backup.")
    if _sha256(db) != want:
        raise BackupError("Checksum backup tidak cocok: file berubah atau rusak sejak dibuat.")
    count, user_version = _db_facts(db)
    if count != m.get("merchant_count") or user_version != m.get("db_user_version"):
        raise BackupError("Isi database tidak cocok dengan manifest.")
    checked = False
    if key is not None:
        with tempfile.TemporaryDirectory() as td:              # the store may write (tables, chmod): use a copy
            copy = Path(td) / DB_NAME
            shutil.copyfile(db, copy)
            try:
                with sqlstore.SqliteMerchantStore(copy, StaticKeyProvider(key)) as store:
                    for row in store.list():
                        store.load(row["merchant_id"])
            except sqlstore.SqlStoreError as e:
                raise BackupError("Kunci tidak bisa membuka data di backup ini "
                                  f"({type(e).__name__}).") from None
            checked = True
    return {"ok": True, "merchants": count, "decrypt_checked": checked, "created_at": m.get("created_at")}


# ---------------------------------------------------------------- restore
def app_is_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _resolve_key(backup: Path, data: Path) -> tuple[bytes, str]:
    """Find a key that opens this backup. Returns (key, action): keep_current | install_backup_key."""
    tried = False
    for action, key_file in (("keep_current", data / KEY_NAME), ("install_backup_key", backup / KEY_NAME)):
        if not key_file.is_file():
            continue
        tried = True
        try:
            key = _provider(key_file).key()
            verify_backup(backup, key)
            return key, action
        except (KeyUnavailable, BackupError):
            continue
    raise BackupError(("Tidak ada kunci yang cocok dengan backup ini. " if tried else "Tidak ada file kunci. ")
                      + "Backup hanya bisa dibuka di akun Windows yang membuatnya.")


def restore_backup(backup, data_dir, now: datetime | None = None, check_app: bool = True) -> dict:
    """Replace <data_dir>/merchants.db with the backup. The current database (and key, if it is replaced) is first
    moved aside as *.before-restore-<time>, so nothing is lost. Refuses while the app is running."""
    backup, data = Path(backup), Path(data_dir)
    verify_backup(backup)
    if check_app and app_is_running():
        raise BackupError("Aplikasi sedang berjalan. Tutup dulu, lalu ulangi.")
    key, action = _resolve_key(backup, data)
    stamp = _utc_stamp(now)
    data.mkdir(parents=True, exist_ok=True)
    live, aside = data / DB_NAME, None
    if live.exists():
        aside = data / f"{DB_NAME}.before-restore-{stamp}"
        os.replace(live, aside)
    journal = data / (DB_NAME + "-journal")
    if journal.exists():                                       # belongs to the old database; would corrupt the new
        os.replace(journal, data / f"{DB_NAME}-journal.before-restore-{stamp}")
    tmp = data / (DB_NAME + ".restoring")
    shutil.copyfile(backup / DB_NAME, tmp)
    os.replace(tmp, live)
    if os.name == "posix":
        os.chmod(live, 0o600)
    if action == "install_backup_key":
        kf = data / KEY_NAME
        if kf.exists():
            os.replace(kf, data / f"{KEY_NAME}.before-restore-{stamp}")
        shutil.copy2(backup / KEY_NAME, kf)
    count, _ = _db_facts(live)
    return {"merchants": count, "key": action, "previous_database": aside.name if aside else None}


# ---------------------------------------------------------------- command line
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m merchant_notebook.backup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("create", "list", "verify", "restore"):
        sp = sub.add_parser(name)
        sp.add_argument("--data-dir", default="merchant_data")
        if name in ("create", "list"):
            sp.add_argument("--dest", help="folder backup (default: <data-dir>/backups)")
        if name == "create":
            sp.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="jumlah backup terbaru yang disimpan")
            sp.add_argument("--quiet", action="store_true")
        if name in ("verify", "restore"):
            sp.add_argument("path")
        if name == "verify":
            sp.add_argument("--check-data", action="store_true", help="buka & dekripsi semua merchant dengan kunci saat ini")
        if name == "restore":
            sp.add_argument("--yes", action="store_true", help="jangan tanya konfirmasi")
    a = ap.parse_args(argv)
    data = Path(a.data_dir)
    try:
        if a.cmd == "create":
            path = create_backup(data, a.dest, a.keep)
            if not a.quiet:
                print(f"Backup dibuat: {path}")
        elif a.cmd == "list":
            rows = list_backups(a.dest or data / "backups")
            for r in rows:
                print(f"{r['name']}  {r['merchants']} merchant  {r['size_kb']} KB")
            if not rows:
                print("Belum ada backup.")
        elif a.cmd == "verify":
            key = _provider(data / KEY_NAME).key() if a.check_data else None
            r = verify_backup(a.path, key)
            print(f"OK: {r['merchants']} merchant" + (", semua berhasil didekripsi." if r["decrypt_checked"] else
                                                      " (struktur & checksum; belum cek dekripsi)."))
        else:
            if not a.yes:
                print("Ini mengganti database saat ini dengan isi backup. Database lama disimpan sebagai "
                      "*.before-restore-*. Lanjut? [y/N] ", end="", flush=True)
                if input().strip().lower() not in ("y", "yes"):
                    print("Dibatalkan.")
                    return 1
            r = restore_backup(a.path, data)
            print(f"Dipulihkan: {r['merchants']} merchant. Kunci: {r['key']}."
                  + (f" Database sebelumnya: {r['previous_database']}" if r["previous_database"] else ""))
    except (BackupError, KeyUnavailable) as e:
        print(f"Gagal: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
