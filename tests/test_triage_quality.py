"""Measures triage against a labelled corpus instead of spot-checking it.

The scoring formula used to be untestable in any meaningful sense: individual examples
passed while a plain feature request was still classified as a connectivity problem.
These tests pin the aggregate behaviour, so changing a weight or a threshold shows up as
a number rather than as a surprise in production.
"""

import math

import pytest

from app.hive.workers import triage
from app.schemas import IssueInput
from tests.fixtures.triage_corpus import ALL_SAMPLES, NEGATIVES, POSITIVES, Sample


def classify(sample: Sample) -> tuple[bool, str | None]:
    result = triage.run(
        IssueInput(title=sample.title, body=sample.body, labels=list(sample.labels))
    )
    top = result.matches[0].category if result.matches else None
    return result.is_connectivity_issue, top


def test_no_false_positives_on_out_of_scope_issues():
    """The expensive mistake: a confident, wrong diagnosis that also costs a Claude call."""
    misfiled = [(s.title, classify(s)[1]) for s in NEGATIVES if classify(s)[0]]
    assert misfiled == []


def test_every_connectivity_issue_is_recognised():
    missed = [s.title for s in POSITIVES if not classify(s)[0]]
    assert missed == []


def test_top_category_is_correct_for_every_positive():
    wrong = [
        (s.title, s.expected, classify(s)[1]) for s in POSITIVES if classify(s)[1] != s.expected
    ]
    assert wrong == []


def test_confidence_never_saturates():
    """Clipping at exactly 1.0 threw away the ranking above the threshold."""
    for sample in ALL_SAMPLES:
        result = triage.run(IssueInput(title=sample.title, body=sample.body))
        for match in result.matches:
            assert match.confidence < 1.0


def test_adding_a_signal_cannot_lower_a_categorys_score():
    """The old formula divided by the signal count, penalising richer categories.

    Contributors are explicitly asked for new signals, so this has to stay monotone.
    """
    points = 3.0
    before = triage._confidence(points)
    after = triage._confidence(points + 0.5)
    assert after > before


def test_confidence_is_monotone_in_evidence():
    scores = [triage._confidence(p) for p in (0.5, 1.0, 2.0, 4.0, 8.0)]
    assert scores == sorted(scores)
    assert all(0.0 < s < 1.0 for s in scores)


def test_a_single_weak_cue_stays_below_the_threshold() -> None:
    """One incidental mention of "timeout" must not amount to a diagnosis."""
    weakest_strong_cue = 0.6
    assert triage._confidence(weakest_strong_cue) < triage.MIN_CONFIDENCE


@pytest.mark.parametrize("sample", POSITIVES, ids=lambda s: s.expected)
def test_positive_samples_clear_the_threshold(sample: Sample) -> None:
    result = triage.run(
        IssueInput(title=sample.title, body=sample.body, labels=list(sample.labels))
    )
    assert result.matches[0].confidence >= triage.MIN_CONFIDENCE


def test_saturation_curve_matches_its_definition():
    assert triage._confidence(triage.SATURATION) == pytest.approx(
        round(1 - math.exp(-1), 2), abs=0.01
    )
