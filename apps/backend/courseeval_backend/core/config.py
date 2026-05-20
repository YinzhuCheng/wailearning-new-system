from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATABASE_URL = "postgresql://courseeval:change-me@127.0.0.1:5432/courseeval"
_DEFAULT_SECRET_KEY = "change-me-in-production"
_MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    APP_NAME: str = "CourseEval API"
    APP_ENV: str = "development"
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8001

    DATABASE_URL: str = _DEFAULT_DATABASE_URL
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    UPLOADS_DIR: str = ""

    BACKEND_CORS_ORIGINS_RAW: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5174,http://127.0.0.1:5174",
        alias="BACKEND_CORS_ORIGINS",
    )
    TRUSTED_HOSTS_RAW: str = Field(
        default="localhost,127.0.0.1",
        alias="TRUSTED_HOSTS",
    )

    INIT_ADMIN_USERNAME: str = "admin"
    INIT_ADMIN_PASSWORD: str = "ChangeMe123!"
    INIT_ADMIN_REAL_NAME: str = "System Administrator"
    INIT_DEFAULT_DATA: bool = True
    ALLOW_PUBLIC_REGISTRATION: bool = False
    # Optional absolute school SPA origin for links in system emails/notifications (e.g. https://example.com).
    # If empty, password-reset notifications use a relative /users?... path.
    FRONTEND_ADMIN_BASE_URL: str = ""

    # Optional throttle for POST /api/auth/forgot-password (reduces admin-notification spam and brute-force noise).
    FORGOT_PASSWORD_USERNAME_COOLDOWN_SECONDS: int = 600
    FORGOT_PASSWORD_MAX_REQUESTS_PER_IP_PER_HOUR: int = 40

    # Public registration: require class_id to reference an existing Class row (prevents orphan student accounts).
    PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS: bool = True

    # Ephemeral E2E seed API (/api/e2e/dev/reset-scenario). Never enable in production.
    E2E_DEV_SEED_ENABLED: bool = False
    E2E_DEV_SEED_TOKEN: str = ""
    # When True, destructive / powerful /api/e2e/dev/* endpoints require an admin JWT in addition
    # to X-E2E-Seed-Token (Bearer). Playwright sets E2E_DEV_ADMIN_* env vars so automation keeps working.
    E2E_DEV_REQUIRE_ADMIN_JWT: bool = False
    E2E_DEV_ADMIN_USERNAME: str = ""
    E2E_DEV_ADMIN_PASSWORD: str = ""

    GUNICORN_WORKERS: int = 3
    LOG_LEVEL: str = "info"
    ENABLE_LLM_GRADING_WORKER: bool = True
    # If True, only the leader process runs the in-process grader (multi-worker gunicorn safe).
    # If False, every app process with ENABLE_LLM_GRADING_WORKER runs a worker (each drains the same SQL queue; OK for single-uvicorn).
    LLM_GRADING_WORKER_LEADER: bool = True
    LLM_GRADING_WORKER_POLL_SECONDS: int = 2
    LLM_GRADING_TASK_STALE_SECONDS: int = 600
    DEFAULT_ESTIMATED_IMAGE_TOKENS: int = 850

    # Optional: seed / override API key for the default LLM preset name (see bootstrap).
    DEFAULT_LLM_API_KEY: str = ""

    # When True, refuse weak SECRET_KEY / default DATABASE_URL even if APP_ENV is not production.
    REQUIRE_STRONG_SECRETS: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("BACKEND_CORS_ORIGINS_RAW", "TRUSTED_HOSTS_RAW", mode="before")
    @classmethod
    def normalize_csv_value(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item).strip() for item in value if str(item).strip())
        raise TypeError("Expected a comma-separated string or a list.")

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def BACKEND_CORS_ORIGINS(self) -> list[str]:
        return self._split_csv(self.BACKEND_CORS_ORIGINS_RAW)

    @property
    def TRUSTED_HOSTS(self) -> list[str]:
        return self._split_csv(self.TRUSTED_HOSTS_RAW)

    def expose_e2e_dev_api(self) -> bool:
        """
        Whether FastAPI should mount ``/api/e2e/*`` routes.

        Always false in production (defense in depth; ``model_validator`` also rejects
        ``E2E_DEV_SEED_ENABLED`` with production ``APP_ENV`` at settings parse time).
        """
        if self._is_production_env(self.APP_ENV):
            return False
        return bool(self.E2E_DEV_SEED_ENABLED)

    @staticmethod
    def _is_production_env(app_env: str) -> bool:
        name = (app_env or "").strip().lower()
        return name in ("production", "prod")

    @model_validator(mode="after")
    def reject_weak_secrets_in_production(self) -> "Settings":
        if self.E2E_DEV_SEED_ENABLED and self._is_production_env(self.APP_ENV):
            raise ValueError("E2E_DEV_SEED_ENABLED must be false when APP_ENV is production.")

        require = bool(self.REQUIRE_STRONG_SECRETS) or self._is_production_env(self.APP_ENV)
        if not require:
            return self

        sk = (self.SECRET_KEY or "").strip()
        if len(sk) < _MIN_SECRET_KEY_LENGTH or sk == _DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set to a strong random value (at least "
                f"{_MIN_SECRET_KEY_LENGTH} characters) when APP_ENV is production or REQUIRE_STRONG_SECRETS is true."
            )

        db_url = (self.DATABASE_URL or "").strip()
        if db_url == _DEFAULT_DATABASE_URL or "change-me" in db_url.lower():
            raise ValueError(
                "DATABASE_URL must not use the default placeholder credentials when APP_ENV is production "
                "or REQUIRE_STRONG_SECRETS is true."
            )

        return self


settings = Settings()
