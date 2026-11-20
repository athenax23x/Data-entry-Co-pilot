"""Portable, password-protected export and import of every merchant record.

Why: the database key is tied to one Windows account (DPAPI), so merchants.db and the backups cannot be opened on
another PC. This writes ONE file (.mcnx), encrypted with a key made from a password (scrypt + AES-256-GCM), that
any PC with this app can import. Sensitive values are inside the encrypted payload only. Keep the password
somewhere safe: without it the file cannot be opened, and nobody can recover it.

    python -m merchant_notebook.portable export --file merchants.mcnx [--data-dir merchant_data]
    python -m merchant_notebook.portable import --file merchants.mcnx [--data-dir merchant_data]
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

FORMAT = "mcn-portable-1"
MIN_PASSWORD = 12
_N, _R, _P = 2 ** 16, 8, 1                      # scrypt cost: about 64 MB and a fraction of a second


class PortableError(Exception):
    """A message that is safe to show: it never contains merchant data or the password."""


def _key(password: str, salt: bytes, n: int = _N, r: int = _R, p: int = _P) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode("utf-8"))


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise PortableError(f"The password must have at least {MIN_PASSWORD} characters.")


def export_records(records: list[dict], password: str) -> bytes:
    check_password(password)
    salt, nonce = os.urandom(16), os.urandom(12)
    payload = json.dumps({"records": records}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = {"format": FORMAT, "kdf": {"name": "scrypt", "n": _N, "r": _R, "p": _P, "salt": _b64(salt)}, "nonce": _b64(nonce)}
    aad = FORMAT.encode("ascii")
    box = AESGCM(_key(password, salt)).encrypt(nonce, payload, aad)
    return json.dumps(dict(header, ciphertext=_b64(box)), separators=(",", ":")).encode("utf-8")


def read_records(blob: bytes, password: str) -> list[dict]:
    try:
        doc = json.loads(blob.decode("utf-8"))
        if doc.get("format") != FORMAT or doc["kdf"]["name"] != "scrypt":
            raise ValueError
        kdf = doc["kdf"]
        if not (2 ** 14 <= kdf["n"] <= 2 ** 20 and kdf["r"] == _R and kdf["p"] == _P):
            raise ValueError
        key = _key(password, base64.b64decode(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"])
        payload = AESGCM(key).decrypt(base64.b64decode(doc["nonce"]), base64.b64decode(doc["ciphertext"]), FORMAT.encode("ascii"))
        records = json.loads(payload.decode("utf-8"))["records"]
    except InvalidTag:
        raise PortableError("Wrong password, or the file was changed.") from None
    except (ValueError, KeyError, TypeError):
        raise PortableError("This is not a valid .mcnx file.") from None
    if not isinstance(records, list):
        raise PortableError("This is not a valid .mcnx file.")
    return records


def export_store(store, path, password: str) -> int:
    records = [store.load(m["merchant_id"])[0] for m in store.list()]
    Path(path).write_bytes(export_records(records, password))
    return len(records)


def import_into_store(store, path, password: str) -> dict:
    """Existing merchants are skipped, never overwritten. A record the store refuses is counted as failed."""
    from .sqlstore import SqlStoreError
    out = {"imported": 0, "skipped": 0, "failed": 0}
    for rec in read_records(Path(path).read_bytes(), password):
        try:
            store.load(rec.get("merchant_id", ""))
            out["skipped"] += 1
            continue
        except SqlStoreError:
            pass
        try:
            store.save(rec, expected_version=None)
            out["imported"] += 1
        except SqlStoreError:
            out["failed"] += 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m merchant_notebook.portable")
    ap.add_argument("command", choices=["export", "import"])
    ap.add_argument("--file", required=True)
    ap.add_argument("--data-dir", default="merchant_data")
    args = ap.parse_args(argv)
    from .keys import DpapiKeyProvider, KeyUnavailable
    from .sqlstore import SqliteMerchantStore
    data = Path(args.data_dir)
    try:
        if args.command == "export":
            if Path(args.file).exists():
                raise PortableError(f"{args.file} already exists. Choose another file name.")
            pw = getpass.getpass("Password for the file (min 12 characters): ")
            if pw != getpass.getpass("Type it again: "):
                raise PortableError("The two passwords are different.")
            check_password(pw)
            n = export_store(SqliteMerchantStore(data / "merchants.db", DpapiKeyProvider(data / "mcn.key")), args.file, pw)
            print(f"{n} merchant(s) written to {args.file}. Keep the password safe; it cannot be recovered.")
        else:
            pw = getpass.getpass("Password of the file: ")
            r = import_into_store(SqliteMerchantStore(data / "merchants.db", DpapiKeyProvider(data / "mcn.key")), args.file, pw)
            print(f"Imported {r['imported']}, skipped (already here) {r['skipped']}, failed {r['failed']}.")
    except (PortableError, KeyUnavailable, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
