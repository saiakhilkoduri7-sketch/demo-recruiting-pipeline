import importlib
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _reload_production_app(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_USERNAME", "recruiter")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-unique-password")
    monkeypatch.setenv("SESSION_SECRET", "x" * 48)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://localhost/recruiting_db?sslmode=require",
    )
    monkeypatch.setenv("CORS_ORIGINS", "https://testserver")
    monkeypatch.setenv("TRUSTED_HOSTS", "testserver")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "https://testserver/auth/google/callback",
    )
    import app.config as config_module

    importlib.reload(config_module)
    import app.api as api_module

    return importlib.reload(api_module)


def test_google_connect_callback_import_and_disconnect(monkeypatch):
    api_module = _reload_production_app(monkeypatch)
    client = TestClient(api_module.app, base_url="https://testserver")
    assert client.get("/auth/google/connect").status_code == 401
    assert "Connect Gmail" in client.get("/ui").text

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
        api_module.google_oauth,
        "create_auth_flow",
        lambda settings, redirect_uri: (
            "https://accounts.google.com/authorize",
            "one-time-state",
        ),
    )
    connect = client.get("/auth/google/connect", follow_redirects=False)
    assert connect.status_code == 302
    assert connect.headers["location"] == "https://accounts.google.com/authorize"

    monkeypatch.setattr(
        api_module.google_oauth,
        "complete_auth_flow",
        lambda settings, state, authorization_response: "recruiter@gmail.com",
    )
    callback = client.get(
        "/auth/google/callback?state=one-time-state&code=sample-code",
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/ui?gmail=connected"

    monkeypatch.setattr(
        api_module.google_oauth,
        "get_connected_account",
        lambda username: username,
    )
    assert client.get("/auth/google/status").json() == {
        "configured": True,
        "connected": True,
        "account": "recruiter@gmail.com",
    }

    monkeypatch.setattr(
        api_module.google_oauth,
        "acquire_access_token",
        lambda username: "server-side-access-token",
    )
    monkeypatch.setattr(
        api_module,
        "ingest_gmail_candidates",
        lambda client, repository, top: {
            "messages_received": 2,
            "candidates_stored": 1,
            "messages_skipped": 1,
        },
    )
    imported = client.post(
        "/auth/google/import",
        headers={"Origin": "https://testserver"},
        json={"top": 5},
    )
    assert imported.status_code == 200
    assert imported.json() == {
        "messages_received": 2,
        "candidates_stored": 1,
        "messages_skipped": 1,
    }

    disconnected = client.post(
        "/auth/google/disconnect",
        headers={"Origin": "https://testserver"},
    )
    assert disconnected.status_code == 200
    assert disconnected.json() == {"connected": False}


def test_google_import_requires_configured_connector(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    import app.config as config_module

    importlib.reload(config_module)
    import app.api as api_module

    api_module = importlib.reload(api_module)
    client = TestClient(api_module.app)

    response = client.post("/auth/google/import", json={"top": 1})

    assert response.status_code == 503
    assert response.json()["detail"] == "Google sign-in is not configured."


def test_google_oauth_failure_returns_safe_diagnostic_code(monkeypatch):
    api_module = _reload_production_app(monkeypatch)
    client = TestClient(api_module.app, base_url="https://testserver")
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
        api_module.google_oauth,
        "create_auth_flow",
        lambda settings, redirect_uri: (
            "https://accounts.google.com/authorize",
            "diagnostic-state",
        ),
    )
    assert client.get("/auth/google/connect", follow_redirects=False).status_code == 302
    monkeypatch.setattr(
        api_module.google_oauth,
        "complete_auth_flow",
        lambda settings, state, authorization_response: (_ for _ in ()).throw(
            api_module.google_oauth.GoogleOAuthError(
                "Safe message",
                code="token_exchange",
            )
        ),
    )

    callback = client.get(
        "/auth/google/callback?state=diagnostic-state&code=secret-code",
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == "/ui?gmail=token_exchange"
    assert "secret-code" not in callback.headers["location"]
