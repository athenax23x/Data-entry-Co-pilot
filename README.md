# Data-entry-Co-pilot — Merchant Context Notebook

Two parts, kept deliberately separate:

| Part | What it is | Where |
|---|---|---|
| **Quick Parser (Mode 1)** | An AI prompt that turns messy US merchant text into one 11-column table. No code. | `instructions.md` (unchanged original) |
| **Merchant Notebook (Mode 2)** | A local command-line app that builds merchant records step by step, tracks status and source for every value, saves JSON and exports CSV. | `merchant_notebook/` |

`schema.json` (JSON Schema Draft 2020-12) defines the one and only record structure. The app, `instructions.md` and the tests all follow it, and a test fails if they drift apart.

## Run it

Requires Python 3.10+ (tested on 3.12). Run everything from the project root.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # jsonschema[format] and pytest
python -m merchant_notebook              # data folder: ./merchant_data
python -m merchant_notebook --data-dir ~/some/other/folder
```

You get a prompt. The session lives only in memory: **nothing is written to disk until you run `SAVE MERCHANT` or `EXPORT CSV`**, and anything unsaved is lost when you leave (Ctrl-D). The nine commands are exactly the ones in `instructions.md`:

| Command | What it does |
|---|---|
| `NEW MERCHANT <text>` | Start a record (new `merchant_id`) and extract what it can from the text. |
| `ADD CONTEXT [merchant_id] <text>` | Merge more text into a record. Conflicts are recorded, never overwritten. |
| `UPDATE FIELD [merchant_id] <field> = <value>` | Set a value (becomes `verified`). Also `= confirm` and `= missing`. |
| `SHOW MERCHANT [merchant_id]` | Show one record: value, status, source for every field, plus open conflicts. |
| `SHOW MISSING FIELDS [merchant_id]` | List what is still needed. |
| `SAVE MERCHANT [merchant_id]` | Validate against `schema.json`, then write `<data-dir>/<merchant_id>.json`. |
| `LOAD MERCHANT <merchant_id or file path>` | Load and validate a saved record. |
| `EXPORT CSV [merchant_id or ALL]` | Write a CSV under `<data-dir>/exports/`. |
| `CLEAR SESSION` | Forget everything in memory (asks first if something is unsaved). Never deletes files. |

Example (all data here is fake):

```
mcn> NEW MERCHANT name: Alex Sample; sole proprietor; dba Sample Mobile Detailing; 88 Pine Rd Tampa FL 33602; alex@example.com
mcn> UPDATE FIELD phone = 555.010.0187
mcn> ADD CONTEXT call him at 555-010-0199
mcn> SHOW MERCHANT
mcn> SAVE MERCHANT
```

The second phone number does not replace the one you confirmed: the field becomes `conflict`, the confirmed value stays, and the new one is kept as a candidate in `conflicts`.

Field names for `UPDATE FIELD` are the paths in `schema.json` (for example `contact_information.phone`), or a short name when it is unique (`phone`, `city`, `ein`). Owner fields mean the primary owner unless you write `owners[1].last_name` (indexes start at 0; `owners[N]` can add the next owner). Add products with `items[+] = car wash`. Extra fields go in `custom_fields.<key>`.

## What the extraction does (and does not do)

Extraction is rule-based and deliberately cautious. It finds emails, phone numbers, EINs, 9-digit routing numbers (with a "routing" label), US street addresses (needs a street type such as St, Rd, Ave), websites, DBA names, business names that end in LLC/Inc/Corp/etc., the eight entity types, and `label: value` pairs such as `name: Alex Sample` or `mcc: 5812`. Values it is unsure about are stored as `needs_review`, never guessed:

- A leading unlabeled personal name is `needs_review`; a labeled name is `inferred`.
- A business name guessed from lowercase or a long run of words is `needs_review`.
- A bare 9-digit number (EIN or routing?) is `needs_review`.
- A P.O. Box street address is `needs_review`.

Use `UPDATE FIELD` for anything it misses. Only you can make a value `verified`.

Card numbers, card security codes, full Social Security numbers, passwords and one-time codes are removed from text before anything is stored, and the app tells you so. For an SSN, only the last 4 digits can be stored (`ssn_last4`, for example `UPDATE FIELD ssn_last4 = 1234` or `ssn last 4: 1234`). A full SSN is refused in every command and never truncated. An unlabeled bare 9-digit number is not treated as an SSN (it could be an EIN or routing number), so do not type a full SSN without dashes or a label.

## Where data is stored and how it is protected

- **Default folder:** `./merchant_data/` (relative to where you start the app), or `--data-dir`.
  - Records: `merchant_data/<merchant_id>.json` — one record per file, exactly the `schema.json` structure.
  - Exports: `merchant_data/exports/merchants_<YYYYMMDD-HHMMSS>.csv`.
- Files are written with owner-only permissions (`0600`; folders `0700`) through a temp file and an atomic rename, then read back. If any step fails, the command says `NOT saved` / `NOT exported`; it never reports success otherwise. On Windows the Unix mode `0600` is not enforced, so access to saved files follows the permissions (ACL) of your Windows user profile instead.
- Overwriting an existing record file asks first.
- Everything is local. Nothing is sent anywhere by this app. (If you also use an AI model for Quick Parser or Notebook prompts, that model may receive what you paste.)
- **`.gitignore`** keeps merchant data out of git: `data/`, `merchants/`, `merchant_data/`, `*.merchants.json` and `*.csv`. `schema.json` and `instructions.md` are not ignored. The rules also catch same-named folders deeper in the tree (for example `src/data/`). **One exception:** CSV files directly in `tests/fixtures/` are not ignored (`!tests/fixtures/*.csv`), so fake sample exports can be committed; CSVs anywhere else, in sub-folders of `tests/fixtures/`, and every `*.merchants.json` and `data/` folder stay ignored. If you point `--data-dir` somewhere inside the repo that is not covered by these rules, add it to `.gitignore` first.
- Code, tests and this README use only fake data: `example.com/.org/.net` emails and 555 phone numbers. `tests/fixtures/` holds the fake samples (see its README). A test scans **every file** there, of any type, and also rejects real-looking emails and phones, Social Security and card-number patterns, and any EIN or routing number that is not one of the known fakes (`12-3456789`, `98-7654321`, `123456789`).

## CSV export: how the nested record is flattened

One row per record; RFC 4180 quoting (CRLF line ends, UTF-8); a CSV is a read-only view and is never loaded back. The row is built from the record like this:

| Column(s) | Comes from |
|---|---|
| `merchant_id` | `merchant_id` |
| First Name, Last Name | the **primary** owner's `first_name`, `last_name` |
| Business Name | `business_information.legal_business_name` (legal name only) |
| Street Address, City, State, ZIP | `business_address.*` |
| Email, Phone | `contact_information.*` |
| EIN / Notes | `EIN: <ein>; Routing: <routing_number>` (only the parts that exist) |
| Status | `record_status` |
| Business Entity Type, DBA Name | `business_entity_type.value` (`unknown` if empty), `business_information.dba_name` |
| business_description, refund_policy, business_start_date, state_of_formation, website | `business_information.*` |
| mcc … routing_number (8 columns) | `processing_information.*` |
| date_of_birth | the primary owner's `date_of_birth` (`MM/DD/YYYY`) |
| ssn_last4 | the primary owner's `ssn_last4` (4 digits only) |
| ownership_percentage | the primary owner's `ownership_percentage` |
| other_owners | every other owner as `First Last (NN%)`, joined with `; ` |
| products_and_services_description, products_and_services_items | `products_and_services.description`; the items joined with `; ` |
| first_name_status … ein_status (12 columns) | the `status` of the matching field |
| `custom.<key>` (after all others) | `custom_fields.<key>.value`, one column per key used by any exported record |

Rules: empty values in the required original columns (everything except `EIN / Notes` and `Status`) are written as `[MISSING]`; every other empty value is blank. A field in `conflict` exports its kept value with `conflict` in its status column — competing candidates, sources and history are not exported (they stay in the JSON). `EXPORT CSV` with no argument exports the active merchant only; `ALL` combines every record in the session.

**Sensitive fields in the CSV.** The CSV is plain text. It **does** include the primary owner's `date_of_birth` and `ssn_last4` (the last 4 digits only, by design). It can never contain a full Social Security number, because a full SSN is never stored (see above). Treat every exported CSV like the JSON records: it stays on your computer, under `merchant_data/exports/`, which is ignored by git. If you do not want these two columns in a file you share, delete them from the CSV before sharing it.

## Local API (M3)

```bash
pip install -r requirements.txt
python -m merchant_notebook.api [--data-dir merchant_data] [--no-browser]
```

Listens on `127.0.0.1:8765` only (the port is fixed; nothing binds to `0.0.0.0`). Data is `<data-dir>/merchants.db` (SQLite, sensitive values encrypted; key from Windows DPAPI, see `keys.py`). Safeguards: only `127.0.0.1:8765` / `localhost:8765` as Host (else 400); a POST/PATCH/DELETE with a foreign `Origin` gets 403; **every `/api` request needs the header `X-MCN-Token`**, a random token made at each start and embedded in the page served at `/` (`<meta name="mcn-token">`), else 401. The access log is off and error messages never echo submitted values. SSN, last 4, licence, passport and account numbers are shown in full by the API (local use only) and never written to logs or error messages.

Endpoints: `GET /api/health`, `GET /api/merchants?q=`, `POST /api/merchants` (`{text?}`), `GET /api/merchants/{id}`, `PATCH /api/merchants/{id}/fields/{path}` (`{expected_version, action: set|confirm|missing, value}`), `POST /api/merchants/{id}/context` (`{expected_version, text}`), `POST /api/merchants/{id}/conflicts/{cid}/resolve` (`{expected_version, value}`). Every write needs the `version` last read: 409 if the record changed. Errors: 404 not found, 409 stale, 422 invalid record or request, 400 refused change, 500 generic.

## Web UI (M4)

`python -m merchant_notebook.api` also serves the UI at `http://127.0.0.1:8765/`: merchant list and search, new merchant from pasted text, and a workspace with the seven Paykings steps (value, status, source, Ubah / Confirm / Kosongkan), "Tambah konteks" and the conflict panel. UI text is Indonesian; field labels are the Paykings column names. Values are shown in full (local use only). The page reads the session token from `<meta name="mcn-token">`, keeps it in memory, and never uses localStorage, the console or the URL for values. A Content-Security-Policy allows only this server: no CDN, fonts or scripts from the internet.

The built UI is committed in `merchant_notebook/api/static/`, so **Node.js is needed only to rebuild it**:

```bash
cd web && npm ci && npm test && npm run build     # writes ../merchant_notebook/api/static/
python tools/gen_layout.py                         # only after paykings_layout.json / paykings_map.py change
```

## Claude bridge (M5): copy-paste, no API

In a merchant's workspace, the tab **Jembatan Claude** lets you use Claude Pro without any API or extra cost. The app never contacts Claude: it prepares text, you paste it into the Claude chat, and you paste the JSON answer back.

1. **Siapkan**: paste the source text. Cards, security codes, passwords, one-time codes, full SSNs are removed; bank account numbers, driver licence / SIM numbers, passport numbers and the last 4 of an SSN become `[DISAMARKAN]` (`merchant_notebook/bridge/mask.py`). Routing numbers are kept (public, and a field Claude may fill). The prompt (`bridge/prompt.md`) lists only the Paykings fields that are not sensitive.
2. **Salin** the prompt into Claude, copy its JSON answer.
3. **Periksa**: the app checks every proposal in code (`bridge/check.py`): JSON shape and size (max 50 KB), allowed path (sensitive paths refused), `evidence` must be in the source text (spaces and case ignored), the value must pass the field's normalizer and schema_v2, an existing value is never overwritten (a different one becomes a conflict), and an ambiguous date (`06/02/2004`, or `"ambiguous": true`) is stored as `needs_review`.
4. **Terapkan** the proposals you tick. They are stored as `inferred` with the evidence quote (max 200 characters) as source; the source text itself is never stored. The server checks the answer again on apply.

SSN, last 4 of SSN, driver licence, passport and account number are never sent to Claude and never filled from its answer: type them in the workspace. Endpoints: `POST /api/bridge/prepare`, `POST /api/merchants/{id}/bridge/preview`, `POST /api/merchants/{id}/bridge/apply`.

## Tests

```bash
pytest
```

347 Python tests on Linux (plus 21 Vitest tests in `web/`), no network (a few Unix-only or Windows-only checks are skipped depending on the platform). They cover: confirmed values are never overwritten; nothing is saved unless asked; failed saves and exports are reported as failures; schema validation with real format checking (email, date, URI, date-time); the eight entity types and the sole-proprietor rules; privacy (including SSN: last 4 only); CSV flattening; the fake-data fixtures and the `.gitignore` rules around them; sync between the app, `instructions.md` and `schema.json`; and a regression test that pins the Quick Parser text and its 11 columns.

## Layout

```
instructions.md         AI prompts: Quick Parser (Mode 1) and Notebook (Mode 2)
schema.json             the record structure (single source of truth)
merchant_notebook/      the CLI app (store, commands, record logic, extraction, CSV)
tests/                  pytest suite
tests/fixtures/         fake sample data only (record, CSV export, messy inputs), scanned by a test
```
