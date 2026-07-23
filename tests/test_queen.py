import pytest

from app.hive import HiveQueen
from app.schemas import IssueInput


@pytest.fixture
def queen() -> HiveQueen:
    return HiveQueen()


async def test_full_pipeline_heuristic_mode(queen):
    issue = IssueInput(
        title="Request hangs and times out under concurrent load",
        body="Endpoints using async def with time.sleep block the event loop. "
             "Only one request at a time gets processed, everything else times out.",
    )
    report = await queen.analyze_issue(issue)

    assert report.triage.is_connectivity_issue
    assert report.diagnosis.root_causes
    assert report.diagnosis.fixes
    assert not report.diagnosis.enhanced_by_claude  # no API key in tests
    assert report.suggested_reply
    assert "triage" in report.workers_used
    assert "reporter" in report.workers_used


async def test_research_brief_is_notebooklm_ready(queen):
    issue = IssueInput(
        title="WebSocket closes with code 1006 behind nginx",
        body="wss:// handshake succeeds locally but the connection closed error "
             "appears in production behind nginx.",
    )
    report = await queen.analyze_issue(issue)
    brief = report.research_brief

    assert brief.title.startswith("Research Brief:")
    assert "## Original Issue" in brief.markdown
    assert "## Suggested NotebookLM prompts" in brief.markdown
    assert "WebSocket" in brief.markdown


async def test_out_of_scope_issue_gets_clarifying_reply(queen):
    issue = IssueInput(title="Please add CSV export button", body="Export data as CSV.")
    report = await queen.analyze_issue(issue)

    assert not report.triage.is_connectivity_issue
    assert "error message" in report.suggested_reply
