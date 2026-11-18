# preview_tool

Turns a CSV made by `EXPORT CSV` into **one HTML page** you can open in any browser: one card per merchant.

```bash
python -m preview_tool path/to/export.csv                 # -> merchant_data/previews/export.html
python -m preview_tool path/to/export.csv --out report.html
```

What you see:

- One card per row (merchant). Core columns first: name, business name, DBA, entity type, address, contact, EIN / Notes, and the record `Status` as a badge in the card header. Everything else is under "More details".
- Empty columns are hidden. `[MISSING]` is shown in a clearly different (red) style.
- The `*_status` columns are not shown as columns: each one is a small badge (`verified`, `inferred`, `needs_review`, `conflict`, `missing`) next to its value.
- Works on wide and narrow screens, light and dark mode.

Rules it follows:

- **Read-only for your data.** It only reads the CSV. It writes one file, the HTML, and refuses an output name that does not end in `.html` or that equals the input file.
- **Nothing external.** No scripts, no links, no CDN, no web fonts, no images; all CSS is inline, and the page carries a Content-Security-Policy that blocks any network request. Every value from the CSV is HTML-escaped, so text like `<script>` is shown as text and never runs.
- Standard library only; no extra install.

## No Python? Use `viewer.html`

`preview_tool/viewer.html` is a single file that needs **nothing installed**: no Python, no Git, no Node. Copy it anywhere (a USB drive is enough), open it in any modern browser, then drop in or choose the exported CSV. It shows the same cards, badges and `[MISSING]` highlighting as the Python tool.

It reads the CSV inside the browser tab only. Nothing is uploaded or saved, it loads no external resources, and a Content-Security-Policy blocks all network requests. Values are inserted as plain text, so `<script>` in the CSV never runs. This page is the only part of the tool that contains JavaScript. Once real data is loaded, the tab shows confidential data: close it when done and do not save the page.

## Paykings form layout

A CSV whose header has a `Legal Business Name` column is shown in the order of the Paykings application form: 1. Business Information, 2. Address, 3. Fulfillment, 4. Sales Metrics, 5. Banking, 6. MCC and Tax, 7. Business Owner, then Notes. The 70 columns and the rules live in `paykings_layout.json` (the viewer keeps an identical copy; a test fails if they differ). Other CSVs, such as `EXPORT CSV` output, keep the original card layout.

- Dates stay `MM/DD/YYYY`; a small badge shows the `DD/MM/YYYY` order the form's date picker uses.
- `SSN` and `Bank Account Number` show only the last 4 digits until you click "show".
- Warnings: Public + B2B, National + International and Swipe + Keyed + Internet must each total 100%; Website is required when Card Internet % is above 0.
- `Owner Title` is always `Owner`; `Business Type` is the business entity type (Sole Proprietorship, LLC, Corporation, ...).
- One owner per row; put any extra owners in `Notes`.

This layout is display-only: the Merchant Notebook app still saves and exports its own format.

## Privacy

The default output folder `merchant_data/previews/` is inside `merchant_data/`, which git ignores. **The page contains the same confidential data as the CSV** (including date of birth and the last 4 digits of the SSN if the CSV has them), so treat it like the CSV and do not share or commit it. If you use `--out`, choose a location that git ignores.
