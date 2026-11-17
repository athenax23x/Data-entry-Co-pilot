"""Record operations. Every record is exactly the structure in schema.json (no second layout)."""
from __future__ import annotations

from datetime import datetime, timezone

STATUSES = ("inferred", "verified", "missing", "conflict", "needs_review")
SOLE = "sole_proprietorship"


class RecordError(Exception):
    pass


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_field() -> dict:
    return {"value": None, "status": "missing", "source_context": None, "source_document": None}


def new_owner(n: int, primary: bool) -> dict:
    return {
        "owner_id": f"OWN-{n}", "is_primary_owner": primary,
        "first_name": empty_field(), "last_name": empty_field(), "date_of_birth": empty_field(),
        "ssn_last4": empty_field(), "title": empty_field(), "ownership_percentage": empty_field(),
    }


def new_record(merchant_id: str, now: str) -> dict:
    f = empty_field
    return {
        "schema_version": 1,
        "merchant_id": merchant_id,
        "record_status": "Incomplete",
        "business_entity_type": f(),
        "personal_information": {"owners": [new_owner(1, True)]},
        "business_information": {k: f() for k in (
            "legal_business_name", "dba_name", "business_description", "refund_policy",
            "business_start_date", "state_of_formation", "website")},
        "business_address": {k: f() for k in ("street_address", "city", "state", "zip")},
        "contact_information": {"email": f(), "phone": f()},
        "ein": f(),
        "processing_information": {k: f() for k in (
            "mcc", "monthly_card_volume", "average_ticket", "high_ticket",
            "card_present_percentage", "keyed_percentage", "ecommerce_percentage", "routing_number")},
        "products_and_services": {"description": f(), "items": []},
        "sources": [],
        "conflicts": [],
        "created_at": now,
        "updated_at": now,
    }


def add_source(rec: dict, source_type: str, now: str, label: str | None = None) -> str:
    sid = f"SRC-{len(rec['sources']) + 1:03d}"
    rec["sources"].append({"source_id": sid, "source_type": source_type, "label": label, "received_at": now})
    return sid


def pointer(keys) -> str:
    return "/" + "/".join(str(k) for k in keys)


def spec_key(keys) -> str:
    parts = []
    for k in keys:
        if isinstance(k, int):
            parts[-1] += "[]"
        else:
            parts.append(k)
    return ".".join(parts)


def get_field(rec: dict, keys) -> dict:
    node = rec
    for k in keys:
        try:
            node = node[k]
        except (KeyError, IndexError, TypeError):
            raise RecordError(f"No such field: {pointer(keys)}")
    return node


def ensure_owner(rec: dict, idx: int) -> None:
    owners = rec["personal_information"]["owners"]
    if idx == len(owners):
        owners.append(new_owner(idx + 1, False))
    elif idx > len(owners):
        raise RecordError(f"There are {len(owners)} owner(s); owners[{idx}] does not exist yet "
                          f"(next new owner is owners[{len(owners)}]).")


def ensure_custom(rec: dict, keys) -> None:
    if keys and keys[0] == "custom_fields":
        rec.setdefault("custom_fields", {}).setdefault(keys[1], empty_field())


def _set(f: dict, value, status: str, ctx, sid, now: str) -> None:
    f["value"], f["status"] = value, status
    f["source_context"], f["source_document"] = ctx, sid
    f["updated_at"] = now


def push_history(f: dict, now: str) -> None:
    if f["value"] is None and f["status"] == "missing":
        return
    f.setdefault("history", []).append({
        "value": f["value"], "status": f["status"], "source_context": f["source_context"],
        "source_document": f["source_document"], "replaced_at": now,
    })


def _open_conflict(rec: dict, keys, f: dict, value, ctx, sid, now: str) -> None:
    ptr = pointer(keys)
    c = next((c for c in rec["conflicts"]
              if c["field_path"] == ptr and c["resolution"]["state"] == "open"), None)
    cand = {"value": value, "source_context": ctx, "source_document": sid, "detected_at": now}
    if c is None:
        rec["conflicts"].append({
            "conflict_id": f"CNF-{len(rec['conflicts']) + 1:03d}",
            "field_path": ptr,
            "current_value": f["value"],
            "current_status": f["status"] if f["status"] != "conflict" else "inferred",
            "candidates": [cand],
            "resolution": {"state": "open"},
        })
    elif value != c["current_value"] and all(x["value"] != value for x in c["candidates"]):
        c["candidates"].append(cand)
    # the value in place (e.g. a verified one) is never touched; only the status flags the conflict
    f["status"] = "conflict"
    f["updated_at"] = now


