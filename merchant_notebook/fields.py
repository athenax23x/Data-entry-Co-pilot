"""Field registry. Paths and names follow schema.json exactly; tests check they stay in sync."""
from __future__ import annotations

import re

from .normalize import NORMALIZERS

# spec key -> normalizer name. Order matches the Fields Reference in instructions.md.
FIELD_SPECS = {
    "business_entity_type": "entity_type",
    "personal_information.owners[].first_name": "text",
    "personal_information.owners[].last_name": "text",
    "personal_information.owners[].title": "text",
    "personal_information.owners[].ownership_percentage": "percentage",
    "business_information.legal_business_name": "text",
    "business_information.dba_name": "text",
    "business_information.business_description": "text",
    "business_information.business_start_date": "iso_date",
    "business_information.state_of_formation": "state",
    "business_information.website": "uri",
    "business_address.street_address": "text",
    "business_address.city": "text",
    "business_address.state": "state",
    "business_address.zip": "zip_code",
    "contact_information.email": "email",
    "contact_information.phone": "phone",
    "ein": "ein",
    "processing_information.current_processor": "text",
    "processing_information.mcc": "mcc",
    "processing_information.monthly_card_volume": "amount",
    "processing_information.average_ticket": "amount",
    "processing_information.high_ticket": "amount",
    "processing_information.card_present_percentage": "percentage",
    "processing_information.keyed_percentage": "percentage",
    "processing_information.ecommerce_percentage": "percentage",
    "processing_information.routing_number": "routing",
    "products_and_services.description": "text",
    "products_and_services.items[]": "text",
}

OWNER_FIELDS = ("first_name", "last_name", "title", "ownership_percentage")


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
        by_short.setdefault(spec.split(".")[-1], []).append((spec, keys))
    if t in by_path:
        return by_path[t]
    hits = by_short.get(t, [])
    if len(hits) == 1:
        return hits[0][1]
    if len(hits) > 1:
        raise FieldError(f"'{t}' is ambiguous. Use one of: " + ", ".join(s for s, _ in hits) + ".")
    raise FieldError(f"Unknown field '{t}'. Use a path from the Fields Reference in instructions.md.")
