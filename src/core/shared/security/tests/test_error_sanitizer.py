from __future__ import annotations

from src.core.shared.security import error_sanitizer


def test_safe_error_detail_uses_environment_over_defaulted_settings_env(monkeypatch):
    monkeypatch.setattr(error_sanitizer.settings, "env", "development")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    detail = error_sanitizer.safe_error_detail(ValueError("secret=abc"), "create tenant")

    assert detail == "Create tenant failed. Please try again or contact support."
