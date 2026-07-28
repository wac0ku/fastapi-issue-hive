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
    id="cors",                                    # stable identifier, used in the API
    name="CORS / Cross-Origin",                   # human-readable name
    description="Browser blocks ...",             # one-liner shown in /categories
    signals=(                                     # weighted regex cues, matched
        Signal(r"access-control-allow-origin", 1.8),  # case-insensitively against
        Signal(r"\bcors\b", 1.4),                     # title + body + labels
        Signal(r"preflight", 1.5),
        Signal(r"cross[- ]origin"),               # weight defaults to 1.0
    ),
    root_causes=(...),                            # shown in diagnosis
    fixes=(...),                                  # concrete, copy-pasteable remedies
    doc_links=(...),                              # official documentation
)
```

All fields are tuples, not lists: the dataclass is `frozen=True`, and with list fields that only blocked attribute rebinding while leaving the shared `CATEGORIES` singleton mutable process-wide.

## How triage scoring works

1. Title, body and labels are concatenated.
2. Every cue of every category is tested against that text (patterns are compiled once at import, matching case-insensitively).
3. Each hit contributes its **weight**, doubled when the cue also matches the *title* — titles name the actual problem, bodies quote logs full of coincidental keywords.
4. The weighted total runs through a saturation curve, `1 - exp(-points / 2.5)`, giving a confidence in `(0, 1)`.
5. The top 3 categories are returned; below a confidence of **0.30** the issue is declared out of scope and the reporter asks clarifying questions instead of guessing.

Two properties of that curve matter:

- **Adding a cue can never lower a category's score.** The earlier formula divided by the number of cues a category defined, so enriching a category made it *less* confident — a direct disincentive to the contribution this document asks for.
- **Confidence never reaches 1.0.** The earlier formula clipped there, so everything above the threshold looked equally certain and the ranking lost its meaning.

Design intent: **prefer "I don't know" over a confident wrong answer.** A triage system that misdiagnoses trains users to ignore it. That is why weights exist — "access-control-allow-origin" in a body is nearly proof, "timeout" is barely a hint, and treating them equally is what once filed a feature request about a 300ms fade as a connectivity problem.

## Measuring changes to triage

Signals, weights and thresholds are only adjustable because there is something to measure them against: `tests/fixtures/triage_corpus.py` holds labelled issue texts, positives with their expected category and negatives that must be declined.

```bash
uv run pytest tests/test_triage_quality.py -v
```

The suite asserts no false positives, full recall, and the correct top category for every positive. Change a weight and this is what tells you whether you improved anything.

## Adding a category

One dataclass entry, no other code changes. Everything downstream — `/categories`, triage, diagnosis, research briefs — picks it up automatically.

1. Append a `ConnectivityCategory` to `CATEGORIES` in `app/knowledge/connectivity.py`.
2. Choose signals carefully:
   - Use `\b` word boundaries for short/ambiguous terms: `\bssl\b`, not `ssl`, which would also match inside longer tokens like "wsslave".
   - Prefer symptom phrasing users actually type ("bad gateway") over jargon.
   - Add as many as you can justify — more cues can only help. Weight them by how much a hit actually proves: ~1.8 for a string that appears in essentially no other context, 1.0 for a solid cue, ~0.5 for a generic symptom word that shows up in unrelated issues.
3. Write fixes as **actions**, ideally with the exact command or config line.
4. Add a labelled sample to `tests/fixtures/triage_corpus.py` — a realistic issue text with your category as `expected`. If your category could plausibly be confused with an existing one, add a negative too.
5. `uv run pytest -v` — the quality suite tells you whether precision and recall held.

## Quality guidelines for entries

- **Root causes** explain *why* it breaks; **fixes** say *what to type*. Keep them separate.
- Every category needs at least one official documentation link.
- Keep entries framework-current: verify fixes against the FastAPI/uvicorn versions in `pyproject.toml` before adding them.
