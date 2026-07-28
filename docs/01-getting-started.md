# 01 — Getting Started

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- That's it. No API keys, no database, no external services. uv fetches the right Python itself (`.python-version` pins 3.12; the project supports 3.10+, CI tests 3.10 and 3.12).

## Install

```bash
git clone https://github.com/wac0ku/fastapi-issue-hive.git
cd fastapi-issue-hive
uv sync
```

`uv sync` creates `.venv/` in the repo root and installs the exact versions from `uv.lock` — no manual virtualenv step needed.

## Start the server

```bash
uv run uvicorn app.main:app --reload
```

`uv run` executes inside that virtualenv, so there is nothing to activate.

Open **http://localhost:8000/docs** — the interactive Swagger UI lists every endpoint and lets you fire test requests from the browser.

## Your first analysis

Paste any GitHub issue (title + body) into `/analyze/issue`:

```bash
curl -X POST localhost:8000/analyze/issue \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CORS error: blocked by CORS policy from React frontend",
    "body": "The browser console shows: No Access-Control-Allow-Origin header is present. The preflight OPTIONS request fails with 400."
  }'
```

The response contains four things (full schema in [03 — API Reference](03-api-reference.md)):

1. **triage** — which failure categories matched, with confidence scores
2. **diagnosis** — root causes, concrete fixes, documentation links
3. **research_brief** — a NotebookLM-ready markdown deep-dive document
4. **suggested_reply** — a ready-to-post GitHub answer for the issue thread

## Scan a whole repository

```bash
curl -X POST localhost:8000/analyze/repo \
  -H "Content-Type: application/json" \
  -d '{"owner": "fastapi", "repo": "fastapi", "limit": 5}'
```

The hive fetches the repo's open issues via the GitHub API and runs the full pipeline on each one, flagging which are connectivity-related.

> **Rate limits:** unauthenticated GitHub API calls are limited to 60/hour per IP. Set `GITHUB_TOKEN` in `.env` to raise this to 5000/hour — see [05 — Configuration](05-configuration.md).

## Operating modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **heuristic** (default) | no `ANTHROPIC_API_KEY` set | Fully deterministic. Triage, diagnosis, research and replies come from the curated knowledge base. Zero cost, works offline. |
| **claude-enhanced** | `ANTHROPIC_API_KEY` set | Same pipeline, plus issue-specific analysis written by Claude layered on top of the heuristic result. If the API call fails, the hive silently falls back to heuristic output. |

Check the active mode any time:

```bash
curl localhost:8000/health
# {"status": "ok", "version": "1.0.0", "mode": "heuristic"}
```

## Run the tests

```bash
uv run pytest -v
```

12 tests, all offline, no keys required. If these pass, your installation is good.

## Next steps

- Understand how the pieces fit together: [02 — Architecture](02-architecture.md)
- See everything the hive can diagnose: [04 — Knowledge Base](04-knowledge-base.md)
- Put it on a server: [06 — Deployment](06-deployment.md)
