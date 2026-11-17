"""Rule-based extraction from pasted text. Conservative: unlabeled guesses are marked needs_review."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import normalize as N
from .entity import recognize

OWNER = ("personal_information", "owners", 0)
CTX_MAX = 200

# ---------------------------------------------------------------- sensitive data (never stored)
_SENSITIVE = (
    ("payment card number", re.compile(
        r"(?<![\d-])(?:\d{13,19}|\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,7}|\d{4}[ -]\d{6}[ -]\d{4,5})(?![\d-])")),
    ("card security code", re.compile(r"\b(?:cvv2?|cvc2?|cid|security\s+code)\b[\s:=#-]*\d{3,4}\b", re.I)),
    ("password", re.compile(r"\b(?:password|passcode|pwd)\b\s*[:=]?\s*\S+", re.I)),
    ("one-time code", re.compile(
        r"\b(?:otp|one[- ]time\s+(?:code|passcode|password)|verification\s+code)\b\s*[:=]?\s*\d{4,8}\b", re.I)),
)


def redact(text: str):
    found = []
    for label, rx in _SENSITIVE:
        if rx.search(text):
            found.append(label)
            text = rx.sub(" ", text)
    return " ".join(text.split()) if found else text, found


# ---------------------------------------------------------------- items
@dataclass
class Item:
    keys: tuple
    value: object
    status: str
    context: str
    weak: bool = False
    list_item: bool = False


@dataclass
class Extraction:
    items: list = field(default_factory=list)
    discarded: list = field(default_factory=list)


def _ctx(s: str) -> str:
    s = " ".join(s.split())
    return s if len(s) <= CTX_MAX else s[: CTX_MAX - 1] + "…"


def _title(s: str) -> str:
    return s.title() if s == s.lower() else s


def split_name(raw: str):
    toks = [t for t in raw.replace(",", " ").split() if t]
    if not toks:
        return None, None
    toks = [(t.upper() + "." if len(t.rstrip(".")) == 1 else _title(t)) for t in toks]
    if len(toks) == 1:
        return toks[0], None
    return " ".join(toks[:-1]), toks[-1]


# ---------------------------------------------------------------- labeled "key: value"
_ALIASES = {
    "owner_name": ["name", "full name", "owner", "owner name", "contact", "principal"],
    "personal_information.owners[].first_name": ["first name"],
    "personal_information.owners[].last_name": ["last name"],
    "personal_information.owners[].title": ["title"],
    "personal_information.owners[].ownership_percentage": ["ownership", "ownership percentage", "ownership %"],
    "business_information.legal_business_name": ["business", "business name", "company", "legal name",
                                                 "legal business name"],
    "business_information.dba_name": ["dba", "d/b/a", "doing business as", "trading as", "trade name"],
    "entity_text": ["entity", "entity type", "business type"],
    "business_information.business_description": ["description", "business description"],
    "business_information.business_start_date": ["start date", "business start date", "established"],
    "business_information.state_of_formation": ["state of formation", "formed in"],
    "business_information.website": ["website", "url", "site"],
    "address_full": ["address", "street address", "street"],
    "business_address.city": ["city"],
    "business_address.state": ["state"],
    "business_address.zip": ["zip", "zip code"],
    "contact_information.email": ["email", "e-mail"],
    "contact_information.phone": ["phone", "tel", "mobile", "cell"],
    "ein": ["ein", "fein", "tax id"],
    "processing_information.routing_number": ["routing", "routing number", "aba"],
    "processing_information.current_processor": ["processor", "current processor"],
    "processing_information.mcc": ["mcc"],
    "processing_information.monthly_card_volume": ["monthly volume", "monthly card volume"],
    "processing_information.average_ticket": ["average ticket", "avg ticket"],
    "processing_information.high_ticket": ["high ticket"],
    "processing_information.card_present_percentage": ["card present"],
    "processing_information.keyed_percentage": ["keyed"],
    "processing_information.ecommerce_percentage": ["ecommerce", "e-commerce"],
    "products_and_services.description": ["products description", "services description"],
    "products_list": ["products", "services", "products and services"],
}
_ALIAS_TO_TARGET = {a: t for t, aliases in _ALIASES.items() for a in aliases}
_LABEL = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(a) for a in sorted(_ALIAS_TO_TARGET, key=len, reverse=True))
    + r")\s*[:=]\s*", re.I)

# ---------------------------------------------------------------- free-text patterns
_SUFFIX = r"(?:LLC|L\.L\.C\.|Inc\.?|Corp\.?|Incorporated|Corporation|LLP|L\.L\.P\.|LP|L\.P\.|Ltd\.?)"
_STREET_TYPES = (r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Ct|Court|Way|Pl|Place|"
                 r"Pkwy|Parkway|Hwy|Highway|Cir|Circle|Ter|Terrace)")
_CITY_STATE_ZIP = (r"\s*,?\s*(?P<city>[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*){0,2}?)"
                   r"\s*,?\s+(?P<state>[A-Za-z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)\b")
_ADDRESS = re.compile(
    r"(?P<street>\d{1,6}\s+(?:[A-Za-z0-9.'-]+\s+){1,4}?" + _STREET_TYPES + r"\b\.?"
    r"(?:,?\s*(?:Apt|Apartment|Suite|Ste|Unit|#)\.?\s*[\w-]+)?)" + _CITY_STATE_ZIP, re.I)
_POBOX = re.compile(r"(?P<street>P\.?\s?O\.?\s*Box\s+\d+)" + _CITY_STATE_ZIP, re.I)
_EMAIL = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<![\d-])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?![\d-])")
_EIN = re.compile(r"(?<![\d-])\d{2}-\d{7}(?![\d-])")
_ROUTING = re.compile(r"\b(?:routing|aba)(?:\s*(?:number|no\.?|#))?\s*[:#]?\s*(\d{9})(?!\d)", re.I)
_BARE9 = re.compile(r"(?<![\d-])\d{9}(?![\d-])")
_URL = re.compile(r"\bhttps?://[^\s,;]+|\bwww\.[^\s,;]+", re.I)
_DBA = re.compile(
    r"\b(?:d/b/a|dba|doing\s+business\s+as|trading\s+as)\b\s*:?\s+(?P<n>[^,;\n]+?)(?=\s+\d{1,6}\s|\s*[,;\n]|$)", re.I)
_SUFFIX_RX = re.compile(r"(?<![A-Za-z])(" + _SUFFIX + r")(?![A-Za-z])", re.I)
_STOP = {"dba", "d/b/a", "as", "is", "at", "with", "for", "from", "the", "owner", "name"}
_LEAD_NAME = re.compile(
    r"^\s*(?P<n>[A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z]\.?)?\s+[A-Za-z][A-Za-z'.-]*)"
    r"\s*(?=,|\s-\s|\s–\s|:|\s+(?:sole|individual|dba|d/b/a|owner)\b)", re.I)
_NOT_NAME = {"llc", "inc", "corp", "ltd", "lp", "llp", "sole", "individual", "owner", "dba", "the", "company"}


def _legal_name(text: str):
    """Business name ending in a suffix. Boundary is a guess, so lowercase/long runs are needs_review."""
    for m in _SUFFIX_RX.finditer(text):
        before = text[: m.start()].split()
        run = []
        for tok in reversed(before):
            bare = tok.strip(",;")
            if tok.endswith((",", ";")) and run or not bare or bare.lower() in _STOP or bare.isdigit():
                break
            if bare[0].isupper() or bare == "&":
                run.append(bare)
                if len(run) >= 5 or tok.endswith((",", ";")):
                    break
            else:
                break
        status = "inferred"
        if not run:
            status = "needs_review"
            for tok in reversed(before):
                bare = tok.strip(",;")
                if not bare or bare.lower() in _STOP or bare.isdigit() or len(run) >= 2:
                    break
                run.append(bare)
        if not run:
            continue
        if len(run) > 3:
            status = "needs_review"
        words = list(reversed(run))
        suffix = m.group(1)
        if all(w == w.lower() for w in words):
            words = [w.title() for w in words]
        if suffix == suffix.lower():
            suffix = {"llc": "LLC", "llp": "LLP", "lp": "LP"}.get(suffix, suffix.title())
        return " ".join(words + [suffix]), status, " ".join(reversed(run)) + " " + m.group(1)
    return None


def _address_items(m, ctx):
    street = _title(" ".join(m.group("street").split()))
    st = N.state(m.group("state"))
    if st is None:
        return []
    b = ("business_address",)
    out = [Item(b + ("street_address",), street, "needs_review" if re.match(r"P\.?\s?O", street, re.I)
                else "inferred", ctx),
           Item(b + ("city",), _title(" ".join(m.group("city").split())), "inferred", ctx),
           Item(b + ("state",), st, "inferred", ctx),
           Item(b + ("zip",), m.group("zip"), "inferred", ctx)]
    return out


def _labeled(text: str, out: list):
    ms = list(_LABEL.finditer(text))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        raw = re.split(r"[;\n]", text[m.end():end])[0].strip(" ,;|")
        if not raw:
            continue
        target = _ALIAS_TO_TARGET[m.group(1).lower()]
        ctx = _ctx(f"{m.group(1)}: {raw}")
        if target == "owner_name":
            first, last = split_name(raw)
            if first:
                out.append(Item(OWNER + ("first_name",), first, "inferred", ctx))
            if last:
                out.append(Item(OWNER + ("last_name",), last, "inferred", ctx))
        elif target == "entity_text":
            r = recognize(raw)
            if r.kind == "one":
                out.append(Item(("business_entity_type",), r.value, "inferred", ctx))
            elif r.kind == "ambiguous":
                out.append(Item(("business_entity_type",), "unknown", "needs_review", ctx, weak=True))
            else:
                out.append(Item(("business_entity_type",), "other", "inferred", ctx))
        elif target == "address_full":
            am = _POBOX.search(raw) or _ADDRESS.search(raw)
            items = _address_items(am, ctx) if am else []
            out.extend(items or [Item(("business_address", "street_address"), N.text(raw), "inferred", ctx)])
        elif target == "products_list":
            for part in raw.split(","):
                v = N.text(part)
                if v:
                    out.append(Item(("products_and_services", "items", "+"), v, "inferred", ctx, list_item=True))
        else:
            keys = _spec_to_keys(target)
            value = N.NORMALIZERS[_spec_norm(target)](raw)
            if target.endswith("legal_business_name") or target.endswith("dba_name"):
                value = _title(value) if value else value
            out.append(Item(keys, value, "inferred" if value is not None else "needs_review", ctx))


def _spec_to_keys(spec):
    from .fields import spec_keys
    return spec_keys(spec)


def _spec_norm(spec):
    from .fields import FIELD_SPECS
    return FIELD_SPECS[spec]


def extract(text: str) -> Extraction:
    cleaned, discarded = redact(text)
    out: list[Item] = []
    _labeled(cleaned, out)

    for rx in (_POBOX, _ADDRESS):
        m = rx.search(cleaned)
        if m:
            out.extend(_address_items(m, _ctx(m.group(0))))
            break
    for m in _EMAIL.finditer(cleaned):
        v = N.email(m.group(0))
        if v:
            out.append(Item(("contact_information", "email"), v, "inferred", _ctx(m.group(0))))
    for m in _PHONE.finditer(cleaned):
        v = N.phone(m.group(0))
        if v:
            out.append(Item(("contact_information", "phone"), v, "inferred", _ctx(m.group(0))))
    for m in _EIN.finditer(cleaned):
        out.append(Item(("ein",), N.ein(m.group(0)), "inferred", _ctx(m.group(0))))
    for m in _ROUTING.finditer(cleaned):
        out.append(Item(("processing_information", "routing_number"), m.group(1), "inferred", _ctx(m.group(0))))
    routing_digits = {m.group(1) for m in _ROUTING.finditer(cleaned)}
    for m in _BARE9.finditer(cleaned):
        if m.group(0) not in routing_digits:       # could be an EIN or a routing number
            out.append(Item(("ein",), None, "needs_review", _ctx(m.group(0))))
    m = _URL.search(cleaned)
    if m and N.uri(m.group(0)):
        out.append(Item(("business_information", "website"), N.uri(m.group(0)), "inferred", _ctx(m.group(0))))
    m = _DBA.search(cleaned)
    if m and N.text(m.group("n")):
        out.append(Item(("business_information", "dba_name"), _title(N.text(m.group("n"))), "inferred",
                        _ctx(m.group(0))))
    legal = _legal_name(cleaned)
    if legal:
        out.append(Item(("business_information", "legal_business_name"), legal[0], legal[1], _ctx(legal[2])))

    r = recognize(cleaned)
    if r.kind == "one":
        out.append(Item(("business_entity_type",), r.value, "inferred", _ctx(" / ".join(r.signals))))
    elif r.kind == "ambiguous":
        out.append(Item(("business_entity_type",), "unknown", "needs_review", _ctx(" / ".join(r.signals)),
                        weak=True))

    m = _LEAD_NAME.match(cleaned)
    if m and not any(w.lower().strip(".") in _NOT_NAME for w in m.group("n").split()):
        first, last = split_name(m.group("n"))
        if first and last:
            ctx = _ctx(m.group("n"))
            out.append(Item(OWNER + ("first_name",), first, "needs_review", ctx))
            out.append(Item(OWNER + ("last_name",), last, "needs_review", ctx))
    return Extraction(out, discarded)
