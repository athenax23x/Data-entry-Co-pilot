"""CSV export: a flat, read-only view of records (never a storage format). See README for the flattening rules."""
from __future__ import annotations

import csv
import io

from .record import primary_owner

ORIGINAL_COLUMNS = ["First Name", "Last Name", "Business Name", "Street Address", "City", "State", "ZIP",
                    "Email", "Phone", "EIN / Notes", "Status"]
REQUIRED_COLUMNS = ORIGINAL_COLUMNS[:9]          # EIN / Notes and Status are not mandatory
ENTITY_COLUMNS = ["Business Entity Type", "DBA Name"]
BUSINESS_COLUMNS = ["business_description", "refund_policy", "business_start_date", "state_of_formation", "website"]
PROCESSING_COLUMNS = ["mcc", "monthly_card_volume", "average_ticket", "high_ticket",
                      "card_present_percentage", "keyed_percentage", "ecommerce_percentage", "routing_number"]
OWNER_COLUMNS = ["date_of_birth", "ssn_last4", "ownership_percentage", "other_owners"]
PRODUCT_COLUMNS = ["products_and_services_description", "products_and_services_items"]
STATUS_COLUMNS = ["first_name_status", "last_name_status", "business_name_status", "dba_name_status",
                  "business_entity_type_status", "street_address_status", "city_status", "state_status",
                  "zip_status", "email_status", "phone_status", "ein_status"]
FIXED_COLUMNS = (["merchant_id"] + ORIGINAL_COLUMNS + ENTITY_COLUMNS + BUSINESS_COLUMNS + PROCESSING_COLUMNS
                 + OWNER_COLUMNS + PRODUCT_COLUMNS + STATUS_COLUMNS)


def _v(f):
    return f["value"]


def _fmt(v) -> str:
    return "" if v is None else str(v)


def _owner_text(o) -> str:
    name = " ".join(x for x in (_v(o["first_name"]), _v(o["last_name"])) if x)
    pct = _v(o["ownership_percentage"])
    return (name or o["owner_id"]) + (f" ({pct}%)" if pct is not None else "")


def row_for(rec: dict) -> dict:
    o = primary_owner(rec)
    bi, ba, ci, pi, ps = (rec[k] for k in ("business_information", "business_address", "contact_information",
                                             "processing_information", "products_and_services"))
    ein, rt = _v(rec["ein"]), _v(pi["routing_number"])
    row = {
        "merchant_id": rec["merchant_id"],
        "First Name": _v(o["first_name"]), "Last Name": _v(o["last_name"]),
        "Business Name": _v(bi["legal_business_name"]),
        "Street Address": _v(ba["street_address"]), "City": _v(ba["city"]), "State": _v(ba["state"]),
        "ZIP": _v(ba["zip"]), "Email": _v(ci["email"]), "Phone": _v(ci["phone"]),
        "EIN / Notes": "; ".join(p for p in (f"EIN: {ein}" if ein else "", f"Routing: {rt}" if rt else "") if p),
        "Status": rec["record_status"],
        "Business Entity Type": _v(rec["business_entity_type"]) or "unknown",
        "DBA Name": _v(bi["dba_name"]),
        "date_of_birth": _v(o["date_of_birth"]),
        "ssn_last4": _v(o["ssn_last4"]),
        "ownership_percentage": _v(o["ownership_percentage"]),
        "other_owners": "; ".join(_owner_text(x) for x in rec["personal_information"]["owners"] if x is not o),
        "products_and_services_description": _v(ps["description"]),
        "products_and_services_items": "; ".join(str(_v(i)) for i in ps["items"] if _v(i) is not None),
        "first_name_status": o["first_name"]["status"], "last_name_status": o["last_name"]["status"],
        "business_name_status": bi["legal_business_name"]["status"], "dba_name_status": bi["dba_name"]["status"],
        "business_entity_type_status": rec["business_entity_type"]["status"],
        "street_address_status": ba["street_address"]["status"], "city_status": ba["city"]["status"],
        "state_status": ba["state"]["status"], "zip_status": ba["zip"]["status"],
        "email_status": ci["email"]["status"], "phone_status": ci["phone"]["status"],
        "ein_status": rec["ein"]["status"],
    }
    for c in BUSINESS_COLUMNS:
        row[c] = _v(bi[c])
    for c in PROCESSING_COLUMNS:
        row[c] = _v(pi[c])
    for key, f in rec.get("custom_fields", {}).items():
        row[f"custom.{key}"] = _v(f)
    for c in REQUIRED_COLUMNS:
        if row[c] is None or row[c] == "":
            row[c] = "[MISSING]"
    return row


def render_csv(records: list[dict]) -> str:
    rows = [row_for(r) for r in records]
    custom = sorted({k for r in rows for k in r if k.startswith("custom.")})
    columns = FIXED_COLUMNS + custom
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(columns)
    for r in rows:
        w.writerow([_fmt(r.get(c)) for c in columns])
    return buf.getvalue()
