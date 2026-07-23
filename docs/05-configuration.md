# 05 — Configuration

Configuration is handled by `pydantic-settings` (`app/config.py`). Values come from environment variables or a `.env` file in the project root. **Every setting is optional** — an empty configuration is a fully supported production mode.

## Setup

```bash
cp .env.example .env
# edit .env
```

## Settings

| Env variable | Default | Purpose |
|--------------|---------|---------|
| `ANTHROPIC_API_KEY` | *(empty)* | Enables claude-enhanced mode. Get one at [console.anthropic.com](https://console.anthropic.com). Empty = heuristic mode. |
| `GITHUB_TOKEN` | *(empty)* | Raises the GitHub API rate limit for `/analyze/repo` from 60 to 5000 requests/hour. A [fine-grained token](https://github.com/settings/tokens) with public repo read access suffices. |
| `HIVE_MODEL` | `claude-sonnet-5` | Claude model used by workers in claude-enhanced mode. |
| `MAX_ISSUES_PER_REPO` | `10` | Hard server-side cap on issues fetched per repo scan (the request's `limit` is clamped to this). |

## Mode selection logic

```
ANTHROPIC_API_KEY set?  ──no──►  heuristic mode (deterministic, free)
        │yes
        ▼
claude-enhanced mode — and any failed Claude call
falls back to the heuristic answer for that worker
```

There is no flag to force heuristic mode while a key is set; unset the key instead. `GET /health` always reports the active mode.

## Choosing a model

Any current Claude model ID works. Trade-off guidance:

- `claude-sonnet-5` (default) — best quality/cost balance for diagnosis notes
- `claude-haiku-4-5-20251001` — cheapest, fine for high-volume repo scans
- `claude-opus-4-8` — maximum depth, rarely needed for this task shape

Costs stay small either way: the hive sends at most ~4–7k input tokens per issue (two worker calls), and only for issues that pass triage.

## Security notes

- `.env` is gitignored; never commit keys. `.env.example` documents shape only.
- The server itself requires no authentication — if you deploy it publicly, put it behind your own auth/proxy layer, and mind that `/analyze/repo` makes outbound requests to api.github.com on behalf of callers.
- The Claude wrapper truncates issue bodies (4000 chars for diagnosis, 3000 for research) before sending — no unbounded user input reaches the API.
