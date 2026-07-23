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


def load_prompt(worker: str) -> dict:
    templates = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    return templates[worker]


async def ask_claude(worker: str, user_content: str, max_tokens: int = 1024) -> str | None:
    settings = get_settings()
    if not settings.claude_enabled:
        return None
    try:
        from anthropic import AsyncAnthropic

        template = load_prompt(worker)
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.hive_model,
            max_tokens=max_tokens,
            system=template["system"],
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text
    except Exception:
        # Any API problem degrades gracefully to heuristic mode.
        return None
