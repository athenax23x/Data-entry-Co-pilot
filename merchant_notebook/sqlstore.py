"""SQLite storage for v2 merchant records, with sensitive values encrypted per field.

Layout: one row per merchant. Only plain summary columns (id, version, status, business name, entity type, updated
time) are readable without the key; the full record is stored as JSON in `document`, with the sensitive values
replaced by AES-256-GCM tokens. Each token is bound to its merchant and field path, so a token copied to another
field or merchant fails to open.

Rules enforced here:
- Every write is validated against schema_v2.json first. A refused record is not written.
- Writes need the version the caller last read (optimistic lock). Two windows editing the same merchant cannot
  overwrite each other silently; the second one is told to reload.
- Merchants are isolated: every query is keyed by merchant_id.
- Error messages never show a sensitive value.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import jsonschema
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import migrate, record as R
from .keys import KeyProvider
from .store import MERCHANT_ID, StoreError

SCHEMA_V2 = Path(__file__).resolve().parent.parent / "schema_v2.json"
TOKEN_PREFIX = "enc:v1:"
OWNER_SENSITIVE = ("ssn", "ssn_last4", "driver_license_number", "passport_number")
BANK_SENSITIVE = ("account_number",)
SENSITIVE_NAMES = frozenset(OWNER_SENSITIVE + BANK_SENSITIVE)
SCHEMA_VERSION_DB = 2


class SqlStoreError(StoreError):
    pass


class NotFound(SqlStoreError):
    pass


class StaleRecordError(SqlStoreError):
    """The record changed since the caller read it (or it already exists, for a create)."""


class RefusedRecord(SqlStoreError):
    """The record does not match schema_v2.json. Nothing was written."""


class CorruptRecordError(SqlStoreError):
    """Stored data could not be opened: wrong key, altered, or moved to another merchant or field."""


@dataclass
class ImportReport:
    imported: list = field(default_factory=list)
    skipped: list = field(default_factory=list)      # already in the database; left unchanged
    failed: list = field(default_factory=list)       # (file name, reason)


# ---------------------------------------------------------------- validation
@lru_cache(maxsize=1)
def _validator():
    with open(SCHEMA_V2, encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.Draft202012Validator.check_schema(schema)
    fc = jsonschema.FormatChecker()
    missing = {"email", "date", "date-time", "uri"} - set(fc.checkers)
    if missing:
        raise SqlStoreError("Format checkers missing (" + ", ".join(sorted(missing)) + "). "
                            "Install with: pip install 'jsonschema[format]'")
    return jsonschema.Draft202012Validator(schema, format_checker=fc)


def _safe_problem(err) -> str:
    """One line per problem. Values under a sensitive name are never echoed."""
    path = "/".join(str(p) for p in err.absolute_path) or "(record)"
    if any(str(p) in SENSITIVE_NAMES for p in err.absolute_path):
        return f"{path}: value is not in the required format (value not shown)"
    return f"{path}: {err.message}"


def _calendar_check(rec) -> list[str]:
    """A date of birth must be a real calendar date. The value itself is not echoed."""
    from datetime import datetime
    out = []
    for i, o in enumerate(rec["personal_information"]["owners"]):
        v = o["date_of_birth"]["value"]
        if v is not None:
            try:
                datetime.strptime(v, "%m/%d/%Y")
            except ValueError:
                out.append(f"personal_information/owners/{i}/date_of_birth: not a real calendar date")
    return out


def validate_v2(rec) -> list[str]:
    errors = sorted(_validator().iter_errors(rec), key=lambda e: [str(p) for p in e.absolute_path])
    return [_safe_problem(e) for e in errors] + _calendar_check(rec)


# ---------------------------------------------------------------- encryption
def _sensitive_fields(rec: dict):
    """(label, field object) for every sensitive value in a v2 record."""
    for i, o in enumerate(rec["personal_information"]["owners"]):
        for name in OWNER_SENSITIVE:
            if name in o:
                yield f"owners[{i}].{name}", o[name]
    bank = rec.get("banking_information", {})
    for name in BANK_SENSITIVE:
        if name in bank:
            yield f"banking_information.{name}", bank[name]


class FieldCipher:
    def __init__(self, key: bytes):
        self._aead = AESGCM(key)

    def seal(self, text: str, aad: bytes) -> str:
        nonce = os.urandom(12)
        ct = self._aead.encrypt(nonce, text.encode("utf-8"), aad)
        return TOKEN_PREFIX + base64.b64encode(nonce + ct).decode("ascii")

    def open(self, token: str, aad: bytes) -> str:
        if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX):
            raise CorruptRecordError("A protected value is not in the expected form.")
        raw = base64.b64decode(token[len(TOKEN_PREFIX):])
        try:
            return self._aead.decrypt(raw[:12], raw[12:], aad).decode("utf-8")
        except InvalidTag:
            raise CorruptRecordError("A protected value could not be opened: wrong key, or the data was altered "
                                     "or moved to another field or merchant.")


def _aad(merchant_id: str, label: str) -> bytes:
    return f"{merchant_id}|{label}".encode("utf-8")


def _sensitive_slots(rec: dict):
    """(label, dict, key) for every place a sensitive value is kept: the field value, its history, and the values
    inside conflicts about it. (History and conflicts copy the value, so they must be protected the same way.)"""
    for label, f in _sensitive_fields(rec):
        yield label, f, "value"
        for i, h in enumerate(f.get("history", [])):
            yield f"{label}.history[{i}]", h, "value"
    for c in rec.get("conflicts", []):
        if str(c.get("field_path", "")).rsplit("/", 1)[-1] in SENSITIVE_NAMES:
            cid = c.get("conflict_id")
            yield f"conflict {cid}.current", c, "current_value"
            for i, cand in enumerate(c.get("candidates", [])):
                yield f"conflict {cid}.candidate[{i}]", cand, "value"
            res = c.get("resolution", {})
            yield f"conflict {cid}.resolved", res, "resolved_value"


def _encrypt_doc(rec: dict, cipher: FieldCipher) -> dict:
    out = copy.deepcopy(rec)
    mid = out["merchant_id"]
    for label, d, key in _sensitive_slots(out):
        if d.get(key) is not None:
            d[key] = cipher.seal(d[key], _aad(mid, label))
    return out


def _decrypt_doc(doc: dict, cipher: FieldCipher) -> dict:
    out = copy.deepcopy(doc)
    mid = out["merchant_id"]
    for label, d, key in _sensitive_slots(out):
        if d.get(key) is None:
            continue
        strict = ".history[" not in label and not label.startswith("conflict ")    # the field value itself
        if strict or (isinstance(d[key], str) and d[key].startswith(TOKEN_PREFIX)):
            d[key] = cipher.open(d[key], _aad(mid, label))
        # else: a history/conflict value stored in plain text by the first M2 version; re-sealed on the next save
    return out


# ---------------------------------------------------------------- store
class SqliteMerchantStore:
    def __init__(self, path, keys: KeyProvider):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = FieldCipher(keys.key())
        self._db = sqlite3.connect(str(self.path), isolation_level=None)
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS merchants (
                merchant_id   TEXT PRIMARY KEY,
                version       INTEGER NOT NULL CHECK (version >= 1),
                record_status TEXT NOT NULL,
                legal_name    TEXT,
                entity_type   TEXT,
                updated_at    TEXT NOT NULL,
                document      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_merchants_legal_name ON merchants(legal_name);
            CREATE TABLE IF NOT EXISTS archived (
                merchant_id TEXT PRIMARY KEY REFERENCES merchants(merchant_id) ON DELETE CASCADE,
                archived_at TEXT NOT NULL
            );
        """)
        self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION_DB}")
        if os.name == "posix":
            os.chmod(self.path, 0o600)

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def _tx(self):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        else:
            self._db.execute("COMMIT")

    # -- writes
    def save(self, rec: dict, expected_version: int | None) -> int:
        """Write a v2 record. expected_version: None to create (must not exist), or the version last read.

        Returns the new version. Raises RefusedRecord (nothing written), StaleRecordError, or SqlStoreError.
        """
        mid = rec.get("merchant_id")
        if not isinstance(mid, str) or not MERCHANT_ID.fullmatch(mid):
            raise RefusedRecord("merchant_id is not valid.")
        problems = validate_v2(rec)
        if problems:
            raise RefusedRecord("the record does not match schema_v2.json:\n  " + "\n  ".join(problems[:10]))
        doc = _encrypt_doc(rec, self._cipher)
        name = rec["business_information"]["legal_business_name"]["value"]
        etype = rec["business_entity_type"]["value"]
        with self._tx():
            row = self._db.execute("SELECT version FROM merchants WHERE merchant_id = ?", (mid,)).fetchone()
            current = row[0] if row else None
            if current != expected_version:
                if expected_version is None:
                    raise StaleRecordError(f"{mid} already exists. Load it, then save with its version.")
                if current is None:
                    raise StaleRecordError(f"{mid} does not exist yet; create it with expected_version=None.")
                raise StaleRecordError(f"{mid} changed since it was read (now version {current}). Reload it and "
                                       "apply the change again.")
            new_version = (current or 0) + 1
            values = (new_version, rec["record_status"], name, etype, rec["updated_at"],
                      json.dumps(doc, ensure_ascii=False))
            if current is None:
                self._db.execute("INSERT INTO merchants (version, record_status, legal_name, entity_type, updated_at, "
                                 "document, merchant_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (*values, mid))
            else:
                self._db.execute("UPDATE merchants SET version=?, record_status=?, legal_name=?, entity_type=?, "
                                 "updated_at=?, document=? WHERE merchant_id=?", (*values, mid))
        return new_version

    # -- reads
    def load(self, merchant_id: str) -> tuple[dict, int]:
        """Return (decrypted record, version). Raises NotFound or CorruptRecordError."""
        row = self._db.execute("SELECT version, document FROM merchants WHERE merchant_id = ?",
                               (merchant_id,)).fetchone()
        if row is None:
            raise NotFound(f"{merchant_id} is not in the database.")
        doc = _decrypt_doc(json.loads(row[1]), self._cipher)
        if doc["merchant_id"] != merchant_id:
            raise CorruptRecordError(f"Row {merchant_id} holds a record for another merchant. Nothing was returned.")
        problems = validate_v2(doc)
        if problems:
            raise CorruptRecordError(f"{merchant_id} is stored in a form that does not match schema_v2.json:\n  "
                                     + "\n  ".join(problems[:10]))
        return doc, row[0]

    def list(self, query: str | None = None) -> list[dict]:
        """Summaries only (no decryption), archived ones included (flag 'archived'). query matches the business name
        (case-insensitive) or the id."""
        cols = ("SELECT m.merchant_id, m.legal_name, m.entity_type, m.record_status, m.version, m.updated_at, "
                "a.archived_at FROM merchants m LEFT JOIN archived a ON a.merchant_id = m.merchant_id ")
        if query:
            q = query.strip()
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = self._db.execute(cols + "WHERE m.legal_name LIKE ? ESCAPE '\\' OR m.merchant_id LIKE ? ESCAPE '\\' "
                                    "ORDER BY m.updated_at DESC", (like, like)).fetchall()
        else:
            rows = self._db.execute(cols + "ORDER BY m.updated_at DESC").fetchall()
        keys = ("merchant_id", "legal_name", "entity_type", "record_status", "version", "updated_at")
        return [dict(zip(keys, r[:6]), archived=r[6] is not None) for r in rows]

    # -- archive and delete (M22). Archiving hides a merchant from the list; only an archived one can be deleted.
    def set_archived(self, merchant_id: str, archived: bool, now: str) -> None:
        with self._tx():
            if not self._exists(merchant_id):
                raise NotFound(f"{merchant_id} is not in the database.")
            if archived:
                self._db.execute("INSERT OR IGNORE INTO archived (merchant_id, archived_at) VALUES (?, ?)",
                                 (merchant_id, now))
            else:
                self._db.execute("DELETE FROM archived WHERE merchant_id = ?", (merchant_id,))

    def delete(self, merchant_id: str, expected_version: int) -> None:
        """Remove an archived merchant for good. The version must match, so a merchant changed elsewhere is kept."""
        with self._tx():
            row = self._db.execute("SELECT m.version, a.merchant_id FROM merchants m LEFT JOIN archived a "
                                   "ON a.merchant_id = m.merchant_id WHERE m.merchant_id = ?", (merchant_id,)).fetchone()
            if row is None:
                raise NotFound(f"{merchant_id} is not in the database.")
            if row[1] is None:
                raise RefusedRecord(f"{merchant_id} is not archived. Archive it first, then delete it.")
            if row[0] != expected_version:
                raise StaleRecordError(f"{merchant_id} changed since it was read (now version {row[0]}). Reload it.")
            self._db.execute("DELETE FROM merchants WHERE merchant_id = ?", (merchant_id,))

    # -- import of the JSON files from the Notebook (v1 or v2)
    def import_json_dir(self, directory) -> ImportReport:
        """Import MCN-*.json files. Existing merchants are skipped, never overwritten. Source files are not changed."""
        report = ImportReport()
        for path in sorted(Path(directory).glob("MCN-*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                rec = migrate.migrate_record(raw)
                mid = rec["merchant_id"]
                if self._exists(mid):
                    report.skipped.append(mid)
                    continue
                self.save(rec, expected_version=None)
                report.imported.append(mid)
            except (SqlStoreError, migrate.MigrationError, json.JSONDecodeError, KeyError, OSError) as e:
                report.failed.append((path.name, str(e).splitlines()[0] if str(e) else type(e).__name__))
        return report

    def _exists(self, mid: str) -> bool:
        return self._db.execute("SELECT 1 FROM merchants WHERE merchant_id = ?", (mid,)).fetchone() is not None
