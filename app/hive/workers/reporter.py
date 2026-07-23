"""Worker 4 — Reporter: assemble the final report and a suggested issue reply."""

from app.schemas import Diagnosis, IssueInput, TriageResult


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
