"""Hide sensitive data before text is copied out.

extract.redact already removes cards, security codes, passwords, one-time codes and full SSNs (the value is deleted).
This adds bank account numbers, driver licence / SIM numbers, passport numbers and the last 4 of an SSN. Those are
replaced by MASK, so the reader sees that a value existed but not what it was.

Routing numbers are not masked: the routing number is a public bank identifier and a field Claude may fill.
"""
from __future__ import annotations

import re

from .. import extract as X

MASK = "[DISAMARKAN]"

_NUM = r"\d(?:[ -]?\d){3,16}"                                   # 4 to 17 digits, with spaces or dashes
_NUMBER_WORD = r"(?:\s+(?:number|no\.?|num|nomor|#))?"
_SEP = r"\s*[:=#'\"-]?\s*['\"]?"

# (label, compiled pattern, group to replace; 0 = the whole match)
_PATTERNS = (
    ("bank account number", re.compile(
        r"\b(?:(?:bank\s+)?acc(?:oun)?t|acct|rekening|no\.?\s*rek(?:ening)?)\b" + _NUMBER_WORD + _SEP + "(" + _NUM + ")",
        re.I), 1),
    ("bank account number", re.compile(
        r"\b(?:routing|aba)\b[^\d\n]{0,25}\d{9}\s*[,/&;-]?\s*(?:and\s+)?(?:(?:acc(?:oun)?t|acct|rekening)\b)?"
        + _NUMBER_WORD + _SEP + "(" + _NUM + ")", re.I), 1),
    ("driver licence number", re.compile(
        r"(?:\b(?:driver'?s?\s+)?licen[sc]e|\bDL|\bSIM)\b" + _NUMBER_WORD + _SEP + r"((?=[A-Za-z0-9-]*\d)[A-Za-z0-9][A-Za-z0-9-]{4,19})\b",
        re.I),
     1),
    ("passport number", re.compile(
        r"\b(?:passport|paspor)\b" + _NUMBER_WORD + _SEP + r"((?=[A-Za-z0-9-]*\d)[A-Za-z0-9][A-Za-z0-9-]{4,19})\b", re.I), 1),
    ("SSN last 4", re.compile(
        r"\b(?:ssn|social\s+security(?:\s+(?:number|no\.?|#))?)\b[^\d\n]{0,25}?(?:last\s*(?:4|four)|ending(?:\s+in)?)\W{0,3}(\d{4})\b",
        re.I), 1),
)

# Looser second pass (runs after the exact patterns and after extract.redact): a long run of digits near a bank or
# SSN word is hidden even when other words sit in between ("Bank: Chase, 123...", "my social is 123..."). This may
# hide a harmless number now and then; that is the accepted price. A routing number is not reached: the gap may
# not contain the word routing / ABA.
_GAP_BANK = r"(?:(?!routing|\baba\b)[^\d\n]){0,40}?"
_GAP_SSN = r"[^\d\n]{0,30}?"
_LOOSE = (
    ("bank account number", re.compile(
        r"\b(?:acc(?:oun)?t?|a/c|bank|rekening|rek|no\.?\s*rek)\b" + _GAP_BANK + r"(\d(?:[ -]?\d){5,16})", re.I), 1),
    ("SSN", re.compile(r"\b(?:ssn|social|sosial)\b" + _GAP_SSN + r"(\d(?:[ -]?\d){3,15})", re.I), 1),
)


def _hide(text: str, patterns, found: list) -> str:
    for label, rx, group in patterns:
        def repl(m, group=group):
            s, e = m.span(group)
            return m.group(0)[: s - m.start()] + MASK + m.group(0)[e - m.start():]
        new, n = rx.subn(repl, text)
        if n:
            found.append(label)
            text = new
    return text


def mask(text: str) -> tuple[str, list[str]]:
    """Return (text safe to copy, kinds of data that were hidden). The input is not changed."""
    found: list[str] = []
    text = _hide(text, _PATTERNS, found)
    text, removed = X.redact(text)
    found += removed
    return _hide(text, _LOOSE, found), found
