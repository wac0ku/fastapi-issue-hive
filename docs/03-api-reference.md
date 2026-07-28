# 03 — API Reference

Interactive version: start the server and open **http://localhost:8000/docs** (Swagger UI) or **/redoc**.

---

## `GET /health`

Liveness probe plus active mode.

**Response `200`**

```json
{ "status": "ok", "version": "1.0.0", "mode": "heuristic" }
```

`mode` is `"claude-enhanced"` when `ANTHROPIC_API_KEY` is configured, else `"heuristic"`.

---

## `GET /categories`

Lists every connectivity failure mode the hive can diagnose.

**Response `200`**

```json
[
  { "id": "cors", "name": "CORS / Cross-Origin", "description": "Browser blocks requests because CORS headers are missing or misconfigured." },
  { "id": "connection_refused", "name": "Connection Refused / Binding", "description": "..." }
]
```

---

## `POST /analyze/issue`

Runs the full hive pipeline on a single issue.

**Request body** (`IssueInput`)

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | ✅ | 3–500 chars |
| `body` | string | – | ≤ 20 000 chars |
| `url` | string | – | source link, echoed into the research brief |
| `labels` | string[] | – | labels participate in triage matching |

**Response `200`** (`AnalysisReport`)

```json
{
  "issue_title": "502 Bad Gateway with nginx in front of uvicorn",
  "triage": {
    "matches": [
      {
        "category": "reverse_proxy",
        "name": "Reverse Proxy (nginx / Traefik / Cloudflare)",
        "confidence": 0.61,
        "matched_signals": ["\\bnginx\\b", "\\b502\\b", "bad gateway"]
      }
    ],
    "is_connectivity_issue": true,
    "summary": "Connectivity issue detected — most likely: Reverse Proxy (nginx / Traefik / Cloudflare)."
  },
  "diagnosis": {
    "root_causes": ["Proxy forwards to the wrong upstream host/port (502 Bad Gateway)", "..."],
    "fixes": ["In nginx: proxy_pass http://127.0.0.1:8000; ...", "..."],
    "doc_links": ["https://fastapi.tiangolo.com/deployment/behind-a-proxy/"],
    "enhanced_by_claude": false,
    "claude_notes": ""
  },
  "research_brief": {
    "title": "Research Brief: 502 Bad Gateway with nginx in front of uvicorn",
    "markdown": "# Research Brief: ...\n\n## Original Issue\n..."
  },
  "suggested_reply": "Thanks for the report — this looks like a **Reverse Proxy ...** problem.\n...",
  "workers_used": ["triage", "diagnosis", "research", "reporter"]
}
```

Field notes:

- `triage.matches` — top 3 categories, sorted by confidence (0.0–1.0)
- `triage.is_connectivity_issue` — `false` means the reply asks clarifying questions instead of diagnosing
- `diagnosis.enhanced_by_claude` / `claude_notes` — populated only in claude-enhanced mode
- `research_brief.markdown` — save as `.md` and feed to NotebookLM ([07 — NotebookLM Workflow](07-notebooklm-workflow.md))
- `workers_used` — includes `"claude-enhancement"` in claude-enhanced mode

**Response `422`** — validation error (e.g. empty title).

---

## `POST /analyze/repo`

Fetches open issues of a **public** GitHub repository and analyzes each.

**Request body** (`RepoScanRequest`)

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `owner` | string | ✅ | 1–100 chars |
| `repo` | string | ✅ | 1–100 chars |
| `limit` | int | – | 1–25, default 5 |

Pull requests returned by the GitHub issues endpoint are filtered out.

**Response `200`** (`RepoScanReport`)

```json
{
  "owner": "fastapi",
  "repo": "fastapi",
  "issues_scanned": 5,
  "connectivity_issues_found": 2,
  "reports": [ { "issue_title": "...", "triage": { }, "diagnosis": { }, "...": "..." } ]
}
```

`reports` contains a full `AnalysisReport` per scanned issue, connectivity-related or not — filter client-side on `triage.is_connectivity_issue`.

**Response `502`** — upstream GitHub error, with a human-readable `detail`:

| Cause | detail |
|-------|--------|
| Repo missing/private | `Repository owner/repo not found or private` |
| Rate limit | `GitHub API rate limit exceeded — set GITHUB_TOKEN in .env` |
| Other | `GitHub API error <status>` |

**Response `504`** — the scan exceeded `SCAN_TIMEOUT_SECONDS` (`Repository scan exceeded its time budget`).

---

## `POST /analyze/repo/corpus`

The same scan as **one deduplicated markdown document** for NotebookLM. Same request body as `/analyze/repo`, and the same `502`/`504` responses.

**Response `200`** — `text/markdown`, not JSON:

```markdown
# Connectivity Scan: fastapi/fastapi

Scanned 25 open issues on 2026-07-28; 9 matched a known connectivity failure mode.

## Category frequency

| Category | Issues | Avg. confidence |
|---|---|---|
| CORS / Cross-Origin (`cors`) | 4 | 0.91 |
...
```

Category background is deliberately **absent** — pair this with `GET /knowledge/export` in the same notebook. See [07 — NotebookLM Workflow](07-notebooklm-workflow.md).

---

## `GET /knowledge/export`

The whole knowledge base as a single NotebookLM source: every category with its root causes, fixes and documentation links.

**Response `200`** — `text/markdown`. Static, so it can be cached or committed alongside your notebooks; add it once and reuse it across scans.

---

## Programmatic use without HTTP

The Queen is importable — useful for scripts, notebooks, or your own bots:

```python
import asyncio
from app.hive import HiveQueen
from app.schemas import IssueInput

async def main():
    queen = HiveQueen()
    report = await queen.analyze_issue(
        IssueInput(title="WebSocket closes with 1006 behind nginx", body="...")
    )
    print(report.suggested_reply)

asyncio.run(main())
```
