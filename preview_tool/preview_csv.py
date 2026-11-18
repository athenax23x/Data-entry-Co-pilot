"""Turn a CSV exported by the Merchant Notebook into one self-contained, readable HTML page.

Read-only with respect to merchant data: it reads the CSV and writes only the HTML file you ask for.
Standard library only. The page has no scripts, no links and no external resources (all CSS is inline).
"""
from __future__ import annotations

import argparse
import csv
import html
import sys
from pathlib import Path

DEFAULT_OUT_DIR = Path("merchant_data") / "previews"
MISSING = "[MISSING]"
ID_COL = "merchant_id"
RECORD_STATUS_COL = "Status"

# CSV column -> the *_status column that describes it (shown as a small badge, never as a column of its own)
STATUS_OF = {
    "First Name": "first_name_status", "Last Name": "last_name_status",
    "Business Name": "business_name_status", "DBA Name": "dba_name_status",
    "Business Entity Type": "business_entity_type_status",
    "Street Address": "street_address_status", "City": "city_status", "State": "state_status",
    "ZIP": "zip_status", "Email": "email_status", "Phone": "phone_status", "EIN / Notes": "ein_status",
}
STATUS_COLUMNS = set(STATUS_OF.values())

# Core columns first, in this order.
CORE_GROUPS = (
    ("Identity", ("First Name", "Last Name", "Business Name", "DBA Name", "Business Entity Type")),
    ("Address", ("Street Address", "City", "State", "ZIP")),
    ("Contact", ("Email", "Phone")),
    ("EIN / Notes", ("EIN / Notes",)),
)
CORE_COLUMNS = {c for _, cols in CORE_GROUPS for c in cols}

# Badge CSS classes come only from these whitelists, never from CSV text.
FIELD_BADGE = {"verified": "b-verified", "inferred": "b-inferred", "needs_review": "b-review",
               "missing": "b-missing", "conflict": "b-conflict"}
RECORD_BADGE = {"Complete": "b-verified", "Incomplete": "b-missing", "Needs Review": "b-review"}
LABELS = {"ssn_last4": "SSN last 4", "mcc": "MCC", "ein": "EIN", "other_owners": "Other owners",
          "date_of_birth": "Date of birth"}

CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#1c2430;--muted:#5b6675;--line:#e1e5ea;--accent:#2f5d9e;
--verified-bg:#dff5e6;--verified-fg:#14532d;--inferred-bg:#e0ecff;--inferred-fg:#1e3a8a;
--review-bg:#fff0cc;--review-fg:#7a4b00;--conflict-bg:#fde2e2;--conflict-fg:#8a1c1c;
--missing-bg:#eceff3;--missing-fg:#445064;--other-bg:#eceff3;--other-fg:#445064}
@media (prefers-color-scheme:dark){:root{--bg:#14181f;--card:#1d232d;--ink:#e8ecf2;--muted:#9aa6b6;--line:#2c3542;
--accent:#8fb4ee;--verified-bg:#143a24;--verified-fg:#a6e8bf;--inferred-bg:#172c55;--inferred-fg:#b5ceff;
--review-bg:#4a3510;--review-fg:#ffd98a;--conflict-bg:#521c1c;--conflict-fg:#ffb4b4;
--missing-bg:#2a3340;--missing-fg:#b6c1d1;--other-bg:#2a3340;--other-fg:#b6c1d1}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);line-height:1.45;
font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
main{max-width:88rem;margin:0 auto;padding:1rem}
.page h1{margin:.2rem 0;font-size:1.35rem}
.page p,.foot{color:var(--muted);font-size:.85rem;margin:.2rem 0}
.grid{display:grid;gap:1rem;margin-top:1rem;grid-template-columns:repeat(auto-fill,minmax(min(100%,24rem),1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:.75rem;padding:1rem;min-width:0}
.card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:.75rem;
border-bottom:1px solid var(--line);padding-bottom:.6rem;margin-bottom:.4rem}
.card-head h2{margin:0;font-size:1.1rem;overflow-wrap:anywhere}
.mid{margin:.15rem 0 0;color:var(--muted);font-size:.78rem;overflow-wrap:anywhere}
.group{margin:.6rem 0 0}
.group h3{margin:0 0 .25rem;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--accent)}
dl{margin:0}
.row{display:grid;grid-template-columns:minmax(6.5rem,10.5rem) 1fr;gap:.5rem;padding:.2rem 0;
border-bottom:1px dotted var(--line)}
.row:last-child{border-bottom:0}
dt{color:var(--muted);font-size:.85rem}
dd{margin:0;overflow-wrap:anywhere;min-width:0}
.value{white-space:pre-wrap}
.missing-value{background:#ffe3e3;color:#a10000;border:1px dashed #d33;border-radius:.3rem;padding:0 .35rem;
font-weight:700;letter-spacing:.02em}
@media (prefers-color-scheme:dark){.missing-value{background:#5a1d1d;color:#ffb4b4;border-color:#ff7b7b}}
.badge{display:inline-block;margin-left:.35rem;padding:.02rem .45rem;border-radius:999px;font-size:.7rem;
font-weight:600;vertical-align:middle;white-space:nowrap;background:var(--other-bg);color:var(--other-fg)}
.b-verified{background:var(--verified-bg);color:var(--verified-fg)}
.b-inferred{background:var(--inferred-bg);color:var(--inferred-fg)}
.b-review{background:var(--review-bg);color:var(--review-fg)}
.b-conflict{background:var(--conflict-bg);color:var(--conflict-fg)}
.b-missing{background:var(--missing-bg);color:var(--missing-fg)}
.record{margin-left:0;font-size:.78rem;padding:.15rem .6rem}
details{margin-top:.7rem;border-top:1px solid var(--line);padding-top:.5rem}
summary{cursor:pointer;color:var(--accent);font-size:.85rem}
@media (max-width:480px){main{padding:.6rem}.row{grid-template-columns:1fr;gap:0}
.card-head{flex-direction:column}.card{padding:.8rem}}
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def label_for(column: str) -> str:
    if column in LABELS:
        return LABELS[column]
    if column in CORE_COLUMNS:
        return column
    text = column.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def _badge(text: str, classes: dict, extra: str = "") -> str:
    text = text.strip()
    if not text:
        return ""
    cls = classes.get(text, "")
    return f'<span class="badge {cls}{extra}">{esc(text)}</span>'


def _row(label: str, value: str, status: str = "") -> str:
    value = value.strip() if isinstance(value, str) else ""
    if not value:
        return ""                                            # empty columns are hidden
    shown = (f'<span class="value missing-value">{esc(value)}</span>' if value == MISSING
             else f'<span class="value">{esc(value)}</span>')
    return (f'<div class="row"><dt>{esc(label)}</dt><dd>{shown}{_badge(status, FIELD_BADGE)}</dd></div>')


def _title(row: dict, index: int) -> str:
    name = " ".join(p for p in (row.get("First Name", ""), row.get("Last Name", "")) if p and p != MISSING)
    for candidate in (name, row.get("Business Name", ""), row.get("DBA Name", ""), row.get(ID_COL, "")):
        if candidate and candidate.strip() and candidate != MISSING:
            return candidate.strip()
    return f"Merchant {index}"


def render_card(row: dict, index: int) -> str:
    parts = ['<article class="card">', '<header class="card-head"><div>',
             f"<h2>{esc(_title(row, index))}</h2>"]
    if row.get(ID_COL, "").strip():
        parts.append(f'<p class="mid">{esc(row[ID_COL].strip())}</p>')
    parts.append("</div>")
    parts.append(_badge(row.get(RECORD_STATUS_COL, ""), RECORD_BADGE, " record"))
    parts.append("</header>")
    for title, columns in CORE_GROUPS:
        rows = "".join(_row(label_for(c), row.get(c, ""), row.get(STATUS_OF.get(c, ""), "")) for c in columns)
        if rows:
            parts.append(f'<section class="group"><h3>{esc(title)}</h3><dl>{rows}</dl></section>')
    extras = "".join(
        _row(label_for(c), v) for c, v in row.items()
        if c and c not in CORE_COLUMNS and c not in STATUS_COLUMNS and c not in (ID_COL, RECORD_STATUS_COL))
    if extras:
        parts.append(f'<details><summary>More details</summary><dl>{extras}</dl></details>')
    parts.append("</article>")
    return "".join(parts)


def read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("the CSV file has no header row")
        rows = []
        for raw in reader:
            rows.append({k: (v if isinstance(v, str) else "") for k, v in raw.items() if k is not None})
        return rows


def render_page(rows: list[dict], source_name: str) -> str:
    cards = "".join(render_card(r, i) for i, r in enumerate(rows, 1))
    count = len(rows)
    noun = "merchant" if count == 1 else "merchants"
    body = cards or '<p class="foot">The CSV has no data rows.</p>'
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
        f"<title>Merchant preview: {esc(source_name)}</title><style>{CSS}</style></head><body><main>"
        f'<header class="page"><h1>Merchant preview</h1><p>{esc(source_name)} · {count} {noun}</p></header>'
        f'<div class="grid">{body}</div>'
        '<p class="foot">Contains confidential merchant data. Generated locally from the CSV; '
        "nothing was loaded from the internet.</p>"
        "</main></body></html>\n"
    )


def default_out(csv_path: Path) -> Path:
    return DEFAULT_OUT_DIR / (csv_path.stem + ".html")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="preview_tool", description="Make a readable HTML page from an exported CSV.")
    p.add_argument("csv_path", help="CSV file produced by EXPORT CSV")
    p.add_argument("--out", help=f"HTML file to write (default: {DEFAULT_OUT_DIR}/<csv name>.html)")
    args = p.parse_args(argv)

    src = Path(args.csv_path)
    out = Path(args.out) if args.out else default_out(src)
    if out.suffix.lower() not in (".html", ".htm"):
        print(f"Error: the output file must end in .html (got {out}); nothing was written.", file=sys.stderr)
        return 2
    try:
        same = out.resolve() == src.resolve()
    except OSError:
        same = False
    if same:
        print("Error: the output file is the same as the input CSV; nothing was written.", file=sys.stderr)
        return 2
    try:
        rows = read_rows(src)
    except (OSError, ValueError, csv.Error, UnicodeDecodeError) as e:
        print(f"Error: cannot read {src}: {e}", file=sys.stderr)
        return 2
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_page(rows, src.name), encoding="utf-8")
    except OSError as e:
        print(f"Error: could not write {out}: {e.strerror or e}", file=sys.stderr)
        return 1
    print(f"Wrote {out} ({len(rows)} {'merchant' if len(rows) == 1 else 'merchants'})")
    return 0
