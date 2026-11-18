"""Paykings CSV export: one row per merchant, the same 70 columns as the Paykings sheet (preview_tool layout).

A file on disk is not encrypted, so sensitive values (SSN, last 4, licence, passport, account number) are left blank
unless include_sensitive is set on purpose. Columns the user decided not to collect stay as blank columns.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from . import fields, record as R
from .paykings_map import COLUMN_TO_SPEC, RECORD_COLUMNS, SENSITIVE_SPECS, SKIPPED_COLUMNS

_LAYOUT = json.loads((Path(__file__).resolve().parent.parent / "preview_tool" / "paykings_layout.json").read_text(encoding="utf-8"))
TEMPLATE_COLUMNS = [_LAYOUT["id_column"], _LAYOUT["status_column"]] + [c for st in _LAYOUT["steps"] for c in st["columns"]]

# A cell that starts like this would be run as a formula by a spreadsheet. "+1 (555)..." and "-5" are plain values.
_FORMULA = re.compile(r"^(?:[=@\t\r]|[+\-](?![\d\s.(]))")


def _cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if _FORMULA.match(s) else s


def row_for(rec: dict, include_sensitive: bool = False) -> dict:
    row = {}
    for col in TEMPLATE_COLUMNS:
        if col in RECORD_COLUMNS:
            row[col] = _cell(rec.get(RECORD_COLUMNS[col]))
            continue
        spec = COLUMN_TO_SPEC.get(col)
        if not spec or col in SKIPPED_COLUMNS or (spec in SENSITIVE_SPECS and not include_sensitive):
            row[col] = ""
            continue
        try:
            row[col] = _cell(R.get_field(rec, fields.spec_keys(spec))["value"])
        except R.RecordError:
            row[col] = ""
    return row


def render_csv(records: list[dict], include_sensitive: bool = False) -> str:
    out = io.StringIO(newline="")
    w = csv.DictWriter(out, fieldnames=TEMPLATE_COLUMNS, lineterminator="\r\n")
    w.writeheader()
    for rec in records:
        w.writerow(row_for(rec, include_sensitive))
    return out.getvalue()
