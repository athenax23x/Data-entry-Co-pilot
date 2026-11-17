"""Interactive command line: python -m merchant_notebook [--data-dir DIR]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .commands import COMMANDS, Session

DEFAULT_DATA_DIR = "merchant_data"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="merchant_notebook",
                                description="Merchant Context Notebook (local, one session per run).")
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                   help=f"where SAVE MERCHANT / EXPORT CSV write (default ./{DEFAULT_DATA_DIR})")
    args = p.parse_args(argv)

    def confirm(question: str) -> bool:
        print(f"{question} [y/N] ", end="", flush=True)
        try:
            return input().strip().lower() in ("y", "yes")
        except EOFError:
            return False

    session = Session(Path(args.data_dir), confirm=confirm)
    tty = sys.stdin.isatty()
    if tty:
        print("Merchant Context Notebook. Commands: " + ", ".join(COMMANDS) + ".")
        print("Nothing is saved unless you run SAVE MERCHANT. Leave with Ctrl-D (unsaved records are lost).")
    while True:
        try:
            line = input("mcn> " if tty else "")
        except EOFError:
            break
        if line.strip():
            print(session.execute(line), flush=True)
    lost = sorted(session.dirty & set(session.records))
    if lost:
        print("Unsaved records discarded: " + ", ".join(lost), file=sys.stderr)
    return 0
