"""Structured logging, request correlation and RFC 9457 error responses.

The project had no logging at all, so a failing Claude key or a 502 from GitHub looked
exactly like normal operation. Everything here is standard library plus Starlette — no
extra runtime dependency, because "runs with zero external services" is a property worth
keeping. Swapping the formatter for structlog or an OTLP exporter later is a local change.
"""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Set per request and read by the log formatter, so every line emitted while handling a
# request carries the same id without threading it through every call.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Stable, resolvable-looking type URIs. RFC 9457 wants a URI; it need not dereference.
PROBLEM_TYPES = {
    400: "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400",
    404: "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404",
    422: "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/422",
    500: "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500",
    502: "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/502",
    504: "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/504",
}

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the active request id and any `extra` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def problem_response(
    status: int, title: str, detail: str, instance: str | None = None
) -> JSONResponse:
    """An RFC 9457 problem detail.

    `detail` is a standard RFC 9457 member and also what FastAPI used to return on its
    own, so existing clients reading `.detail` keep working — this adds structure rather
    than replacing the shape.
    """
    body: dict[str, Any] = {
        "type": PROBLEM_TYPES.get(status, "about:blank"),
        "title": title,
        "status": status,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers={"X-Request-ID": request_id_var.get()},
    )


def _safe_request_id(incoming: str | None) -> str:
    """Reuse a caller's correlation id, but only a plausible one.

    The value is echoed into logs and response headers, so an arbitrary caller-supplied
    string would allow log forging via newlines.
    """
    if incoming and 8 <= len(incoming) <= 64 and all(c.isalnum() or c in "-_" for c in incoming):
        return incoming
    return uuid.uuid4().hex


def register(app: FastAPI) -> None:
    """Attach the request-id middleware and the error handlers."""
    logger = logging.getLogger("app.request")

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        request_id = _safe_request_id(request.headers.get("X-Request-ID"))
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request handled",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException) -> Any:
        if not isinstance(exc, HTTPException) and exc.status_code < 500:
            # Starlette's own 404/405 for unrouted paths — keep FastAPI's default shape.
            return await http_exception_handler(request, exc)
        return problem_response(
            exc.status_code,
            title=str(exc.detail),
            detail=str(exc.detail),
            instance=request.url.path,
        )

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception) -> Any:
        logger.exception(
            "unhandled error", extra={"method": request.method, "path": request.url.path}
        )
        return problem_response(
            500,
            title="Internal Server Error",
            detail="The hive failed to process this request.",
            instance=request.url.path,
        )
