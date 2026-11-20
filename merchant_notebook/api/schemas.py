"""Request bodies. Unknown keys are refused. No example values."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TEXT_MAX = 20000


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewMerchant(_Body):
    text: Optional[str] = Field(default=None, max_length=TEXT_MAX)


class Archive(_Body):
    archived: bool = True


class Stage(_Body):
    stage: Literal["baru", "menunggu_info", "siap_diisi"]


class AppStatus(_Body):
    app_status: Literal["no_info", "not_submitted", "submitted", "signed_waiting_underwriting", "approved", "declined"]


class FieldUpdate(_Body):
    expected_version: int = Field(ge=1)
    action: Literal["set", "confirm", "missing"] = "set"
    value: Optional[str] = Field(default=None, max_length=TEXT_MAX)


class AddContext(_Body):
    expected_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=TEXT_MAX)


class ResolveConflict(_Body):
    expected_version: int = Field(ge=1)
    value: str = Field(min_length=1, max_length=TEXT_MAX)


# ---- bridge (M5). Texts are never stored; only the short evidence quotes of accepted proposals are.
BRIDGE_TEXT_MAX = 100000
BRIDGE_ANSWER_MAX = 200000       # the real limit (50 KB) is checked by bridge/check.py with a plain message


class BridgePrepare(_Body):
    text: str = Field(min_length=1, max_length=BRIDGE_TEXT_MAX)


class BridgePreview(_Body):
    expected_version: int = Field(ge=1)
    answer: str = Field(max_length=BRIDGE_ANSWER_MAX)
    source_text: str = Field(min_length=1, max_length=BRIDGE_TEXT_MAX)


class BridgeApply(BridgePreview):
    accept: list[int] = Field(max_length=200)
