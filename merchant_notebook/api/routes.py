"""Endpoints. Thin: they call service.py (the rules) and SqliteMerchantStore (the storage)."""
from __future__ import annotations

import copy
import re

from fastapi import APIRouter, Request, Response

from .. import extract as X, migrate, paykings_export, record as R, review, service as S
from ..fields import resolve_target
from ..paykings_map import SENSITIVE_SPECS
from ..service import CommandError
from ..sqlstore import NotFound, StaleRecordError
from . import schemas

router = APIRouter(prefix="/api")
_RESERVED = ("confirm", "missing")


def _store(request: Request):
    return request.app.state.store


def _now(request: Request) -> str:
    return R.iso(request.app.state.clock())


def _load(request: Request, merchant_id: str, expected_version: int):
    """Load a record for a change. A client holding an older version is refused before anything is changed."""
    rec, version = _store(request).load(merchant_id)
    if version != expected_version:
        raise StaleRecordError(f"{merchant_id} changed since it was read (now version {version}). "
                               "Reload it and apply the change again.")
    return rec, version


def _saved(request: Request, rec: dict, version: int, **extra) -> dict:
    new_version = _store(request).save(rec, expected_version=version)
    return {"merchant_id": rec["merchant_id"], "version": new_version, "record": rec, **extra}


def _new_id(request: Request, now: str) -> str:
    day = now[:10].replace("-", "")
    used = {m["merchant_id"] for m in _store(request).list()}
    n = 1
    while f"MCN-{day}-{n:03d}" in used:
        n += 1
    return f"MCN-{day}-{n:03d}"


def _field_text(pointer: str) -> str:
    """'/personal_information/owners/0/ssn' -> 'personal_information.owners[0].ssn'."""
    out = ""
    for part in pointer.strip("/").split("/"):
        out += f"[{part}]" if part.isdigit() else ("." if out else "") + part
    return out


def _check_text(text: str) -> None:
    """Card numbers, security codes, passwords and one-time codes are never accepted (same rule as the CLI)."""
    removed = X.redact(text)[1]
    if removed:
        raise CommandError("That text looks like sensitive data (" + ", ".join(removed) + "). Nothing was stored.")


@router.get("/health")
async def health():
    return {"status": "ok", "schema_version": migrate.V2_VERSION}


def _progress(store, merchant_id: str) -> dict:
    """How many Paykings form fields are filled, and how many conflicts are open. Counts only, no values."""
    try:
        rec = store.load(merchant_id)[0]
    except Exception:                            # a broken row must not hide the whole list
        return {"filled": None, "total": None, "open_conflicts": None, "errors": None, "warnings": None}
    filled, total = paykings_export.form_progress(rec)
    open_c = sum(1 for c in rec.get("conflicts", []) if c.get("resolution", {}).get("state") == "open")
    found = review.checks(rec)
    return {"filled": filled, "total": total, "open_conflicts": open_c,
            "errors": sum(1 for w in found if w["level"] == "error"), "warnings": sum(1 for w in found if w["level"] != "error")}


@router.get("/merchants")
async def list_merchants(request: Request, q: str | None = None, archived: bool = False):
    """The merchant list. archived=true lists only the archived ones; by default they are hidden."""
    store = _store(request)
    rows = [m for m in store.list(q) if m["archived"] == archived]
    return {"merchants": [m | _progress(store, m["merchant_id"]) for m in rows]}


@router.post("/merchants", status_code=201)
async def create_merchant(request: Request, body: schemas.NewMerchant):
    now = _now(request)
    rec = migrate.migrate_record(R.new_record(_new_id(request, now), now))
    sid = R.add_source(rec, "new_merchant", now)
    discarded, tally = [], {}
    if body.text and body.text.strip():
        ex, tally = S.apply_extraction(rec, body.text.strip(), sid, now)
        discarded = ex.discarded
    R.touch(rec, now)
    return _saved(request, rec, None, discarded=discarded, outcome=tally)


@router.get("/merchants/{merchant_id}")
async def get_merchant(request: Request, merchant_id: str):
    rec, version = _store(request).load(merchant_id)
    return {"merchant_id": merchant_id, "version": version, "record": rec}


@router.post("/merchants/{merchant_id}/duplicate", status_code=201)
async def duplicate_merchant(request: Request, merchant_id: str):
    """A new merchant with the same values (for example a second business of the same owner)."""
    src = _store(request).load(merchant_id)[0]
    now = _now(request)
    rec = copy.deepcopy(src)
    rec["merchant_id"] = _new_id(request, now)
    rec["created_at"] = now
    R.add_source(rec, "other", now, label=f"Duplikat dari {merchant_id}")
    R.touch(rec, now)
    return _saved(request, rec, None)


