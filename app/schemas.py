from pydantic import BaseModel, Field

MAX_BODY_CHARS = 20000


class IssueInput(BaseModel):
    """A GitHub issue (or free-form problem description) to analyze."""

    title: str = Field(..., min_length=3, max_length=500)
    body: str = Field(default="", max_length=MAX_BODY_CHARS)
    url: str = ""
    labels: list[str] = []


class RepoScanRequest(BaseModel):
    # Both are interpolated straight into the GitHub API path, so they are constrained to
    # GitHub's own naming rules. Length alone let a value like "../.." change which
    # endpoint got called.
    owner: str = Field(..., pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
    repo: str = Field(..., pattern=r"^[A-Za-z0-9._-]{1,100}$")
    limit: int = Field(default=5, ge=1, le=25)


class CategoryMatch(BaseModel):
    category: str
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    matched_signals: list[str]


class TriageResult(BaseModel):
    matches: list[CategoryMatch]
    is_connectivity_issue: bool
    summary: str


class Diagnosis(BaseModel):
    root_causes: list[str]
    fixes: list[str]
    doc_links: list[str]
    enhanced_by_claude: bool = False
    claude_notes: str = ""


class ResearchBrief(BaseModel):
    """NotebookLM-ready source document for deep-dive research."""

    title: str
    markdown: str


class AnalysisReport(BaseModel):
    issue_title: str
    issue_url: str = ""
    triage: TriageResult
    diagnosis: Diagnosis
    research_brief: ResearchBrief
    suggested_reply: str
    workers_used: list[str]


class RepoScanReport(BaseModel):
    owner: str
    repo: str
    issues_scanned: int
    connectivity_issues_found: int
    reports: list[AnalysisReport] = Field(
        description=(
            "One report per scanned issue, connectivity-related or not. Filter on "
            "triage.is_connectivity_issue to get only the matches counted by "
            "connectivity_issues_found."
        )
    )


class HealthResponse(BaseModel):
    status: str
    version: str
    mode: str = Field(description="'heuristic' or 'claude-enhanced'")


class CategoryInfo(BaseModel):
    id: str
    name: str
    description: str
