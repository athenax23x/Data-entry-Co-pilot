# Test fixtures

Everything in this folder is **made up**. Nothing here may ever be real merchant, owner or customer data.

Rules (enforced by `tests/test_fixtures.py`, which scans every file in this folder):

- Emails only use `example.com`, `example.org` or `example.net`.
- Phone numbers only use the fictional `555` range (area code or exchange).
- EIN `12-3456789` / `98-7654321` and routing number `123456789` are the only allowed tax and bank numbers.
- No Social Security number (not even partly masked), no card number, no security code, no password.
- Names are obvious placeholders (Alex Sample, Pat Example, Blake Demo, ...).

Files:

| File | What it is |
|---|---|
| `sample_record.json` | One complete record in the `schema.json` structure (with a verified value in conflict). |
| `sample_export.csv` | The exact CSV that `EXPORT CSV` produces for that record (golden file). |
| `sample_input.txt` | Messy one-line inputs for `NEW MERCHANT`. |

`.gitignore` ignores `*.csv`, `*.merchants.json` and `data/` everywhere **except** `tests/fixtures/*.csv`. If you add a fixture, keep it fake and keep it directly in this folder.
