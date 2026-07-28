"""Thin optional wrapper around the Anthropic SDK.

The hive must never *require* Claude: every worker has a deterministic
heuristic path. When ANTHROPIC_API_KEY is set, workers call ask_claude() to
enrich their output; when it is empty (or the call fails) they get None back
and silently stay heuristic.
"""

import json
from pathlib import Path

from app.config import get_settings

PROMPTS_PATH = Path(__file__).resolve().parents[2] / "prompts" / "templates.json"

DEFAULT_MAX_TOKENS = 1024


def load_prompt(worker: str) -> dict:
    templates = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    return templates[worker]


def _resolve_max_tokens(template: dict, explicit: int | None) -> int:
    """Output budget for one call: explicit argument wins, then the worker's own
    max_tokens from templates.json, then the global default.

    Takes the already-loaded template rather than a worker name so that resolving the
    budget costs no extra read of templates.json.
    """
    if explicit is not None:
        return explicit
    configured = template.get("max_tokens")
    return int(configured) if configured else DEFAULT_MAX_TOKENS


async def ask_claude(worker: str, user_content: str, max_tokens: int | None = None) -> str | None:
    settings = get_settings()
    if not settings.claude_enabled:
        return None
    try:
        from anthropic import AsyncAnthropic

        template = load_prompt(worker)
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.hive_model,
            max_tokens=_resolve_max_tokens(template, max_tokens),
            system=template["system"],
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text
    except Exception:
        # Any API problem degrades gracefully to heuristic mode.
        return None