def merge_value(rec, keys, value, status, ctx, sid, now, weak=False) -> str:
    """Merge one extracted value. Returns: filled | unchanged | conflict | review | ignored."""
    f = get_field(rec, keys)
    cur = f["value"]
    if value is None:                       # unclear text: keep raw excerpt, never disturb a real value
        if cur is None:
            _set(f, None, "needs_review", ctx, sid, now)
            return "review"
        return "ignored"
    if cur is None:
        _set(f, value, status, ctx, sid, now)
        return "review" if status == "needs_review" else "filled"
    if cur == value:
        return "unchanged"
    if weak:
        return "ignored"
    _open_conflict(rec, keys, f, value, ctx, sid, now)
    return "conflict"


def merge_list_item(rec, keys, value, ctx, sid, now) -> str:
    items = rec["products_and_services"]["items"]
    if any(i["value"] == value for i in items):
        return "unchanged"
    f = empty_field()
    _set(f, value, "inferred", ctx, sid, now)
    items.append(f)
    return "filled"


def _resolve_conflict(rec: dict, keys, chosen, now: str) -> None:
    ptr = pointer(keys)
    for c in rec["conflicts"]:
        if c["field_path"] == ptr and c["resolution"]["state"] == "open":
            c["resolution"] = {"state": "resolved", "resolved_value": chosen, "resolved_at": now}


def user_set(rec, keys, value, ctx, sid, now):
    """Explicit user value: becomes verified. Returns the (old_value, old_status)."""
    f = get_field(rec, keys)
    old = (f["value"], f["status"])
    push_history(f, now)
    _set(f, value, "verified", ctx, sid, now)
    _resolve_conflict(rec, keys, value, now)
    return old


def user_confirm(rec, keys, ctx, sid, now):
    f = get_field(rec, keys)
    if f["status"] == "conflict":
        raise RecordError("This field is in conflict. Choose the value to keep with UPDATE FIELD <field> = <value>.")
    if f["value"] is None:
        raise RecordError("There is no value to confirm. Give a value with UPDATE FIELD <field> = <value>.")
    old = (f["value"], f["status"])
    push_history(f, now)
    _set(f, f["value"], "verified", ctx, sid, now)
    return old


def user_clear(rec, keys, now):
    f = get_field(rec, keys)
    old = (f["value"], f["status"])
    push_history(f, now)
    f["value"], f["status"] = None, "missing"
    f["source_context"] = f["source_document"] = None
    f["updated_at"] = now
    _resolve_conflict(rec, keys, None, now)
    return old


def primary_owner(rec: dict) -> dict:
    owners = rec["personal_information"]["owners"]
    return next((o for o in owners if o.get("is_primary_owner")), owners[0])


def needed_fields(rec: dict):
    """(label, field) pairs that decide record_status."""
    o = primary_owner(rec)
    bi = rec["business_information"]
    legal, dba = bi["legal_business_name"], bi["dba_name"]
    name = legal
    if rec["business_entity_type"]["value"] == SOLE and legal["value"] is None and dba["value"] is not None:
        name = dba                          # a sole proprietor's DBA satisfies the business-name need
    ba, ci = rec["business_address"], rec["contact_information"]
    return [
        ("personal_information.owners[0].first_name", o["first_name"]),
        ("personal_information.owners[0].last_name", o["last_name"]),
        ("business_information.legal_business_name", name),
        ("business_address.street_address", ba["street_address"]),
        ("business_address.city", ba["city"]),
        ("business_address.state", ba["state"]),
        ("business_address.zip", ba["zip"]),
        ("contact_information.email", ci["email"]),
        ("contact_information.phone", ci["phone"]),
    ]


def compute_record_status(rec: dict) -> str:
    statuses = [f["status"] for _, f in needed_fields(rec)]
    if all(s in ("verified", "inferred") for s in statuses):
        return "Complete"
    if any(s in ("conflict", "needs_review") for s in statuses):
        return "Needs Review"
    return "Incomplete"


def touch(rec: dict, now: str) -> None:
    rec["updated_at"] = now
    rec["record_status"] = compute_record_status(rec)
