"""Auth + rate limiting at the service boundary."""
from tests.conftest import TEST_KEY, auth_headers, make_settings


def test_chat_requires_api_key(client):
    resp = client.post("/v1/chat", json={"message": "x"})  # no header
    assert resp.status_code == 401


def test_chat_rejects_wrong_api_key(client):
    resp = client.post("/v1/chat", json={"message": "x"}, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_chunks_requires_api_key(client):
    assert client.get("/v1/chunks").status_code == 401
    assert client.get("/v1/chunks", headers=auth_headers()).status_code == 200


def test_health_is_public(client):
    # liveness must NOT require a key (nginx/uptime checks hit it unauthenticated)
    assert client.get("/v1/health").status_code == 200


def test_rate_limit_returns_429(app_factory):
    from fastapi.testclient import TestClient
    client = TestClient(app_factory(settings=make_settings(rate_limit_per_min=2)))
    h = {"X-API-Key": TEST_KEY}
    assert client.post("/v1/chat", json={"message": "a"}, headers=h).status_code == 200
    assert client.post("/v1/chat", json={"message": "b"}, headers=h).status_code == 200
    assert client.post("/v1/chat", json={"message": "c"}, headers=h).status_code == 429
