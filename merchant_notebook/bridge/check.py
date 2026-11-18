"""Checks Claude's answer. Code, not AI. Every proposal is checked on its own; a failed one gets a reason and is
never stored. No message here contains a submitted value."""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass

from .. import extract as X, record as R
from ..fields import FIELD_SPECS, normalizer_for, resolve_target
from ..service import CommandError
from ..sqlstore import validate_v2
from . import mask as M, prompt as P

MAX_BYTES = 50 * 1024
BAD_ANSWER = "Jawaban tidak bisa dibaca. Tempel jawaban JSON dari Claude apa adanya (maks. 50 KB)."
_DATE_KINDS = ("iso_date", "us_date", "expiry_date")
_DMY = re.compile(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-]\d{4}\s*$")


class BridgeError(CommandError):
    """The answer as a whole cannot be used. The message is general and never repeats the answer."""


@dataclass
class Proposal:
    index: int
    path: str
    value: str | None          # normalized value; None when the proposal was refused before normalizing
    evidence: str
    status: str                # status it will be stored with: inferred | needs_review
    ambiguous: bool
    ok: bool
    reason: str | None = None
    outcome: str | None = None  # filled | review | unchanged | conflict | ignored (what applying would do)

    def public(self) -> dict:
        return {"index": self.index, "path": self.path, "value": self.value, "evidence": self.evidence,
                "status": self.status, "ambiguous": self.ambiguous, "ok": self.ok, "reason": self.reason,
                "outcome": self.outcome}


def squash(s: str) -> str:
    return " ".join(s.split()).lower()


def parse_answer(answer: str) -> list:
    """The candidate list of an answer, or BridgeError. A surrounding ```json fence is allowed."""
    if len(answer.encode("utf-8")) > MAX_BYTES:
        raise BridgeError(BAD_ANSWER)
    text = answer.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S | re.I)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise BridgeError(BAD_ANSWER) from None
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise BridgeError(BAD_ANSWER)
    return data["candidates"]


def is_ambiguous_date(value: str) -> bool:
    """06/02/2004 reads as two different dates: both parts could be a month and they differ."""
    m = _DMY.match(value)
    return bool(m) and int(m.group(1)) <= 12 and int(m.group(2)) <= 12 and m.group(1).lstrip("0") != m.group(2).lstrip("0")


def _refuse(i, path, evidence, reason, ambiguous=False):
    return Proposal(i, path, None, evidence, "needs_review" if ambiguous else "inferred", ambiguous, False, reason)


def check_answer(rec: dict, answer: str, source_text: str, now: str = "1970-01-01T00:00:00Z") -> list[Proposal]:
    """Check every proposal. rec is not changed. The source text is masked here too, the same way as before copying,
    so evidence is compared with exactly what Claude was shown."""
    candidates = parse_answer(answer)
    seen_text = squash(M.mask(source_text)[0])
    allowed, sensitive = P.allowed_specs(), P.sensitive_paths()
    out: list[Proposal] = []
    taken: set[tuple] = set()
    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            out.append(_refuse(i, "", "", "Usulan bukan objek."))
            continue
        path, value, evidence = c.get("path"), c.get("value"), c.get("evidence")
        amb = c.get("ambiguous") is True
        path = path if isinstance(path, str) else ""
        ev = evidence.strip() if isinstance(evidence, str) else ""
        shown_path = path[:120]
        if path in sensitive:
            out.append(_refuse(i, shown_path, "", "Field sensitif: hanya boleh diisi manual.", amb)); continue
        if path not in allowed:
            out.append(_refuse(i, shown_path, "", "Path tidak dikenal.", amb)); continue
        ev_short = ev[: X.CTX_MAX]
        if not ev or squash(ev) not in seen_text:
            out.append(_refuse(i, path, "", "Bukti tidak ditemukan di teks sumber.", amb)); continue
        if isinstance(value, bool) or not isinstance(value, (str, int, float)) or not str(value).strip():
            out.append(_refuse(i, path, ev_short, "Nilai kosong atau bentuknya salah.", amb)); continue
        raw = str(value).strip()
        if M.mask(raw)[0] != raw:
            out.append(_refuse(i, path, ev_short, "Nilai tampak seperti data sensitif.", amb)); continue
        spec = allowed[path]
        norm = normalizer_for(spec)(raw)
        if norm is None:
            out.append(_refuse(i, path, ev_short, "Nilai tidak sesuai format field ini.", amb)); continue
        if FIELD_SPECS[spec] in _DATE_KINDS and (amb or is_ambiguous_date(raw)):
            amb = True
        if (path, str(norm)) in taken:
            out.append(_refuse(i, path, ev_short, "Usulan ganda.", amb)); continue
        trial = copy.deepcopy(rec)
        keys = resolve_target(path)
        R.merge_value(trial, keys, norm, "needs_review" if amb else "inferred", ev_short, "SRC-000", now)
        if validate_v2(trial):
            out.append(_refuse(i, path, ev_short, "Nilai tidak lolos validasi skema.", amb)); continue
        taken.add((path, str(norm)))
        out.append(Proposal(i, path, norm if isinstance(norm, str) else str(norm), ev_short,
                            "needs_review" if amb else "inferred", amb, True, None,
                            _outcome(rec, keys, norm, "needs_review" if amb else "inferred", ev_short, now)))
    return out


def _outcome(rec, keys, norm, status, ev, now) -> str:
    trial = copy.deepcopy(rec)
    return R.merge_value(trial, keys, norm, status, ev, "SRC-000", now)


def _plain(rec: dict) -> str:
    """The record without sources and update times: used to see whether applying changed anything."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in ("updated_at", "sources")}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    return json.dumps(strip(rec), sort_keys=True, ensure_ascii=False)


def apply_proposals(rec: dict, proposals: list[Proposal], accept: list[int], now: str) -> dict:
    """Merge the accepted proposals into rec (changed in place). Returns {'applied': [...], 'changed': bool}.
    Nothing is added to rec when the accepted proposals would change nothing, so applying twice adds no duplicates."""
    by_index = {p.index: p for p in proposals}
    chosen = []
    for idx in dict.fromkeys(accept):
        p = by_index.get(idx)
        if p is None or not p.ok:
            raise BridgeError("Ada usulan terpilih yang tidak lolos pemeriksaan. Periksa ulang daftarnya.")
        chosen.append(p)
    if not chosen:
        raise BridgeError("Pilih setidaknya satu usulan.")

    def merge(target: dict, sid: str) -> list[dict]:
        done = []
        for p in chosen:
            out = R.merge_value(target, resolve_target(p.path), p.value, p.status, p.evidence, sid, now)
            done.append({"index": p.index, "path": p.path, "outcome": out})
        return done

    dry = copy.deepcopy(rec)
    merge(dry, "SRC-000")
    if _plain(dry) == _plain(rec):
        return {"applied": [{"index": p.index, "path": p.path, "outcome": "unchanged"} for p in chosen],
                "changed": False}
    sid = R.add_source(rec, "other", now, label="Jembatan Claude")
    return {"applied": merge(rec, sid), "changed": True}
