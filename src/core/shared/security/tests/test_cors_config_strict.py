"""
Unit tests for strict CORS configuration logic.
Constitutional Hash: cdd01ef066bc6cf2
"""

import pytest

from src.core.shared.security.cors_config import (
    CORSConfig,
    CORSEnvironment,
    get_cors_config,
)


def test_cors_config_production_wildcard_rejection():
    """Verify that wildcard origins are rejected in production."""
    with pytest.raises(ValueError, match="Wildcard origins not allowed in production"):
        CORSConfig(
            allow_origins=["*"], allow_credentials=False, environment=CORSEnvironment.PRODUCTION
        )


def test_cors_config_production_credentials_wildcard_rejection():
    """Verify that wildcard + credentials are rejected as a critical error."""
    with pytest.raises(
        ValueError, match=r"SECURITY ERROR: allow_origins=\['\*'\] with allow_credentials=True"
    ):
        CORSConfig(
            allow_origins=["*"], allow_credentials=True, environment=CORSEnvironment.PRODUCTION
        )


def test_cors_config_environment_detection(monkeypatch):
    """Test environment detection from multiple variables."""
    monkeypatch.delenv("CORS_ENVIRONMENT", raising=False)
    monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    from src.core.shared.security.cors_config import detect_environment

    assert detect_environment() == CORSEnvironment.PRODUCTION

    monkeypatch.setenv("ENV", "staging")
    monkeypatch.delenv("ENVIRONMENT")
    monkeypatch.delenv("CORS_ENVIRONMENT", raising=False)
    monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
    assert detect_environment() == CORSEnvironment.STAGING


def test_cors_config_environment_detection_runtime_precedence(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", " production ")
    from src.core.shared.security.cors_config import detect_environment

    assert detect_environment() == CORSEnvironment.PRODUCTION


def test_cors_config_origins_from_env(monkeypatch):
    """Test loading origins from CORS_ALLOWED_ORIGINS."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app1.com, https://app2.com")
    config = get_cors_config(environment=CORSEnvironment.PRODUCTION)
    assert "https://app1.com" in config["allow_origins"]
    assert "https://app2.com" in config["allow_origins"]
    assert "http://localhost:3000" not in config["allow_origins"]


def test_cors_config_development_defaults(monkeypatch):
    """Test development defaults when no origins specified."""
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    config = get_cors_config(environment=CORSEnvironment.DEVELOPMENT)
    assert "http://localhost:3000" in config["allow_origins"]
