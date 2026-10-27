from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "candidates.db"


class Settings:
    def __init__(self) -> None:
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.session_secret = os.getenv("SESSION_SECRET", "dev-session-secret-change-me").strip()
        self.admin_username = os.getenv("ADMIN_USERNAME", "").strip()
        self.admin_password = os.getenv("ADMIN_PASSWORD", "")
        self.database_url = os.getenv("DATABASE_URL", "").strip() or None
        self.outlook_shared_mailbox = os.getenv("OUTLOOK_SHARED_MAILBOX", "").strip()
        self.graph_access_token = os.getenv("GRAPH_ACCESS_TOKEN", "").strip()
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        self.google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
        self.cors_origins = [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "*").split(",")
            if origin.strip()
        ]
        self.trusted_hosts = [
            host.strip()
            for host in os.getenv("TRUSTED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
            if host.strip()
        ]
        if self.is_production:
            missing = [
                name
                for name, value in (
                    ("ADMIN_USERNAME", self.admin_username),
                    ("ADMIN_PASSWORD", self.admin_password),
                    ("SESSION_SECRET", os.getenv("SESSION_SECRET", "").strip()),
                    ("DATABASE_URL", self.database_url),
                    ("CORS_ORIGINS", os.getenv("CORS_ORIGINS", "").strip()),
                    ("TRUSTED_HOSTS", os.getenv("TRUSTED_HOSTS", "").strip()),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"Missing required production environment variables: {', '.join(missing)}"
                )
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must contain explicit origins in production.")
            if not self.cors_origins:
                raise ValueError("CORS_ORIGINS must include at least one explicit origin.")
            if "*" in self.trusted_hosts:
                raise ValueError("TRUSTED_HOSTS must not allow wildcard hosts in production.")
            if len(self.session_secret) < 32:
                raise ValueError("SESSION_SECRET must be at least 32 characters in production.")
            if len(self.admin_password) < 16:
                raise ValueError("ADMIN_PASSWORD must be at least 16 characters in production.")

            database = urlparse(self.database_url or "")
            if database.scheme not in {"postgres", "postgresql"} or not database.hostname:
                raise ValueError("DATABASE_URL must use PostgreSQL in production.")
            sslmode = parse_qs(database.query).get("sslmode", [""])[0]
            if sslmode not in {"require", "verify-ca", "verify-full"}:
                raise ValueError("DATABASE_URL must require TLS with sslmode=require or stronger.")
            if self.google_redirect_uri:
                redirect_uri = urlparse(self.google_redirect_uri)
                if redirect_uri.scheme != "https" or not redirect_uri.hostname:
                    raise ValueError("GOOGLE_REDIRECT_URI must use HTTPS in production.")
                if redirect_uri.hostname not in self.trusted_hosts:
                    raise ValueError(
                        "GOOGLE_REDIRECT_URI host must be included in TRUSTED_HOSTS."
                    )
                if redirect_uri.path != "/auth/google/callback":
                    raise ValueError(
                        "GOOGLE_REDIRECT_URI must end in /auth/google/callback."
                    )
        self.project_root = PROJECT_ROOT
        self.frontend_dir = PROJECT_ROOT / "frontend"
        self.sqlite_path = str(DEFAULT_SQLITE_PATH)
        self.max_resume_size_bytes = 10 * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def allowed_origins(self) -> list[str]:
        if not self.cors_origins or self.cors_origins == ["*"]:
            return ["*"]
        return self.cors_origins


settings = Settings()
