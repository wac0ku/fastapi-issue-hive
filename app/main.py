from fastapi import FastAPI, HTTPException

from app import __version__
from app.config import get_settings
from app.hive import HiveQueen
from app.knowledge import CATEGORIES
from app.schemas import AnalysisReport, IssueInput, RepoScanReport, RepoScanRequest

app = FastAPI(
    title="FastAPI Issue Hive",
    version=__version__,
    description=(
        "A hive-mind multi-agent system that analyzes GitHub issues and "
        "diagnoses FastAPI connectivity problems. Works fully offline in "
        "heuristic mode; add an Anthropic API key for Claude-enhanced analysis."
    ),
)

queen = HiveQueen()


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "mode": "claude-enhanced" if settings.claude_enabled else "heuristic",
    }


@app.get("/categories")
async def categories() -> list[dict]:
    """The connectivity failure modes the hive knows how to diagnose."""
    return [
        {"id": c.id, "name": c.name, "description": c.description}
        for c in CATEGORIES
    ]


@app.post("/analyze/issue", response_model=AnalysisReport)
async def analyze_issue(issue: IssueInput) -> AnalysisReport:
    """Run the full hive pipeline on a single issue (title + body)."""
    return await queen.analyze_issue(issue)


@app.post("/analyze/repo", response_model=RepoScanReport)
async def analyze_repo(request: RepoScanRequest) -> RepoScanReport:
    """Fetch open issues of a public repository and analyze each one."""
    from app.services.github import GitHubError

    try:
        return await queen.scan_repository(request.owner, request.repo, request.limit)
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
