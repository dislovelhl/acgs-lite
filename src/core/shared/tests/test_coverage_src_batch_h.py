"""Comprehensive tests for batch H coverage targets.

Covers:
- src.core.shared.auth.workos
- src.core.shared.security.rotation.backend
- src.core.shared.security.security_headers
- src.core.shared.audit_client
- src.core.shared.config.security
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr


# ---------------------------------------------------------------------------
# 1. auth/workos.py
# ---------------------------------------------------------------------------

class TestWorkOSHelpers:
    """Tests for private helpers in workos module."""

    def test_secret_value_with_get_secret_value(self):
        from src.core.shared.auth.workos import _secret_value

        secret = SecretStr("my-secret")
        assert _secret_value(secret) == "my-secret"

    def test_secret_value_plain_string(self):
        from src.core.shared.auth.workos import _secret_value

        assert _secret_value("plain") == "plain"

    def test_secret_value_non_string(self):
        from src.core.shared.auth.workos import _secret_value

        assert _secret_value(42) == "42"

    def test_normalize_config_value(self):
        from src.core.shared.auth.workos import _normalize_config_value

        assert _normalize_config_value("  Replace_Me!  ") == "replaceme"
        assert _normalize_config_value("hello-world") == "helloworld"

    def test_ensure_not_placeholder_raises(self):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _ensure_not_placeholder,
        )

        with pytest.raises(WorkOSConfigurationError, match="placeholder"):
            _ensure_not_placeholder("replace_me", "TEST_FIELD")

        with pytest.raises(WorkOSConfigurationError, match="placeholder"):
            _ensure_not_placeholder("Your_Api_Key", "TEST_FIELD")

        with pytest.raises(WorkOSConfigurationError):
            _ensure_not_placeholder("placeholder", "TEST_FIELD")

    def test_ensure_not_placeholder_passes(self):
        from src.core.shared.auth.workos import _ensure_not_placeholder

        result = _ensure_not_placeholder("real-key-abc123", "TEST_FIELD")
        assert result == "real-key-abc123"


class TestWorkOSConfigGetters:
    """Tests for _get_workos_* functions."""

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_client_id_success(self, mock_settings):
        from src.core.shared.auth.workos import _get_workos_client_id

        mock_settings.sso.workos_client_id = "client_abc123"
        assert _get_workos_client_id() == "client_abc123"

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_client_id_empty(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_client_id,
        )

        mock_settings.sso.workos_client_id = ""
        with pytest.raises(WorkOSConfigurationError, match="not configured"):
            _get_workos_client_id()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_client_id_none(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_client_id,
        )

        mock_settings.sso.workos_client_id = None
        with pytest.raises(WorkOSConfigurationError, match="not configured"):
            _get_workos_client_id()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_client_id_placeholder(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_client_id,
        )

        mock_settings.sso.workos_client_id = "your_client_id"
        with pytest.raises(WorkOSConfigurationError):
            _get_workos_client_id()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_api_key_success(self, mock_settings):
        from src.core.shared.auth.workos import _get_workos_api_key

        mock_settings.sso.workos_api_key = SecretStr("sk_live_abc123")
        assert _get_workos_api_key() == "sk_live_abc123"

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_api_key_none(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_api_key,
        )

        mock_settings.sso.workos_api_key = None
        with pytest.raises(WorkOSConfigurationError, match="not configured"):
            _get_workos_api_key()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_api_key_empty_after_strip(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_api_key,
        )

        mock_settings.sso.workos_api_key = SecretStr("   ")
        with pytest.raises(WorkOSConfigurationError, match="empty"):
            _get_workos_api_key()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_webhook_secret_success(self, mock_settings):
        from src.core.shared.auth.workos import _get_workos_webhook_secret

        mock_settings.sso.workos_webhook_secret = SecretStr("whsec_abc123")
        assert _get_workos_webhook_secret() == "whsec_abc123"

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_webhook_secret_none(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_webhook_secret,
        )

        mock_settings.sso.workos_webhook_secret = None
        with pytest.raises(WorkOSConfigurationError, match="not configured"):
            _get_workos_webhook_secret()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_webhook_secret_empty(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_webhook_secret,
        )

        mock_settings.sso.workos_webhook_secret = SecretStr("  ")
        with pytest.raises(WorkOSConfigurationError, match="empty"):
            _get_workos_webhook_secret()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_base_url_success(self, mock_settings):
        from src.core.shared.auth.workos import _get_workos_base_url

        mock_settings.sso.workos_api_base_url = "https://api.workos.com/"
        assert _get_workos_base_url() == "https://api.workos.com"

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_base_url_empty(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_base_url,
        )

        mock_settings.sso.workos_api_base_url = "  "
        with pytest.raises(WorkOSConfigurationError, match="not configured"):
            _get_workos_base_url()

    @patch("src.core.shared.auth.workos.settings")
    def test_get_workos_base_url_not_https(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            _get_workos_base_url,
        )

        mock_settings.sso.workos_api_base_url = "http://api.workos.com"
        with pytest.raises(WorkOSConfigurationError, match="HTTPS"):
            _get_workos_base_url()


class TestIsWorkOSEnabled:

    @patch("src.core.shared.auth.workos.settings")
    def test_disabled_when_flag_off(self, mock_settings):
        from src.core.shared.auth.workos import is_workos_enabled

        mock_settings.sso.workos_enabled = False
        assert is_workos_enabled() is False

    @patch("src.core.shared.auth.workos.settings")
    def test_enabled_happy_path(self, mock_settings):
        from src.core.shared.auth.workos import is_workos_enabled

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_client_id = "client_abc"
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        assert is_workos_enabled() is True

    @patch("src.core.shared.auth.workos.settings")
    def test_disabled_when_client_id_missing(self, mock_settings):
        from src.core.shared.auth.workos import is_workos_enabled

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_client_id = None
        assert is_workos_enabled() is False

    @patch("src.core.shared.auth.workos.settings")
    def test_disabled_when_api_key_missing(self, mock_settings):
        from src.core.shared.auth.workos import is_workos_enabled

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_client_id = "client_abc"
        mock_settings.sso.workos_api_key = None
        assert is_workos_enabled() is False


class TestGenerateWorkOSAdminPortalLink:

    @patch("src.core.shared.auth.workos.settings")
    async def test_disabled_raises(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            generate_workos_admin_portal_link,
        )

        mock_settings.sso.workos_enabled = False
        with pytest.raises(WorkOSConfigurationError, match="disabled"):
            await generate_workos_admin_portal_link("org_123", intent="sso")

    @patch("src.core.shared.auth.workos.httpx.AsyncClient")
    @patch("src.core.shared.auth.workos.settings")
    async def test_success(self, mock_settings, mock_client_cls):
        from src.core.shared.auth.workos import generate_workos_admin_portal_link

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        mock_settings.sso.workos_api_base_url = "https://api.workos.com"
        mock_settings.sso.workos_portal_return_url = "https://app.example.com"
        mock_settings.sso.workos_portal_success_url = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"link": "https://portal.workos.com/abc"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        result = await generate_workos_admin_portal_link("org_123", intent="sso")
        assert result == "https://portal.workos.com/abc"

    @patch("src.core.shared.auth.workos.httpx.AsyncClient")
    @patch("src.core.shared.auth.workos.settings")
    async def test_api_error_status(self, mock_settings, mock_client_cls):
        from src.core.shared.auth.workos import (
            WorkOSAPIError,
            generate_workos_admin_portal_link,
        )

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        mock_settings.sso.workos_api_base_url = "https://api.workos.com"
        mock_settings.sso.workos_portal_return_url = None
        mock_settings.sso.workos_portal_success_url = None

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(WorkOSAPIError, match="403"):
            await generate_workos_admin_portal_link("org_123", intent="sso")

    @patch("src.core.shared.auth.workos.httpx.AsyncClient")
    @patch("src.core.shared.auth.workos.settings")
    async def test_missing_link_in_response(self, mock_settings, mock_client_cls):
        from src.core.shared.auth.workos import (
            WorkOSAPIError,
            generate_workos_admin_portal_link,
        )

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        mock_settings.sso.workos_api_base_url = "https://api.workos.com"
        mock_settings.sso.workos_portal_return_url = None
        mock_settings.sso.workos_portal_success_url = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"something": "else"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(WorkOSAPIError, match="valid portal link"):
            await generate_workos_admin_portal_link("org_123", intent="sso")

    @patch("src.core.shared.auth.workos.httpx.AsyncClient")
    @patch("src.core.shared.auth.workos.settings")
    async def test_with_intent_options_and_urls(self, mock_settings, mock_client_cls):
        from src.core.shared.auth.workos import generate_workos_admin_portal_link

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        mock_settings.sso.workos_api_base_url = "https://api.workos.com"
        mock_settings.sso.workos_portal_return_url = "https://default-return.com"
        mock_settings.sso.workos_portal_success_url = "https://default-success.com"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"link": "https://portal.workos.com/xyz"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        result = await generate_workos_admin_portal_link(
            "org_123",
            intent="dsync",
            return_url="https://custom-return.com",
            success_url="https://custom-success.com",
            intent_options={"foo": "bar"},
        )
        assert result == "https://portal.workos.com/xyz"


class TestListWorkOSEvents:

    @patch("src.core.shared.auth.workos.settings")
    async def test_disabled_raises(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            list_workos_events,
        )

        mock_settings.sso.workos_enabled = False
        with pytest.raises(WorkOSConfigurationError, match="disabled"):
            await list_workos_events(["connection.activated"])

    @patch("src.core.shared.auth.workos.settings")
    async def test_empty_event_types_raises(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSConfigurationError,
            list_workos_events,
        )

        mock_settings.sso.workos_enabled = True
        with pytest.raises(WorkOSConfigurationError, match="event type"):
            await list_workos_events([])

    @patch("src.core.shared.auth.workos.httpx.AsyncClient")
    @patch("src.core.shared.auth.workos.settings")
    async def test_success(self, mock_settings, mock_client_cls):
        from src.core.shared.auth.workos import list_workos_events

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        mock_settings.sso.workos_api_base_url = "https://api.workos.com"

        expected_data = {"data": [{"id": "evt_1"}], "list_metadata": {}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected_data

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        result = await list_workos_events(
            ["connection.activated"],
            organization_id="org_123",
            after="cursor_abc",
            range_start="2024-01-01",
            range_end="2024-12-31",
            limit=50,
        )
        assert result == expected_data

    @patch("src.core.shared.auth.workos.httpx.AsyncClient")
    @patch("src.core.shared.auth.workos.settings")
    async def test_api_error(self, mock_settings, mock_client_cls):
        from src.core.shared.auth.workos import WorkOSAPIError, list_workos_events

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        mock_settings.sso.workos_api_base_url = "https://api.workos.com"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(WorkOSAPIError, match="500"):
            await list_workos_events(["connection.activated"])

    @patch("src.core.shared.auth.workos.httpx.AsyncClient")
    @patch("src.core.shared.auth.workos.settings")
    async def test_non_dict_response_raises(self, mock_settings, mock_client_cls):
        from src.core.shared.auth.workos import WorkOSAPIError, list_workos_events

        mock_settings.sso.workos_enabled = True
        mock_settings.sso.workos_api_key = SecretStr("sk_live_key123")
        mock_settings.sso.workos_api_base_url = "https://api.workos.com"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["not", "a", "dict"]

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(WorkOSAPIError, match="not a JSON object"):
            await list_workos_events(["connection.activated"])


class TestWorkOSWebhookSignature:

    def test_parse_signature_header_valid(self):
        from src.core.shared.auth.workos import _parse_workos_signature_header

        ts_ms, sig = _parse_workos_signature_header("t=1234567890,v1=abcdef")
        assert ts_ms == 1234567890
        assert sig == "abcdef"

    def test_parse_signature_header_with_spaces(self):
        from src.core.shared.auth.workos import _parse_workos_signature_header

        ts_ms, sig = _parse_workos_signature_header("t=111, v1=xyz")
        assert ts_ms == 111
        assert sig == "xyz"

    def test_parse_signature_header_missing_t(self):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            _parse_workos_signature_header,
        )

        with pytest.raises(WorkOSWebhookVerificationError, match="t.*v1"):
            _parse_workos_signature_header("v1=abc")

    def test_parse_signature_header_missing_v1(self):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            _parse_workos_signature_header,
        )

        with pytest.raises(WorkOSWebhookVerificationError):
            _parse_workos_signature_header("t=123")

    def test_parse_signature_header_invalid_timestamp(self):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            _parse_workos_signature_header,
        )

        with pytest.raises(WorkOSWebhookVerificationError, match="invalid"):
            _parse_workos_signature_header("t=notanumber,v1=abc")

    def test_parse_signature_header_no_equals(self):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            _parse_workos_signature_header,
        )

        with pytest.raises(WorkOSWebhookVerificationError):
            _parse_workos_signature_header("garbage")

    def test_verify_webhook_signature_valid(self):
        from src.core.shared.auth.workos import verify_workos_webhook_signature

        secret = "whsec_test123"
        body = b'{"event":"test"}'
        timestamp_ms = int(time.time() * 1000)
        signed_content = f"{timestamp_ms}.{body.decode('utf-8')}"
        expected_hash = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        sig_header = f"t={timestamp_ms},v1={expected_hash}"
        # Should not raise
        verify_workos_webhook_signature(body, sig_header, secret=secret)

    def test_verify_webhook_signature_mismatch(self):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            verify_workos_webhook_signature,
        )

        timestamp_ms = int(time.time() * 1000)
        sig_header = f"t={timestamp_ms},v1=badhash"
        with pytest.raises(WorkOSWebhookVerificationError, match="mismatch"):
            verify_workos_webhook_signature(b"body", sig_header, secret="secret")

    def test_verify_webhook_signature_expired(self):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            verify_workos_webhook_signature,
        )

        secret = "whsec_test123"
        body = b'{"event":"test"}'
        # Timestamp 1 hour ago
        timestamp_ms = int((time.time() - 3600) * 1000)
        signed_content = f"{timestamp_ms}.{body.decode('utf-8')}"
        expected_hash = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        sig_header = f"t={timestamp_ms},v1={expected_hash}"
        with pytest.raises(WorkOSWebhookVerificationError, match="tolerance"):
            verify_workos_webhook_signature(body, sig_header, secret=secret, tolerance_seconds=180)


class TestParseAndVerifyWorkOSWebhook:

    @patch("src.core.shared.auth.workos.settings")
    def test_success(self, mock_settings):
        from src.core.shared.auth.workos import parse_and_verify_workos_webhook

        mock_settings.sso.workos_webhook_secret = SecretStr("whsec_test123")

        payload = {
            "id": "evt_123",
            "event": "connection.activated",
            "data": {"org": "org_1"},
            "created_at": "2024-01-01T00:00:00Z",
        }
        body = json.dumps(payload).encode("utf-8")
        secret = "whsec_test123"
        timestamp_ms = int(time.time() * 1000)
        signed_content = f"{timestamp_ms}.{body.decode('utf-8')}"
        expected_hash = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        sig_header = f"t={timestamp_ms},v1={expected_hash}"

        result = parse_and_verify_workos_webhook(body, sig_header)
        assert result.id == "evt_123"
        assert result.event == "connection.activated"

    @patch("src.core.shared.auth.workos.settings")
    def test_invalid_json(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            parse_and_verify_workos_webhook,
        )

        mock_settings.sso.workos_webhook_secret = SecretStr("whsec_test123")
        secret = "whsec_test123"
        body = b"not-json"
        timestamp_ms = int(time.time() * 1000)
        signed_content = f"{timestamp_ms}.{body.decode('utf-8')}"
        expected_hash = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        sig_header = f"t={timestamp_ms},v1={expected_hash}"

        with pytest.raises(WorkOSWebhookVerificationError, match="not valid JSON"):
            parse_and_verify_workos_webhook(body, sig_header)

    @patch("src.core.shared.auth.workos.settings")
    def test_non_dict_json(self, mock_settings):
        from src.core.shared.auth.workos import (
            WorkOSWebhookVerificationError,
            parse_and_verify_workos_webhook,
        )

        mock_settings.sso.workos_webhook_secret = SecretStr("whsec_test123")
        secret = "whsec_test123"
        body = b"[1,2,3]"
        timestamp_ms = int(time.time() * 1000)
        signed_content = f"{timestamp_ms}.{body.decode('utf-8')}"
        expected_hash = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        sig_header = f"t={timestamp_ms},v1={expected_hash}"

        with pytest.raises(WorkOSWebhookVerificationError, match="JSON object"):
            parse_and_verify_workos_webhook(body, sig_header)


class TestWorkOSWebhookEventModel:

    def test_valid_event(self):
        from src.core.shared.auth.workos import WorkOSWebhookEvent

        event = WorkOSWebhookEvent(
            id="evt_1",
            event="connection.activated",
            data={"key": "val"},
            created_at="2024-01-01T00:00:00Z",
        )
        assert event.id == "evt_1"

    def test_empty_id_rejected(self):
        from src.core.shared.auth.workos import WorkOSWebhookEvent

        with pytest.raises(Exception):
            WorkOSWebhookEvent(id="", event="x", data={}, created_at="2024-01-01")


# ---------------------------------------------------------------------------
# 2. security/rotation/backend.py
# ---------------------------------------------------------------------------

class TestInMemorySecretBackend:

    async def test_store_and_get(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        result = await backend.store_secret("db_pass", "s3cret", "v1")
        assert result is True
        val = await backend.get_secret("db_pass", "v1")
        assert val == "s3cret"

    async def test_get_latest_version(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        await backend.store_secret("key", "val1", "v1")
        await backend.store_secret("key", "val2", "v2")
        latest = await backend.get_secret("key")
        assert latest == "val2"

    async def test_get_nonexistent_name(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        assert await backend.get_secret("nope") is None

    async def test_get_nonexistent_version(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        await backend.store_secret("key", "val", "v1")
        assert await backend.get_secret("key", "v99") is None

    async def test_get_empty_versions_returns_none(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        backend._secrets["key"] = {}
        assert await backend.get_secret("key") is None

    async def test_delete_secret_version(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        await backend.store_secret("key", "val", "v1")
        deleted = await backend.delete_secret_version("key", "v1")
        assert deleted is True
        assert await backend.get_secret("key", "v1") is None

    async def test_delete_nonexistent_returns_false(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        assert await backend.delete_secret_version("nope", "v1") is False

    async def test_delete_nonexistent_version_returns_false(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        await backend.store_secret("key", "val", "v1")
        assert await backend.delete_secret_version("key", "v99") is False

    async def test_list_versions(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        await backend.store_secret("key", "a", "v1")
        await backend.store_secret("key", "b", "v2")
        versions = await backend.list_versions("key")
        assert versions == ["v1", "v2"]

    async def test_list_versions_nonexistent(self):
        from src.core.shared.security.rotation.backend import InMemorySecretBackend

        backend = InMemorySecretBackend()
        assert await backend.list_versions("nope") == []


class TestVaultSecretBackend:

    def test_init_defaults(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        assert backend._mount_point == "secret"
        assert backend._path_prefix == "acgs2/secrets"

    def test_init_custom(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend(
            vault_url="https://vault.example.com",
            vault_token="s.token123",
            mount_point="kv",
            path_prefix="myapp/secrets",
        )
        assert backend._vault_url == "https://vault.example.com"
        assert backend._vault_token == "s.token123"

    @patch.dict("os.environ", {"VAULT_ADDR": "https://env-vault.com", "VAULT_TOKEN": "s.env"})
    def test_init_from_env(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        assert backend._vault_url == "https://env-vault.com"
        assert backend._vault_token == "s.env"

    async def test_get_client_no_hvac(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        with patch.dict("sys.modules", {"hvac": None}):
            with patch("builtins.__import__", side_effect=ImportError("no hvac")):
                client = await backend._get_client()
                assert client is None

    async def test_get_client_with_hvac(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        mock_hvac = MagicMock()
        mock_hvac.Client.return_value = MagicMock()
        backend = VaultSecretBackend(vault_url="https://v.com", vault_token="tok")

        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            client = await backend._get_client()
            assert client is not None
            # Second call returns cached
            client2 = await backend._get_client()
            assert client2 is client

    async def test_get_secret_no_client(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        backend._get_client = AsyncMock(return_value=None)
        assert await backend.get_secret("key") is None

    async def test_get_secret_success_no_version(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "secret_val"}}
        }
        backend._get_client = AsyncMock(return_value=mock_client)

        result = await backend.get_secret("mykey")
        assert result == "secret_val"

    async def test_get_secret_with_version_id_numeric(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "versioned_val"}}
        }
        backend._get_client = AsyncMock(return_value=mock_client)

        # version_id with dash: split("-")[-1] should be numeric
        result = await backend.get_secret("mykey", version_id="key-3")
        assert result == "versioned_val"
        call_kwargs = mock_client.secrets.kv.v2.read_secret_version.call_args
        assert call_kwargs.kwargs.get("version") == 3 or call_kwargs[1].get("version") == 3

    async def test_get_secret_with_version_id_non_numeric_errors(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        backend._get_client = AsyncMock(return_value=mock_client)

        # "key-v3" -> split("-")[-1] = "v3" -> int("v3") raises ValueError -> caught
        result = await backend.get_secret("mykey", version_id="key-v3")
        assert result is None

    async def test_get_secret_with_version_no_dash(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "val"}}
        }
        backend._get_client = AsyncMock(return_value=mock_client)

        result = await backend.get_secret("mykey", version_id="nodash")
        assert result == "val"

    async def test_get_secret_error(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = RuntimeError("boom")
        backend._get_client = AsyncMock(return_value=mock_client)

        assert await backend.get_secret("key") is None

    async def test_store_secret_no_client(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        backend._get_client = AsyncMock(return_value=None)
        assert await backend.store_secret("k", "v", "vid") is False

    async def test_store_secret_success(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        backend._get_client = AsyncMock(return_value=mock_client)

        assert await backend.store_secret("k", "v", "vid") is True

    async def test_store_secret_error(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.create_or_update_secret.side_effect = ValueError("nope")
        backend._get_client = AsyncMock(return_value=mock_client)

        assert await backend.store_secret("k", "v", "vid") is False

    async def test_delete_secret_version_no_client(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        backend._get_client = AsyncMock(return_value=None)
        assert await backend.delete_secret_version("k", "v1") is False

    async def test_delete_secret_version_success(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        backend._get_client = AsyncMock(return_value=mock_client)

        assert await backend.delete_secret_version("k", "key-2") is True

    async def test_delete_secret_version_no_dash(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        backend._get_client = AsyncMock(return_value=mock_client)

        assert await backend.delete_secret_version("k", "nodash") is True
        call_kwargs = mock_client.secrets.kv.v2.delete_secret_versions.call_args
        assert [1] in call_kwargs.args or call_kwargs.kwargs.get("versions") == [1]

    async def test_delete_secret_version_error(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.delete_secret_versions.side_effect = KeyError("x")
        backend._get_client = AsyncMock(return_value=mock_client)

        assert await backend.delete_secret_version("k", "k-v1") is False

    async def test_list_versions_no_client(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        backend._get_client = AsyncMock(return_value=None)
        assert await backend.list_versions("k") == []

    async def test_list_versions_success(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_metadata.return_value = {
            "data": {"versions": {"1": {}, "2": {}, "3": {}}}
        }
        backend._get_client = AsyncMock(return_value=mock_client)

        versions = await backend.list_versions("mykey")
        assert versions == ["mykey-v1", "mykey-v2", "mykey-v3"]

    async def test_list_versions_error(self):
        from src.core.shared.security.rotation.backend import VaultSecretBackend

        backend = VaultSecretBackend()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_metadata.side_effect = RuntimeError("fail")
        backend._get_client = AsyncMock(return_value=mock_client)

        assert await backend.list_versions("k") == []


# ---------------------------------------------------------------------------
# 3. security/security_headers.py
# ---------------------------------------------------------------------------

class TestSecurityHeadersConfig:

    def test_default_values(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig()
        assert cfg.environment == "production"
        assert cfg.enable_hsts is True
        assert cfg.hsts_max_age == 31536000
        assert cfg.frame_options == "DENY"

    def test_for_development(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.for_development()
        assert cfg.environment == "development"
        assert cfg.enable_hsts is False
        assert cfg.hsts_max_age == 300
        assert cfg.custom_csp_directives is not None
        assert "'unsafe-eval'" in cfg.custom_csp_directives["script-src"]

    def test_for_production_strict(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.for_production(strict=True)
        assert cfg.environment == "production"
        assert cfg.enable_hsts is True
        assert cfg.hsts_preload is True
        assert cfg.custom_csp_directives is not None
        assert "'none'" in cfg.custom_csp_directives["frame-ancestors"]

    def test_for_production_not_strict(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.for_production(strict=False)
        assert cfg.custom_csp_directives is None

    def test_for_websocket_service(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.for_websocket_service()
        assert "ws:" in cfg.custom_csp_directives["connect-src"]
        assert "wss:" in cfg.custom_csp_directives["connect-src"]

    def test_for_integration_service(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.for_integration_service()
        assert "https:" in cfg.custom_csp_directives["connect-src"]

    @patch("src.core.shared.security.security_headers._detect_environment", return_value="development")
    @patch.dict("os.environ", {}, clear=False)
    def test_from_env_development(self, mock_detect):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.from_env()
        assert cfg.environment == "development"
        assert cfg.enable_hsts is False
        assert cfg.hsts_max_age == 300

    @patch("src.core.shared.security.security_headers._detect_environment", return_value="staging")
    @patch.dict("os.environ", {}, clear=False)
    def test_from_env_staging(self, mock_detect):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.from_env()
        assert cfg.environment == "staging"
        assert cfg.enable_hsts is True
        assert cfg.hsts_max_age == 86400

    @patch("src.core.shared.security.security_headers._detect_environment", return_value="production")
    @patch.dict("os.environ", {}, clear=False)
    def test_from_env_production(self, mock_detect):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.from_env()
        assert cfg.environment == "production"
        assert cfg.hsts_max_age == 31536000

    @patch("src.core.shared.security.security_headers._detect_environment", return_value="production")
    @patch.dict("os.environ", {"SECURITY_HSTS_ENABLED": "false", "SECURITY_HSTS_MAX_AGE": "999", "SECURITY_FRAME_OPTIONS": "SAMEORIGIN"}, clear=False)
    def test_from_env_custom_vars(self, mock_detect):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig.from_env()
        assert cfg.enable_hsts is False
        assert cfg.hsts_max_age == 999
        assert cfg.frame_options == "SAMEORIGIN"

    def test_get_csp_header_value_default(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig()
        csp = cfg.get_csp_header_value()
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_get_csp_header_value_custom(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig(
            custom_csp_directives={"connect-src": ["'self'", "https://api.example.com"]}
        )
        csp = cfg.get_csp_header_value()
        assert "https://api.example.com" in csp

    def test_get_hsts_header_value_disabled(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig(enable_hsts=False)
        assert cfg.get_hsts_header_value() is None

    def test_get_hsts_header_value_enabled(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig(
            enable_hsts=True,
            hsts_max_age=31536000,
            hsts_include_subdomains=True,
            hsts_preload=True,
        )
        hsts = cfg.get_hsts_header_value()
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts

    def test_get_hsts_no_subdomains_no_preload(self):
        from src.core.shared.security.security_headers import SecurityHeadersConfig

        cfg = SecurityHeadersConfig(
            enable_hsts=True,
            hsts_include_subdomains=False,
            hsts_preload=False,
        )
        hsts = cfg.get_hsts_header_value()
        assert "includeSubDomains" not in hsts
        assert "preload" not in hsts


class TestSecurityHeadersMiddleware:

    @patch("src.core.shared.security.security_headers.SecurityHeadersConfig.from_env")
    def test_init_default_config(self, mock_from_env):
        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        mock_from_env.return_value = SecurityHeadersConfig()
        app = MagicMock()
        mw = SecurityHeadersMiddleware(app)
        assert mw.config is not None

    def test_init_custom_config(self):
        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        cfg = SecurityHeadersConfig(environment="test")
        app = MagicMock()
        mw = SecurityHeadersMiddleware(app, config=cfg)
        assert mw.config.environment == "test"

    async def test_non_http_passthrough(self):
        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        app = AsyncMock()
        cfg = SecurityHeadersConfig()
        mw = SecurityHeadersMiddleware(app, config=cfg)

        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        app.assert_called_once_with(scope, receive, send)

    async def test_http_injects_headers(self):
        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        cfg = SecurityHeadersConfig(enable_hsts=True, enable_xss_protection=True)

        captured_messages: list[dict[str, Any]] = []

        async def mock_app(scope, receive, send):
            message: dict[str, Any] = {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
            await send(message)
            await send({"type": "http.response.body", "body": b"ok"})

        mw = SecurityHeadersMiddleware(mock_app, config=cfg)
        scope = {"type": "http"}
        receive = AsyncMock()

        async def capture_send(message):
            captured_messages.append(message)

        await mw(scope, receive, capture_send)

        assert len(captured_messages) == 2
        start_msg = captured_messages[0]
        # Headers should be set on the message via MutableHeaders
        from starlette.datastructures import MutableHeaders

        headers = MutableHeaders(scope=start_msg)
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "1; mode=block" in headers.get("X-XSS-Protection", "")

    def test_set_security_headers(self):
        from starlette.datastructures import MutableHeaders

        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        cfg = SecurityHeadersConfig(
            enable_hsts=True,
            enable_xss_protection=True,
            frame_options="SAMEORIGIN",
            referrer_policy="no-referrer",
        )
        app = MagicMock()
        mw = SecurityHeadersMiddleware(app, config=cfg)

        msg: dict[str, Any] = {"type": "http.response.start", "status": 200, "headers": []}
        headers = MutableHeaders(scope=msg)
        mw._set_security_headers(headers)

        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "SAMEORIGIN"
        assert headers["Referrer-Policy"] == "no-referrer"
        header_keys = [k for k, v in headers.items()]
        assert "strict-transport-security" in header_keys
        assert "permissions-policy" in header_keys

    def test_set_security_headers_no_hsts(self):
        from starlette.datastructures import MutableHeaders

        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        cfg = SecurityHeadersConfig(enable_hsts=False, enable_xss_protection=False)
        app = MagicMock()
        mw = SecurityHeadersMiddleware(app, config=cfg)

        msg: dict[str, Any] = {"type": "http.response.start", "status": 200, "headers": []}
        headers = MutableHeaders(scope=msg)
        mw._set_security_headers(headers)

        assert headers.get("Strict-Transport-Security") is None
        assert headers.get("X-XSS-Protection") is None

    def test_add_security_headers_response(self):
        from starlette.responses import Response

        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        cfg = SecurityHeadersConfig()
        app = MagicMock()
        mw = SecurityHeadersMiddleware(app, config=cfg)
        response = Response(content="test")
        mw._add_security_headers(response)
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


class TestAddSecurityHeadersFunction:

    def test_with_custom_config(self):
        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            add_security_headers,
        )

        app = MagicMock()
        cfg = SecurityHeadersConfig(environment="custom")
        add_security_headers(app, config=cfg)
        app.add_middleware.assert_called_once()

    def test_with_development_env(self):
        from src.core.shared.security.security_headers import add_security_headers

        app = MagicMock()
        add_security_headers(app, environment="development")
        app.add_middleware.assert_called_once()

    def test_with_production_env(self):
        from src.core.shared.security.security_headers import add_security_headers

        app = MagicMock()
        add_security_headers(app, environment="production")
        app.add_middleware.assert_called_once()

    @patch("src.core.shared.security.security_headers.SecurityHeadersConfig.from_env")
    def test_with_no_env(self, mock_from_env):
        from src.core.shared.security.security_headers import (
            SecurityHeadersConfig,
            add_security_headers,
        )

        mock_from_env.return_value = SecurityHeadersConfig()
        app = MagicMock()
        add_security_headers(app)
        app.add_middleware.assert_called_once()


# ---------------------------------------------------------------------------
# 4. audit_client.py
# ---------------------------------------------------------------------------

class TestAuditClient:

    def _make_client(self):
        from src.core.shared.audit_client import AuditClient

        return AuditClient("http://test-audit:8300")

    async def test_report_validation_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "abc123"}
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.report_validation({"key": "val"})
        assert result == "abc123"

    async def test_report_validation_with_to_dict(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "hash1"}
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        obj = MagicMock()
        obj.to_dict.return_value = {"converted": True}
        result = await client.report_validation(obj)
        assert result == "hash1"

    async def test_report_validation_with_dataclass(self):
        @dataclass
        class FakeResult:
            status: str = "ok"

        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "dc_hash"}
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.report_validation(FakeResult())
        assert result == "dc_hash"

    async def test_report_validation_http_error_fallback(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.report_validation({"key": "val"})
        assert result is not None
        assert result.startswith("simulated_")

    async def test_report_validation_connection_error_fallback(self):
        client = self._make_client()
        client.client = AsyncMock()
        client.client.post = AsyncMock(side_effect=httpx.ConnectError("conn failed"))

        result = await client.report_validation({"key": "val"})
        assert result is not None
        assert result.startswith("simulated_")

    async def test_report_validation_unexpected_error(self):
        client = self._make_client()
        # Cause a TypeError/ValueError/AttributeError in the outer try
        # by passing something that fails in to_dict detection AND dataclass check
        obj = MagicMock()
        obj.to_dict.side_effect = AttributeError("boom")
        client.client = AsyncMock()

        result = await client.report_validation(obj)
        assert result is None

    async def test_report_decision_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "dec_hash"}
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.report_decision({"decision": "allow", "agent_id": "a1"})
        assert result == "dec_hash"

    async def test_report_decision_with_to_dict(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "h2"}
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        obj = MagicMock()
        obj.to_dict.return_value = {"decision": "deny", "agent_id": "a2"}
        result = await client.report_decision(obj)
        assert result == "h2"

    async def test_report_decision_with_dataclass(self):
        @dataclass
        class FakeDecision:
            decision: str = "allow"
            agent_id: str = "a3"

        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "h3"}
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.report_decision(FakeDecision())
        assert result == "h3"

    async def test_report_decision_http_error_fallback(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.report_decision({"decision": "x", "agent_id": "a"})
        assert result.startswith("simulated_")

    async def test_report_decision_connection_error_fallback(self):
        client = self._make_client()
        client.client = AsyncMock()
        client.client.post = AsyncMock(side_effect=OSError("network"))

        result = await client.report_decision({"decision": "x", "agent_id": "a"})
        assert result.startswith("simulated_")

    async def test_report_decision_unexpected_error(self):
        client = self._make_client()
        obj = MagicMock()
        obj.to_dict.side_effect = TypeError("bad")
        client.client = AsyncMock()

        result = await client.report_decision(obj)
        assert result is None

    async def test_get_stats_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"total": 100}
        client.client = AsyncMock()
        client.client.get = AsyncMock(return_value=mock_response)

        stats = await client.get_stats()
        assert stats == {"total": 100}

    async def test_get_stats_error(self):
        client = self._make_client()
        client.client = AsyncMock()
        client.client.get = AsyncMock(side_effect=httpx.ConnectError("fail"))

        stats = await client.get_stats()
        assert stats == {}

    async def test_close(self):
        client = self._make_client()
        client.client = AsyncMock()
        await client.close()
        client.client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# 5. config/security.py
# ---------------------------------------------------------------------------

class TestSecuritySettings:

    def test_default_values(self):
        from src.core.shared.config.security import SecuritySettings

        s = SecuritySettings()
        assert s.jwt_public_key == "SYSTEM_PUBLIC_KEY_PLACEHOLDER"

    @patch.dict("os.environ", {"JWT_SECRET": "PLACEHOLDER"}, clear=False)
    def test_placeholder_jwt_secret_rejected(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception):
            SecuritySettings()

    @patch.dict("os.environ", {"JWT_SECRET": "CHANGE_ME"}, clear=False)
    def test_placeholder_change_me_rejected(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception):
            SecuritySettings()

    @patch.dict("os.environ", {"JWT_SECRET": "DANGEROUS_DEFAULT"}, clear=False)
    def test_placeholder_dangerous_default_rejected(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception):
            SecuritySettings()

    @patch.dict("os.environ", {"JWT_SECRET": "dev-secret"}, clear=False)
    def test_placeholder_dev_secret_rejected(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception):
            SecuritySettings()

    @patch.dict("os.environ", {"JWT_SECRET": "a" * 64}, clear=False)
    def test_valid_jwt_secret(self):
        from src.core.shared.config.security import SecuritySettings

        s = SecuritySettings()
        assert s.jwt_secret.get_secret_value() == "a" * 64

    def test_none_jwt_secret_ok(self):
        from src.core.shared.config.security import SecuritySettings

        s = SecuritySettings()
        assert s.jwt_secret is None

    @patch.dict("os.environ", {"API_KEY_INTERNAL": "PLACEHOLDER"}, clear=False)
    def test_api_key_internal_placeholder_rejected(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception):
            SecuritySettings()


class TestOPASettings:

    def test_defaults(self):
        from src.core.shared.config.security import OPASettings

        s = OPASettings()
        assert s.url == "http://localhost:8181"
        assert s.fail_closed is True
        assert s.mode == "http"

    @patch.dict("os.environ", {"OPA_URL": "http://opa:8181", "OPA_MODE": "embedded"}, clear=False)
    def test_custom(self):
        from src.core.shared.config.security import OPASettings

        s = OPASettings()
        assert s.url == "http://opa:8181"
        assert s.mode == "embedded"


class TestAuditSettings:

    def test_defaults(self):
        from src.core.shared.config.security import AuditSettings

        s = AuditSettings()
        assert s.url == "http://localhost:8001"


class TestVaultSettings:

    def test_defaults(self):
        from src.core.shared.config.security import VaultSettings

        s = VaultSettings()
        assert s.address == "http://127.0.0.1:8200"
        assert s.kv_mount == "secret"
        assert s.kv_version == 2
        assert s.verify_tls is True
        assert s.timeout == 30.0

    @patch.dict("os.environ", {
        "VAULT_ADDR": "https://vault.prod.com",
        "VAULT_TOKEN": "s.mytoken",
        "VAULT_NAMESPACE": "prod",
        "VAULT_TRANSIT_MOUNT": "my_transit",
        "VAULT_KV_MOUNT": "kv",
        "VAULT_KV_VERSION": "1",
        "VAULT_TIMEOUT": "10.0",
        "VAULT_VERIFY_TLS": "false",
    }, clear=False)
    def test_custom(self):
        from src.core.shared.config.security import VaultSettings

        s = VaultSettings()
        assert s.address == "https://vault.prod.com"
        assert s.token.get_secret_value() == "s.mytoken"
        assert s.namespace == "prod"
        assert s.kv_version == 1
        assert s.verify_tls is False


class TestSSOSettings:

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch):
        from src.core.shared.config.security import SSOSettings

        for env_var in (
            "SSO_ENABLED",
            "OIDC_ENABLED",
            "SAML_ENABLED",
            "WORKOS_ENABLED",
            "SSO_AUTO_PROVISION",
            "SSO_DEFAULT_ROLE",
        ):
            monkeypatch.delenv(env_var, raising=False)

        s = SSOSettings()
        assert s.enabled is True
        assert s.oidc_enabled is True
        assert s.saml_enabled is True
        assert s.workos_enabled is False
        assert s.auto_provision_users is True
        assert s.default_role_on_provision == "viewer"

    @patch.dict("os.environ", {
        "WORKOS_ENABLED": "true",
        "WORKOS_CLIENT_ID": "client_xyz",
        "WORKOS_API_KEY": "sk_live_test",
        "WORKOS_WEBHOOK_SECRET": "whsec_test",
    }, clear=False)
    def test_workos_fields(self):
        from src.core.shared.config.security import SSOSettings

        s = SSOSettings()
        assert s.workos_enabled is True
        assert s.workos_client_id == "client_xyz"
        assert s.workos_api_key.get_secret_value() == "sk_live_test"

    @patch.dict("os.environ", {
        "OIDC_CLIENT_ID": "oidc_id",
        "OIDC_CLIENT_SECRET": "oidc_secret",
        "OIDC_ISSUER_URL": "https://issuer.example.com",
        "OIDC_USE_PKCE": "false",
    }, clear=False)
    def test_oidc_fields(self):
        from src.core.shared.config.security import SSOSettings

        s = SSOSettings()
        assert s.oidc_client_id == "oidc_id"
        assert s.oidc_use_pkce is False

    @patch.dict("os.environ", {
        "SAML_ENTITY_ID": "https://sp.example.com/metadata",
        "SAML_SIGN_REQUESTS": "true",
        "SAML_WANT_ASSERTIONS_SIGNED": "true",
        "SAML_WANT_ASSERTIONS_ENCRYPTED": "true",
    }, clear=False)
    def test_saml_fields(self):
        from src.core.shared.config.security import SSOSettings

        s = SSOSettings()
        assert s.saml_entity_id == "https://sp.example.com/metadata"
        assert s.saml_want_assertions_encrypted is True


class TestHasPydanticSettings:
    """Test the conditional import path."""

    def test_has_pydantic_settings_flag(self):
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS

        # Should be True if pydantic_settings is installed
        assert isinstance(HAS_PYDANTIC_SETTINGS, bool)
