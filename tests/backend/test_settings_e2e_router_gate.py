"""Settings gate for mounting E2E dev API (production must never expose /api/e2e)."""

from __future__ import annotations

import pytest

from apps.backend.courseeval_backend.core.config import Settings


def test_expose_e2e_dev_api_true_in_development_when_enabled() -> None:
    s = Settings(
        APP_ENV="development",
        E2E_DEV_SEED_ENABLED=True,
        SECRET_KEY="x" * 40,
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/testdb",
    )
    assert s.expose_e2e_dev_api() is True


def test_expose_e2e_dev_api_false_when_seed_disabled() -> None:
    s = Settings(
        APP_ENV="development",
        E2E_DEV_SEED_ENABLED=False,
        SECRET_KEY="x" * 40,
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/testdb",
    )
    assert s.expose_e2e_dev_api() is False


def test_expose_e2e_dev_api_false_in_production_even_if_flag_true_rejected_by_validator() -> None:
    """Production cannot enable E2E seed; model_validator rejects the combination."""
    with pytest.raises(ValueError, match="E2E_DEV_SEED_ENABLED"):
        Settings(
            APP_ENV="production",
            E2E_DEV_SEED_ENABLED=True,
            SECRET_KEY="x" * 40,
            DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/testdb",
        )


def test_expose_e2e_dev_api_false_production_normal() -> None:
    s = Settings(
        APP_ENV="production",
        E2E_DEV_SEED_ENABLED=False,
        SECRET_KEY="x" * 40,
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/testdb",
    )
    assert s.expose_e2e_dev_api() is False
