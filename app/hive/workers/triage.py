"""Worker 1 — Triage: classify an issue against the connectivity knowledge base.

Deterministic: regex signal matching produces a ranked list of category
matches with confidence scores. No API calls — triage is always free.
"""

import re

from app.knowledge import CATEGORIES
from app.schemas import CategoryMatch, IssueInput, TriageResult

# A single weak signal match can be coincidence; require a minimum score
# before declaring the issue connectivity-related.
MIN_CONFIDENCE = 0.15


def run(issue: IssueInput) -> TriageResult:
    text = f"{issue.title}\n{issue.body}\n{' '.join(issue.labels)}".lower()

    matches: list[CategoryMatch] = []
    for category in CATEGORIES:
        hits = []
        for pattern in category.signals:
            if re.search(pattern, text):
                hits.append(pattern)
        if hits:
            # Title hits weigh double — the title names the actual problem.
            title_bonus = sum(
                1 for p in hits if re.search(p, issue.title.lower())
            )
            score = min(1.0, (len(hits) + title_bonus) / (len(category.signals) * 0.75))
            matches.append(
                CategoryMatch(
                    category=category.id,
                    name=category.name,
                    confidence=round(score, 2),
                    matched_signals=hits,
                )
            )

    matches.sort(key=lambda m: m.confidence, reverse=True)
    is_connectivity = bool(matches) and matches[0].confidence >= MIN_CONFIDENCE

    if is_connectivity:
        top = ", ".join(m.name for m in matches[:2])
        summary = f"Connectivity issue detected — most likely: {top}."
    else:
        summary = "No FastAPI connectivity signals found — likely out of scope for this hive."

    return TriageResult(matches=matches[:3], is_connectivity_issue=is_connectivity, summary=summary)
