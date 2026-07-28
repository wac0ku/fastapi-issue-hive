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
| `MAX_CONCURRENT_ANALYSES` | `5` | How many issues of a scan are analysed at the same time. Caps how many Claude calls one request can have in flight. |
| `SCAN_TIMEOUT_SECONDS` | `120` | Time budget for a whole repo scan. Exceeding it returns `504` instead of leaving the client hanging. |
| `ALLOWED_ORIGINS` | *(empty)* | Comma-separated browser origins allowed to call the API. Empty sends no CORS headers at all, which is the right default for a service with no authentication. |

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

Costs stay small either way: the hive sends at most ~2.1k input tokens per issue (two worker calls), and only for issues that pass triage — an issue the triage rejects costs nothing at all, because both the diagnosis and the research worker skip Claude entirely. Each call's output is capped by the `max_tokens` its worker declares in `prompts/templates.json` (512 for diagnosis and research), not by an open-ended default.

## Observability

Logs are JSON, one object per line, on stdout — ready to ship into any log backend
without a parsing rule:

```json
{"timestamp":"2026-07-28T13:41:02","level":"info","logger":"app.request","message":"request handled","request_id":"3f9c…","method":"POST","path":"/analyze/issue","status":200,"duration_ms":18.4}
```

Every response carries an `X-Request-ID` header, and every log line emitted while handling
that request carries the same id. Send your own `X-Request-ID` to correlate across
services — it is reused when it looks like an id (8–64 alphanumeric characters, dashes or
underscores) and replaced otherwise, so a caller cannot inject line breaks into your logs.

Errors are [RFC 9457](https://www.rfc-editor.org/info/rfc9457/) problem documents served
as `application/problem+json`:

```json
{"type":"https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/502","title":"Repository not found or private","status":502,"detail":"Repository not found or private","instance":"/analyze/repo"}
```

`detail` is both an RFC 9457 member and what FastAPI returned before, so clients that
already read `.detail` keep working.

## Security notes

- `.env` is gitignored; never commit keys. `.env.example` documents shape only.
- Keys are held as `SecretStr`, so they are masked in reprs, logs and tracebacks.
- The server itself requires no authentication — if you deploy it publicly, put it behind your own auth/proxy layer, and mind that `/analyze/repo` makes outbound requests to api.github.com on behalf of callers.
- The Claude wrapper truncates issue bodies (4000 chars for diagnosis, 3000 for research) before sending — no unbounded user input reaches the API.
