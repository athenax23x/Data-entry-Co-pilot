"""Field registry. Paths and names follow schema.json exactly; tests check they stay in sync."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .normalize import NORMALIZERS
from .paykings_map import COLUMN_TO_SPEC, OWNER as OWNER_PREFIX

SCHEMA_V2 = Path(__file__).resolve().parent.parent / "schema_v2.json"

# Schema type (the $defs name in schema_v2.json) -> normalizer name.
_TYPE_NORMALIZER = {
    "stringField": "text", "dateField": "iso_date", "usDateField": "us_date", "last4Field": "last4",
    "uriField": "uri", "emailField": "email", "phoneField": "phone", "stateField": "state", "zipField": "zip_code",
    "einField": "ein", "routingNumberField": "routing", "mccField": "mcc", "amountField": "amount",
    "percentageField": "percentage", "entityTypeField": "entity_type", "yesNoField": "yes_no",
    "accountNumberField": "account_number", "ssnField": "ssn", "taxIdTypeField": "tax_id_type",
}
# Owner dates that are expiration dates (the future is allowed, unlike a date of birth).
_EXPIRY_SPECS = frozenset(OWNER_PREFIX + n for n in ("driver_license_expiration", "passport_expiration"))
# Fields that exist since v1 but are not columns of the Paykings form (so not in paykings_map.COLUMN_TO_SPEC).
_EXTRA_SPECS = (
    "business_information.state_of_formation",
    OWNER_PREFIX + "ssn_last4",
    "products_and_services.description",
    "products_and_services.items[]",
)


def _build_specs() -> dict:
    with open(SCHEMA_V2, encoding="utf-8") as fh:
        schema = json.load(fh)
    specs = {}
    for spec in [s for s in COLUMN_TO_SPEC.values() if s] + list(_EXTRA_SPECS):
        if spec.endswith("items[]"):
            specs[spec] = "text"
            continue
        if spec.startswith(OWNER_PREFIX):
            ref = schema["$defs"]["owner"]["properties"][spec[len(OWNER_PREFIX):]]["$ref"]
        else:
            node = schema
            for part in spec.split("."):
                node = node["properties"][part]
            ref = node["$ref"]
        name = _TYPE_NORMALIZER[ref.rsplit("/", 1)[-1]]
        specs[spec] = "expiry_date" if spec in _EXPIRY_SPECS else name
    return specs


# spec key -> normalizer name. Generated from the Paykings map (every v2 form field) plus the v1-only fields.
# The normalizer follows the field's type in schema_v2.json. tests/test_fields_v2.py keeps all of it in step.
FIELD_SPECS = _build_specs()

OWNER_FIELDS = tuple(s[len(OWNER_PREFIX):] for s in FIELD_SPECS if s.startswith(OWNER_PREFIX))


def spec_keys(spec: str):
    """'personal_information.owners[].first_name' -> ('personal_information','owners',0,'first_name')"""
    out = []
    for part in spec.split("."):
        if part.endswith("[]"):
            out.append(part[:-2])
            out.append(0)
        else:
            out.append(part)
    return tuple(out)


def normalizer_for(spec: str):
    return NORMALIZERS[FIELD_SPECS.get(spec, "text")]


class FieldError(ValueError):
    pass


def resolve_target(text: str):
    """User-typed field -> key path into the record.

    Accepts a full path, a short name that matches exactly one field, owners[N].<name>,
    items[N] / items[+], and custom_fields.<key>. Owner fields without an index mean the primary owner.
    Indexes are 0-based, like the JSON arrays.
    """
    t = text.strip()
    if not t:
        raise FieldError("No field name given.")
    m = re.fullmatch(r"custom_fields\.([a-z][a-z0-9_]*)", t)
    if m:
        return ("custom_fields", m.group(1))
    m = re.fullmatch(r"(?:products_and_services\.)?items\[(\+|\d+)\]", t)
    if m:
        return ("products_and_services", "items", "+" if m.group(1) == "+" else int(m.group(1)))
    m = re.fullmatch(r"(?:personal_information\.)?owners\[(\d+)\]\.(\w+)", t)
    if m:
        if m.group(2) not in OWNER_FIELDS:
            raise FieldError(f"Unknown owner field '{m.group(2)}'. Owner fields: {', '.join(OWNER_FIELDS)}.")
        return ("personal_information", "owners", int(m.group(1)), m.group(2))
    by_path = {}
    by_short = {}
    for spec in FIELD_SPECS:
        if spec.endswith("[]"):
            continue
        keys = spec_keys(spec)
        by_path[spec] = keys
        by_path[spec.replace("[]", "[0]")] = keys
        # An owner field is reachable by its short name only when no business field has that name
        # ('state' means business_address.state; the owner's is owners[0].state).
        by_short.setdefault((spec.startswith(OWNER_PREFIX), spec.split(".")[-1]), []).append((spec, keys))
    if t in by_path:
        return by_path[t]
    hits = by_short.get((False, t)) or by_short.get((True, t), [])
    if len(hits) == 1:
        return hits[0][1]
    if len(hits) > 1:
        raise FieldError(f"'{t}' is ambiguous. Use one of: " + ", ".join(s for s, _ in hits) + ".")
    raise FieldError(f"Unknown field '{t}'. Use a path from the Fields Reference in instructions.md.")
