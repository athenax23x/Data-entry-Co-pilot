"""Upgrade a v1 merchant record to the v2 structure (schema_v2.json).

Only adds what v2 requires, as empty fields (value null, status 'missing'). Nothing is inferred and no existing
value, status, source or history is changed. The input is never modified. v2 input is returned as a copy.
"""
from __future__ import annotations

import copy

from . import record as R

V2_VERSION = 2

# Fields v2 adds to existing sections, and the new sections/top-level fields.
_ADDED = {
    "business_information": ("advertising_methods", "dba_different_from_legal"),
    "contact_information": ("customer_service_phone", "customer_service_email"),
    "business_address": ("suite", "building_type", "building_ownership", "building_zoning",
                         "building_square_footage"),
    "processing_information": ("public_sales_percentage", "b2b_sales_percentage", "national_sales_percentage",
                               "international_sales_percentage", "industry_category",
                               "currently_accepts_cards", "previously_terminated"),
    "fulfillment_information": ("service_only_business", "inventory_storage", "uses_third_party_fulfillment",
                                "fulfillment_time_frame", "delivery_time_frame", "accepts_recurring_payments",
                                "when_customers_charged"),
    "banking_information": ("bank_name", "account_number"),
}
_ADDED_TOP = ("tax_id_type", "notes")
OWNER_ADDED = ("email", "phone", "street_address", "suite", "city", "country", "state", "zip", "ssn",
               "driver_license_number", "driver_license_expiration", "driver_license_state",
               "passport_number", "passport_expiration")


class MigrationError(Exception):
    pass


def new_owner_v2(n: int, primary: bool) -> dict:
    owner = R.new_owner(n, primary)
    for k in OWNER_ADDED:
        owner[k] = R.empty_field()
    return owner


def migrate_record(rec: dict) -> dict:
    version = rec.get("schema_version") if isinstance(rec, dict) else None
    if version == V2_VERSION:
        return copy.deepcopy(rec)
    if version != 1:
        raise MigrationError(f"Cannot migrate schema_version {version!r}; only 1 -> {V2_VERSION} is supported.")
    out = copy.deepcopy(rec)
    out["schema_version"] = V2_VERSION
    for section, names in _ADDED.items():
        node = out.setdefault(section, {})
        for name in names:
            node.setdefault(name, R.empty_field())
    for name in _ADDED_TOP:
        out.setdefault(name, R.empty_field())
    for owner in out["personal_information"]["owners"]:
        for name in OWNER_ADDED:
            owner.setdefault(name, R.empty_field())
    return out
