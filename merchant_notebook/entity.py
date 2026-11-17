"""Business entity type recognition (the eight US types in instructions.md)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_F = re.IGNORECASE
_END = r"(?=[\s,;:)]|$)"

_PATTERNS = {
    "sole_proprietorship": re.compile(r"\bsole[\s-]+prop(?:rietor(?:ship)?)?\b|\bindividual\s+owner\b", _F),
    "llc": re.compile(r"\bL\.?L\.?C\b\.?|\blimited\s+liability\s+company\b", _F),
    "limited_liability_partnership": re.compile(r"\bL\.?L\.?P\b\.?|\blimited\s+liability\s+partnership\b", _F),
    "limited_partnership": re.compile(r"\bL\.?P\b\.?|\blimited\s+partnership\b", _F),
    "s_corporation": re.compile(r"\bS[\s-]?corp(?:oration)?\b|\bsubchapter\s+S\b", _F),
    "c_corporation": re.compile(r"\bC[\s-]?corp(?:oration)?\b", _F),
    "corporation": re.compile(rf"\binc\b\.?{_END}|\bincorporated\b|\bcorp\b\.?{_END}|\bcorporation\b", _F),
    "general_partnership": re.compile(r"\bgeneral\s+partnership\b", _F),
}
_AMBIGUOUS = re.compile(rf"\bltd\b\.?{_END}|\bpartnership\b", _F)


@dataclass
class Recognition:
    kind: str                 # "none" | "one" | "ambiguous"
    value: str | None = None  # schema value when kind == "one"
    signals: tuple = ()       # matched phrases (for context / review)


def recognize(text: str) -> Recognition:
    hits = {}
    for name, rx in _PATTERNS.items():
        m = rx.search(text)
        if m:
            hits[name] = m.group(0)
    # most specific wins; an LLC's tax election does not change the legal type
    if "limited_liability_partnership" in hits:
        hits.pop("limited_partnership", None)
    if "s_corporation" in hits or "c_corporation" in hits:
        hits.pop("corporation", None)
    if "llc" in hits:
        hits.pop("s_corporation", None)
        hits.pop("c_corporation", None)
    if "general_partnership" in hits or "limited_partnership" in hits or "limited_liability_partnership" in hits:
        amb = None
    else:
        amb = _AMBIGUOUS.search(text)
    if not hits:
        return Recognition("ambiguous", None, (amb.group(0),)) if amb else Recognition("none")
    if len(hits) == 1:
        (name, phrase), = hits.items()
        return Recognition("one", name, (phrase,))
    return Recognition("ambiguous", None, tuple(hits.values()))
