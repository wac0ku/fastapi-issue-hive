from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mode"] in ("heuristic", "claude-enhanced")


def test_categories_lists_knowledge_base():
    response = client.get("/categories")
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert "cors" in ids
    assert "docker_networking" in ids
    assert len(ids) >= 8


def test_analyze_issue_endpoint():
    response = client.post(
        "/analyze/issue",
        json={
            "title": "Connection refused when calling FastAPI from another machine",
            "body": "uvicorn runs on 127.0.0.1 and curl from my laptop says ERR_CONNECTION_REFUSED.",
        },
    )
    assert response.status_code == 200
    report = response.json()
    assert report["triage"]["is_connectivity_issue"] is True
    assert report["triage"]["matches"][0]["category"] == "connection_refused"
    assert report["suggested_reply"]
    assert report["research_brief"]["markdown"]


def test_analyze_issue_validates_input():
    response = client.post("/analyze/issue", json={"title": ""})
    assert response.status_code == 422
