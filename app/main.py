import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from app import __version__
from app.config import get_settings
from app.hive import HiveQueen
from app.hive.workers import reporter
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


async def _scan(request: RepoScanRequest) -> RepoScanReport:
    """Shared by the JSON and the NotebookLM corpus variant of a repo scan."""
    from app.services.github import GitHubError

    try:
        return await queen.scan_repository(request.owner, request.repo, request.limit)
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504, detail="Repository scan exceeded its time budget"
        ) from exc


@app.post("/analyze/repo", response_model=RepoScanReport)
async def analyze_repo(request: RepoScanRequest) -> RepoScanReport:
    """Fetch open issues of a public repository and analyze each one."""
    return await _scan(request)


@app.post("/analyze/repo/corpus", response_class=PlainTextResponse)
async def analyze_repo_corpus(request: RepoScanRequest) -> PlainTextResponse:
    """The same scan as one deduplicated markdown document, ready to drop into NotebookLM.

    Pair it with /knowledge/export, which carries the category background this document
    deliberately leaves out.
    """
    report = await _scan(request)
    return PlainTextResponse(reporter.build_corpus(report), media_type="text/markdown")


@app.get("/knowledge/export", response_class=PlainTextResponse)
async def knowledge_export() -> PlainTextResponse:
    """The whole knowledge base as a single NotebookLM source document."""
    return PlainTextResponse(
        reporter.build_knowledge_source(), media_type="text/markdown"
    )