@router.get("/merchants/{merchant_id}/review")
async def review_merchant(request: Request, merchant_id: str):
    """Checks before the Paykings form (M24) and the message asking the merchant for what is missing (M23)."""
    store = _store(request)
    rec = store.load(merchant_id)[0]
    return {"merchant_id": merchant_id, "checks": review.checks(rec),
            "missing": [{k: it[k] for k in ("section", "label", "ask")} for it in review.missing(rec)],
            "message": review.missing_message(rec), "stage": store.stage_of(merchant_id),
            "app_status": store.app_status_of(merchant_id)}


@router.post("/merchants/{merchant_id}/stage")
async def set_stage(request: Request, merchant_id: str, body: schemas.Stage):
    _store(request).set_stage(merchant_id, body.stage, _now(request))
    return {"merchant_id": merchant_id, "stage": body.stage}


@router.post("/merchants/{merchant_id}/application-status")
async def set_app_status(request: Request, merchant_id: str, body: schemas.AppStatus):
    _store(request).set_app_status(merchant_id, body.app_status, _now(request))
    return {"merchant_id": merchant_id, "app_status": body.app_status}


@router.post("/merchants/{merchant_id}/archive")
async def archive_merchant(request: Request, merchant_id: str, body: schemas.Archive):
    _store(request).set_archived(merchant_id, body.archived, _now(request))
    return {"merchant_id": merchant_id, "archived": body.archived}


@router.delete("/merchants/{merchant_id}")
async def delete_merchant(request: Request, merchant_id: str, expected_version: int):
    """Delete for good. Only an archived merchant, at the version the person last saw."""
    _store(request).delete(merchant_id, expected_version)
    return {"merchant_id": merchant_id, "deleted": True}


@router.patch("/merchants/{merchant_id}/fields/{path}")
async def update_field(request: Request, merchant_id: str, path: str, body: schemas.FieldUpdate):
    rec, version = _load(request, merchant_id, body.expected_version)
    if body.action == "set":
        if body.value is None or not body.value.strip():
            raise CommandError("No value given. Use a value, or action 'confirm' or 'missing'.")
        value = body.value.strip()
        if value.lower() in _RESERVED:
            raise CommandError("That value is reserved. Use action 'confirm' or 'missing' instead.")
    else:
        value = body.action
    keys = resolve_target(path)
    if body.action == "set" and R.spec_key(keys) not in SENSITIVE_SPECS:
        _check_text(value)
    now = _now(request)
    message = S.set_field(rec, path, value, now, lambda: R.add_source(rec, "update_field", now), mask=True)
    R.touch(rec, now)
    return _saved(request, rec, version, message=message)


@router.post("/merchants/{merchant_id}/context")
async def add_context(request: Request, merchant_id: str, body: schemas.AddContext):
    rec, version = _load(request, merchant_id, body.expected_version)
    text = body.text.strip()
    S.check_same_merchant(rec, text)
    now = _now(request)
    sid = R.add_source(rec, "add_context", now)
    ex, tally = S.apply_extraction(rec, text, sid, now)
    R.touch(rec, now)
    return _saved(request, rec, version, discarded=ex.discarded, outcome=tally)


@router.post("/merchants/{merchant_id}/conflicts/{conflict_id}/resolve")
async def resolve_conflict(request: Request, merchant_id: str, conflict_id: str, body: schemas.ResolveConflict):
    rec, version = _load(request, merchant_id, body.expected_version)
    c = next((c for c in rec["conflicts"] if c["conflict_id"] == conflict_id), None)
    if c is None:
        raise NotFound(f"{conflict_id} is not a conflict of {merchant_id}.")
    if c["resolution"]["state"] != "open":
        raise CommandError(f"{conflict_id} is already resolved.")
    allowed = [c["current_value"]] + [x["value"] for x in c["candidates"]]
    if body.value.strip() not in {str(v) for v in allowed if v is not None}:
        raise CommandError("Choose the kept value or one of the candidates of this conflict.")
    now = _now(request)
    message = S.set_field(rec, _field_text(c["field_path"]), body.value.strip(), now,
                          lambda: R.add_source(rec, "update_field", now), mask=True)
    R.touch(rec, now)
    return _saved(request, rec, version, message=message)


@router.get("/export/paykings.csv")
async def export_paykings(request: Request, merchant_id: str | None = None, include_sensitive: bool = False):
    """The Paykings 70-column CSV for one merchant (or all). Sensitive columns are blank unless asked for."""
    store = _store(request)
    if merchant_id and not re.fullmatch(r"MCN-[0-9]{8}-[0-9]{3,}", merchant_id):
        raise NotFound(f"{merchant_id} is not a merchant id.")            # also keeps odd text out of the file name
    ids = [merchant_id] if merchant_id else [m["merchant_id"] for m in store.list() if not m["archived"]]
    records = [store.load(i)[0] for i in ids]
    name = (merchant_id or "all-merchants") + ("-with-sensitive" if include_sensitive else "") + ".csv"
    return Response(paykings_export.render_csv(records, include_sensitive), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
