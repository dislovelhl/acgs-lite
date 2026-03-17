import pytest
from pydantic import SecretStr

from src.core.shared.auth.workos import (
    WorkOSConfigurationError,
    _get_workos_api_key,
    _get_workos_base_url,
    is_workos_enabled,
)
from src.core.shared.config import settings


def test_get_workos_api_key_rejects_placeholder(monkeypatch):
    monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr(" replace_me "), raising=False)

    with pytest.raises(WorkOSConfigurationError) as exc:
        _get_workos_api_key()
    assert "placeholder" in str(exc.value).lower()


def test_get_workos_base_url_requires_https(monkeypatch):
    monkeypatch.setattr(
        settings.sso, "workos_api_base_url", "http://api.workos.test", raising=False
    )

    with pytest.raises(WorkOSConfigurationError) as exc:
        _get_workos_base_url()
    assert "https" in str(exc.value).lower()


def test_is_workos_enabled_false_for_placeholder_client_id(monkeypatch):
    monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
    monkeypatch.setattr(settings.sso, "workos_client_id", " your-client-id ", raising=False)
    monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_valid"), raising=False)

    assert is_workos_enabled() is False


def test_is_workos_enabled_true_for_valid_configuration(monkeypatch):
    monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
    monkeypatch.setattr(settings.sso, "workos_client_id", "client_123", raising=False)
    monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_valid"), raising=False)

    assert is_workos_enabled() is True
