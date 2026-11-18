"""Endpoints of the Claude copy-paste bridge. Nothing here calls an AI or the network."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..bridge import check, mask, prompt
from . import schemas
from .routes import _load, _now, _saved

router = APIRouter(prefix="/api")


@router.post("/bridge/prepare")
async def prepare(body: schemas.BridgePrepare):
    """Mask the text and build the prompt. Stores nothing."""
    masked, hidden = mask.mask(body.text)
    return {"masked_text": masked, "prompt": prompt.build_prompt(masked), "hidden": hidden}


@router.post("/merchants/{merchant_id}/bridge/preview")
async def preview(request: Request, merchant_id: str, body: schemas.BridgePreview):
    """Check Claude's answer, proposal by proposal. Stores nothing."""
    rec, version = _load(request, merchant_id, body.expected_version)
    proposals = check.check_answer(rec, body.answer, body.source_text, _now(request))
    return {"merchant_id": merchant_id, "version": version, "proposals": [p.public() for p in proposals]}


@router.post("/merchants/{merchant_id}/bridge/apply")
async def apply(request: Request, merchant_id: str, body: schemas.BridgeApply):
    """Check the answer again here (the browser's list is not trusted), then store the chosen proposals."""
    rec, version = _load(request, merchant_id, body.expected_version)
    now = _now(request)
    proposals = check.check_answer(rec, body.answer, body.source_text, now)
    result = check.apply_proposals(rec, proposals, body.accept, now)
    if not result["changed"]:
        return {"merchant_id": merchant_id, "version": version, "record": rec, **result}
    from ..record import touch
    touch(rec, now)
    return _saved(request, rec, version, **result)
