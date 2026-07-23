# 04 — Knowledge Base

The knowledge base (`app/knowledge/connectivity.py`) is the heart of the hive: a curated list of `ConnectivityCategory` dataclasses. It is what makes the system useful with **zero API keys** — Claude only enhances these answers, it never replaces them.

## The 9 categories

| ID | Name | Typical symptoms |
|----|------|------------------|
| `cors` | CORS / Cross-Origin | "blocked by CORS policy", failing preflight OPTIONS |
| `connection_refused` | Connection Refused / Binding | ERR_CONNECTION_REFUSED, "address already in use" |
| `reverse_proxy` | Reverse Proxy | 502/504 behind nginx/Traefik/Cloudflare, broken `/docs` under sub-paths |
| `timeout` | Timeouts / Hanging Requests | requests hang, keep-alive drops, "never returns" |
| `websocket` | WebSocket Connectivity | close code 1006, failing handshakes, ws:// vs wss:// |
| `ssl_https` | SSL / HTTPS | certificate errors, mixed content, redirect loops |
| `docker_networking` | Docker / Container Networking | "name or service not known", localhost-in-container confusion |
| `event_loop_blocking` | Event Loop Blocking | one request at a time, throughput collapse under load |
| `streaming` | Streaming / SSE Buffering | StreamingResponse arrives all at once, proxy buffering |

## Anatomy of a category

```python
ConnectivityCategory(
    id="cors",                          # stable identifier, used in the API
    name="CORS / Cross-Origin",         # human-readable name
    description="Browser blocks ...",   # one-liner shown in /categories
    signals=[                           # regex patterns for triage (matched
        r"\bcors\b", r"preflight",      # case-insensitively against
    ],                                  # title + body + labels)
    root_causes=[...],                  # shown in diagnosis
    fixes=[...],                        # concrete, copy-pasteable remedies
    doc_links=[...],                    # official documentation
)
```

## How triage scoring works

1. Title, body and labels are concatenated and lowercased.
2. Every signal regex of every category is tested against this text.
3. Score per category: `min(1.0, (hits + title_hits) / (signal_count * 0.75))` — a match in the *title* counts twice, because titles name the actual problem while bodies quote logs full of coincidental keywords.
4. The top 3 categories are returned; below a confidence of **0.15** the issue is declared out of scope and the reporter asks clarifying questions instead of guessing.

Design intent: **prefer "I don't know" over a confident wrong answer.** A triage system that misdiagnoses trains users to ignore it.

## Adding a category

One dataclass entry, no other code changes. Everything downstream — `/categories`, triage, diagnosis, research briefs — picks it up automatically.

1. Append a `ConnectivityCategory` to `CATEGORIES` in `app/knowledge/connectivity.py`.
2. Choose signals carefully:
   - Use `\b` word boundaries for short/ambiguous terms: `\bssl\b`, not `ssl`, which would also match inside longer tokens like "wsslave".
   - Prefer symptom phrasing users actually type ("bad gateway") over jargon.
   - 5–9 signals is the sweet spot; too few starves the confidence score, too many dilutes it.
3. Write fixes as **actions**, ideally with the exact command or config line.
4. Add a test in `tests/test_triage.py` with a realistic issue text asserting your category wins.
5. `pytest -v` — done.

## Quality guidelines for entries

- **Root causes** explain *why* it breaks; **fixes** say *what to type*. Keep them separate.
- Every category needs at least one official documentation link.
- Keep entries framework-current: verify fixes against the FastAPI/uvicorn versions in `pyproject.toml` before adding them.
