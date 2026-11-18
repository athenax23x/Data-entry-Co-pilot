"""The FastAPI app: security middleware, error mapping, and the router. No request data is ever logged."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from ..fields import FieldError
from ..record import RecordError
from ..service import CommandError
from ..sqlstore import (CorruptRecordError, NotFound, RefusedRecord, SqlStoreError, StaleRecordError)
from ..store import StoreError
from . import routes, security

log = logging.getLogger("merchant_notebook.api")


def _json(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status)


def create_app(store_factory, token: str | None = None, clock=None) -> FastAPI:
    """store_factory() builds the SqliteMerchantStore on the server's own thread (SQLite connections are bound to
    the thread that made them). token: for tests; by default a new random one per run."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = store_factory()
        try:
            yield
        finally:
            app.state.store.close()

    app = FastAPI(title="Merchant Notebook API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token = token or security.new_token()
    app.state.clock = clock or (lambda: datetime.now(timezone.utc))

    @app.middleware("http")
    async def guard(request: Request, call_next):
        refused = security.check_request(request, app.state.token)
        try:
            response = refused or await call_next(request)
        except Exception as exc:                  # not re-raised: the server would print the message (may hold values)
            log.error("request failed (%s)", type(exc).__name__)
            response = _json(500, "The record could not be processed. See the server window.")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def page(request: Request):
        # The page the server hands out carries this run's token. The real UI (M4) will be served from here.
        return HTMLResponse('<!doctype html><meta charset="utf-8"><title>Merchant Notebook</title>'
                            f'<meta name="mcn-token" content="{escape(request.app.state.token)}">'
                            "<p>Merchant Notebook API is running.</p>")

    app.include_router(routes.router)

    # ---- errors: fixed, plain messages; never the submitted values
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(p) for p in e["loc"][1:] if p != "__root__") or str(e["loc"][0])
                         for e in exc.errors()})
        return JSONResponse({"detail": "The request is not valid.", "fields": fields}, status_code=422)

    @app.exception_handler(NotFound)
    async def not_found(request, exc):
        return _json(404, str(exc))

    @app.exception_handler(StaleRecordError)
    async def stale(request, exc):
        return _json(409, str(exc))

    @app.exception_handler(RefusedRecord)
    async def refused(request, exc):
        return _json(422, str(exc))

    @app.exception_handler(CommandError)
    @app.exception_handler(RecordError)
    @app.exception_handler(FieldError)
    async def bad_request(request, exc):
        return _json(400, str(exc))

    @app.exception_handler(CorruptRecordError)
    @app.exception_handler(SqlStoreError)
    @app.exception_handler(StoreError)
    async def server_error(request, exc):
        log.error("request failed (%s)", type(exc).__name__)       # the class only: messages may hold values
        return _json(500, "The record could not be processed. See the server window.")

    return app
