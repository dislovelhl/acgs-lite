"""Tests for WorkOS integration helpers.

Covers configuration validation, placeholder rejection, webhook signature
verification, admin portal link generation, event listing, and webhook parsing.
"""

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr

from src.core.shared.auth.workos import (
    WorkOSAPIError,
    WorkOSConfigurationError,
    WorkOSWebhookEvent,
    WorkOSWebhookVerificationError,
    _ensure_not_placeholder,
    _get_workos_api_key,
    _get_workos_base_url,
    _get_workos_client_id,
    _get_workos_webhook_secret,
    _normalize_config_value,
    _parse_workos_signature_header,
    _secret_value,
    generate_workos_admin_portal_link,
    is_workos_enabled,
    list_workos_events,
    parse_and_verify_workos_webhook,
    verify_workos_webhook_signature,
)
from src.core.shared.config import settings

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


class TestSecretValue:
    def test_plain_string(self):
        assert _secret_value("hello") == "hello"

    def test_secret_str(self):
        assert _secret_value(SecretStr("secret123")) == "secret123"


class TestNormalizeConfigValue:
    def test_strips_and_lowercases(self):
        assert _normalize_config_value("  Hello World  ") == "helloworld"

    def test_removes_non_alnum(self):
        assert _normalize_config_value("your_api_key!") == "yourapikey"


class TestEnsureNotPlaceholder:
    def test_rejects_known_placeholders(self):
        for ph in ["replace_me", " Your_API_Key ", "placeholder"]:
            with pytest.raises(WorkOSConfigurationError, match="placeholder"):
                _ensure_not_placeholder(ph, "TEST_FIELD")

    def test_accepts_real_value(self):
        result = _ensure_not_placeholder("sk_live_abc123", "TEST_FIELD")
        assert result == "sk_live_abc123"


# ---------------------------------------------------------------------------
# Configuration getters
# ---------------------------------------------------------------------------


