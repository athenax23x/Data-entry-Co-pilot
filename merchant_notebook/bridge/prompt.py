"""Builds the prompt for Claude from prompt.md. The field list comes from paykings_map.COLUMN_TO_SPEC and never
contains a sensitive field."""
from __future__ import annotations

from pathlib import Path

from .. import fields, paykings_map as PM

PROMPT_FILE = Path(__file__).with_name("prompt.md")
HINTS = {
    "text": "free text", "yes_no": "Yes or No", "percentage": "number 0-100", "amount": "US dollars, e.g. 25000",
    "phone": "US phone, 10 digits", "email": "email address", "state": "2-letter US state code, e.g. FL",
    "zip_code": "5-digit ZIP (or ZIP+4)", "ein": "EIN, e.g. 12-3456789", "routing": "9 digits", "mcc": "4 digits",
    "iso_date": "date YYYY-MM-DD", "us_date": "date MM/DD/YYYY", "expiry_date": "date MM/DD/YYYY",
    "uri": "website address",
    "entity_type": "one of: " + ", ".join(v for v in ("sole_proprietorship", "llc", "corporation", "s_corporation",
                                                     "c_corporation", "general_partnership", "limited_partnership",
                                                     "limited_liability_partnership", "other")),
}


def path_of(spec: str) -> str:
    return spec.replace("[]", "[0]")


def allowed_specs() -> dict[str, str]:
    """{path: spec} for every field Claude may fill: the Paykings form fields minus the sensitive and the skipped ones."""
    return {path_of(s): s for s in PM.COLUMN_TO_SPEC.values() if s and s not in PM.SENSITIVE_SPECS and s not in PM.HIDDEN_SPECS}


def sensitive_paths() -> frozenset[str]:
    return frozenset(path_of(s) for s in PM.SENSITIVE_SPECS)


def allowed_fields_text() -> str:
    return "\n".join(f"- {p} — {HINTS.get(fields.FIELD_SPECS[s], 'free text')}" for p, s in allowed_specs().items())


def build_prompt(masked_text: str) -> str:
    """masked_text must already be masked (mask.mask). The text goes in last so it cannot change the template."""
    return PROMPT_FILE.read_text(encoding="utf-8").replace("{{ALLOWED_FIELDS}}", allowed_fields_text()) \
        .replace("{{TEXT}}", masked_text)
