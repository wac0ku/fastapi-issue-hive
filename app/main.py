import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app import __version__
from app.config import get_settings
from app.hive import HiveQueen
from app.hive.workers import reporter
from app.knowledge import CATEGORIES
from app.observability import configure_logging, register
from app.schemas import (
    AnalysisReport,
    CategoryInfo,
    HealthResponse,
    IssueInput,
    RepoScanReport,
    RepoScanRequest,
)
from app.services.claude import close_client
from app.services.github import GitHubError, close_http_client


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Own the shared HTTP clients for the process lifetime.

    Both clients used to be constructed per request, which meant a fresh TCP and TLS
    handshake every time and, for the Anthropic client, one that was never closed.
    """
    configure_logging()
    yield
    await close_http_client()
    await close_client()


app = FastAPI(
    title="FastAPI Issue Hive",
    version=__version__,
    description=(
        "A hive-mind multi-agent system that analyzes GitHub issues and "
        "diagnoses FastAPI connectivity problems. Works fully offline in "
        "heuristic mode; add an Anthropic API key for Claude-enhanced analysis."
    ),
    lifespan=lifespan,
)

register(app)

# Empty by default: the service has no authentication, so it should not be callable from
# arbitrary origins unless someone opts in via ALLOWED_ORIGINS.
_origins = get_settings().allowed_origins
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

queen = HiveQueen()


@app.get("/health")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        mode="claude-enhanced" if settings.claude_enabled else "heuristic",
    )


@app.get("/categories")
async def categories() -> list[CategoryInfo]:
    """The connectivity failure modes the hive knows how to diagnose."""
    return [CategoryInfo(id=c.id, name=c.name, description=c.description) for c in CATEGORIES]


@app.post("/analyze/issue")
async def analyze_issue(issue: IssueInput) -> AnalysisReport:
    """Run the full hive pipeline on a single issue (title + body)."""
    return await queen.analyze_issue(issue)


async def _scan(request: RepoScanRequest) -> RepoScanReport:
    """Shared by the JSON and the NotebookLM corpus variant of a repo scan."""
    try:
        return await queen.scan_repository(request.owner, request.repo, request.limit)
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504, detail="Repository scan exceeded its time budget"
        ) from exc


@app.post("/analyze/repo")
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
    return PlainTextResponse(reporter.build_knowledge_source(), media_type="text/markdown")
