"""
Tests for ACGS-2 SAML 2.0 Handler Service
Constitutional Hash: cdd01ef066bc6cf2

Covers: SAMLHandler initialization, IdP registration, request tracking,
metadata fetching, login initiation, ACS processing, logout, metadata
generation, and resource cleanup.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shared.auth.saml_config import (
    SAMLConfig,
    SAMLConfigurationError,
    SAMLIdPConfig,
    SAMLSPConfig,
)
from src.core.shared.auth.saml_handler import SAMLHandler
from src.core.shared.auth.saml_types import (
    SAMLError,
    SAMLProviderError,
    SAMLReplayError,
    SAMLUserInfo,
    SAMLValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sp_config(**overrides: Any) -> SAMLSPConfig:
    """Build a minimal SAMLSPConfig for testing."""
    defaults: dict[str, Any] = {
        "entity_id": "urn:test:sp",
        "acs_url": "https://sp.example.com/acs",
        "sign_authn_requests": False,
    }
    defaults.update(overrides)
    return SAMLSPConfig(**defaults)


def _make_idp_kwargs(**overrides: Any) -> dict[str, Any]:
    """Build valid register_idp kwargs."""
    defaults: dict[str, Any] = {
        "name": "test-idp",
        "metadata_url": "https://idp.example.com/metadata",
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture()
def sp_config() -> SAMLSPConfig:
    return _make_sp_config()


@pytest.fixture()
def handler(sp_config: SAMLSPConfig) -> SAMLHandler:
    return SAMLHandler(sp_config=sp_config)


@pytest.fixture()
def handler_with_idp(handler: SAMLHandler) -> SAMLHandler:
    handler.register_idp(**_make_idp_kwargs())
    return handler


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestSAMLHandlerInit:
    """SAMLHandler.__init__ branch coverage."""

    def test_default_config_when_no_args(self) -> None:
        h = SAMLHandler()
        assert h.sp_config.entity_id == "urn:acgs2:saml:sp"
        assert h.sp_config.acs_url == "/sso/saml/acs"

    def test_init_with_sp_config(self, sp_config: SAMLSPConfig) -> None:
        h = SAMLHandler(sp_config=sp_config)
        assert h.sp_config is sp_config

    def test_init_with_full_config(self, sp_config: SAMLSPConfig) -> None:
        full = SAMLConfig(sp=sp_config)
        h = SAMLHandler(config=full)
        assert h.sp_config is sp_config

    def test_config_overrides_sp_config(self, sp_config: SAMLSPConfig) -> None:
        """When both config and sp_config given, config wins."""
        other_sp = _make_sp_config(entity_id="urn:other:sp")
        full = SAMLConfig(sp=other_sp)
        h = SAMLHandler(sp_config=sp_config, config=full)
        assert h.sp_config.entity_id == "urn:other:sp"

    def test_sp_config_property(self, handler: SAMLHandler) -> None:
        assert handler.sp_config.entity_id == "urn:test:sp"


# ---------------------------------------------------------------------------
# IdP registration
# ---------------------------------------------------------------------------


class TestIdPRegistration:
    """register_idp, register_idp_from_model, get_idp, list_idps."""

    def test_register_idp_with_metadata_url(self, handler: SAMLHandler) -> None:
        handler.register_idp(**_make_idp_kwargs())
        assert "test-idp" in handler.list_idps()

    def test_register_idp_with_metadata_xml(self, handler: SAMLHandler) -> None:
        handler.register_idp(name="xml-idp", metadata_xml="<xml/>")
        assert handler.get_idp("xml-idp").metadata_xml == "<xml/>"

    def test_register_idp_with_manual_config(self, handler: SAMLHandler) -> None:
        handler.register_idp(
            name="manual",
            entity_id="urn:manual:idp",
            sso_url="https://idp.example.com/sso",
            certificate="CERTDATA",
        )
        idp = handler.get_idp("manual")
        assert idp.entity_id == "urn:manual:idp"
        assert idp.sso_url == "https://idp.example.com/sso"

    def test_register_idp_invalid_config_raises(self, handler: SAMLHandler) -> None:
        with pytest.raises(SAMLConfigurationError, match="Invalid IdP configuration"):
            handler.register_idp(name="bad")

    def test_register_idp_clears_cached_client(self, handler: SAMLHandler) -> None:
        handler.register_idp(**_make_idp_kwargs())
        # Manually plant a cached client
        handler._saml_clients["test-idp"] = MagicMock()
        # Re-register should evict the cache
        handler.register_idp(**_make_idp_kwargs())
        assert "test-idp" not in handler._saml_clients

    def test_get_idp_unknown_raises(self, handler: SAMLHandler) -> None:
        with pytest.raises(SAMLConfigurationError, match="not registered"):
            handler.get_idp("nonexistent")

    def test_list_idps_empty(self, handler: SAMLHandler) -> None:
        assert handler.list_idps() == []

    def test_list_idps_multiple(self, handler: SAMLHandler) -> None:
        handler.register_idp(name="a", metadata_url="https://a.example.com/meta")
        handler.register_idp(name="b", metadata_url="https://b.example.com/meta")
        assert set(handler.list_idps()) == {"a", "b"}

    def test_register_idp_from_model_non_saml_raises(self, handler: SAMLHandler) -> None:
        provider = MagicMock()
        provider.is_saml = False
        provider.name = "oidc-provider"
        with pytest.raises(SAMLConfigurationError, match="not a SAML provider"):
            handler.register_idp_from_model(provider)

    def test_register_idp_from_model_invalid_config_raises(self, handler: SAMLHandler) -> None:
        provider = MagicMock()
        provider.is_saml = True
        provider.name = "bad-saml"
        provider.validate_saml_config.return_value = ["missing entity_id"]
        with pytest.raises(SAMLConfigurationError, match="Invalid SAML configuration"):
            handler.register_idp_from_model(provider)

    def test_register_idp_from_model_success(self, handler: SAMLHandler) -> None:
        provider = MagicMock()
        provider.is_saml = True
        provider.name = "okta"
        provider.validate_saml_config.return_value = []
        provider.saml_metadata_url = "https://okta.example.com/meta"
        provider.saml_metadata_xml = None
        provider.saml_entity_id = "urn:okta:idp"
        provider.saml_sp_cert = None
        provider.saml_sign_assertions = True
        handler.register_idp_from_model(provider)
        assert "okta" in handler.list_idps()


# ---------------------------------------------------------------------------
# Request tracking (delegates to SAMLRequestTracker)
# ---------------------------------------------------------------------------


class TestRequestTracking:
    """Outstanding request storage, verification, listing, expiry."""

    def test_store_and_verify_request(self, handler: SAMLHandler) -> None:
        rid = handler.store_outstanding_request(idp_name="idp1")
        assert rid.startswith("_saml_")
        assert handler.verify_and_remove_request(rid) is True

    def test_verify_unknown_request_returns_false(self, handler: SAMLHandler) -> None:
        assert handler.verify_and_remove_request("unknown") is False

    def test_double_verify_returns_false(self, handler: SAMLHandler) -> None:
        rid = handler.store_outstanding_request()
        handler.verify_and_remove_request(rid)
        assert handler.verify_and_remove_request(rid) is False

    def test_get_outstanding_requests(self, handler: SAMLHandler) -> None:
        handler.store_outstanding_request(request_id="r1", idp_name="idp1")
        reqs = handler.get_outstanding_requests()
        assert "r1" in reqs
        assert reqs["r1"] == "idp1"

    def test_clear_expired_requests(self, handler: SAMLHandler) -> None:
        handler.store_outstanding_request(request_id="old", expiry_minutes=0)
        cleared = handler.clear_expired_requests()
        assert cleared >= 1

    def test_generate_request_id(self, handler: SAMLHandler) -> None:
        rid = handler._generate_request_id()
        assert isinstance(rid, str)
        assert rid.startswith("_saml_")


# ---------------------------------------------------------------------------
# Metadata fetching
# ---------------------------------------------------------------------------


class TestFetchMetadata:
    """_fetch_metadata with mocked httpx."""

    @pytest.mark.asyncio
    async def test_returns_inline_xml_when_no_url(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="inline", metadata_xml="<md/>")
        result = await handler._fetch_metadata(idp)
        assert result == "<md/>"

    @pytest.mark.asyncio
    async def test_returns_inline_xml_when_url_is_none(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="none", metadata_xml=None)
        result = await handler._fetch_metadata(idp)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetches_from_url(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="remote", metadata_url="https://idp.example.com/meta")
        mock_response = MagicMock()
        mock_response.text = "<EntityDescriptor/>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        handler._http_client = mock_client

        result = await handler._fetch_metadata(idp)
        assert result == "<EntityDescriptor/>"
        mock_client.get.assert_awaited_once_with("https://idp.example.com/meta")

    @pytest.mark.asyncio
    async def test_uses_cache(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="cached", metadata_url="https://idp.example.com/meta")
        handler._metadata_cache["cached"] = ("<cached/>", datetime.now(UTC))

        result = await handler._fetch_metadata(idp)
        assert result == "<cached/>"

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="refresh", metadata_url="https://idp.example.com/meta")
        handler._metadata_cache["refresh"] = ("<old/>", datetime.now(UTC))

        mock_response = MagicMock()
        mock_response.text = "<new/>"
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        handler._http_client = mock_client

        result = await handler._fetch_metadata(idp, force_refresh=True)
        assert result == "<new/>"

    @pytest.mark.asyncio
    async def test_falls_back_to_cached_on_error(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="fallback", metadata_url="https://idp.example.com/meta")
        handler._metadata_cache["fallback"] = ("<stale/>", datetime.now(UTC))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network down"))
        handler._http_client = mock_client

        result = await handler._fetch_metadata(idp, force_refresh=True)
        assert result == "<stale/>"

    @pytest.mark.asyncio
    async def test_raises_when_no_cache_and_error(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="nocache", metadata_url="https://idp.example.com/meta")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network down"))
        handler._http_client = mock_client

        with pytest.raises(SAMLProviderError, match="Failed to fetch metadata"):
            await handler._fetch_metadata(idp)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class TestGetHttpClient:
    """_get_http_client lazy initialization."""

    @pytest.mark.asyncio
    async def test_raises_when_httpx_unavailable(self, handler: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_HTTPX", False):
            with pytest.raises(SAMLError, match="httpx library is required"):
                await handler._get_http_client()

    @pytest.mark.asyncio
    async def test_creates_client_lazily(self, handler: SAMLHandler) -> None:
        assert handler._http_client is None
        with patch("src.core.shared.auth.saml_handler.HAS_HTTPX", True):
            with patch("src.core.shared.auth.saml_handler.httpx") as mock_httpx:
                mock_httpx.Timeout = MagicMock()
                mock_httpx.AsyncClient = MagicMock()
                client = await handler._get_http_client()
                assert client is not None

    @pytest.mark.asyncio
    async def test_reuses_existing_client(self, handler: SAMLHandler) -> None:
        sentinel = MagicMock()
        handler._http_client = sentinel
        client = await handler._get_http_client()
        assert client is sentinel


# ---------------------------------------------------------------------------
# _build_pysaml2_config
# ---------------------------------------------------------------------------


class TestBuildPysaml2Config:
    """Configuration dictionary building for PySAML2."""

    def test_basic_config_structure(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="basic", metadata_url="https://idp.example.com/meta")
        config = handler._build_pysaml2_config(idp, None)

        assert config["entityid"] == "urn:test:sp"
        assert "service" in config
        assert "sp" in config["service"]
        sp_section = config["service"]["sp"]
        assert sp_section["want_assertions_signed"] is True
        assert sp_section["want_response_signed"] is True

    def test_sls_endpoint_included_when_configured(self) -> None:
        sp = _make_sp_config(sls_url="https://sp.example.com/sls")
        h = SAMLHandler(sp_config=sp)
        idp = SAMLIdPConfig(name="sls", metadata_url="https://idp.example.com/meta")
        config = h._build_pysaml2_config(idp, None)
        endpoints = config["service"]["sp"]["endpoints"]
        assert "single_logout_service" in endpoints

    def test_sls_endpoint_absent_when_not_configured(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="nosls", metadata_url="https://idp.example.com/meta")
        config = handler._build_pysaml2_config(idp, None)
        endpoints = config["service"]["sp"]["endpoints"]
        assert "single_logout_service" not in endpoints

    def test_metadata_xml_written_to_local_key(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(name="xmlidp", metadata_url="https://idp.example.com/meta")
        config = handler._build_pysaml2_config(idp, "<EntityDescriptor/>")
        assert "local" in config["metadata"]

    def test_manual_idp_config_uses_inline(self, handler: SAMLHandler) -> None:
        idp = SAMLIdPConfig(
            name="manual",
            entity_id="urn:manual",
            sso_url="https://idp.example.com/sso",
            certificate="CERT",
        )
        config = handler._build_pysaml2_config(idp, None)
        assert "inline" in config["metadata"]
        inline = config["metadata"]["inline"][0]
        assert inline["entity_id"] == "urn:manual"

    def test_cert_and_key_written_to_temp_files(self) -> None:
        sp = _make_sp_config(
            cert_content="-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----",
            key_content="-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----",
        )
        h = SAMLHandler(sp_config=sp)
        idp = SAMLIdPConfig(name="certs", metadata_url="https://idp.example.com/meta")
        config = h._build_pysaml2_config(idp, None)
        assert "cert_file" in config
        assert "key_file" in config


# ---------------------------------------------------------------------------
# _get_saml_client
# ---------------------------------------------------------------------------


class TestGetSamlClient:
    """Client creation with PySAML2 dependency gating."""

    @pytest.mark.asyncio
    async def test_raises_without_pysaml2(self, handler_with_idp: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            with pytest.raises(SAMLError, match="PySAML2 is required"):
                await handler_with_idp._get_saml_client("test-idp")

    @pytest.mark.asyncio
    async def test_raises_for_unknown_idp(self, handler: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            with pytest.raises(SAMLConfigurationError, match="not registered"):
                await handler._get_saml_client("ghost")

    @pytest.mark.asyncio
    async def test_returns_cached_client(self, handler_with_idp: SAMLHandler) -> None:
        sentinel = MagicMock()
        handler_with_idp._saml_clients["test-idp"] = sentinel
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            client = await handler_with_idp._get_saml_client("test-idp")
        assert client is sentinel


# ---------------------------------------------------------------------------
# _detect_idp_name
# ---------------------------------------------------------------------------


class TestDetectIdpName:
    """IdP detection from request ID or fallback to first registered."""

    def test_detects_from_request_tracker(self, handler_with_idp: SAMLHandler) -> None:
        rid = handler_with_idp.store_outstanding_request(request_id="r1", idp_name="test-idp")
        result = handler_with_idp._detect_idp_name("r1")
        assert result == "test-idp"

    def test_falls_back_to_first_idp(self, handler_with_idp: SAMLHandler) -> None:
        result = handler_with_idp._detect_idp_name(None)
        assert result == "test-idp"

    def test_falls_back_when_request_has_no_idp(self, handler_with_idp: SAMLHandler) -> None:
        handler_with_idp.store_outstanding_request(request_id="r2", idp_name=None)
        result = handler_with_idp._detect_idp_name("r2")
        assert result == "test-idp"

    def test_raises_when_no_idps_registered(self, handler: SAMLHandler) -> None:
        with pytest.raises(SAMLConfigurationError, match="No IdPs registered"):
            handler._detect_idp_name(None)


# ---------------------------------------------------------------------------
# _handle_replay_prevention
# ---------------------------------------------------------------------------


class TestHandleReplayPrevention:
    """Replay detection for ACS responses."""

    def test_no_op_when_request_id_is_none(self, handler: SAMLHandler) -> None:
        handler._handle_replay_prevention(None)  # Should not raise

    def test_passes_for_valid_request(self, handler: SAMLHandler) -> None:
        rid = handler.store_outstanding_request(request_id="valid")
        handler._handle_replay_prevention("valid")  # Should not raise

    def test_raises_on_replay(self, handler: SAMLHandler) -> None:
        rid = handler.store_outstanding_request(request_id="once")
        handler._handle_replay_prevention("once")
        with pytest.raises(SAMLReplayError, match="replay detected"):
            handler._handle_replay_prevention("once")

    def test_raises_for_unknown_request(self, handler: SAMLHandler) -> None:
        with pytest.raises(SAMLReplayError, match="replay detected"):
            handler._handle_replay_prevention("unknown-id")


# ---------------------------------------------------------------------------
# initiate_login
# ---------------------------------------------------------------------------


class TestInitiateLogin:
    """SP-initiated login flow."""

    @pytest.mark.asyncio
    async def test_raises_without_pysaml2(self, handler_with_idp: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            with pytest.raises(SAMLError, match="PySAML2 is required"):
                await handler_with_idp.initiate_login("test-idp")

    @pytest.mark.asyncio
    async def test_raises_for_missing_entity_id(self, handler_with_idp: SAMLHandler) -> None:
        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = []
        handler_with_idp._saml_clients["test-idp"] = mock_client
        # The IdP has no entity_id set, and client returns empty list
        handler_with_idp._idp_configs["test-idp"].entity_id = None

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            with pytest.raises(SAMLConfigurationError, match="Cannot determine entity ID"):
                await handler_with_idp.initiate_login("test-idp")

    @pytest.mark.asyncio
    async def test_successful_login_flow(self, handler_with_idp: SAMLHandler) -> None:
        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req123",
            {"headers": [("Location", "https://idp.example.com/sso?SAMLRequest=xxx")]},
        )
        handler_with_idp._saml_clients["test-idp"] = mock_client
        handler_with_idp._idp_configs["test-idp"].entity_id = "urn:idp:entity"

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            url, rid = await handler_with_idp.initiate_login("test-idp", relay_state="/dashboard")

        assert url == "https://idp.example.com/sso?SAMLRequest=xxx"
        assert rid == "req123"

    @pytest.mark.asyncio
    async def test_raises_when_no_redirect_url(self, handler_with_idp: SAMLHandler) -> None:
        """When no Location header, SAMLError is raised internally.

        Without real pysaml2, UnknownPrincipal == Exception, so it may be
        caught by the first except clause and re-raised as
        SAMLConfigurationError. We accept either SAMLError subclass.
        """
        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req456",
            {"headers": []},
        )
        handler_with_idp._saml_clients["test-idp"] = mock_client
        handler_with_idp._idp_configs["test-idp"].entity_id = "urn:idp:entity"

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            with pytest.raises((SAMLError, SAMLConfigurationError)):
                await handler_with_idp.initiate_login("test-idp")

    @pytest.mark.asyncio
    async def test_wraps_runtime_error(self, handler_with_idp: SAMLHandler) -> None:
        """RuntimeError from prepare_for_authenticate is wrapped.

        Without real pysaml2, UnknownPrincipal == Exception catches RuntimeError
        first, wrapping it as SAMLConfigurationError.
        """
        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.side_effect = RuntimeError("boom")
        handler_with_idp._saml_clients["test-idp"] = mock_client
        handler_with_idp._idp_configs["test-idp"].entity_id = "urn:idp:entity"

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            with pytest.raises((SAMLError, SAMLConfigurationError)):
                await handler_with_idp.initiate_login("test-idp")

    @pytest.mark.asyncio
    async def test_entity_id_from_client_metadata(self, handler_with_idp: SAMLHandler) -> None:
        """When IdP has no entity_id, falls back to client metadata."""
        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = ["urn:discovered:idp"]
        mock_client.prepare_for_authenticate.return_value = (
            "req789",
            {"headers": [("Location", "https://idp.example.com/sso")]},
        )
        handler_with_idp._saml_clients["test-idp"] = mock_client
        handler_with_idp._idp_configs["test-idp"].entity_id = None

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            url, rid = await handler_with_idp.initiate_login("test-idp")

        mock_client.prepare_for_authenticate.assert_called_once()
        call_kwargs = mock_client.prepare_for_authenticate.call_args
        assert call_kwargs[1]["entityid"] == "urn:discovered:idp"


# ---------------------------------------------------------------------------
# process_acs_response
# ---------------------------------------------------------------------------


class TestProcessAcsResponse:
    """Assertion Consumer Service response processing."""

    @pytest.mark.asyncio
    async def test_raises_without_pysaml2(self, handler_with_idp: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            with pytest.raises(SAMLError, match="PySAML2 is required"):
                await handler_with_idp.process_acs_response("base64resp")

    @pytest.mark.asyncio
    async def test_raises_on_none_response(self, handler_with_idp: SAMLHandler) -> None:
        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = None
        handler_with_idp._saml_clients["test-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            with pytest.raises(SAMLValidationError, match="Failed to parse"):
                await handler_with_idp.process_acs_response(
                    "base64resp", idp_name="test-idp"
                )

    @pytest.mark.asyncio
    async def test_successful_acs_flow(self, handler_with_idp: SAMLHandler) -> None:
        # Store a request so replay prevention passes
        handler_with_idp.store_outstanding_request(request_id="acs-req", idp_name="test-idp")

        mock_response = MagicMock()
        mock_response.name_id = MagicMock()
        mock_response.name_id.__str__ = lambda self: "user@example.com"
        mock_response.name_id.format = "emailAddress"
        mock_response.session_info.return_value = {"session_index": "si1"}
        mock_response.ava = {"email": ["user@example.com"], "name": ["Test User"]}
        mock_response.issuer.return_value = "urn:idp:entity"

        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = mock_response
        handler_with_idp._saml_clients["test-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            user_info = await handler_with_idp.process_acs_response(
                "base64resp", request_id="acs-req", idp_name="test-idp"
            )

        assert user_info.email == "user@example.com"
        assert user_info.name == "Test User"

    @pytest.mark.asyncio
    async def test_replay_prevention_triggers(self, handler_with_idp: SAMLHandler) -> None:
        mock_response = MagicMock()
        mock_response.name_id = MagicMock()
        mock_response.name_id.__str__ = lambda self: "user@example.com"
        mock_response.name_id.format = "emailAddress"
        mock_response.session_info.return_value = {}
        mock_response.ava = {}
        mock_response.issuer.return_value = None

        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = mock_response
        handler_with_idp._saml_clients["test-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            with pytest.raises(SAMLReplayError):
                await handler_with_idp.process_acs_response(
                    "base64resp", request_id="fake-id", idp_name="test-idp"
                )

    @pytest.mark.asyncio
    async def test_wraps_runtime_error_as_validation(
        self, handler_with_idp: SAMLHandler
    ) -> None:
        mock_client = MagicMock()
        mock_client.parse_authn_request_response.side_effect = RuntimeError("bad xml")
        handler_with_idp._saml_clients["test-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            with pytest.raises(SAMLValidationError, match="validation failed"):
                await handler_with_idp.process_acs_response(
                    "base64resp", idp_name="test-idp"
                )

    @pytest.mark.asyncio
    async def test_detects_idp_from_request_id(self, handler_with_idp: SAMLHandler) -> None:
        handler_with_idp.store_outstanding_request(request_id="detect-req", idp_name="test-idp")

        mock_response = MagicMock()
        mock_response.name_id = MagicMock()
        mock_response.name_id.__str__ = lambda self: "u@e.com"
        mock_response.name_id.format = "emailAddress"
        mock_response.session_info.return_value = {}
        mock_response.ava = {}
        mock_response.issuer.return_value = None

        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = mock_response
        handler_with_idp._saml_clients["test-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            user_info = await handler_with_idp.process_acs_response(
                "base64resp", request_id="detect-req"
            )

        assert user_info.name_id == "u@e.com"


# ---------------------------------------------------------------------------
# initiate_logout
# ---------------------------------------------------------------------------


class TestInitiateLogout:
    """Single Logout flow."""

    @pytest.mark.asyncio
    async def test_returns_none_without_pysaml2(self, handler_with_idp: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            result = await handler_with_idp.initiate_logout("test-idp", "user@e.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_slo_url(self, handler_with_idp: SAMLHandler) -> None:
        # Default IdP has no slo_url
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            result = await handler_with_idp.initiate_logout("test-idp", "user@e.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_logout(self, handler: SAMLHandler) -> None:
        handler.register_idp(
            name="slo-idp",
            metadata_url="https://idp.example.com/meta",
            slo_url="https://idp.example.com/slo",
            entity_id="urn:slo:idp",
        )

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = ["urn:slo:idp"]
        mock_client.do_logout.return_value = (
            "logout-req",
            {"headers": [("Location", "https://idp.example.com/slo?SAMLRequest=xxx")]},
        )
        handler._saml_clients["slo-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            url = await handler.initiate_logout(
                "slo-idp", "user@e.com", relay_state="/logged-out"
            )

        assert url is not None
        assert "RelayState" in url

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, handler: SAMLHandler) -> None:
        handler.register_idp(
            name="err-idp",
            metadata_url="https://idp.example.com/meta",
            slo_url="https://idp.example.com/slo",
            entity_id="urn:err:idp",
        )

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = ["urn:err:idp"]
        mock_client.do_logout.side_effect = RuntimeError("slo failed")
        handler._saml_clients["err-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            result = await handler.initiate_logout("err-idp", "user@e.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_entity_id(self, handler: SAMLHandler) -> None:
        handler.register_idp(
            name="noeid",
            metadata_url="https://idp.example.com/meta",
            slo_url="https://idp.example.com/slo",
        )
        handler._idp_configs["noeid"].entity_id = None

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = []
        handler._saml_clients["noeid"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            result = await handler.initiate_logout("noeid", "user@e.com")
        assert result is None


# ---------------------------------------------------------------------------
# process_sls_response
# ---------------------------------------------------------------------------


class TestProcessSlsResponse:
    """SLS response processing."""

    @pytest.mark.asyncio
    async def test_returns_true_without_pysaml2(self, handler_with_idp: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            assert await handler_with_idp.process_sls_response("resp", "test-idp") is True

    @pytest.mark.asyncio
    async def test_successful_logout_response(self, handler_with_idp: SAMLHandler) -> None:
        mock_response = MagicMock()
        mock_response.status_ok.return_value = True

        mock_client = MagicMock()
        mock_client.parse_logout_request_response.return_value = mock_response
        handler_with_idp._saml_clients["test-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            assert await handler_with_idp.process_sls_response("resp", "test-idp") is True

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, handler_with_idp: SAMLHandler) -> None:
        mock_client = MagicMock()
        mock_client.parse_logout_request_response.side_effect = RuntimeError("parse fail")
        handler_with_idp._saml_clients["test-idp"] = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            assert await handler_with_idp.process_sls_response("resp", "test-idp") is False


# ---------------------------------------------------------------------------
# generate_metadata
# ---------------------------------------------------------------------------


class TestGenerateMetadata:
    """SP metadata generation."""

    @pytest.mark.asyncio
    async def test_generates_minimal_metadata_without_pysaml2(
        self, handler: SAMLHandler
    ) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            xml = await handler.generate_metadata()

        assert "EntityDescriptor" in xml
        assert handler.sp_config.entity_id in xml
        assert handler.sp_config.acs_url in xml
        assert "SPSSODescriptor" in xml

    @pytest.mark.asyncio
    async def test_includes_org_and_contact(self, handler: SAMLHandler) -> None:
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            xml = await handler.generate_metadata()

        assert handler.sp_config.org_name in xml
        assert handler.sp_config.contact_email in xml


# ---------------------------------------------------------------------------
# close / cleanup
# ---------------------------------------------------------------------------


class TestClose:
    """Resource cleanup on close."""

    @pytest.mark.asyncio
    async def test_close_without_http_client(self, handler: SAMLHandler) -> None:
        await handler.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_closes_http_client(self, handler: SAMLHandler) -> None:
        mock_client = AsyncMock()
        handler._http_client = mock_client
        await handler.close()
        mock_client.aclose.assert_awaited_once()
        assert handler._http_client is None

    @pytest.mark.asyncio
    async def test_close_cleans_temp_files(self, handler: SAMLHandler) -> None:
        import tempfile
        from pathlib import Path

        # Create real temp files to verify cleanup
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".crt", delete=False)
        tf.write("fake-cert")
        tf.flush()
        handler._temp_cert_file = tf

        await handler.close()

        assert not Path(tf.name).exists()

    @pytest.mark.asyncio
    async def test_close_tolerates_missing_temp_files(self, handler: SAMLHandler) -> None:
        mock_file = MagicMock()
        mock_file.name = "/nonexistent/path/file.crt"
        handler._temp_cert_file = mock_file
        await handler.close()  # Should not raise
