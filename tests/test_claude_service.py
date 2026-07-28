"""The Claude wrapper — the paths that only run when a key is configured.

Nothing here reaches the network: the shared client is replaced with a stub. These are
the branches that previously could not fail visibly, because one blanket except turned
every problem into "heuristic mode".
"""

import logging
from typing import Any

import pytest
from anthropic import AnthropicError
from pydantic import SecretStr

from app.config import Settings
from app.services import claude
from app.services.claude import DEFAULT_MAX_TOKENS, _first_text, _resolve_max_tokens, ask_claude


class Block:
    """Minimal stand-in for a response content block."""

    def __init__(self, text: str | None = None) -> None:
        if text is not None:
            self.text = text


class StubMessages:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class StubClient:
    def __init__(self, result: Any) -> None:
        self.messages = StubMessages(result)


class Response:
    def __init__(self, *blocks: Block) -> None:
        self.content = list(blocks)


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        claude, "get_settings", lambda: Settings(anthropic_api_key=SecretStr("sk-test"))
    )


def stub(monkeypatch: pytest.MonkeyPatch, result: Any) -> StubClient:
    client = StubClient(result)
    monkeypatch.setattr(claude, "_client", lambda: client)
    return client


async def test_returns_none_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The core promise: no key means no call, not a failed call."""
    called = False

    def explode() -> StubClient:
        nonlocal called
        called = True
        raise AssertionError("must not build a client without a key")

    monkeypatch.setattr(claude, "_client", explode)

    assert await ask_claude("diagnosis", "anything") is None
    assert not called


async def test_returns_the_text_block(monkeypatch: pytest.MonkeyPatch, with_key: None) -> None:
    stub(monkeypatch, Response(Block("the analysis")))

    assert await ask_claude("diagnosis", "an issue") == "the analysis"


async def test_skips_non_text_blocks(monkeypatch: pytest.MonkeyPatch, with_key: None) -> None:
    """Indexing content[0].text raised AttributeError on a thinking or tool block."""
    client = stub(monkeypatch, Response(Block(), Block("  "), Block("the real answer")))

    assert await ask_claude("diagnosis", "an issue") == "the real answer"
    assert client.messages.kwargs["max_tokens"] == 512


async def test_response_without_text_logs_and_degrades(
    monkeypatch: pytest.MonkeyPatch, with_key: None, caplog: pytest.LogCaptureFixture
) -> None:
    stub(monkeypatch, Response(Block()))

    with caplog.at_level(logging.WARNING):
        assert await ask_claude("diagnosis", "an issue") is None

    assert "no text block" in caplog.text


async def test_api_error_is_logged_as_a_warning(
    monkeypatch: pytest.MonkeyPatch, with_key: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Rate limits and bad keys are operational, not bugs — but they must be visible."""
    stub(monkeypatch, AnthropicError("rate limited"))

    with caplog.at_level(logging.WARNING):
        assert await ask_claude("diagnosis", "an issue") is None

    assert "claude call failed" in caplog.text
    assert caplog.records[0].levelno == logging.WARNING


async def test_unexpected_error_is_logged_with_a_traceback(
    monkeypatch: pytest.MonkeyPatch, with_key: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A bug on our side used to be indistinguishable from normal heuristic operation."""
    stub(monkeypatch, TypeError("bug on our side"))

    with caplog.at_level(logging.ERROR):
        assert await ask_claude("diagnosis", "an issue") is None

    assert "unexpected error" in caplog.text
    assert caplog.records[0].exc_info is not None


async def test_worker_budget_is_sent(monkeypatch: pytest.MonkeyPatch, with_key: None) -> None:
    client = stub(monkeypatch, Response(Block("x")))

    await ask_claude("research", "an issue")

    assert client.messages.kwargs["max_tokens"] == 512
    assert client.messages.kwargs["system"].startswith("You are a technical research analyst")


async def test_explicit_budget_overrides_the_template(
    monkeypatch: pytest.MonkeyPatch, with_key: None
) -> None:
    client = stub(monkeypatch, Response(Block("x")))

    await ask_claude("diagnosis", "an issue", max_tokens=64)

    assert client.messages.kwargs["max_tokens"] == 64


def test_first_text_ignores_blank_and_missing() -> None:
    assert _first_text([Block(), Block("   "), Block("real")]) == "real"
    assert _first_text([Block(), Block("  ")]) is None
    assert _first_text([]) is None


def test_templates_are_read_once() -> None:
    claude._templates.cache_clear()
    claude.load_prompt("diagnosis")
    claude.load_prompt("research")
    claude.load_prompt("niche")

    assert claude._templates.cache_info().misses == 1


def test_max_tokens_falls_back_to_the_default() -> None:
    assert _resolve_max_tokens({"system": "x"}, None) == DEFAULT_MAX_TOKENS
    assert _resolve_max_tokens({"system": "x", "max_tokens": 0}, None) == DEFAULT_MAX_TOKENS


async def test_close_client_is_safe_when_never_built() -> None:
    claude._client.cache_clear()
    await claude.close_client()  # must not raise
