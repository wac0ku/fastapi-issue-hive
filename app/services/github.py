"""Fetch open issues from a public GitHub repository via the REST API."""

import asyncio
import logging
from functools import lru_cache
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import MAX_BODY_CHARS, IssueInput

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
PER_PAGE_MAX = 100
RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
MAX_ATTEMPTS = 3


class GitHubError(Exception):
    pass


@lru_cache(maxsize=1)
def _client() -> httpx.AsyncClient:
    """One pooled client for the process rather than a fresh one per request.

    Building a client per call meant a new TCP and TLS handshake for every scan.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=5.0),
        headers={"Accept": "application/vnd.github+json"},
        follow_redirects=True,
    )


async def close_http_client() -> None:
    """Release the shared client. Called on application shutdown."""
    if _client.cache_info().currsize:
        await _client().aclose()
        _client.cache_clear()


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    if settings.github_authenticated:
        return {"Authorization": f"Bearer {settings.github_token.get_secret_value()}"}
    return {}


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 404:
        raise GitHubError("Repository not found or private")
    if response.status_code in (403, 429):
        # 403 covers both rate limiting and plain lack of permission; the remaining-quota
        # header is what actually distinguishes them.
        if response.status_code == 429 or response.headers.get("x-ratelimit-remaining") == "0":
            raise GitHubError("GitHub API rate limit exceeded — set GITHUB_TOKEN in .env")
        raise GitHubError("GitHub denied access to this repository")
    if response.status_code != 200:
        raise GitHubError(f"GitHub API error {response.status_code}")


async def _get(url: str, params: dict[str, Any]) -> httpx.Response:
    """GET with bounded retries on transient failures, honouring Retry-After."""
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await _client().get(url, headers=_auth_headers(), params=params)
        except httpx.RequestError as exc:
            last_error = exc
            logger.warning("github request failed", extra={"attempt": attempt, "error": str(exc)})
        else:
            if response.status_code not in RETRYABLE_STATUS:
                return response
            last_error = GitHubError(f"GitHub API error {response.status_code}")
            logger.warning(
                "github returned a retryable status",
                extra={"attempt": attempt, "status": response.status_code},
            )
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                await asyncio.sleep(min(float(retry_after), 10.0))
                continue

        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(0.5 * 2 ** (attempt - 1))

    raise GitHubError(f"GitHub unreachable after {MAX_ATTEMPTS} attempts: {last_error}")


def _to_issue(item: dict[str, Any]) -> IssueInput | None:
    """Map one API item onto IssueInput, or None if it does not fit.

    IssueInput's constraints were written for user-submitted text (a title of at least
    three characters, a bounded body). Real trackers contain issues titled "ok" and
    bodies past the limit, and those used to abort an entire scan with a ValidationError.
    One unusable issue should cost that issue, not the report.
    """
    try:
        return IssueInput(
            title=item["title"],
            body=(item.get("body") or "")[:MAX_BODY_CHARS],
            url=item.get("html_url", ""),
            labels=[label["name"] for label in item.get("labels", [])],
        )
    except (ValidationError, KeyError, TypeError) as exc:
        logger.warning(
            "skipping unusable issue", extra={"url": item.get("html_url", ""), "error": str(exc)}
        )
        return None


async def fetch_open_issues(owner: str, repo: str, limit: int = 5) -> list[IssueInput]:
    """Open issues of a public repository, pull requests excluded.

    Pages until `limit` real issues are collected: the issues endpoint also returns pull
    requests, so one page of `limit` items can come back short after filtering.
    """
    settings = get_settings()
    wanted = min(limit, settings.max_issues_per_repo)
    url = f"{API_BASE}/repos/{owner}/{repo}/issues"

    issues: list[IssueInput] = []
    page = 1
    while len(issues) < wanted:
        response = await _get(
            url,
            {"state": "open", "per_page": min(wanted * 2, PER_PAGE_MAX), "page": page},
        )
        _raise_for_status(response)

        batch: list[dict[str, Any]] = response.json()
        if not batch:
            break

        for item in batch:
            if "pull_request" in item:  # the issues endpoint also returns PRs
                continue
            parsed = _to_issue(item)
            if parsed is None:
                continue
            issues.append(parsed)
            if len(issues) == wanted:
                break

        if 'rel="next"' not in response.headers.get("Link", ""):
            break
        page += 1

    return issues
