import importlib
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _reload_production_app(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_USERNAME", "recruiter")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-unique-password")
    monkeypatch.setenv("SESSION_SECRET", "x" * 48)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/recruiting_db?sslmode=require")
    monkeypatch.setenv("CORS_ORIGINS", "https://testserver")
    monkeypatch.setenv("TRUSTED_HOSTS", "testserver")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "microsoft-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "microsoft-client-secret")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "https://testserver/auth/microsoft/callback",
    )
    import app.config as config_module

    importlib.reload(config_module)
    import app.api as api_module

    return importlib.reload(api_module)


def test_personal_microsoft_connect_callback_and_manual_import(monkeypatch):
    api_module = _reload_production_app(monkeypatch)
    client = TestClient(api_module.app, base_url="https://testserver")
    assert client.get("/auth/microsoft/connect").status_code == 401

    monkeypatch.setattr(
        api_module,
        "get_repository",
        lambda: SimpleNamespace(check_connection=lambda: None),
    )
    login = client.post(
        "/auth/login",
        headers={"Origin": "https://testserver"},
        json={"username": "recruiter", "password": "a-long-unique-password"},
    )
    assert login.status_code == 200

    monkeypatch.setattr(
        api_module.microsoft_oauth,
        "create_auth_flow",
        lambda settings, redirect_uri: {
            "state": "safe-one-time-state",
            "auth_uri": "https://login.microsoftonline.com/authorize",
        },
    )
    connect = client.get("/auth/microsoft/connect", follow_redirects=False)
    assert connect.status_code == 302
    assert connect.headers["location"] == "https://login.microsoftonline.com/authorize"

    monkeypatch.setattr(
        api_module.microsoft_oauth,
        "complete_auth_flow",
        lambda settings, state, auth_response: "recruiter@outlook.com",
    )
    callback = client.get(
        "/auth/microsoft/callback?state=safe-one-time-state&code=sample-code",
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/ui?mail=connected"

    monkeypatch.setattr(
        api_module.microsoft_oauth,
        "get_connected_account",
        lambda settings, username: username,
    )
    assert client.get("/auth/microsoft/status").json() == {
        "configured": True,
        "connected": True,
        "account": "recruiter@outlook.com",
    }

    monkeypatch.setattr(
        api_module.microsoft_oauth,
        "acquire_access_token",
        lambda settings, username: "server-only-token",
    )
    monkeypatch.setattr(
        api_module,
        "ingest_mailbox_candidates",
        lambda client, repository, top, use_current_user: {
            "messages_received": 1,
            "candidates_stored": 1,
            "messages_skipped": 0,
        },
    )
    imported = client.post(
        "/auth/microsoft/import",
        headers={"Origin": "https://testserver"},
        json={"top": 5},
    )
    assert imported.status_code == 200
    assert imported.json() == {
        "messages_received": 1,
        "candidates_stored": 1,
        "messages_skipped": 0,
    }

    disconnected = client.post(
        "/auth/microsoft/disconnect",
        headers={"Origin": "https://testserver"},
    )
    assert disconnected.status_code == 200
    assert disconnected.json() == {"connected": False}
