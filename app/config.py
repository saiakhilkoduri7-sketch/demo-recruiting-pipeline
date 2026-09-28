from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "candidates.db"


class Settings:
    def __init__(self) -> None:
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me").strip()
        self.api_key = os.getenv("API_KEY", "").strip()
        self.database_url = os.getenv("DATABASE_URL", "").strip() or None
        self.outlook_shared_mailbox = os.getenv("OUTLOOK_SHARED_MAILBOX", "").strip()
        self.graph_access_token = os.getenv("GRAPH_ACCESS_TOKEN", "").strip()
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
        self.project_root = PROJECT_ROOT
        self.frontend_dir = PROJECT_ROOT / "frontend"
        self.sqlite_path = str(DEFAULT_SQLITE_PATH)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def allowed_origins(self) -> list[str]:
        if not self.cors_origins or self.cors_origins == ["*"]:
            return ["*"]
        return self.cors_origins


settings = Settings()
