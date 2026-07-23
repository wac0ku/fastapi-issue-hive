# 08 — Troubleshooting

Problems running the hive itself. (Yes, several of these are the exact failure modes the hive diagnoses — the fixes below are its own medicine.)

| Problem | Cause & fix |
|---------|-------------|
| `ModuleNotFoundError: No module named 'app'` | Install the package first: `pip install -e ".[dev]"` from the repo root. |
| Server runs but is unreachable from another machine | uvicorn binds to 127.0.0.1 by default. Start with `--host 0.0.0.0` and open the port in your firewall. |
| `address already in use` on startup | Another process owns port 8000: `lsof -i :8000`, kill it or use `--port 8001`. |
| `/analyze/repo` returns 502 "rate limit exceeded" | Unauthenticated GitHub API allows 60 requests/hour per IP. Set `GITHUB_TOKEN` in `.env` (5000/hour). |
| `/analyze/repo` returns 502 "not found or private" | The repo doesn't exist, is private, or owner/repo are swapped. The hive only scans public repositories. |
| `/health` says `heuristic` although a key is set | The key must be available *at process start* — restart uvicorn after editing `.env`, and confirm the file sits in the working directory you launched from. |
| `enhanced_by_claude` stays `false` despite a valid key | Any Claude API failure falls back silently to heuristics by design. Check the key's credit balance and that `HIVE_MODEL` names an existing model. |
| Issue clearly connectivity-related but triage says out of scope | Confidence stayed below 0.15 — the text lacks the category's signal terms. Include the actual error message (e.g. "502 Bad Gateway", "ERR_CONNECTION_REFUSED") in the body, or extend the category's signals ([04 — Knowledge Base](04-knowledge-base.md)). |
| Tests fail after adding a knowledge-base category | Overlapping signals can flip the top match of existing tests. Make new signals more specific (word boundaries, multi-word phrases) rather than loosening assertions. |
| `422 Unprocessable Entity` on `/analyze/issue` | Request violates the schema — most commonly a title under 3 characters or a body over 20 000. The response `detail` names the field. |
| Swagger UI broken behind a reverse proxy sub-path | Classic `root_path` issue: start uvicorn with `--root-path /your-prefix` and match it in the proxy config. |

Still stuck? [Open an issue](https://github.com/wac0ku/fastapi-issue-hive/issues) — including the exact error output. Bonus points if you paste your issue into the hive first and attach its analysis.
