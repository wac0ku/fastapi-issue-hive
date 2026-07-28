"""Thin optional wrapper around the Anthropic SDK.

The hive must never *require* Claude: every worker has a deterministic heuristic path.
When ANTHROPIC_API_KEY is set, workers call ask_claude() to enrich their output; when it
is empty (or the call fails) they get None back and stay heuristic.

Failures degrade but are never silent — an API problem logs a warning, an unexpected one
logs a stack trace. A permanently broken key used to be indistinguishable from normal
heuristic operation.
"""

import json
import logging
from functools import lru_cache
from importlib.resources import files
from typing import Any

from anthropic import AnthropicError, AsyncAnthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 1024


@lru_cache(maxsize=1)
def _templates() -> dict[str, Any]:
    """Prompt templates, read once.

    Loaded through importlib.resources rather than a path relative to this file: the
    templates are package data, so this keeps working when the project is installed as a
    wheel instead of served from a source tree.
    """
    raw = files("app.prompts").joinpath("templates.json").read_text(encoding="utf-8")
    parsed: dict[str, Any] = json.loads(raw)
    return parsed


def load_prompt(worker: str) -> dict[str, Any]:
    template: dict[str, Any] = _templates()[worker]
    return template


def _resolve_max_tokens(template: dict[str, Any], explicit: int | None) -> int:
    """Output budget for one call: explicit argument wins, then the worker's own
    max_tokens from templates.json, then the global default.

    Takes the already-loaded template rather than a worker name so that resolving the
    budget costs no extra read of templates.json.
    """
    if explicit is not None:
        return explicit
    configured = template.get("max_tokens")
    return int(configured) if configured else DEFAULT_MAX_TOKENS


def _first_text(blocks: list[Any]) -> str | None:
    """First text block of a response.

    Indexing content[0].text assumed the first block is always text, which is not true
    once a model emits thinking or tool-use blocks — that raised AttributeError, which
    the blanket except then turned into a silent downgrade.
    """
    for block in blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    return None


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    """One client for the process, so calls reuse connections instead of rebuilding TLS.

    Cached rather than built per call; closed from the app lifespan via close_client().
    """
    return AsyncAnthropic(api_key=get_settings().anthropic_api_key.get_secret_value())


async def close_client() -> None:
    """Release the shared client. Called on application shutdown."""
    if _client.cache_info().currsize:
        await _client().close()
        _client.cache_clear()


async def ask_claude(worker: str, user_content: str, max_tokens: int | None = None) -> str | None:
    settings = get_settings()
    if not settings.claude_enabled:
        return None

    template = load_prompt(worker)
    try:
        response = await _client().messages.create(
            model=settings.hive_model,
            max_tokens=_resolve_max_tokens(template, max_tokens),
            system=template["system"],
            messages=[{"role": "user", "content": user_content}],
        )
    except AnthropicError as exc:
        # Expected in operation: rate limits, bad key, network trouble. Heuristic mode
        # still answers, so this is a warning rather than an error.
        logger.warning(
            "claude call failed, falling back to heuristic",
            extra={"worker": worker, "error": str(exc)},
        )
        return None
    except Exception:
        # Not expected: a bug on our side. Still degrades, but leaves a stack trace.
        logger.exception("unexpected error in claude call", extra={"worker": worker})
        return None

    text = _first_text(list(response.content))
    if text is None:
        logger.warning("claude response carried no text block", extra={"worker": worker})
    return text
