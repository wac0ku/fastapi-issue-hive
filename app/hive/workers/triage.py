"""Worker 1 — Triage: classify an issue against the connectivity knowledge base.

Deterministic: weighted regex cues produce a ranked list of category matches with
confidence scores. No API calls — triage is always free.

Scoring is evidence-based rather than coverage-based. The previous formula divided hits
by the number of signals a category happened to define, so a category scored *lower* the
more cues it knew about — a direct disincentive to the contributions CONTRIBUTING.md asks
for — and it clipped hard at 1.0, so everything above the threshold looked equally
certain. Now every cue contributes its own weight and the total runs through a saturation
curve: monotone, asymptotic to 1.0, and independent of how many cues a category defines.

Changes here must be measured against tests/fixtures/triage_corpus.py.
"""

import math
import re

from app.knowledge import CATEGORIES
from app.schemas import CategoryMatch, IssueInput, TriageResult

# Weighted evidence needed for a ~63% score. Chosen against the labelled corpus: real
# issues accumulate 2-6 points, incidental mentions stay well below 1.
SATURATION = 2.5

# A cue in the title counts double — the title names the problem, the body often only
# describes its surroundings.
TITLE_MULTIPLIER = 2.0

# Below this the issue is out of scope. Deliberately above what a single weak cue
# (0.4-0.6 points) can reach, so a feature request mentioning a fade "timeout" is not
# diagnosed as a connectivity problem.
MIN_CONFIDENCE = 0.30

# Compiled once at import rather than per call: run() is synchronous, sits in the request
# path, and evaluates ~73 patterns per issue. Case folding moves into the pattern flags,
# so the haystack no longer has to be lowercased first.
_COMPILED: tuple[tuple[str, tuple[tuple[re.Pattern[str], float, str], ...]], ...] = tuple(
    (
        category.id,
        tuple(
            (re.compile(signal.pattern, re.IGNORECASE), signal.weight, signal.pattern)
            for signal in category.signals
        ),
    )
    for category in CATEGORIES
)

_BY_ID = {category.id: category for category in CATEGORIES}


def _confidence(points: float) -> float:
    """Saturating curve: strictly increasing, asymptotic to 1.0, never reaching it."""
    return round(1.0 - math.exp(-points / SATURATION), 2)


def run(issue: IssueInput) -> TriageResult:
    haystack = f"{issue.title}\n{issue.body}\n{' '.join(issue.labels)}"

    matches: list[CategoryMatch] = []
    for category_id, signals in _COMPILED:
        points = 0.0
        hits: list[str] = []
        for compiled, weight, pattern in signals:
            if not compiled.search(haystack):
                continue
            hits.append(pattern)
            points += weight * (TITLE_MULTIPLIER if compiled.search(issue.title) else 1.0)

        if hits:
            matches.append(
                CategoryMatch(
                    category=category_id,
                    name=_BY_ID[category_id].name,
                    confidence=_confidence(points),
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
