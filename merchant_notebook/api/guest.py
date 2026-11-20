"""Guest mode (--guest): for a computer you do not own, such as an internet cafe.

Nothing is kept: the database and a random key live in a temporary folder that is deleted when the app stops.
Sensitive values (SSN, last 4, driver licence, passport, bank account number) are refused, so they are never typed
or stored on that computer. Everything else (auto-fill from text, the Claude bridge, click-to-copy, CSV without
sensitive columns) works as usual.
"""
from __future__ import annotations

from ..sqlstore import _sensitive_fields

MESSAGE = ("Mode tamu: data sensitif (SSN, 4 digit SSN, SIM, paspor, nomor rekening) tidak boleh disimpan di "
           "komputer ini. Hapus bagian itu dari teks dan isi di perangkat Anda sendiri.")


class GuestRefused(Exception):
    """A record with a sensitive value was about to be saved in guest mode."""


class GuestStore:
    """Wraps a store: every method passes through, except save(), which refuses a record with a sensitive value."""

    def __init__(self, store):
        self._store = store

    def save(self, rec: dict, expected_version):
        for _label, f in _sensitive_fields(rec):
            if f.get("value") not in (None, ""):
                raise GuestRefused(MESSAGE)
        return self._store.save(rec, expected_version)

    def __getattr__(self, name):
        return getattr(self._store, name)
