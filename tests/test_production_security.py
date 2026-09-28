import importlib

from fastapi.testclient import TestClient


def test_production_requires_api_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "super-secret-key")

    import app.api as api_module

    api_module = importlib.reload(api_module)
    client = TestClient(api_module.app)

    response = client.get("/health")
    assert response.status_code == 401

    response = client.get("/health", headers={"x-api-key": "super-secret-key"})
    assert response.status_code == 200
