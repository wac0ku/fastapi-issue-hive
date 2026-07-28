"""The NotebookLM source documents.

The corpus exists because dropping N self-contained briefs into one notebook fills it with
duplicates. These tests pin down that it actually stays deduplicated.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.hive import queen as queen_module
from app.hive.workers import reporter
from app.knowledge import CATEGORIES
from app.main import app
from app.schemas import IssueInput

client = TestClient(app)

# One body per category signal set, plus a deliberate out-of-scope issue.
SAMPLE_ISSUES = [
    IssueInput(
        title="CORS error blocked by CORS policy",
        body="No Access-Control-Allow-Origin header is present, preflight OPTIONS fails.",
        url="https://github.com/o/r/issues/1",
    ),
    IssueInput(
        title="502 Bad Gateway with nginx in front of uvicorn",
        body="nginx returns 502, /docs broken behind the reverse proxy, root_path set.",
        url="https://github.com/o/r/issues/2",
    ),
    IssueInput(
        title="CORS blocked from React frontend",
        body="cross-origin preflight OPTIONS request keeps failing.",
        url="https://github.com/o/r/issues/3",
    ),
    IssueInput(
        title="Add dark mode to the admin panel",
        body="A theme toggle in the settings page would be nice.",
        url="https://github.com/o/r/issues/4",
    ),
]


def scan_corpus() -> str:
    with patch.object(queen_module, "fetch_open_issues", return_value=SAMPLE_ISSUES):
        response = client.post(
            "/analyze/repo/corpus", json={"owner": "o", "repo": "r", "limit": 4}
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    return response.text


def test_knowledge_export_carries_every_category():
    response = client.get("/knowledge/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    for category in CATEGORIES:
        assert category.name in response.text
        assert category.id in response.text


def test_corpus_has_a_category_frequency_table():
    corpus = scan_corpus()

    assert "## Category frequency" in corpus
    assert "| Category | Issues | Avg. confidence |" in corpus
    # Two of the four sample issues are CORS, so that row must report 2.
    cors_row = next(line for line in corpus.splitlines() if "`cors`" in line)
    assert "| 2 |" in cors_row


def test_corpus_does_not_repeat_knowledge_base_prose():
    """The whole point of the corpus: category background lives in the other source."""
    corpus = scan_corpus()

    for category in CATEGORIES:
        for cause in category.root_causes:
            assert cause not in corpus
        for fix in category.fixes:
            assert fix not in corpus


def test_corpus_carries_the_prompt_block_exactly_once():
    corpus = scan_corpus()

    assert corpus.count("Suggested NotebookLM prompts") == 1
    for prompt in reporter.NOTEBOOKLM_PROMPTS:
        assert corpus.count(prompt) == 1


def test_corpus_links_back_to_every_issue():
    corpus = scan_corpus()

    for issue in SAMPLE_ISSUES:
        assert issue.title in corpus
        assert issue.url in corpus


def test_corpus_is_much_smaller_than_concatenated_briefs():
    """Regression guard for the dedup win — briefs stay self-contained, the corpus doesn't."""
    with patch.object(queen_module, "fetch_open_issues", return_value=SAMPLE_ISSUES):
        report = client.post(
            "/analyze/repo", json={"owner": "o", "repo": "r", "limit": 4}
        ).json()

    concatenated = "\n\n".join(r["research_brief"]["markdown"] for r in report["reports"])
    corpus = scan_corpus()

    assert len(corpus) < len(concatenated) * 0.6
