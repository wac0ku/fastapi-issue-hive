"""Worker 4 — Reporter: assemble the final report and a suggested issue reply.

Also builds the two NotebookLM source documents. A single brief (see research.py) stays
deliberately self-contained, but a whole repo scan must not be: repeating every category's
background once per issue would fill a notebook with duplicates and dilute the grounding.
So the corpus carries only what is specific to each issue, and the shared knowledge base
goes in as its own source via build_knowledge_source().
"""

from datetime import date

from app.knowledge import CATEGORIES
from app.schemas import Diagnosis, IssueInput, RepoScanReport, TriageResult

# Kept in one place so the corpus can carry them exactly once, at the end.
NOTEBOOKLM_PROMPTS = [
    "- 'Which failure categories cluster most often, and what do they share?'",
    "- 'Rank the issues by how much a single configuration change would fix.'",
    "- 'Which issues look similar on the surface but have different root causes?'",
    "- 'What should I ask the reporters to narrow down the ambiguous ones?'",
]


def build_reply(issue: IssueInput, triage: TriageResult, diagnosis: Diagnosis) -> str:
    if not triage.is_connectivity_issue:
        return (
            "Thanks for the report! This doesn't look like a FastAPI connectivity "
            "problem. Could you share the exact error message, how the app is "
            "deployed (bare uvicorn, Docker, behind a proxy?) and what client "
            "is making the request?"
        )

    lines = [
        f"Thanks for the report — this looks like a **{triage.matches[0].name}** problem.",
        "",
        "Most likely causes:",
        *[f"- {cause}" for cause in diagnosis.root_causes[:3]],
        "",
        "Suggested fixes to try:",
        *[f"- {fix}" for fix in diagnosis.fixes[:3]],
    ]
    if diagnosis.claude_notes:
        lines += ["", diagnosis.claude_notes.strip()]
    if diagnosis.doc_links:
        lines += ["", "References:", *[f"- {link}" for link in diagnosis.doc_links[:3]]]
    return "\n".join(lines)


def build_knowledge_source() -> str:
    """The whole knowledge base as one NotebookLM source.

    Add this to a notebook once. The scan corpus then names categories instead of
    restating their root causes for every issue.
    """
    lines = [
        "# FastAPI Connectivity Knowledge Base",
        "",
        "Every failure mode the hive can diagnose, with root causes, fixes and reference "
        "documentation. This is the shared background for any scan corpus in the same "
        "notebook — the corpus itself only carries per-issue findings.",
        "",
    ]
    for category in CATEGORIES:
        lines += [
            f"## {category.name} (`{category.id}`)",
            category.description,
            "",
            "Known root causes:",
            *[f"- {cause}" for cause in category.root_causes],
            "",
            "Fixes:",
            *[f"- {fix}" for fix in category.fixes],
            "",
            "Reference documentation:",
            *[f"- {link}" for link in category.doc_links],
            "",
        ]
    return "\n".join(lines)


def build_corpus(report: RepoScanReport) -> str:
    """A whole repo scan as a single deduplicated NotebookLM source.

    Carries the category frequency table the 'which problems cluster most often' question
    needs, then only the issue-specific findings. Category background is deliberately
    absent — it lives in build_knowledge_source().
    """
    lines = [
        f"# Connectivity Scan: {report.owner}/{report.repo}",
        "",
        f"Scanned {report.issues_scanned} open issues on {date.today().isoformat()}; "
        f"{report.connectivity_issues_found} matched a known connectivity failure mode.",
        "",
        "Category background for the findings below is in the companion source "
        "*FastAPI Connectivity Knowledge Base*.",
        "",
        "## Category frequency",
        "",
    ]

    tally: dict[str, list[float]] = {}
    for entry in report.reports:
        if entry.triage.is_connectivity_issue and entry.triage.matches:
            top = entry.triage.matches[0]
            tally.setdefault(f"{top.name} (`{top.category}`)", []).append(top.confidence)

    if tally:
        lines += ["| Category | Issues | Avg. confidence |", "|---|---|---|"]
        for name, scores in sorted(tally.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            lines.append(f"| {name} | {len(scores)} | {sum(scores) / len(scores):.2f} |")
        lines.append("")
        lines.append("Counted by each issue's top-ranked category, not by every signal match.")
    else:
        lines.append("_No issue in this scan matched a known connectivity category._")
    lines.append("")

    lines += ["## Findings per issue", ""]
    for entry in report.reports:
        lines.append(f"### {entry.issue_title}")
        if entry.issue_url:
            lines.append(f"Source: {entry.issue_url}")
        lines += ["", entry.triage.summary]
        if entry.triage.matches:
            ranked = ", ".join(
                f"{match.name} ({match.confidence})" for match in entry.triage.matches[:2]
            )
            lines.append(f"Ranked categories: {ranked}")
        if entry.diagnosis.claude_notes:
            lines += ["", entry.diagnosis.claude_notes.strip()]
        lines.append("")

    lines += ["## Suggested NotebookLM prompts", "", *NOTEBOOKLM_PROMPTS]
    return "\n".join(lines)
