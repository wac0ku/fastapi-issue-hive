"""Guards against silently spending Claude calls or output budget.

Every test here runs offline — the point is exactly that the hive must not reach for the
API when it has nothing to gain from it.
"""

import asyncio

import pytest

from app.config import Settings
from app.hive import queen as queen_module
from app.hive.workers import research, triage
from app.schemas import IssueInput
from app.services.claude import DEFAULT_MAX_TOKENS, _resolve_max_tokens


class CallCounter:
    """Stands in for ask_claude and records how often it was reached."""

    def __init__(self):
        self.calls = 0

    async def __call__(self, worker, user_content, max_tokens=None):
        self.calls += 1
        return "stand-in deep dive"


@pytest.fixture
def spy(monkeypatch) -> CallCounter:
    counter = CallCounter()
    monkeypatch.setattr(research, "ask_claude", counter)
    return counter


async def test_research_skips_claude_for_out_of_scope_issue(spy):
    """A deep-dive on an issue triage already rejected has nothing to work with."""
    issue = IssueInput(title="Feature request: add dark mode", body="Theme toggle please.")
    result = triage.run(issue)
    assert not result.is_connectivity_issue

    brief = await research.run(issue, result)

    assert spy.calls == 0
    assert "Claude Deep-Dive" not in brief.markdown


async def test_research_still_calls_claude_for_connectivity_issue(spy):
    issue = IssueInput(
        title="CORS error blocked by CORS policy",
        body="No Access-Control-Allow-Origin header is present, preflight OPTIONS fails.",
    )
    result = triage.run(issue)
    assert result.is_connectivity_issue

    brief = await research.run(issue, result)

    assert spy.calls == 1
    assert "Claude Deep-Dive" in brief.markdown


def test_max_tokens_precedence():
    """Explicit argument beats templates.json, which beats the global default."""
    template = {"system": "...", "max_tokens": 512}

    assert _resolve_max_tokens(template, 256) == 256
    assert _resolve_max_tokens(template, None) == 512
    assert _resolve_max_tokens({"system": "..."}, None) == DEFAULT_MAX_TOKENS


def test_shipped_templates_all_declare_a_budget():
    """Regression for the config that used to be read by nobody."""
    from app.services.claude import load_prompt

    for worker in ("diagnosis", "research", "niche"):
        template = load_prompt(worker)
        assert _resolve_max_tokens(template, None) == template["max_tokens"]
        assert template["max_tokens"] < DEFAULT_MAX_TOKENS


async def test_repo_scan_caps_concurrency(monkeypatch):
    """One request must not fan out into a Claude call per issue simultaneously."""
    issues = [IssueInput(title=f"CORS error number {n}", body="preflight fails") for n in range(12)]

    monkeypatch.setattr(
        queen_module, "get_settings", lambda: Settings(max_concurrent_analyses=3)
    )

    async def fake_fetch(owner, repo, limit):
        return issues

    monkeypatch.setattr(queen_module, "fetch_open_issues", fake_fetch)

    live = 0
    peak = 0
    original = queen_module.HiveQueen.analyze_issue

    async def tracked(self, issue):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        try:
            await asyncio.sleep(0.01)
            return await original(self, issue)
        finally:
            live -= 1

    monkeypatch.setattr(queen_module.HiveQueen, "analyze_issue", tracked)

    report = await queen_module.HiveQueen().scan_repository("o", "r", len(issues))

    assert report.issues_scanned == len(issues)
    assert peak <= 3, f"ran {peak} analyses at once despite a cap of 3"


async def test_repo_scan_times_out_instead_of_hanging(monkeypatch):
    monkeypatch.setattr(
        queen_module, "get_settings", lambda: Settings(scan_timeout_seconds=0.05)
    )

    async def fake_fetch(owner, repo, limit):
        return [IssueInput(title="CORS error blocked", body="preflight fails")]

    monkeypatch.setattr(queen_module, "fetch_open_issues", fake_fetch)

    async def never_finishes(self, issue):
        await asyncio.sleep(10)

    monkeypatch.setattr(queen_module.HiveQueen, "analyze_issue", never_finishes)

    with pytest.raises(asyncio.TimeoutError):
        await queen_module.HiveQueen().scan_repository("o", "r", 1)
