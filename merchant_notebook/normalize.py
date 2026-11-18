"""Value normalizers. Each returns the normalized value, or None if the text cannot be normalized."""
from __future__ import annotations

import re
from datetime import date, datetime

US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR GU VI AS MP".split()
)

ENTITY_VALUES = (
    "sole_proprietorship", "llc", "corporation", "s_corporation", "c_corporation",
    "general_partnership", "limited_partnership", "limited_liability_partnership", "other", "unknown",
)

_EMAIL = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+")


def text(s: str):
    s = " ".join(str(s).split())
    return s or None


def phone(s: str):
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return None
    return f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def email(s: str):
    s = s.strip().lower()
    return s if _EMAIL.fullmatch(s) else None


def state(s: str):
    s = s.strip().upper()
    return s if s in US_STATES else None


def zip_code(s: str):
    s = s.strip()
    return s if re.fullmatch(r"\d{5}(-\d{4})?", s) else None


def ein(s: str):
    m = re.fullmatch(r"(\d{2})-?(\d{7})", s.strip())
    return f"{m.group(1)}-{m.group(2)}" if m else None


def routing(s: str):
    s = s.strip()
    return s if re.fullmatch(r"\d{9}", s) else None


def mcc(s: str):
    s = s.strip()
    return s if re.fullmatch(r"\d{4}", s) else None


def _num(x: float):
    return int(x) if float(x).is_integer() else x


def percentage(s: str):
    m = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*%?", s.strip())
    if not m:
        return None
    v = float(m.group(1))
    return _num(v) if v <= 100 else None


def amount(s: str):
    m = re.fullmatch(r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?", s.strip())
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    v *= {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return _num(round(v, 2))


def iso_date(s: str):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def us_date(s: str):
    """Date of birth in US format MM/DD/YYYY. Accepts M/D/YYYY and YYYY-MM-DD input; must be a real date."""
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if d.year < 1900 or d > date.today():
            return None
        return d.strftime("%m/%d/%Y")
    return None


def last4(s: str):
    """Exactly four digits. Anything longer (e.g. a full SSN) is refused, never truncated."""
    s = s.strip()
    return s if re.fullmatch(r"\d{4}", s) else None


def yes_no(s: str):
    """The Paykings Yes/No answer. Accepts yes/no/y/n/true/false in any case."""
    v = s.strip().lower()
    return {"yes": "Yes", "y": "Yes", "true": "Yes", "no": "No", "n": "No", "false": "No"}.get(v)


def tax_id_type(s: str):
    """The Paykings Tax Id Type dropdown: EIN or SSN, any case."""
    v = s.strip().upper()
    return v if v in ("EIN", "SSN") else None


def expiry_date(s: str):
    """An expiration date in US format MM/DD/YYYY (a future date is fine). Must be a real calendar date."""
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        return d.strftime("%m/%d/%Y") if 1900 <= d.year <= 2200 else None
    return None


def ssn(s: str):
    """A full SSN as 9 digits. Dashes and spaces are accepted and removed."""
    digits = re.sub(r"[\s-]", "", s)
    return digits if re.fullmatch(r"\d{9}", digits) else None


def account_number(s: str):
    """A bank account number: 4 to 17 digits (spaces and dashes removed)."""
    digits = re.sub(r"[\s-]", "", s)
    return digits if re.fullmatch(r"\d{4,17}", digits) else None


def uri(s: str):
    s = s.strip().rstrip(".,;)")
    if not s or re.search(r"\s", s):
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://\S+$", s, re.I):
        return s
    if re.fullmatch(r"(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?", s):
        return "https://" + s
    return None


def entity_type(s: str):
    from .entity import recognize

    v = re.sub(r"[\s-]+", "_", s.strip().lower())
    if v in ENTITY_VALUES:
        return v
    r = recognize(s)
    return r.value if r.kind == "one" else None


NORMALIZERS = {
    "text": text, "phone": phone, "email": email, "state": state, "zip_code": zip_code, "ein": ein,
    "routing": routing, "mcc": mcc, "percentage": percentage, "amount": amount, "iso_date": iso_date,
    "us_date": us_date, "last4": last4,
    "uri": uri, "entity_type": entity_type, "yes_no": yes_no, "tax_id_type": tax_id_type, "expiry_date": expiry_date, "ssn": ssn,
    "account_number": account_number,
}
