"""Settings validation for production-style deployments."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.backend.courseeval_backend.core.config import Settings


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError) as exc:
        Settings(
            APP_ENV="production",
            SECRET_KEY="change-me-in-production",
            DATABASE_URL="postgresql://user:strongpass@127.0.0.1:5432/mydb",
        )
    assert "SECRET_KEY" in str(exc.value) or "secret" in str(exc.value).lower()


def test_production_rejects_default_database_url():
    with pytest.raises(ValidationError) as exc:
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 40 + "-unique-production-secret-value",
            DATABASE_URL="postgresql://courseeval:change-me@127.0.0.1:5432/courseeval",
        )
    assert "DATABASE_URL" in str(exc.value) or "database" in str(exc.value).lower()


def test_require_strong_secrets_without_production_env():
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="development",
            REQUIRE_STRONG_SECRETS=True,
            SECRET_KEY="change-me-in-production",
            DATABASE_URL="postgresql://u:p@127.0.0.1:5432/db",
        )


def test_development_allows_short_secret_by_default():
    s = Settings(APP_ENV="development", SECRET_KEY="short", DATABASE_URL="sqlite:///./tmp.db")
    assert s.SECRET_KEY == "short"
