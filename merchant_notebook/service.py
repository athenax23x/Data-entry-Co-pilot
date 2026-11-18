"""Service layer: the merchant operations, with no text-command parsing and no session state.

The CLI (commands.py) parses typed commands and keeps the session. A web API (later milestone) calls these same
functions. Every function takes a record (a dict, see record.py) and a timestamp string, changes the record in place,
and returns plain results. Nothing here reads or writes files.
"""
from __future__ import annotations

from . import extract as X, record as R
from .fields import FieldError, normalizer_for, resolve_target


class CommandError(Exception):
    """A request that cannot be done. The message says why, in plain words (shown to the user as-is)."""


def show(v) -> str:
    return "—" if v is None else str(v)


def apply_extraction(rec: dict, text: str, sid: str, now: str):
    """Extract values from text and merge them into rec. Returns (extraction, tally of outcomes by field path)."""
    ex = X.extract(text)
    tally = {"filled": [], "unchanged": [], "conflict": [], "review": [], "ignored": []}
    for it in ex.items:
        if it.list_item:
            out = R.merge_list_item(rec, it.keys, it.value, it.context, sid, now)
        else:
            out = R.merge_value(rec, it.keys, it.value, it.status, it.context, sid, now, it.weak)
        tally[out].append(R.pointer(it.keys))
    return ex, tally


def check_same_merchant(rec: dict, text: str) -> None:
    """Refuse to merge text that names a different business (different legal name AND different EIN)."""
    ex = X.extract(text)
    cur_name = rec["business_information"]["legal_business_name"]["value"]
    cur_ein = rec["ein"]["value"]
    new_name = next((i.value for i in ex.items if i.keys[-1] == "legal_business_name" and i.value), None)
    new_ein = next((i.value for i in ex.items if i.keys == ("ein",) and i.value), None)
    if cur_name and cur_ein and new_name and new_ein and new_name != cur_name and new_ein != cur_ein:
        raise CommandError("This looks like a different merchant (different business name and EIN). "
                           "Nothing was merged. Use NEW MERCHANT for it.")


def resolve_path(rec: dict, field_txt: str, ensure_list_slot=None):
    """Turn a field name into a path. Creates the owner / custom / item slot when that is what was named.

    Returns (keys, label). Raises FieldError or RecordError when the field or slot cannot be used.
    """
    keys = resolve_target(field_txt)
    if keys[0] == "custom_fields":
        R.ensure_custom(rec, keys)
    if keys[:2] == ("personal_information", "owners"):
        R.ensure_owner(rec, keys[2])
    if keys[:2] == ("products_and_services", "items"):
        items = rec["products_and_services"]["items"]
        idx = len(items) if keys[2] == "+" else keys[2]
        if idx > len(items) or (idx == len(items) and keys[2] != "+"):
            raise R.RecordError(f"There are {len(items)} item(s); item {idx} does not exist.")
        if idx == len(items):
            items.append(R.empty_field())
        keys = ("products_and_services", "items", idx)
    return keys, R.pointer(keys)


def set_field(rec: dict, field_txt: str, value_txt: str, now: str, new_source):
    """Apply UPDATE FIELD semantics: a value (verified), 'confirm', or 'missing'. Returns the message line.

    new_source() adds the source entry and returns its id. It is called only once the request is valid, so a
    refused request leaves no source behind. The caller does touch().
    """
    keys, label = resolve_path(rec, field_txt)
    ctx = f"UPDATE FIELD {field_txt.strip()} = {value_txt}"[: X.CTX_MAX]
    low = value_txt.lower()
    if low == "confirm":
        if R.get_field(rec, keys)["status"] == "conflict":
            raise R.RecordError("This field is in conflict. Choose the value to keep with UPDATE FIELD <field> = <value>.")
        if R.get_field(rec, keys)["value"] is None:
            raise R.RecordError("There is no value to confirm. Give a value with UPDATE FIELD <field> = <value>.")
        old = R.user_confirm(rec, keys, ctx, new_source(), now)
        return f"{label}: confirmed {show(old[0])} (was {old[1]}) -> verified"
    if low == "missing":
        f = R.get_field(rec, keys)
        if f["value"] is None and f["status"] == "missing":
            raise CommandError(f"{label} is already missing.")
        old = R.user_clear(rec, keys, now)
        new_source()
        return f"{label}: cleared (was {show(old[0])}, {old[1]}) -> missing; previous value kept in history"
    spec = R.spec_key(keys)
    norm = normalizer_for(spec)(value_txt)
    if norm is None:
        raise CommandError(f"'{value_txt}' is not a valid value for {spec or label}; nothing was changed.")
    old = R.user_set(rec, keys, norm, ctx, new_source(), now)
    return f"{label}: {show(old[0])} ({old[1]}) -> {norm} (verified)"