class TestGetWorkOSClientId:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_client_id", None, raising=False)
        with pytest.raises(WorkOSConfigurationError, match="WORKOS_CLIENT_ID"):
            _get_workos_client_id()

    def test_raises_when_empty(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_client_id", "   ", raising=False)
        with pytest.raises(WorkOSConfigurationError, match="WORKOS_CLIENT_ID"):
            _get_workos_client_id()

    def test_rejects_placeholder(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_client_id", "your_client_id", raising=False)
        with pytest.raises(WorkOSConfigurationError, match="placeholder"):
            _get_workos_client_id()

    def test_returns_valid_id(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_client_id", "client_real", raising=False)
        assert _get_workos_client_id() == "client_real"


class TestGetWorkOSApiKey:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_api_key", None, raising=False)
        with pytest.raises(WorkOSConfigurationError, match="WORKOS_API_KEY"):
            _get_workos_api_key()

    def test_raises_when_empty_secret(self, monkeypatch):
        # SecretStr("") is falsy, so it hits "not configured" before "empty"
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr(""), raising=False)
        with pytest.raises(WorkOSConfigurationError, match="not configured"):
            _get_workos_api_key()

    def test_raises_when_whitespace_only_secret(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("   "), raising=False)
        with pytest.raises(WorkOSConfigurationError, match="empty"):
            _get_workos_api_key()

    def test_rejects_placeholder(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr(" replace_me "), raising=False)
        with pytest.raises(WorkOSConfigurationError, match="placeholder"):
            _get_workos_api_key()

    def test_returns_valid_key(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_real"), raising=False)
        assert _get_workos_api_key() == "sk_live_real"


class TestGetWorkOSWebhookSecret:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_webhook_secret", None, raising=False)
        with pytest.raises(WorkOSConfigurationError, match="WORKOS_WEBHOOK_SECRET"):
            _get_workos_webhook_secret()

    def test_raises_when_empty(self, monkeypatch):
        monkeypatch.setattr(
            settings.sso, "workos_webhook_secret", SecretStr("  "), raising=False
        )
        with pytest.raises(WorkOSConfigurationError, match="empty"):
            _get_workos_webhook_secret()

    def test_returns_valid_secret(self, monkeypatch):
        monkeypatch.setattr(
            settings.sso, "workos_webhook_secret", SecretStr("whsec_abc"), raising=False
        )
        assert _get_workos_webhook_secret() == "whsec_abc"


class TestGetWorkOSBaseUrl:
    def test_requires_https(self, monkeypatch):
        monkeypatch.setattr(
            settings.sso, "workos_api_base_url", "http://bad.example.com", raising=False
        )
        with pytest.raises(WorkOSConfigurationError, match="HTTPS"):
            _get_workos_base_url()

    def test_raises_when_empty(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_api_base_url", "   ", raising=False)
        with pytest.raises(WorkOSConfigurationError, match="not configured"):
            _get_workos_base_url()

    def test_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setattr(
            settings.sso, "workos_api_base_url", "https://api.workos.com/", raising=False
        )
        assert _get_workos_base_url() == "https://api.workos.com"


# ---------------------------------------------------------------------------
# is_workos_enabled
# ---------------------------------------------------------------------------


class TestIsWorkOSEnabled:
    def test_false_when_disabled(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", False, raising=False)
        assert is_workos_enabled() is False

    def test_false_for_placeholder_client_id(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
        monkeypatch.setattr(settings.sso, "workos_client_id", "your_client_id", raising=False)
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_ok"), raising=False)
        assert is_workos_enabled() is False

    def test_true_for_valid_config(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
        monkeypatch.setattr(settings.sso, "workos_client_id", "client_123", raising=False)
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_ok"), raising=False)
        assert is_workos_enabled() is True


# ---------------------------------------------------------------------------
# Webhook signature parsing and verification
# ---------------------------------------------------------------------------


class TestParseSignatureHeader:
    def test_valid_header(self):
        ts, sig = _parse_workos_signature_header("t=1234567890,v1=abc123")
        assert ts == 1234567890
        assert sig == "abc123"

    def test_missing_timestamp(self):
        with pytest.raises(WorkOSWebhookVerificationError, match=r"t.*v1"):
            _parse_workos_signature_header("v1=abc")

    def test_missing_v1(self):
        with pytest.raises(WorkOSWebhookVerificationError, match=r"t.*v1"):
            _parse_workos_signature_header("t=123")

    def test_invalid_timestamp(self):
        with pytest.raises(WorkOSWebhookVerificationError, match="invalid"):
            _parse_workos_signature_header("t=notanumber,v1=abc")


class TestVerifyWebhookSignature:
    def _make_signature(self, body: bytes, secret: str, timestamp_ms: int) -> str:
        body_text = body.decode("utf-8")
        signed_content = f"{timestamp_ms}.{body_text}"
        sig = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp_ms},v1={sig}"

    def test_valid_signature(self):
        secret = "test_secret_key"
        body = b'{"event":"test"}'
        ts_ms = int(time.time() * 1000)
        header = self._make_signature(body, secret, ts_ms)

        # Should not raise
        verify_workos_webhook_signature(body, header, secret=secret, tolerance_seconds=300)

    def test_invalid_hash(self):
        body = b'{"event":"test"}'
        header = f"t={int(time.time() * 1000)},v1=badhash"
        with pytest.raises(WorkOSWebhookVerificationError, match="mismatch"):
            verify_workos_webhook_signature(body, header, secret="secret")

    def test_expired_timestamp(self):
        secret = "test_secret"
        body = b'{"event":"test"}'
        old_ts = int((time.time() - 999) * 1000)
        header = self._make_signature(body, secret, old_ts)

        with pytest.raises(WorkOSWebhookVerificationError, match="tolerance"):
            verify_workos_webhook_signature(body, header, secret=secret, tolerance_seconds=10)


# ---------------------------------------------------------------------------
# parse_and_verify_workos_webhook
# ---------------------------------------------------------------------------


class TestParseAndVerifyWebhook:
    def _sign(self, body: bytes, secret: str) -> str:
        ts_ms = int(time.time() * 1000)
        body_text = body.decode("utf-8")
        signed = f"{ts_ms}.{body_text}"
        sig = hmac.new(
            secret.encode("utf-8"), signed.encode("utf-8"), digestmod=hashlib.sha256
        ).hexdigest()
        return f"t={ts_ms},v1={sig}"

    def test_valid_webhook(self, monkeypatch):
        secret = "whsec_test"
        monkeypatch.setattr(
            settings.sso, "workos_webhook_secret", SecretStr(secret), raising=False
        )
        payload = {
            "id": "evt_1",
            "event": "user.created",
            "data": {"user": "alice"},
            "created_at": "2025-01-01T00:00:00Z",
        }
        body = json.dumps(payload).encode("utf-8")
        sig = self._sign(body, secret)

        event = parse_and_verify_workos_webhook(body, sig, tolerance_seconds=300)
        assert isinstance(event, WorkOSWebhookEvent)
        assert event.id == "evt_1"
        assert event.event == "user.created"

    def test_invalid_json_body(self, monkeypatch):
        secret = "whsec_test2"
        monkeypatch.setattr(
            settings.sso, "workos_webhook_secret", SecretStr(secret), raising=False
        )
        body = b"not-json"
        sig = self._sign(body, secret)
        with pytest.raises(WorkOSWebhookVerificationError, match="not valid JSON"):
            parse_and_verify_workos_webhook(body, sig, tolerance_seconds=300)


# ---------------------------------------------------------------------------
# Async API functions
# ---------------------------------------------------------------------------


class TestGeneratePortalLink:
    @pytest.mark.asyncio
    async def test_disabled_raises(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", False, raising=False)
        with pytest.raises(WorkOSConfigurationError, match="disabled"):
            await generate_workos_admin_portal_link("org_1", intent="sso")

    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_ok"), raising=False)
        monkeypatch.setattr(
            settings.sso, "workos_api_base_url", "https://api.workos.com", raising=False
        )
        monkeypatch.setattr(settings.sso, "workos_portal_return_url", None, raising=False)
        monkeypatch.setattr(settings.sso, "workos_portal_success_url", None, raising=False)

        mock_response = httpx.Response(
            200,
            json={"link": "https://portal.workos.com/abc"},
            request=httpx.Request("POST", "https://api.workos.com/portal/generate_link"),
        )
        with patch("src.core.shared.auth.workos.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            link = await generate_workos_admin_portal_link("org_1", intent="sso")
        assert link == "https://portal.workos.com/abc"

    @pytest.mark.asyncio
    async def test_api_error(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_ok"), raising=False)
        monkeypatch.setattr(
            settings.sso, "workos_api_base_url", "https://api.workos.com", raising=False
        )

        mock_response = httpx.Response(
            403,
            text="Forbidden",
            request=httpx.Request("POST", "https://api.workos.com/portal/generate_link"),
        )
        with patch("src.core.shared.auth.workos.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(WorkOSAPIError, match="403"):
                await generate_workos_admin_portal_link("org_1", intent="sso")

    @pytest.mark.asyncio
    async def test_missing_link_in_response(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_ok"), raising=False)
        monkeypatch.setattr(
            settings.sso, "workos_api_base_url", "https://api.workos.com", raising=False
        )
        monkeypatch.setattr(settings.sso, "workos_portal_return_url", None, raising=False)
        monkeypatch.setattr(settings.sso, "workos_portal_success_url", None, raising=False)

        mock_response = httpx.Response(
            200,
            json={"no_link": True},
            request=httpx.Request("POST", "https://api.workos.com/portal/generate_link"),
        )
        with patch("src.core.shared.auth.workos.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(WorkOSAPIError, match="valid portal link"):
                await generate_workos_admin_portal_link("org_1", intent="sso")


class TestListWorkOSEvents:
    @pytest.mark.asyncio
    async def test_disabled_raises(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", False, raising=False)
        with pytest.raises(WorkOSConfigurationError, match="disabled"):
            await list_workos_events(["user.created"])

    @pytest.mark.asyncio
    async def test_empty_event_types_raises(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
        with pytest.raises(WorkOSConfigurationError, match="event type"):
            await list_workos_events([])

    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        monkeypatch.setattr(settings.sso, "workos_enabled", True, raising=False)
        monkeypatch.setattr(settings.sso, "workos_api_key", SecretStr("sk_live_ok"), raising=False)
        monkeypatch.setattr(
            settings.sso, "workos_api_base_url", "https://api.workos.com", raising=False
        )

        response_data = {"data": [{"id": "e1"}], "list_metadata": {"after": None}}
        mock_response = httpx.Response(
            200,
            json=response_data,
            request=httpx.Request("GET", "https://api.workos.com/events"),
        )
        with patch("src.core.shared.auth.workos.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await list_workos_events(["user.created"])
        assert result["data"][0]["id"] == "e1"


# ---------------------------------------------------------------------------
# WebhookEvent model
# ---------------------------------------------------------------------------


class TestWebhookEventModel:
    def test_valid_event(self):
        evt = WorkOSWebhookEvent(
            id="evt_1",
            event="user.created",
            data={"foo": "bar"},
            created_at="2025-01-01T00:00:00Z",
        )
        assert evt.id == "evt_1"

    def test_rejects_empty_id(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WorkOSWebhookEvent(
                id="", event="x", data={}, created_at="2025-01-01T00:00:00Z"
            )
