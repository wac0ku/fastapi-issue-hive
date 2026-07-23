"""Worker 3 — Research: build a NotebookLM-ready research brief.

NotebookLM has no public API, so the hive produces what NotebookLM consumes
best: a dense, self-contained markdown source document. Drop the brief into
a NotebookLM notebook to generate audio overviews, FAQs, and deep-dive
follow-ups on the issue. See docs/notebooklm-workflow.md.
"""

from app.knowledge import CATEGORIES
from app.schemas import IssueInput, ResearchBrief, TriageResult
from app.services.claude import ask_claude

_BY_ID = {c.id: c for c in CATEGORIES}


async def run(issue: IssueInput, triage: TriageResult) -> ResearchBrief:
    sections = [
        f"# Research Brief: {issue.title}",
        "",
        "## Original Issue",
        issue.body.strip() or "_No body provided._",
    ]
    if issue.url:
        sections.append(f"\nSource: {issue.url}")

    sections += ["", "## Triage", triage.summary, ""]

    for match in triage.matches[:2]:
        category = _BY_ID[match.category]
        sections += [
            f"## Background: {category.name} (confidence {match.confidence})",
            category.description,
            "",
            "Known root causes:",
            *[f"- {cause}" for cause in category.root_causes],
            "",
            "Reference documentation:",
            *[f"- {link}" for link in category.doc_links],
            "",
        ]

    extra = await ask_claude(
        "research",
        f"Issue: {issue.title}\n\n{issue.body[:3000]}\n\nTriage: {triage.summary}",
    )
    if extra:
        sections += ["## Claude Deep-Dive", extra, ""]

    sections += [
        "## Suggested NotebookLM prompts",
        "- 'Summarize the most likely root cause and rank the fixes by effort.'",
        "- 'Generate a checklist to reproduce and verify the fix.'",
        "- 'What questions should I ask the issue reporter to narrow this down?'",
    ]

    return ResearchBrief(title=f"Research Brief: {issue.title}", markdown="\n".join(sections))
