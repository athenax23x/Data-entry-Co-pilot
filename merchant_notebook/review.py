"""Checks before a merchant goes into the Paykings form (M24) and the message that asks the merchant for what is
still missing (M23). Code, not AI. Messages hold field names and short reasons, never the values themselves.
"""
from __future__ import annotations

from datetime import date, datetime

from . import fields, record as R
from .paykings_map import COLUMN_TO_SPEC, SENSITIVE_SPECS, SKIPPED_COLUMNS

OWNER = "personal_information.owners[]."

# ---- helpers


def _value(rec: dict, spec: str):
    try:
        v = R.get_field(rec, fields.spec_keys(spec))["value"]
    except R.RecordError:
        return None
    return None if v in (None, "") else v


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date(v):
    if not isinstance(v, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _label(spec: str) -> str:
    return next((c for c, s in COLUMN_TO_SPEC.items() if s == spec), spec)


# First three digits of a ZIP code -> states that use it (USPS sectional centers; a few prefixes are shared).
_ZIP_RANGES = {
    "AL": [(350, 369)], "AK": [(995, 999)], "AZ": [(850, 865)], "AR": [(716, 729)], "CA": [(900, 961)],
    "CO": [(800, 816)], "CT": [(60, 69)], "DE": [(197, 199)], "DC": [(200, 205), (569, 569)], "FL": [(320, 349)],
    "GA": [(300, 319), (398, 399)], "HI": [(967, 968)], "ID": [(832, 838)], "IL": [(600, 629)], "IN": [(460, 479)],
    "IA": [(500, 528)], "KS": [(660, 679)], "KY": [(400, 427)], "LA": [(700, 714)], "ME": [(39, 49)],
    "MD": [(206, 219)], "MA": [(10, 27), (55, 55)], "MI": [(480, 499)], "MN": [(550, 567)], "MS": [(386, 397)],
    "MO": [(630, 658)], "MT": [(590, 599)], "NE": [(680, 693)], "NV": [(889, 898)], "NH": [(30, 38)],
    "NJ": [(70, 89)], "NM": [(870, 884)], "NY": [(5, 5), (63, 63), (100, 149)], "NC": [(270, 289)],
    "ND": [(580, 588)], "OH": [(430, 459)], "OK": [(730, 749)], "OR": [(970, 979)], "PA": [(150, 196)],
    "RI": [(28, 29)], "SC": [(290, 299)], "SD": [(570, 577)], "TN": [(370, 385)],
    "TX": [(733, 733), (750, 799), (885, 885)], "UT": [(840, 847)], "VT": [(50, 59)], "VA": [(201, 201), (220, 246)],
    "WA": [(980, 994)], "WV": [(247, 268)], "WI": [(530, 549)], "WY": [(820, 831), (834, 834)],
    "PR": [(6, 9)], "VI": [(8, 8)], "GU": [(969, 969)], "AS": [(967, 967)], "MP": [(969, 969)],
}


def zip_matches_state(zip_code: str, state: str) -> bool | None:
    """True/False when the state is in the table; None when it cannot be told."""
    ranges = _ZIP_RANGES.get(str(state).upper())
    if not ranges or not str(zip_code)[:5].isdigit():
        return None
    p = int(str(zip_code)[:3])
    return any(lo <= p <= hi for lo, hi in ranges)


def routing_checksum_ok(routing: str) -> bool:
    d = [int(c) for c in str(routing)]
    return len(d) == 9 and (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + d[2] + d[5] + d[8]) % 10 == 0


# ---- M24: checks

def _w(level: str, code: str, message: str, *specs: str) -> dict:
    return {"level": level, "code": code, "message": message, "fields": [_label(s) for s in specs]}


def _sum_check(rec, specs, code, what):
    vals = [_num(_value(rec, s)) for s in specs]
    if all(v is not None for v in vals) and abs(sum(vals) - 100) > 0.01:
        total = sum(vals)
        return _w("error", code, f"{what} berjumlah {total:g}%, seharusnya 100%.", *specs)
    return None


def checks(rec: dict, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out: list[dict] = []
    P = "processing_information."

    for item in (
        _sum_check(rec, [P + "public_sales_percentage", P + "b2b_sales_percentage"], "sales_public_b2b",
                   "Public Sales % + B2B Sales %"),
        _sum_check(rec, [P + "national_sales_percentage", P + "international_sales_percentage"], "sales_national_intl",
                   "National Sales % + International Sales %"),
        _sum_check(rec, [P + "card_present_percentage", P + "keyed_percentage", P + "ecommerce_percentage"],
                   "card_mix", "Card Swipe % + Card Keyed % + Card Internet %"),
    ):
        if item:
            out.append(item)

    avg, high, vol = (_num(_value(rec, P + k)) for k in ("average_ticket", "high_ticket", "monthly_card_volume"))
    if avg is not None and high is not None and avg > high:
        out.append(_w("error", "avg_gt_high", "Average Transaction Amount lebih besar dari Maximum Transaction Amount.",
                      P + "average_ticket", P + "high_ticket"))
    if avg is not None and vol is not None and avg > vol:
        out.append(_w("error", "avg_gt_volume", "Average Transaction Amount lebih besar dari Monthly Processing Volume.",
                      P + "average_ticket", P + "monthly_card_volume"))
    if high is not None and vol is not None and high > vol:
        out.append(_w("warn", "high_gt_volume", "Maximum Transaction Amount lebih besar dari volume sebulan. Pastikan benar.",
                      P + "high_ticket", P + "monthly_card_volume"))

    for zspec, sspec, who in (("business_address.zip", "business_address.state", "bisnis"),
                              (OWNER + "zip", OWNER + "state", "pemilik")):
        z, s = _value(rec, zspec), _value(rec, sspec)
        if z and s and zip_matches_state(z, s) is False:
            out.append(_w("warn", f"zip_state_{'owner' if who == 'pemilik' else 'business'}",
                          f"ZIP alamat {who} tampaknya bukan milik state {s}. Periksa ZIP atau state.", zspec, sspec))

    etype = _value(rec, "business_entity_type")
    ein = _value(rec, "ein")
    if etype and etype not in ("sole_proprietorship", "unknown") and not ein:
        out.append(_w("error", "ein_needed", "Badan usaha selain sole proprietorship biasanya wajib punya EIN; EIN masih kosong.",
                      "business_entity_type", "ein"))
    if str(_value(rec, "tax_id_type") or "").upper() == "EIN" and not ein:
        out.append(_w("error", "ein_type_without_ein", "Tax Id Type = EIN, tetapi Federal Tax ID (EIN) kosong.", "tax_id_type", "ein"))

    flag = str(_value(rec, "business_information.dba_different_from_legal") or "")
    dba, legal = _value(rec, "business_information.dba_name"), _value(rec, "business_information.legal_business_name")
    if flag.lower() == "yes" and not dba:
        out.append(_w("error", "dba_missing", "DBA Different From Legal Info = Yes, tetapi DBA Name kosong.",
                      "business_information.dba_different_from_legal", "business_information.dba_name"))
    if flag.lower() == "no" and dba and legal and str(dba).strip().lower() != str(legal).strip().lower():
        out.append(_w("warn", "dba_flag_no", "Ada DBA Name yang berbeda, tetapi DBA Different From Legal Info = No.",
                      "business_information.dba_different_from_legal", "business_information.dba_name"))
    if dba and not flag:
        out.append(_w("warn", "dba_flag_empty", "Ada DBA Name; isi DBA Different From Legal Info dengan Yes.",
                      "business_information.dba_different_from_legal"))

    start = _date(_value(rec, "business_information.business_start_date"))
    if start and start > today:
        out.append(_w("error", "start_in_future", "Business Start Date ada di masa depan.", "business_information.business_start_date"))

    dob = _date(_value(rec, OWNER + "date_of_birth"))
    if dob:
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            out.append(_w("error", "owner_under_18", "Menurut Date of Birth, pemilik belum berusia 18 tahun.", OWNER + "date_of_birth"))
    for spec, name in ((OWNER + "driver_license_expiration", "Driver License"), (OWNER + "passport_expiration", "Passport")):
        exp = _date(_value(rec, spec))
        if exp and exp < today:
            out.append(_w("error", f"{name.split()[0].lower()}_expired", f"{name} sudah kedaluwarsa.", spec))

    own = _num(_value(rec, OWNER + "ownership_percentage"))
    if own is not None and own < 25:
        out.append(_w("warn", "ownership_low", "Ownership % pemilik di bawah 25%. Biasanya pemilik dengan 25% atau lebih yang dicantumkan.",
                      OWNER + "ownership_percentage"))

    routing = _value(rec, P + "routing_number")
    if routing and not routing_checksum_ok(routing):
        out.append(_w("error", "routing_checksum", "Routing Number tidak lolos pemeriksaan digit (kemungkinan salah ketik).",
                      P + "routing_number"))

    if str(_value(rec, P + "previously_terminated") or "").lower() == "yes":
        out.append(_w("warn", "previously_terminated", "Merchant pernah diputus oleh processor. Siapkan penjelasannya.",
                      P + "previously_terminated"))

    open_conflicts = sum(1 for c in rec.get("conflicts", []) if c.get("resolution", {}).get("state") == "open")
    if open_conflicts:
        out.append({"level": "error", "code": "open_conflicts", "fields": [],
                    "message": f"Ada {open_conflicts} konflik yang belum dipilih. Selesaikan di tab Formulir."})
    return out


# ---- M23: what is still missing, and a message to the merchant

_SECTIONS = [  # English heading for the merchant, and the fields in Paykings order
    ("Business", ["business_information.legal_business_name", "business_information.business_start_date",
                  "business_information.business_description", "business_information.advertising_methods",
                  "contact_information.phone", "contact_information.email", "contact_information.customer_service_phone",
                  "contact_information.customer_service_email", "business_information.website"]),
    ("Business address", ["business_address.street_address", "business_address.suite", "business_address.city",
                          "business_address.state", "business_address.zip",
                          "business_information.dba_different_from_legal", "business_information.dba_name"]),
    ("Sales and card processing", ["processing_information.public_sales_percentage", "processing_information.b2b_sales_percentage",
                                   "processing_information.national_sales_percentage",
                                   "processing_information.international_sales_percentage",
                                   "processing_information.card_present_percentage", "processing_information.keyed_percentage",
                                   "processing_information.ecommerce_percentage", "processing_information.monthly_card_volume",
                                   "processing_information.average_ticket", "processing_information.high_ticket",
                                   "processing_information.currently_accepts_cards", "processing_information.previously_terminated"]),
    ("Bank", ["banking_information.bank_name", "banking_information.account_number", "processing_information.routing_number"]),
    ("Business type and tax ID", ["business_entity_type", "ein"]),
    ("Owner", [OWNER + k for k in ("first_name", "last_name", "ownership_percentage", "email", "phone", "street_address",
                                   "city", "state", "zip", "ssn", "date_of_birth")]),
]

# How each field is asked in the message (plain English for the merchant).
_ASK = {
    "business_information.legal_business_name": "Legal business name (as registered)",
    "business_information.business_start_date": "Date the business started (MM/DD/YYYY)",
    "business_information.business_description": "Short description of what the business sells",
    "business_information.advertising_methods": "How the business advertises (e.g. Google, Instagram, flyers)",
    "contact_information.phone": "Business phone number",
    "contact_information.email": "Business email",
    "contact_information.customer_service_phone": "Customer service phone (if different from the business phone)",
    "contact_information.customer_service_email": "Customer service email (if different)",
    "business_information.website": "Website (if any)",
    "business_address.street_address": "Business street address",
    "business_address.suite": "Suite / unit number (if any)",
    "business_address.city": "Business city",
    "business_address.state": "Business state",
    "business_address.zip": "Business ZIP code",
    "business_information.dba_different_from_legal": "Do you operate under a different name (DBA)? Yes or No",
    "business_information.dba_name": "DBA / trade name",
    "processing_information.monthly_card_volume": "Expected monthly card sales (USD)",
    "processing_information.average_ticket": "Average sale amount (USD)",
    "processing_information.high_ticket": "Largest single sale amount (USD)",
    "processing_information.currently_accepts_cards": "Do you accept credit cards today? Yes or No",
    "processing_information.previously_terminated": "Has a card processor ever closed your account? Yes or No",
    "banking_information.bank_name": "Bank name",
    "banking_information.account_number": "Bank account number (please send securely, not in a plain email)",
    "processing_information.routing_number": "Bank routing number",
    "business_entity_type": "Business type (sole proprietor, LLC, corporation, partnership)",
    "ein": "Federal Tax ID (EIN)",
    OWNER + "first_name": "Owner first name", OWNER + "last_name": "Owner last name",
    OWNER + "ownership_percentage": "Ownership percentage",
    OWNER + "email": "Owner email", OWNER + "phone": "Owner mobile phone",
    OWNER + "street_address": "Owner home address (street)", OWNER + "city": "Owner home city",
    OWNER + "state": "Owner home state", OWNER + "zip": "Owner home ZIP code",
    OWNER + "ssn": "Owner Social Security Number (please send securely, not in a plain email)",
    OWNER + "date_of_birth": "Owner date of birth (MM/DD/YYYY)",
}
_SALES_GROUPS = [
    (["processing_information.public_sales_percentage", "processing_information.b2b_sales_percentage"],
     "Share of sales to consumers vs. businesses (%, total 100)"),
    (["processing_information.national_sales_percentage", "processing_information.international_sales_percentage"],
     "Share of sales in the US vs. international (%, total 100)"),
    (["processing_information.card_present_percentage", "processing_information.keyed_percentage",
      "processing_information.ecommerce_percentage"],
     "How cards are taken: swiped/tapped vs. keyed in vs. online (%, total 100)"),
]
_ID_FIELDS = [OWNER + k for k in ("driver_license_number", "driver_license_expiration", "driver_license_state",
                                  "passport_number", "passport_expiration")]


def missing(rec: dict) -> list[dict]:
    """[{section, spec, label, ask}] for empty fields the merchant can answer, in form order."""
    out = []
    flag = str(_value(rec, "business_information.dba_different_from_legal") or "").lower()
    etype = _value(rec, "business_entity_type")
    grouped = {s for specs, _ in _SALES_GROUPS for s in specs}
    for section, specs in _SECTIONS:
        done_groups = set()
        for spec in specs:
            if _value(rec, spec) is not None:
                continue
            if spec == "business_information.dba_name" and flag == "no":
                continue
            if spec == "ein" and etype == "sole_proprietorship":
                continue
            if spec in grouped:
                for i, (gs, ask) in enumerate(_SALES_GROUPS):
                    if spec in gs and i not in done_groups:
                        done_groups.add(i)
                        out.append({"section": section, "spec": spec, "label": " / ".join(_label(s) for s in gs), "ask": ask})
                continue
            out.append({"section": section, "spec": spec, "label": _label(spec), "ask": _ASK.get(spec, _label(spec))})
    has_dl = _value(rec, OWNER + "driver_license_number") is not None
    has_pp = _value(rec, OWNER + "passport_number") is not None
    if not has_dl and not has_pp:
        out.append({"section": "Owner", "spec": OWNER + "driver_license_number", "label": "Driver License / Passport",
                    "ask": "Photo ID: driver license number, state and expiration date (or passport number and expiration)"})
    elif has_dl:
        for k, ask in (("driver_license_expiration", "Driver license expiration date"), ("driver_license_state", "Driver license issuing state")):
            if _value(rec, OWNER + k) is None:
                out.append({"section": "Owner", "spec": OWNER + k, "label": _label(OWNER + k), "ask": ask})
    elif _value(rec, OWNER + "passport_expiration") is None:
        out.append({"section": "Owner", "spec": OWNER + "passport_expiration", "label": "Passport Expiration", "ask": "Passport expiration date"})
    return out


def missing_message(rec: dict) -> str:
    items = missing(rec)
    first = _value(rec, OWNER + "first_name")
    name = _value(rec, "business_information.dba_name") or _value(rec, "business_information.legal_business_name")
    lines = [f"Hi {first}," if first else "Hi,", ""]
    if not items:
        lines += ["Thank you, we have everything we need for your merchant application" + (f" for {name}." if name else "."),
                  "", "Best regards,"]
        return "\n".join(lines)
    lines += ["Thank you for applying for card processing" + (f" for {name}" if name else "") + ".",
              "To complete the application, could you please send the following:", ""]
    section = None
    for it in items:
        if it["section"] != section:
            if section is not None:
                lines.append("")
            section = it["section"]
            lines.append(f"{section}:")
        lines.append(f"- {it['ask']}")
    if any(it["spec"] in SENSITIVE_SPECS or it["spec"] in _ID_FIELDS for it in items):
        lines += ["", "For your security, please share your SSN, ID and bank account number by phone or a secure upload "
                      "link rather than in a regular email."]
    lines += ["", "Thank you!", "Best regards,"]
    return "\n".join(lines)

