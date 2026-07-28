# 07 — NotebookLM Research Workflow

NotebookLM has no public API, so the hive integrates with it the way NotebookLM is designed to be used: **it generates high-quality source documents** that you drop into a notebook.

There are two shapes, and picking the right one matters more than it looks:

| You want to… | Use | Why |
|---|---|---|
| Dig into **one** issue | `research_brief.markdown` from `/analyze/issue` | Self-contained: issue, triage, category background and doc links in a single file |
| Analyse a **whole repository** | `POST /analyze/repo/corpus` + `GET /knowledge/export` | Two sources instead of N near-identical ones |

## Per-issue deep dives

1. Run an analysis: `POST /analyze/issue`
2. Save `research_brief.markdown` from the response as a `.md` file:
   ```bash
   curl -s -X POST localhost:8000/analyze/issue \
     -H "Content-Type: application/json" \
     -d '{"title": "...", "body": "..."}' \
     | python -c "import sys, json; print(json.load(sys.stdin)['research_brief']['markdown'])" \
     > brief.md
   ```
3. In [notebooklm.google.com](https://notebooklm.google.com), create a notebook and add the file as a source
4. Use the prompts embedded at the bottom of every brief:
   - *"Summarize the most likely root cause and rank the fixes by effort."*
   - *"Generate a checklist to reproduce and verify the fix."*
   - *"What questions should I ask the issue reporter to narrow this down?"*
5. Optional: generate an **Audio Overview** to review a triaged issue hands-free

## Why briefs instead of raw issues

Each brief is self-contained by design: original issue text, triage verdict, background on the matched failure modes, official documentation links, and (in claude-enhanced mode) an issue-specific deep-dive section. NotebookLM answers are only as good as their sources — the brief packages exactly the context a grounded answer needs, which a bare issue body does not.

## Repository scans: two sources, not twenty

Self-containment is the right call for a single brief and the wrong one for a scan. Every brief of the same category repeats the same background, so a notebook built from twenty of them is roughly **three quarters duplicated text** — identical root-cause paragraphs once per issue, plus the same prompt block twenty times. Ask *"which failure categories cluster most often?"* and NotebookLM ends up grounding on repetition rather than on evidence.

A scan therefore splits into the part that changes and the part that doesn't:

```bash
# 1. The shared background — add once per notebook, reuse across scans
curl -s localhost:8000/knowledge/export > knowledge-base.md

# 2. The scan itself — findings only, no repeated background
curl -s -X POST localhost:8000/analyze/repo/corpus \
  -H "Content-Type: application/json" \
  -d '{"owner": "fastapi", "repo": "fastapi", "limit": 25}' \
  > scan-fastapi.md
```

Both endpoints return `text/markdown` directly, so there is no JSON extraction step.

Add both files to one notebook. `scan-*.md` carries:

- a **category frequency table** (category, number of issues, average confidence) — the direct answer to the clustering question
- per issue: title, link back to GitHub, triage verdict, ranked categories, and the Claude notes when a key is configured
- the suggested prompts **once**, at the end

Scanning several repositories? Add one `scan-*.md` per repo and keep the single `knowledge-base.md`. Cross-repo questions then work without re-uploading the background every time.

## Niche research at scale

The same workflow found this project's niche. Repeatable recipe:

1. Export a corpus for several FastAPI-adjacent repositories
2. Add them plus `knowledge-base.md` as sources to a single NotebookLM notebook
3. Ask: *"Which failure categories cluster most often across these repos?"*, *"Which recurring problems have no good existing tooling?"*, *"Draft a landing-page pitch for a tool solving the top cluster."*

The result of that process for this project is documented in [research/niche-analysis.md](research/niche-analysis.md).
