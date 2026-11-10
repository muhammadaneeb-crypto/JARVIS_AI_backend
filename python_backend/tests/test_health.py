from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer test-token"}


def test_health_is_public():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_system_info_requires_token():
    assert client.get("/windows/system-info").status_code == 401
    assert client.get("/windows/system-info",
                      headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_system_info_with_token():
    r = client.get("/windows/system-info", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["ram"]["percent"] <= 100
    assert "cpu_percent" in body


def test_planned_endpoint_returns_501():
    r = client.post("/ai/chat", json={"message": "hi"}, headers=AUTH)
    assert r.status_code == 501
    assert r.json()["status"] == "not_implemented"


def test_planned_endpoint_requires_token():
    assert client.post("/ai/chat", json={"message": "hi"}).status_code == 401
