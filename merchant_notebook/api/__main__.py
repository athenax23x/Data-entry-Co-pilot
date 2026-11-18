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


def serve(store_factory, open_browser: bool = False) -> None:
    app = create_app(store_factory)
    if open_browser:
        webbrowser.open(f"http://{HOST}:{PORT}/")
    uvicorn.run(app, host=HOST, port=PORT, access_log=False, log_level="warning")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m merchant_notebook.api")
    ap.add_argument("--data-dir", default="merchant_data", help="folder for merchants.db and the key file")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
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
