import importlib
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.config import Settings


def _set_production_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_USERNAME", "recruiter")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-unique-password")
    monkeypatch.setenv("SESSION_SECRET", "x" * 48)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/recruiting_db?sslmode=require")
    monkeypatch.setenv("CORS_ORIGINS", "https://testserver")
    monkeypatch.setenv("TRUSTED_HOSTS", "testserver")


def test_production_ui_uses_secure_login_session(monkeypatch):
    _set_production_environment(monkeypatch)
    import app.config as config_module

    importlib.reload(config_module)
    import app.api as api_module

    api_module = importlib.reload(api_module)
    client = TestClient(api_module.app, base_url="https://testserver")

    assert client.get("/ui").status_code == 200
    assert client.get("/jobs").status_code == 401
    assert client.get("/auth/session").json() == {
        "authenticated": False,
        "folder_import_enabled": False,
    }

    headers = {"Origin": "https://testserver"}
    rejected = client.post(
        "/auth/login",
        headers=headers,
        json={"username": "recruiter", "password": "wrong-password"},
    )
    assert rejected.status_code == 401

    monkeypatch.setattr(
        api_module,
        "get_repository",
        lambda: SimpleNamespace(
            list_jobs=lambda: [
                SimpleNamespace(id="job-1", title="Engineer", description="Description")
            ],
            check_connection=lambda: None,
        ),
    )
    response = client.post(
        "/auth/login",
        headers=headers,
        json={"username": "recruiter", "password": "a-long-unique-password"},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert client.get("/jobs").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/jobs").headers["cache-control"] == "no-store"
    assert client.get("/health", headers={"Host": "render-internal-host"}).status_code == 200
    assert client.get("/auth/session", headers={"Host": "untrusted.example"}).status_code == 400

    folder_import = client.post(
        "/jobs/job-1/match",
        headers=headers,
        json={"resume_folder": "."},
    )
    assert folder_import.status_code == 400
    assert client.post(
        "/run-demo",
        headers=headers,
        json={"resume_folder": ".", "job_title": "Role", "job_description": "Description"},
    ).status_code == 404

    unsupported = client.post(
        "/candidates/upload",
        headers=headers,
        files={"file": ("resume.exe", b"not a resume")},
    )
    assert unsupported.status_code == 415
    too_large = client.post(
        "/candidates/upload",
        headers=headers,
        files={"file": ("resume.txt", b"x" * (10 * 1024 * 1024 + 1))},
    )
    assert too_large.status_code == 413

    rejected_origin = client.post("/auth/logout", headers={"Origin": "https://evil.example"})
    assert rejected_origin.status_code == 403
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/jobs").status_code == 401


@pytest.mark.parametrize(
    "missing_variable",
    [
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "SESSION_SECRET",
        "DATABASE_URL",
        "CORS_ORIGINS",
        "TRUSTED_HOSTS",
    ],
)
def test_production_fails_to_start_without_required_configuration(monkeypatch, missing_variable):
    _set_production_environment(monkeypatch)
    monkeypatch.delenv(missing_variable)

    with pytest.raises(ValueError, match=missing_variable):
        Settings()


def test_production_requires_secure_postgres_url(monkeypatch):
    _set_production_environment(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/recruiting_db")

    with pytest.raises(ValueError, match="sslmode=require"):
        Settings()


def test_production_rejects_short_admin_password(monkeypatch):
    _set_production_environment(monkeypatch)
    monkeypatch.setenv("ADMIN_PASSWORD", "too-short")

    with pytest.raises(ValueError, match="16 characters"):
        Settings()


def test_production_rejects_wildcard_cors_origins(monkeypatch):
    _set_production_environment(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ValueError, match="explicit origins"):
        Settings()


def test_production_rejects_wildcard_trusted_hosts(monkeypatch):
    _set_production_environment(monkeypatch)
    monkeypatch.setenv("TRUSTED_HOSTS", "*")

    with pytest.raises(ValueError, match="wildcard hosts"):
        Settings()
