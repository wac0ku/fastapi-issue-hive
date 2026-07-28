"""Structured logging, request correlation and RFC 9457 error bodies."""

import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.observability import (
    JsonFormatter,
    _safe_request_id,
    problem_response,
    register,
    request_id_var,
)

client = TestClient(app)


def test_json_formatter_emits_one_object_per_record() -> None:
    record = logging.LogRecord("app.test", logging.INFO, "f.py", 1, "hello", None, None)
    record.worker = "diagnosis"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "hello"
    assert payload["level"] == "info"
    assert payload["logger"] == "app.test"
    assert payload["worker"] == "diagnosis"  # `extra` fields survive
    assert "timestamp" in payload


def test_formatter_includes_the_active_request_id() -> None:
    token = request_id_var.set("abcd1234")
    try:
        record = logging.LogRecord("app.test", logging.INFO, "f.py", 1, "x", None, None)
        assert json.loads(JsonFormatter().format(record))["request_id"] == "abcd1234"
    finally:
        request_id_var.reset(token)


def test_formatter_renders_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "app.test", logging.ERROR, "f.py", 1, "failed", None, sys.exc_info()
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]


def test_every_response_carries_a_request_id() -> None:
    response = client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32


def test_a_plausible_incoming_request_id_is_reused() -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-0001"})

    assert response.headers["X-Request-ID"] == "trace-0001"


def test_implausible_request_ids_are_replaced() -> None:
    """The value is echoed into logs, so a newline would let a caller forge log lines."""
    for hostile in ("short", "x" * 200, "with space", "line\nbreak"):
        assert _safe_request_id(hostile) != hostile
    assert _safe_request_id(None) != ""


def test_problem_response_follows_rfc_9457() -> None:
    response = problem_response(502, "Upstream failed", "GitHub said no", instance="/analyze/repo")
    body = json.loads(bytes(response.body))

    assert response.media_type == "application/problem+json"
    assert body["status"] == 502
    assert body["title"] == "Upstream failed"
    assert body["instance"] == "/analyze/repo"
    # `detail` is both an RFC 9457 member and what FastAPI used to return, so existing
    # clients reading .detail keep working.
    assert body["detail"] == "GitHub said no"
    assert body["type"].startswith("https://")


def test_validation_errors_still_use_the_default_shape() -> None:
    """422 comes from FastAPI's own validation and stays machine-readable as before."""
    response = client.post("/analyze/issue", json={"title": ""})

    assert response.status_code == 422
    assert "detail" in response.json()


def test_unhandled_errors_become_a_problem_document() -> None:
    boom = FastAPI()
    register(boom)

    @boom.get("/boom")
    async def _boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(boom, raise_server_exceptions=False) as local:
        response = local.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == 500
    assert body["type"].endswith("/500")
    assert "kaboom" not in body["detail"]  # internals are not leaked to the caller


def test_http_exceptions_become_a_problem_document() -> None:
    boom = FastAPI()
    register(boom)

    @boom.get("/teapot")
    async def _teapot() -> None:
        raise HTTPException(status_code=502, detail="upstream is down")

    with TestClient(boom, raise_server_exceptions=False) as local:
        response = local.get("/teapot")

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "upstream is down"


def test_unrouted_paths_keep_the_plain_404() -> None:
    response = client.get("/nope")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
