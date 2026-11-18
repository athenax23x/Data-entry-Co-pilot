"""Where the local encryption key comes from.

Windows (the target): a random 256-bit key is generated once and stored in a file that is wrapped with Windows DPAPI,
so only the Windows account that created it can unwrap it. Nothing to type, nothing to install.

Elsewhere: no silent fallback to an unprotected key. Pass a key explicitly (StaticKeyProvider), e.g. in tests.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

KEY_BYTES = 32


class KeyUnavailable(Exception):
    """No usable key. The message says what to do; it never contains key material."""


class KeyProvider:
    def key(self) -> bytes:
        raise NotImplementedError


class StaticKeyProvider(KeyProvider):
    """Explicit key bytes. For tests and for a caller that manages its own key. Not a default."""

    def __init__(self, key: bytes):
        if not isinstance(key, bytes) or len(key) != KEY_BYTES:
            raise KeyUnavailable(f"The key must be {KEY_BYTES} bytes.")
        self._key = key

    def key(self) -> bytes:
        return self._key


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(fn, data: bytes) -> bytes:
    """Call CryptProtectData / CryptUnprotectData. Windows only."""
    buf = ctypes.create_string_buffer(data, len(data))          # must stay alive for the call
    src = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise KeyUnavailable(f"Windows DPAPI refused the request (error {ctypes.GetLastError()}).")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class DpapiKeyProvider(KeyProvider):
    def __init__(self, key_file: Path):
        self.key_file = Path(key_file)

    def key(self) -> bytes:
        if sys.platform != "win32":
            raise KeyUnavailable("DPAPI key storage needs Windows. Elsewhere, pass a key explicitly.")
        if self.key_file.exists():
            try:
                key = _dpapi(ctypes.windll.crypt32.CryptUnprotectData, self.key_file.read_bytes())
            except KeyUnavailable:
                raise KeyUnavailable("The local key cannot be unlocked by this Windows account. It was created by "
                                     "another account, or the key file is damaged. Data cannot be read.")
            if len(key) != KEY_BYTES:
                raise KeyUnavailable("The local key file is damaged.")
            return key
        key = os.urandom(KEY_BYTES)
        self.install(key)
        return key

    def install(self, key: bytes) -> None:
        """Wrap `key` with DPAPI for this Windows account and store it as the key file (atomic replace).
        Used when a backup is restored on a new account or machine from the passphrase-protected recovery key."""
        if sys.platform != "win32":
            raise KeyUnavailable("DPAPI key storage needs Windows. Elsewhere, pass a key explicitly.")
        if not isinstance(key, bytes) or len(key) != KEY_BYTES:
            raise KeyUnavailable(f"The key must be {KEY_BYTES} bytes.")
        blob = _dpapi(ctypes.windll.crypt32.CryptProtectData, key)
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.key_file.with_name(self.key_file.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.key_file)
