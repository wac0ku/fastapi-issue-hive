from app.hive.workers import triage
from app.schemas import IssueInput


def test_cors_issue_detected():
    issue = IssueInput(
        title="CORS error: blocked by CORS policy from React frontend",
        body="Browser console shows: No 'Access-Control-Allow-Origin' header is present. "
        "The preflight OPTIONS request fails.",
    )
    result = triage.run(issue)
    assert result.is_connectivity_issue
    assert result.matches[0].category == "cors"
    assert result.matches[0].confidence > 0.3


def test_docker_networking_detected():
    issue = IssueInput(
        title="Cannot reach FastAPI container from docker-compose service",
        body="My frontend container gets 'name or service not known' when calling "
        "http://localhost:8000. Both run via docker-compose.",
    )
    result = triage.run(issue)
    assert result.is_connectivity_issue
    assert any(m.category == "docker_networking" for m in result.matches)


def test_reverse_proxy_detected():
    issue = IssueInput(
        title="502 Bad Gateway with nginx in front of uvicorn",
        body="nginx returns 502, /docs is broken behind the reverse proxy, root_path set.",
    )
    result = triage.run(issue)
    assert result.is_connectivity_issue
    assert result.matches[0].category == "reverse_proxy"


def test_unrelated_issue_rejected():
    issue = IssueInput(
        title="Feature request: add dark mode to admin panel",
        body="It would be nice to have a dark theme toggle in the settings page.",
    )
    result = triage.run(issue)
    assert not result.is_connectivity_issue


def test_labels_contribute_to_matching():
    issue = IssueInput(
        title="Requests fail intermittently",
        body="",
        labels=["websocket", "bug"],
    )
    result = triage.run(issue)
    assert any(m.category == "websocket" for m in result.matches)
