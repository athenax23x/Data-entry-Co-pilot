"""Request checks: Host (DNS rebinding), Origin (other sites in the same browser), session token.

Order: Host -> Origin -> token. The token is random per server run and compared in constant time.
Nothing here logs request data.
"""
from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

HOST = "127.0.0.1"
PORT = 8765
ALLOWED_HOSTS = frozenset({f"127.0.0.1:{PORT}", f"localhost:{PORT}"})
ALLOWED_ORIGINS = frozenset({f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"})
WRITE_METHODS = frozenset({"POST", "PATCH", "DELETE"})
TOKEN_HEADER = "X-MCN-Token"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _reply(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status)


def check_request(request: Request, token: str):
    """Return an error response, or None when the request may continue."""
    if request.headers.get("host", "").lower() not in ALLOWED_HOSTS:
        return _reply(400, "Host not allowed.")
    if request.method in WRITE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin.lower() not in ALLOWED_ORIGINS:
            return _reply(403, "Origin not allowed.")
    if request.url.path.startswith("/api"):
        given = request.headers.get(TOKEN_HEADER, "")
        if not secrets.compare_digest(given.encode("utf-8"), token.encode("utf-8")):
            return _reply(401, "Missing or wrong session token.")
    return None
