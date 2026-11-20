"""python -m merchant_notebook.api [--data-dir DIR] [--no-browser]

Binds to 127.0.0.1:8765 only. The access log is off. The database is <data-dir>/merchants.db; the encryption key
is the Windows DPAPI-protected key file <data-dir>/mcn.key (see keys.py).
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import uvicorn

from ..keys import DpapiKeyProvider, KeyUnavailable
from ..sqlstore import SqliteMerchantStore
from .app import create_app
from .security import HOST, PORT


def run_guest(open_browser: bool = True) -> int:
    """Temporary database and random key; everything is deleted when the app stops (Ctrl+C)."""
    import os
    import shutil
    import tempfile

    from ..keys import StaticKeyProvider
    tmp = Path(tempfile.mkdtemp(prefix="mcn-guest-"))
    keys = StaticKeyProvider(os.urandom(32))
    print("MODE TAMU: tidak ada yang disimpan; data sensitif ditolak; semua dihapus saat aplikasi berhenti (Ctrl+C).")
    print(f"Merchant Notebook API on http://{HOST}:{PORT}/  (Ctrl-C to stop)")
    try:
        serve(lambda: SqliteMerchantStore(tmp / "merchants.db", keys), open_browser=open_browser, guest=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print("Data sementara dihapus.")
    return 0


def serve(store_factory, open_browser: bool = False, guest: bool = False) -> None:
    app = create_app(store_factory, guest=guest)
    if open_browser:
        webbrowser.open(f"http://{HOST}:{PORT}/")
    uvicorn.run(app, host=HOST, port=PORT, access_log=False, log_level="warning")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m merchant_notebook.api")
    ap.add_argument("--data-dir", default="merchant_data", help="folder for merchants.db and the key file")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--guest", action="store_true",
                    help="for a computer you do not own: nothing is kept, sensitive data is refused (see api/guest.py)")
    args = ap.parse_args(argv)
    if args.guest:
        return run_guest(open_browser=not args.no_browser)
    data = Path(args.data_dir)
    keys = DpapiKeyProvider(data / "mcn.key")
    try:
        keys.key()                                  # fail early, with a clear message
    except KeyUnavailable as e:
        print(f"Cannot start: {e}", file=sys.stderr)
        return 1
    print(f"Merchant Notebook API on http://{HOST}:{PORT}/  (Ctrl-C to stop)")
    serve(lambda: SqliteMerchantStore(data / "merchants.db", keys), open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
