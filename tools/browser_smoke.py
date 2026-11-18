"""Real-browser smoke test (optional developer tool, not part of pytest). Fake data only.

Starts the real server on 127.0.0.1:8765 with a throwaway database and a random key (no Windows DPAPI needed),
drives it with Playwright in Chrome and checks the whole flow: new merchant, click-to-copy, owner title Owner,
Paykings CSV download under the strict CSP, and the Claude bridge (no sensitive data in the prompt, routing number
visible, sensitive / unquoted proposals refused, ambiguous date flagged).

    pip install playwright            # and have Chrome installed
    python tools/browser_smoke.py [--chrome /path/to/chrome]
Exit code 0 = every check passed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765/"
TEXT = ("Example Goods LLC. Owner: Pat Example, phone 555-010-0187. Email: contact@example.com. "
        "Address: 123 Example Ave, Tampa, FL 33602. Bank: Example Bank N.A., account number 87654321. "
        "SSN 123-45-6789. Card 4111 1111 1111 1111 cvv 321. Routing 021000021. Started 06/02/2004.")
SECRETS = ["123-45-6789", "123456789", "87654321", "4111", "cvv 321"]
SERVER = """
import os, sys
sys.path.insert(0, {root!r})
import uvicorn
from merchant_notebook import sqlstore as SQ
from merchant_notebook.api.app import create_app
from merchant_notebook.keys import StaticKeyProvider
key = StaticKeyProvider(os.urandom(32))
uvicorn.run(create_app(lambda: SQ.SqliteMerchantStore({db!r}, key)), host="127.0.0.1", port=8765, access_log=False, log_level="warning")
"""


def cand(path, value, evidence, **kw):
    return {"path": path, "value": value, "evidence": evidence, **kw}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    tmp = tempfile.mkdtemp()
    server = subprocess.Popen([sys.executable, "-I", "-c", SERVER.format(root=str(ROOT), db=os.path.join(tmp, "m.db"))])
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            problems.append(what)

    try:
        time.sleep(3)
        answer = json.dumps({"candidates": [
            cand("business_information.legal_business_name", "Example Goods LLC", "Example Goods LLC"),
            cand("business_address.city", "Tampa", "Address: 123 Example Ave, Tampa, FL 33602"),
            cand("business_information.business_start_date", "06/02/2004", "Started 06/02/2004", ambiguous=True),
            cand("processing_information.routing_number", "021000021", "Routing 021000021"),
            cand("banking_information.account_number", "87654321", "account number 87654321"),
            cand("business_information.business_description", "Sells goods", "this quote is not in the text")]})
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chrome, args=["--no-sandbox"])
            ctx = browser.new_context(accept_downloads=True, permissions=["clipboard-read", "clipboard-write"])
            pg = ctx.new_page()
            console, outside = [], []
            pg.on("console", lambda m: console.append(m.text) if m.type in ("error", "warning") else None)
            pg.on("request", lambda r: outside.append(r.url) if not r.url.startswith(BASE) and not r.url.startswith(("data:", "blob:")) else None)
            pg.goto(BASE)
            pg.wait_for_selector("text=Daftar merchant")
            pg.click("text=Merchant baru")
            pg.fill("textarea", "Example Goods LLC; owner@example.com")
            pg.click("button.primary")
            pg.wait_for_selector("text=Formulir Paykings")
            pg.click("button[aria-label='Salin Business Email']")
            pg.wait_for_selector("text=Tersalin")
            check(pg.evaluate("navigator.clipboard.readText()") == "owner@example.com", "click-to-copy fills the clipboard")
            check(pg.locator("[data-path='personal_information.owners[0].title'] .value").inner_text() == "Owner", "owner title is Owner")
            with pg.expect_download() as d:
                pg.click("button:has-text('Unduh CSV Paykings')")
            text = Path(d.value.path()).read_text(encoding="utf-8")
            check(len(text.splitlines()[0].split(",")) == 70 and "owner@example.com" in text, "CSV download has 70 columns and the data")
            pg.click("[role=tab]:has-text('Jembatan Claude')")
            pg.fill("textarea[aria-label='Teks sumber']", TEXT)
            pg.click("button:has-text('Siapkan')")
            pg.wait_for_selector("textarea[aria-label='Prompt untuk Claude']")
            prompt = pg.input_value("textarea[aria-label='Prompt untuk Claude']")
            check(not [s for s in SECRETS if s in prompt], "no sensitive value in the prompt")
            check("021000021" in prompt and "FIELD LIST" in prompt, "routing number visible; prompt is English")
            pg.fill("textarea[aria-label='Jawaban JSON dari Claude']", answer)
            pg.click("button:has-text('Periksa')")
            pg.wait_for_selector("input[aria-label='Pilih usulan 1']")
            enabled = [pg.locator(f"input[aria-label='Pilih usulan {i}']").is_enabled() for i in range(1, 7)]
            check(enabled == [True, True, True, True, False, False], "sensitive and unquoted proposals cannot be chosen")
            for i, on in enumerate(enabled, 1):
                if on:
                    pg.check(f"input[aria-label='Pilih usulan {i}']")
            pg.click("button:has-text('Terapkan')")
            pg.wait_for_selector("text=Usulan diterapkan")
            pg.click("[role=tab]:has-text('Formulir Paykings')")
            meta = pg.locator("[data-path='business_information.business_start_date'] .meta").first.inner_text()
            check("Perlu ditinjau" in meta, "ambiguous date is flagged for review")
            check(pg.locator("[data-path='banking_information.account_number'] .value").first.inner_text() == "—", "account number stays empty")
            check(not console, f"console is clean {console}")
            check(not outside, f"no request leaves 127.0.0.1:8765 {outside}")
            browser.close()
    finally:
        server.terminate()
    print("ALL OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
