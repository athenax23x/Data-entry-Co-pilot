"""Scanner that makes sure test data stays obviously fake.

scan_code():    emails and phone numbers only (the .py files contain deliberate SSN / card test inputs).
scan_fixture(): every file type in tests/fixtures (.py .json .txt .csv .md ...): emails, phones, SSNs, card
                numbers, and any EIN / routing-looking number that is not one of the known fake ones.
"""
from __future__ import annotations

import re
from pathlib import Path

ALLOWED_DOMAINS = {"example.com", "example.org", "example.net"}
FAKE_EINS = {"12-3456789", "98-7654321"}
FAKE_ROUTING = {"123456789"}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE = re.compile(r"(?<![\d-])(?:\+?1[\s.-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})(?![\d-])")
_SSN = re.compile(r"(?<![\d-])\d{3}[ -]\d{2}[ -]\d{4}(?![\d-])")
_CARD = re.compile(r"(?<![\d-])(?:\d{13,19}|\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,7}|\d{4}[ -]\d{6}[ -]\d{4,5})(?![\d-])")
_EIN = re.compile(r"(?<![\d-])\d{2}-\d{7}(?![\d-])")
_NINE = re.compile(r"(?<![\d-])\d{9}(?![\d-])")


def scan_code(text: str) -> list[str]:
    out = []
    for m in _EMAIL.finditer(text):
        if m.group(1).lower() not in ALLOWED_DOMAINS:
            out.append(f"email outside example.com/.org/.net: {m.group(0)}")
    for m in _PHONE.finditer(text):
        if "555" not in (m.group(1), m.group(2)):
            out.append(f"phone number outside the fictional 555 range: {m.group(0)}")
    return out


def scan_fixture(text: str) -> list[str]:
    out = scan_code(text)
    for rx, what in ((_SSN, "Social Security number pattern"), (_CARD, "card-number pattern")):
        for m in rx.finditer(text):
            out.append(f"{what}: {m.group(0)}")
    for m in _EIN.finditer(text):
        if m.group(0) not in FAKE_EINS:
            out.append(f"EIN that is not a known fake: {m.group(0)}")
    for m in _NINE.finditer(text):
        if m.group(0) not in FAKE_ROUTING:
            out.append(f"9-digit number that is not a known fake: {m.group(0)}")
    return out


def fixture_files(folder: Path) -> list[Path]:
    """Every file under the folder, whatever its type."""
    return sorted(p for p in Path(folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def scan_fixture_folder(folder: Path) -> dict[str, list[str]]:
    found = {}
    for p in fixture_files(folder):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            found[str(p)] = ["file is not UTF-8 text (binary fixtures are not allowed)"]
            continue
        problems = scan_fixture(text)
        if problems:
            found[str(p)] = problems
    return found
