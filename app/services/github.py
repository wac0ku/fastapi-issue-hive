"""Fetch open issues from a public GitHub repository via the REST API."""

import httpx

from app.config import get_settings
from app.schemas import IssueInput

API_BASE = "https://api.github.com"


class GitHubError(Exception):
    pass


async def fetch_open_issues(owner: str, repo: str, limit: int = 5) -> list[IssueInput]:
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    url = f"{API_BASE}/repos/{owner}/{repo}/issues"
    params = {"state": "open", "per_page": min(limit, settings.max_issues_per_repo)}

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code == 404:
        raise GitHubError(f"Repository {owner}/{repo} not found or private")
    if response.status_code == 403:
        raise GitHubError("GitHub API rate limit exceeded — set GITHUB_TOKEN in .env")
    if response.status_code != 200:
        raise GitHubError(f"GitHub API error {response.status_code}")

    issues = []
    for item in response.json():
        if "pull_request" in item:  # the issues endpoint also returns PRs
            continue
        issues.append(
            IssueInput(
                title=item["title"],
                body=item.get("body") or "",
                url=item.get("html_url", ""),
                labels=[label["name"] for label in item.get("labels", [])],
            )
        )
    return issues[:limit]
