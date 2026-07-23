# 07 — NotebookLM Research Workflow

NotebookLM has no public API, so the hive integrates with it the way NotebookLM is designed to be used: **it generates high-quality source documents** that you drop into a notebook. Every `/analyze/issue` response carries one in `research_brief.markdown`.

## Per-issue deep dives

1. Run an analysis: `POST /analyze/issue` (or `/analyze/repo`)
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
5. Optional: generate an **Audio Overview** to review a batch of triaged issues hands-free

## Why briefs instead of raw issues

Each brief is self-contained by design: original issue text, triage verdict, background on the matched failure modes, official documentation links, and (in claude-enhanced mode) an issue-specific deep-dive section. NotebookLM answers are only as good as their sources — the brief packages exactly the context a grounded answer needs, which a bare issue body does not.

## Niche research at scale

The same workflow found this project's niche. Repeatable recipe:

1. Scan several ecosystem repos: `POST /analyze/repo` for FastAPI-adjacent projects
2. Export the briefs of all connectivity-positive reports into one folder
3. Add them all as sources to a single NotebookLM notebook
4. Ask: *"Which failure categories cluster most often?"*, *"Which recurring problems have no good existing tooling?"*, *"Draft a landing-page pitch for a tool solving the top cluster."*

The result of that process for this project is documented in [research/niche-analysis.md](research/niche-analysis.md).
