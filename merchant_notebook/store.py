"""Local JSON storage. Every record is validated against schema.json before it is written or accepted.

Nothing here runs unless a SAVE MERCHANT / LOAD MERCHANT / EXPORT CSV command asks for it.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.json"
MERCHANT_ID = re.compile(r"MCN-[0-9]{8}-[0-9]{3,}")
_REQUIRED_FORMATS = {"email", "date", "date-time", "uri"}


class StoreError(Exception):
    """A storage operation failed. The message says what did NOT happen."""


def _validator() -> Draft202012Validator:
    fc = FormatChecker()
    missing = _REQUIRED_FORMATS - set(fc.checkers)
    if missing:                          # never silently skip format checks
        raise StoreError(f"Format checkers missing ({', '.join(sorted(missing))}). "
                         "Install with: pip install 'jsonschema[format]'")
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=fc)


def _calendar_problems(record) -> list[str]:
    """Beyond the schema pattern: a date of birth must be a real calendar date (e.g. not 02/30/1980)."""
    out = []
    try:
        owners = record["personal_information"]["owners"]
        for i, o in enumerate(owners):
            v = o["date_of_birth"]["value"]
            if v is not None:
                try:
                    datetime.strptime(v, "%m/%d/%Y")
                except ValueError:
                    out.append(f"personal_information/owners/{i}/date_of_birth/value: '{v}' is not a real date")
    except (KeyError, TypeError):
        pass                                   # structural problems are reported by the schema check
    return out


def validate_record(record) -> list[str]:
    """Return a list of human-readable schema problems (empty = valid)."""
    errors = sorted(_validator().iter_errors(record), key=lambda e: [str(p) for p in e.absolute_path])
    problems = [f"{'/'.join(str(p) for p in e.absolute_path) or '(record)'}: {e.message}" for e in errors]
    return problems + _calendar_problems(record)


def record_path(data_dir: Path, merchant_id: str) -> Path:
    if not MERCHANT_ID.fullmatch(merchant_id):
        raise StoreError(f"'{merchant_id}' is not a valid merchant_id.")
    return Path(data_dir) / f"{merchant_id}.json"


def write_text_atomic(path: Path, content: str) -> int:
    """Write via a temp file + rename, then read back. Raises StoreError unless the file is really there."""
    path = Path(path)
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = content.encode("utf-8")
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        tmp = None
        if path.read_bytes() != data:
            raise StoreError(f"{path} was written but reading it back did not match.")
        return len(data)
    except OSError as e:
        raise StoreError(f"could not write {path}: {e.strerror or e}") from e
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


@dataclass
class SaveResult:
    saved: bool
    path: Path
    size: int = 0
    reason: str = ""


def save_record(record: dict, data_dir: Path, confirm_overwrite=lambda path: False) -> SaveResult:
    problems = validate_record(record)
    if problems:
        raise StoreError("the record does not match schema.json:\n  " + "\n  ".join(problems[:10]))
    path = record_path(data_dir, record["merchant_id"])
    if path.exists() and not confirm_overwrite(path):
        return SaveResult(False, path, reason="file exists and overwrite was not confirmed")
    content = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    return SaveResult(True, path, write_text_atomic(path, content))


def load_record(target: str, data_dir: Path) -> tuple[dict, Path]:
    """Load by merchant_id (from data_dir) or by file path. Rejects anything that is not a valid record."""
    path = record_path(data_dir, target) if MERCHANT_ID.fullmatch(target) else Path(target).expanduser()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise StoreError(f"could not read {path}: {e.strerror or e}") from e
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        raise StoreError(f"{path} is not valid JSON: {e}") from e
    problems = validate_record(record)
    if problems:
        raise StoreError(f"{path} does not match schema.json; nothing was loaded:\n  "
                         + "\n  ".join(problems[:10]))
    return record, path
