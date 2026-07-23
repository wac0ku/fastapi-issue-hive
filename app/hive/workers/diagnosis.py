"""Worker 2 — Diagnosis: turn triage matches into root causes and fixes.

Heuristic path merges the knowledge base entries of the top-matched
categories. If Claude is available, it additionally writes issue-specific
notes on top of the deterministic result.
"""

from app.knowledge import CATEGORIES
from app.schemas import Diagnosis, IssueInput, TriageResult
from app.services.claude import ask_claude

_BY_ID = {c.id: c for c in CATEGORIES}


async def run(issue: IssueInput, triage: TriageResult) -> Diagnosis:
    root_causes: list[str] = []
    fixes: list[str] = []
    doc_links: list[str] = []

    for match in triage.matches[:2]:
        category = _BY_ID[match.category]
        root_causes.extend(category.root_causes)
        fixes.extend(category.fixes)
        doc_links.extend(category.doc_links)

    if not triage.is_connectivity_issue:
        root_causes = ["Issue does not match any known FastAPI connectivity pattern."]
        fixes = ["Re-run with a more specific description (error message, deployment setup, client type)."]

    claude_notes = None
    if triage.is_connectivity_issue:
        claude_notes = await ask_claude(
            "diagnosis",
            f"Issue title: {issue.title}\n\nIssue body:\n{issue.body[:4000]}\n\n"
            f"Triage result: {triage.summary}",
        )

    return Diagnosis(
        root_causes=root_causes,
        fixes=fixes,
        doc_links=list(dict.fromkeys(doc_links)),
        enhanced_by_claude=claude_notes is not None,
        claude_notes=claude_notes or "",
    )
