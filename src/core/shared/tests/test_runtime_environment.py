"""Tests for shared runtime environment resolution."""

from __future__ import annotations

from src.core.shared.config.runtime_environment import resolve_runtime_environment


def test_resolve_runtime_environment_prefers_environment_over_defaulted_settings_env(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert resolve_runtime_environment("development") == "production"


def test_resolve_runtime_environment_prefers_explicit_app_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert resolve_runtime_environment("development") == "staging"
