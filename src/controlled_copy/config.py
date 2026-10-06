"""Settings, read from environment variables (and `.env` when present).

Every limit from the product specification lives here, so changing a limit is a
configuration change. `check_startup()` refuses insecure combinations before the
app starts (deploy mode without an access code, without a strong secret key,
with debug on, or with the fake model provider).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(StrEnum):
    LOCAL = "local"
    DEPLOY = "deploy"


class ConfigError(RuntimeError):
    """The configuration is unsafe or incomplete; the app must not start."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    product_name: str = "Controlled Copy"
    product_tagline: str = "A NotebookLM-style notebook for controlled documents"

    app_mode: AppMode = AppMode.LOCAL
    app_debug: bool = False
    app_access_code: SecretStr | None = None
    app_secret_key: SecretStr | None = None
    data_dir: Path = Path("data")

    model_provider: Literal["openrouter", "fake"] = "openrouter"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_generation: str = "openai/gpt-6-luna"
    model_generation_fallback: str = "google/gemini-3.5-flash-lite"
    model_embedding: str = "baai/bge-m3"

    feature_governance: bool = False
    feature_personas: bool = False

    retention_hours: int = Field(default=168, gt=0)
    purge_interval_seconds: int = Field(default=3600, gt=0)

    max_file_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=150, gt=0)
    max_paste_chars: int = Field(default=200_000, gt=0)
    max_title_chars: int = Field(default=200, gt=0)
    max_sources_per_notebook: int = Field(default=20, gt=0)
    # Total extracted characters per notebook (S-08): bounds stored text and embedding work,
    # which raw file sizes do not (a small PDF can extract to a lot of text).
    max_notebook_chars: int = Field(default=2_000_000, gt=0)
    max_notebooks_per_visitor: int = Field(default=5, gt=0)
    max_question_chars: int = Field(default=1500, gt=0)
    max_situation_chars: int = Field(default=2000, gt=0)
    model_calls_per_visitor_hour: int = 120
    model_calls_per_day: int = 3000
    access_attempts_per_hour: int = 10
    provider_timeout_seconds: float = Field(default=45.0, gt=0)
    pdf_parse_timeout_seconds: float = Field(default=20.0, gt=0)
    pdf_parse_memory_mb: int = Field(default=1024, gt=0)

    retrieval_candidates: int = Field(default=20, gt=0)
    retrieval_top_k: int = Field(default=6, gt=0)
    # 0 would silently switch refusals off and 1 would refuse everything.
    evidence_floor: float = Field(default=0.52, gt=0, lt=1)
    embedding_batch_size: int = Field(default=64, gt=0)

    video_mp4: str | None = None
    video_vtt: str | None = None
    video_date: str | None = None

    @property
    def retention_days(self) -> int:
        return self.retention_hours // 24

    @property
    def max_file_mb(self) -> int:
        return self.max_file_bytes // (1024 * 1024)

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "controlled-copy.sqlite3"

    @property
    def secure_cookies(self) -> bool:
        return self.app_mode is AppMode.DEPLOY

    def check_startup(self) -> None:
        problems: list[str] = []
        code = self.app_access_code.get_secret_value() if self.app_access_code else ""
        secret = self.app_secret_key.get_secret_value() if self.app_secret_key else ""
        if not code:
            problems.append("APP_ACCESS_CODE is not set")
        if self.model_provider == "openrouter" and not self.openrouter_api_key:
            problems.append("OPENROUTER_API_KEY is not set")
        base = urlsplit(self.openrouter_base_url)
        if base.scheme != "https" and base.hostname not in ("localhost", "127.0.0.1"):
            problems.append("OPENROUTER_BASE_URL must use https (the API key is sent with every request)")
        for name in ("model_calls_per_visitor_hour", "model_calls_per_day", "access_attempts_per_hour"):
            if getattr(self, name) <= 0:
                problems.append(f"{name.upper()} must be positive")
        if self.app_mode is AppMode.DEPLOY:
            if len(secret) < 32:
                problems.append("APP_SECRET_KEY must be set and at least 32 characters in deploy mode")
            if len(code) < 8:
                problems.append("APP_ACCESS_CODE must be at least 8 characters in deploy mode")
            if self.app_debug:
                problems.append("APP_DEBUG must be off in deploy mode")
            if self.model_provider == "fake":
                problems.append("the fake model provider is not allowed in deploy mode")
        if problems:
            raise ConfigError("Refusing to start: " + "; ".join(problems))
