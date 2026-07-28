"""The GitHub client — previously the only module with no test at all.

Every network call is mocked with respx; nothing here touches api.github.com.
"""

import httpx
import pytest
import respx
from pydantic import SecretStr

from app.config import Settings
from app.services import github
from app.services.github import GitHubError, close_http_client, fetch_open_issues

ISSUES_URL = "https://api.github.com/repos/o/r/issues"


def issue(title: str, **extra: object) -> dict[str, object]:
    return {"title": title, "body": "b", "html_url": f"https://x/{title}", "labels": [], **extra}


@pytest.fixture(autouse=True)
async def fresh_client():
    """Each test gets its own pooled client so respx sees the routes."""
    await close_http_client()
    yield
    await close_http_client()


@respx.mock
async def test_returns_open_issues():
    respx.get(ISSUES_URL).mock(return_value=httpx.Response(200, json=[issue("one"), issue("two")]))

    issues = await fetch_open_issues("o", "r", limit=5)

    assert [i.title for i in issues] == ["one", "two"]


@respx.mock
async def test_filters_out_pull_requests():
    """The issues endpoint also returns PRs; they are not issues to triage."""
    respx.get(ISSUES_URL).mock(
        return_value=httpx.Response(
            200,
            json=[issue("real"), issue("a pr", pull_request={"url": "..."}), issue("also real")],
        )
    )

    issues = await fetch_open_issues("o", "r", limit=5)

    assert [i.title for i in issues] == ["real", "also real"]


@respx.mock
async def test_pages_until_the_limit_is_filled():
    """A page can come back short after PRs are filtered — that used to silently under-deliver."""
    page_one = httpx.Response(
        200,
        json=[issue("issue-1"), issue("pr1", pull_request={}), issue("pr2", pull_request={})],
        headers={"Link": '<https://api.github.com/x?page=2>; rel="next"'},
    )
    page_two = httpx.Response(200, json=[issue("issue-2"), issue("issue-3")])
    respx.get(ISSUES_URL).mock(side_effect=[page_one, page_two])

    issues = await fetch_open_issues("o", "r", limit=3)

    assert [i.title for i in issues] == ["issue-1", "issue-2", "issue-3"]


@respx.mock
async def test_stops_when_there_is_no_next_page():
    respx.get(ISSUES_URL).mock(return_value=httpx.Response(200, json=[issue("only")]))

    issues = await fetch_open_issues("o", "r", limit=10)

    assert [i.title for i in issues] == ["only"]


@respx.mock
async def test_missing_repository_reports_not_found():
    respx.get(ISSUES_URL).mock(return_value=httpx.Response(404, json={}))

    with pytest.raises(GitHubError, match="not found or private"):
        await fetch_open_issues("o", "r")


@respx.mock
async def test_exhausted_rate_limit_is_reported_as_such():
    respx.get(ISSUES_URL).mock(
        return_value=httpx.Response(403, json={}, headers={"x-ratelimit-remaining": "0"})
    )

    with pytest.raises(GitHubError, match="rate limit"):
        await fetch_open_issues("o", "r")


@respx.mock
async def test_forbidden_without_rate_limit_is_not_called_a_rate_limit():
    """403 also means 'no permission'; the old client blamed the rate limit either way."""
    respx.get(ISSUES_URL).mock(
        return_value=httpx.Response(403, json={}, headers={"x-ratelimit-remaining": "4999"})
    )

    with pytest.raises(GitHubError, match="denied access"):
        await fetch_open_issues("o", "r")


@respx.mock
async def test_secondary_rate_limit_429_is_handled():
    respx.get(ISSUES_URL).mock(return_value=httpx.Response(429, json={}))

    with pytest.raises(GitHubError, match="rate limit"):
        await fetch_open_issues("o", "r")


@respx.mock
async def test_transient_server_error_is_retried():
    route = respx.get(ISSUES_URL).mock(
        side_effect=[
            httpx.Response(503, json={}),
            httpx.Response(200, json=[issue("recovered")]),
        ]
    )

    issues = await fetch_open_issues("o", "r", limit=1)

    assert [i.title for i in issues] == ["recovered"]
    assert route.call_count == 2


@respx.mock
async def test_gives_up_after_max_attempts():
    respx.get(ISSUES_URL).mock(return_value=httpx.Response(500, json={}))

    with pytest.raises(GitHubError, match="unreachable after"):
        await fetch_open_issues("o", "r")


@respx.mock
async def test_network_error_is_retried_then_surfaced():
    respx.get(ISSUES_URL).mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(GitHubError, match="unreachable after"):
        await fetch_open_issues("o", "r")


@respx.mock
async def test_token_is_sent_when_configured(monkeypatch):
    monkeypatch.setattr(
        github, "get_settings", lambda: Settings(github_token=SecretStr("ghp-secret"))
    )
    route = respx.get(ISSUES_URL).mock(return_value=httpx.Response(200, json=[issue("some issue")]))

    await fetch_open_issues("o", "r", limit=1)

    assert route.calls[0].request.headers["Authorization"] == "Bearer ghp-secret"


@respx.mock
async def test_no_authorization_header_without_a_token():
    route = respx.get(ISSUES_URL).mock(return_value=httpx.Response(200, json=[issue("some issue")]))

    await fetch_open_issues("o", "r", limit=1)

    assert "Authorization" not in route.calls[0].request.headers


@respx.mock
async def test_server_side_cap_beats_a_larger_request(monkeypatch):
    monkeypatch.setattr(github, "get_settings", lambda: Settings(max_issues_per_repo=2))
    respx.get(ISSUES_URL).mock(
        return_value=httpx.Response(200, json=[issue(f"issue-{n}") for n in range(10)])
    )

    issues = await fetch_open_issues("o", "r", limit=25)

    assert len(issues) == 2


@respx.mock
async def test_unusable_issue_is_skipped_not_fatal():
    """A real tracker contains issues titled "ok"; that must not abort the whole scan.

    IssueInput's minimum title length was written for user-submitted text, so ingesting
    such an issue used to raise ValidationError out of fetch_open_issues.
    """
    respx.get(ISSUES_URL).mock(
        return_value=httpx.Response(
            200, json=[issue("ok"), issue("a proper title"), {"no_title": True}]
        )
    )

    issues = await fetch_open_issues("o", "r", limit=5)

    assert [i.title for i in issues] == ["a proper title"]


@respx.mock
async def test_overlong_body_is_truncated_rather_than_rejected():
    respx.get(ISSUES_URL).mock(
        return_value=httpx.Response(200, json=[issue("long one", body="x" * 50_000)])
    )

    issues = await fetch_open_issues("o", "r", limit=1)

    assert len(issues[0].body) == 20_000
