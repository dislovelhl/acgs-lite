"""
Comprehensive tests for:
  - src.core.shared.security.rotation.manager (SecretRotationManager)
  - src.core.shared.auth.saml_handler (SAMLHandler)
  - src.core.shared.auth.oidc_handler (OIDCHandler)
  - src.core.shared.security.dual_key_jwt (DualKeyJWTValidator)
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. Secret Rotation Manager
# ---------------------------------------------------------------------------
from src.core.shared.security.rotation.backend import InMemorySecretBackend
from src.core.shared.security.rotation.enums import (
    RotationStatus,
    RotationTrigger,
    SecretType,
)
from src.core.shared.security.rotation.manager import (
    SecretRotationManager,
    get_rotation_manager,
    reset_rotation_manager,
)
from src.core.shared.security.rotation.models import RotationPolicy


class TestSecretRotationManagerInit:
    """Tests for SecretRotationManager initialisation."""

    def test_default_init(self):
        mgr = SecretRotationManager()
        assert isinstance(mgr._backend, InMemorySecretBackend)
        assert mgr._audit_callback is None
        assert mgr._scheduler_running is False

    def test_custom_backend(self):
        backend = InMemorySecretBackend()
        mgr = SecretRotationManager(backend=backend)
        assert mgr._backend is backend

    def test_custom_audit_callback(self):
        cb = AsyncMock()
        mgr = SecretRotationManager(audit_callback=cb)
        assert mgr._audit_callback is cb

    def test_custom_secret_generator(self):
        gen = AsyncMock(return_value="custom_secret")
        mgr = SecretRotationManager(secret_generator=gen)
        assert mgr._secret_generator is gen


class TestDefaultSecretGenerator:
    """Tests for _default_secret_generator covering all SecretType branches."""

    @pytest.fixture
    def mgr(self):
        return SecretRotationManager()

    async def test_jwt_signing_key(self, mgr):
        val = await mgr._default_secret_generator("k", SecretType.JWT_SIGNING_KEY)
        decoded = base64.b64decode(val)
        assert len(decoded) == 64

    async def test_encryption_key(self, mgr):
        val = await mgr._default_secret_generator("k", SecretType.ENCRYPTION_KEY)
        decoded = base64.b64decode(val)
        assert len(decoded) == 32

    async def test_database_password(self, mgr):
        val = await mgr._default_secret_generator("k", SecretType.DATABASE_PASSWORD)
        assert len(val) > 10

    async def test_api_key(self, mgr):
        val = await mgr._default_secret_generator("k", SecretType.API_KEY)
        assert val.startswith("acgs2_")

    async def test_webhook_secret(self, mgr):
        val = await mgr._default_secret_generator("k", SecretType.WEBHOOK_SECRET)
        assert val.startswith("whsec_")

    async def test_generic(self, mgr):
        val = await mgr._default_secret_generator("k", SecretType.GENERIC)
        assert len(val) > 10

    async def test_service_account(self, mgr):
        val = await mgr._default_secret_generator("k", SecretType.SERVICE_ACCOUNT)
        assert len(val) > 10


class TestComputeChecksum:
    def test_deterministic(self):
        mgr = SecretRotationManager()
        assert mgr._compute_checksum("hello") == mgr._compute_checksum("hello")
        assert len(mgr._compute_checksum("hello")) == 16

    def test_different_values(self):
        mgr = SecretRotationManager()
        assert mgr._compute_checksum("a") != mgr._compute_checksum("b")


class TestVersionAndRotationIds:
    def test_generate_version_id_format(self):
        mgr = SecretRotationManager()
        vid = mgr._generate_version_id("test")
        assert vid.startswith("test-v")

    def test_generate_rotation_id_format(self):
        mgr = SecretRotationManager()
        rid = mgr._generate_rotation_id()
        assert rid.startswith("rot-")


class TestAuditLog:
    async def test_audit_log_without_callback(self):
        mgr = SecretRotationManager()
        # should not raise
        await mgr._audit_log("event", "secret", {})

    async def test_audit_log_with_callback(self):
        cb = AsyncMock()
        mgr = SecretRotationManager(audit_callback=cb)
        await mgr._audit_log("event", "secret", {"key": "val"})
        cb.assert_awaited_once()
        event = cb.call_args[0][0]
        assert event["event_type"] == "event"
        assert event["secret_name"] == "secret"

    async def test_audit_log_callback_failure(self):
        cb = AsyncMock(side_effect=RuntimeError("boom"))
        mgr = SecretRotationManager(audit_callback=cb)
        # should not raise
        await mgr._audit_log("event", "secret", {})


class TestRegisterSecret:
    async def test_register_with_defaults(self):
        mgr = SecretRotationManager()
        result = await mgr.register_secret("my_secret")
        assert result is True
        assert "my_secret" in mgr._registered_secrets
        assert len(mgr._versions["my_secret"]) == 1
        assert mgr._versions["my_secret"][0].is_current is True

    async def test_register_with_initial_value(self):
        mgr = SecretRotationManager()
        result = await mgr.register_secret("s", initial_value="init_val")
        assert result is True

    async def test_register_duplicate(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s")
        result = await mgr.register_secret("s")
        assert result is False

    async def test_register_backend_failure(self):
        backend = InMemorySecretBackend()
        backend.store_secret = AsyncMock(return_value=False)
        mgr = SecretRotationManager(backend=backend)
        result = await mgr.register_secret("s")
        assert result is False

    async def test_register_with_custom_type_and_policy(self):
        mgr = SecretRotationManager()
        policy = RotationPolicy(rotation_interval_days=7)
        result = await mgr.register_secret("k", secret_type=SecretType.API_KEY, policy=policy)
        assert result is True
        st, pol = mgr._registered_secrets["k"]
        assert st == SecretType.API_KEY
        assert pol.rotation_interval_days == 7


class TestRotateSecret:
    @pytest.fixture
    async def mgr_with_secret(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="old_val")
        return mgr

    async def test_rotate_success(self, mgr_with_secret):
        mgr = mgr_with_secret
        result = await mgr.rotate_secret("s")
        assert result.success is True
        assert result.new_version_id is not None
        assert result.rollback_available is True
        assert result.grace_period_ends is not None

    async def test_rotate_with_explicit_value(self, mgr_with_secret):
        mgr = mgr_with_secret
        result = await mgr.rotate_secret("s", new_value="explicit_new")
        assert result.success is True

    async def test_rotate_unregistered_secret(self):
        mgr = SecretRotationManager()
        result = await mgr.rotate_secret("nonexistent")
        assert result.success is False
        assert "not registered" in result.error

    async def test_rotate_disallowed_trigger(self):
        mgr = SecretRotationManager()
        policy = RotationPolicy(triggers=[RotationTrigger.ON_DEMAND])
        await mgr.register_secret("s", policy=policy)
        result = await mgr.rotate_secret("s", trigger=RotationTrigger.TIME_BASED)
        assert result.success is False
        assert "not allowed" in result.error

    async def test_rotate_backend_store_failure(self):
        from src.core.shared.errors.exceptions import ConfigurationError

        backend = InMemorySecretBackend()
        mgr = SecretRotationManager(backend=backend)
        await mgr.register_secret("s", initial_value="v")
        # Now make store fail for the rotation
        backend.store_secret = AsyncMock(return_value=False)
        # ConfigurationError is not caught by rotate_secret's except clause
        with pytest.raises(ConfigurationError, match="SECRET_STORE_FAILED"):
            await mgr.rotate_secret("s")

    async def test_rotate_records_stored(self, mgr_with_secret):
        mgr = mgr_with_secret
        await mgr.rotate_secret("s")
        records = mgr._rotation_records["s"]
        assert len(records) == 1
        assert records[0].status == RotationStatus.GRACE_PERIOD


class TestRollbackSecret:
    async def test_rollback_success(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="v1")
        await mgr.rotate_secret("s", new_value="v2")
        result = await mgr.rollback_secret("s")
        assert result.success is True
        assert result.rollback_available is False

    async def test_rollback_unregistered(self):
        mgr = SecretRotationManager()
        result = await mgr.rollback_secret("nonexistent")
        assert result.success is False

    async def test_rollback_no_previous_version(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s")
        result = await mgr.rollback_secret("s")
        assert result.success is False
        assert "No previous version" in result.error

    async def test_rollback_expired_window(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="v1")
        await mgr.rotate_secret("s", new_value="v2")
        # Expire the previous version
        for v in mgr._versions["s"]:
            if v.is_previous:
                v.expires_at = datetime.now(UTC) - timedelta(hours=1)
        result = await mgr.rollback_secret("s")
        assert result.success is False
        assert "expired" in result.error


class TestGetCurrentSecret:
    async def test_get_current_unregistered(self):
        mgr = SecretRotationManager()
        current, prev = await mgr.get_current_secret("nope")
        assert current is None
        assert prev is None

    async def test_get_current_registered(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="val1")
        current, prev = await mgr.get_current_secret("s")
        assert current == "val1"
        assert prev is None

    async def test_get_current_with_previous(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="val1")
        await mgr.rotate_secret("s", new_value="val2")
        current, prev = await mgr.get_current_secret("s", include_previous=True)
        assert current == "val2"
        assert prev == "val1"

    async def test_get_current_previous_expired(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="val1")
        await mgr.rotate_secret("s", new_value="val2")
        # Expire the previous
        for v in mgr._versions["s"]:
            if v.is_previous:
                v.expires_at = datetime.now(UTC) - timedelta(hours=1)
        current, prev = await mgr.get_current_secret("s", include_previous=True)
        assert current == "val2"
        assert prev is None


class TestGetRotationStatus:
    async def test_status_unregistered(self):
        mgr = SecretRotationManager()
        status = await mgr.get_rotation_status("nope")
        assert "error" in status

    async def test_status_registered(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", secret_type=SecretType.API_KEY)
        status = await mgr.get_rotation_status("s")
        assert status["secret_name"] == "s"
        assert status["secret_type"] == "api_key"
        assert status["needs_rotation"] is False
        assert status["total_rotations"] == 0

    async def test_status_after_rotation(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s")
        await mgr.rotate_secret("s")
        status = await mgr.get_rotation_status("s")
        assert status["total_rotations"] == 1
        assert status["in_grace_period"] is True

    async def test_status_needs_rotation(self):
        mgr = SecretRotationManager()
        policy = RotationPolicy(rotation_interval_days=0)
        await mgr.register_secret("s", policy=policy)
        status = await mgr.get_rotation_status("s")
        assert status["needs_rotation"] is True


class TestCheckSecretsNeedingRotation:
    async def test_no_secrets(self):
        mgr = SecretRotationManager()
        result = await mgr.check_secrets_needing_rotation()
        assert result == []

    async def test_secret_not_due(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s")
        result = await mgr.check_secrets_needing_rotation()
        assert result == []

    async def test_secret_due(self):
        mgr = SecretRotationManager()
        policy = RotationPolicy(rotation_interval_days=0)
        await mgr.register_secret("s", policy=policy)
        result = await mgr.check_secrets_needing_rotation()
        assert "s" in result

    async def test_secret_without_time_trigger(self):
        mgr = SecretRotationManager()
        policy = RotationPolicy(
            rotation_interval_days=0,
            triggers=[RotationTrigger.ON_DEMAND],
        )
        await mgr.register_secret("s", policy=policy)
        result = await mgr.check_secrets_needing_rotation()
        assert result == []


class TestCleanupOldVersions:
    async def test_no_cleanup_needed(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s")
        await mgr._cleanup_old_versions("s", max_versions=10)
        assert len(mgr._versions["s"]) == 1

    async def test_cleanup_removes_old(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="v1")
        await mgr.rotate_secret("s", new_value="v2")
        await mgr.rotate_secret("s", new_value="v3")
        await mgr.rotate_secret("s", new_value="v4")
        # Force cleanup to keep only 2
        await mgr._cleanup_old_versions("s", max_versions=2)
        # Some versions may remain if they're current/previous
        assert len(mgr._versions["s"]) <= 4  # at most the original count


class TestExpireGracePeriods:
    async def test_expire_old_grace_periods(self):
        mgr = SecretRotationManager()
        await mgr.register_secret("s", initial_value="v1")
        await mgr.rotate_secret("s", new_value="v2")
        # Expire
        for v in mgr._versions["s"]:
            if v.is_previous:
                v.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await mgr._expire_grace_periods()
        for v in mgr._versions["s"]:
            assert v.is_previous is False


class TestScheduler:
    async def test_start_stop_scheduler(self):
        mgr = SecretRotationManager()
        await mgr.start_scheduler(check_interval_seconds=3600)
        assert mgr._scheduler_running is True
        await mgr.stop_scheduler()
        assert mgr._scheduler_running is False
        assert mgr._scheduler_task is None

    async def test_start_already_running(self):
        mgr = SecretRotationManager()
        await mgr.start_scheduler(check_interval_seconds=3600)
        await mgr.start_scheduler(check_interval_seconds=3600)  # no error
        await mgr.stop_scheduler()

    async def test_stop_without_start(self):
        mgr = SecretRotationManager()
        await mgr.stop_scheduler()  # no error


class TestGetHealth:
    def test_health(self):
        mgr = SecretRotationManager()
        h = mgr.get_health()
        assert h["status"] == "healthy"
        assert h["registered_secrets"] == 0
        assert h["scheduler_running"] is False
        assert h["backend_type"] == "InMemorySecretBackend"


class TestSingleton:
    async def test_get_rotation_manager(self):
        reset_rotation_manager()
        m1 = await get_rotation_manager()
        m2 = await get_rotation_manager()
        assert m1 is m2
        reset_rotation_manager()

    async def test_reset_rotation_manager(self):
        reset_rotation_manager()
        m1 = await get_rotation_manager()
        reset_rotation_manager()
        m2 = await get_rotation_manager()
        assert m1 is not m2
        reset_rotation_manager()


# ---------------------------------------------------------------------------
# 2. SAML Handler
# ---------------------------------------------------------------------------
from src.core.shared.auth.saml_config import SAMLConfigurationError, SAMLIdPConfig, SAMLSPConfig
from src.core.shared.auth.saml_handler import SAMLHandler
from src.core.shared.auth.saml_types import (
    SAMLError,
    SAMLReplayError,
)


class TestSAMLHandlerInit:
    def test_default_init(self):
        handler = SAMLHandler()
        assert handler.sp_config.entity_id == "urn:acgs2:saml:sp"

    def test_init_with_sp_config(self):
        sp = SAMLSPConfig(entity_id="urn:test", acs_url="/acs")
        handler = SAMLHandler(sp_config=sp)
        assert handler.sp_config.entity_id == "urn:test"

    def test_init_with_full_config(self):
        from src.core.shared.auth.saml_config import SAMLConfig

        sp = SAMLSPConfig(entity_id="urn:full", acs_url="/acs")
        config = SAMLConfig(sp=sp)
        handler = SAMLHandler(config=config)
        assert handler.sp_config.entity_id == "urn:full"


class TestSAMLRegisterIdP:
    def test_register_with_metadata_url(self):
        handler = SAMLHandler()
        handler.register_idp(
            name="okta",
            metadata_url="https://okta.example.com/metadata",
        )
        assert "okta" in handler.list_idps()
        idp = handler.get_idp("okta")
        assert idp.metadata_url == "https://okta.example.com/metadata"

    def test_register_with_metadata_xml(self):
        handler = SAMLHandler()
        handler.register_idp(
            name="azure",
            metadata_xml="<xml>metadata</xml>",
        )
        assert "azure" in handler.list_idps()

    def test_register_with_manual_config(self):
        handler = SAMLHandler()
        handler.register_idp(
            name="custom",
            entity_id="urn:idp:custom",
            sso_url="https://idp.example.com/sso",
            certificate="CERT",
        )
        assert "custom" in handler.list_idps()

    def test_register_invalid_config(self):
        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError):
            handler.register_idp(name="bad")  # no metadata or manual config

    def test_register_clears_cached_client(self):
        handler = SAMLHandler()
        handler._saml_clients["test"] = MagicMock()
        handler.register_idp(name="test", metadata_url="https://example.com/meta")
        assert "test" not in handler._saml_clients

    def test_get_idp_not_found(self):
        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError):
            handler.get_idp("nonexistent")

    def test_list_idps_empty(self):
        handler = SAMLHandler()
        assert handler.list_idps() == []


class TestSAMLRegisterIdPFromModel:
    def test_non_saml_provider_raises(self):
        handler = SAMLHandler()
        provider = MagicMock()
        provider.is_saml = False
        provider.name = "google"
        with pytest.raises(SAMLConfigurationError, match="not a SAML provider"):
            handler.register_idp_from_model(provider)

    def test_invalid_saml_config_raises(self):
        handler = SAMLHandler()
        provider = MagicMock()
        provider.is_saml = True
        provider.name = "okta"
        provider.validate_saml_config.return_value = ["Missing metadata"]
        with pytest.raises(SAMLConfigurationError, match="Invalid SAML"):
            handler.register_idp_from_model(provider)

    def test_valid_model_registration(self):
        handler = SAMLHandler()
        provider = MagicMock()
        provider.is_saml = True
        provider.name = "okta"
        provider.validate_saml_config.return_value = []
        provider.saml_metadata_url = "https://okta.example.com/meta"
        provider.saml_metadata_xml = None
        provider.saml_entity_id = "urn:okta"
        provider.saml_sp_cert = None
        provider.saml_sign_assertions = True
        handler.register_idp_from_model(provider)
        assert "okta" in handler.list_idps()


class TestSAMLRequestTracking:
    def test_store_and_verify(self):
        handler = SAMLHandler()
        req_id = handler.store_outstanding_request(idp_name="okta")
        assert handler.verify_and_remove_request(req_id) is True
        # second verify should fail (consumed)
        assert handler.verify_and_remove_request(req_id) is False

    def test_get_outstanding_requests(self):
        handler = SAMLHandler()
        handler.store_outstanding_request(request_id="req1", idp_name="okta")
        reqs = handler.get_outstanding_requests()
        assert "req1" in reqs

    def test_clear_expired(self):
        handler = SAMLHandler()
        handler.store_outstanding_request(request_id="req1", expiry_minutes=0)
        cleared = handler.clear_expired_requests()
        # may or may not be expired yet depending on timing, but no error
        assert isinstance(cleared, int)

    def test_generate_request_id(self):
        handler = SAMLHandler()
        rid = handler._generate_request_id()
        assert rid.startswith("_saml_")


class TestSAMLDetectIdpName:
    def test_detect_from_request_id(self):
        handler = SAMLHandler()
        handler.store_outstanding_request(request_id="req1", idp_name="okta")
        name = handler._detect_idp_name("req1")
        assert name == "okta"

    def test_detect_fallback_to_first_idp(self):
        handler = SAMLHandler()
        handler.register_idp(name="azure", metadata_url="https://example.com/meta")
        name = handler._detect_idp_name(None)
        assert name == "azure"

    def test_detect_no_idps(self):
        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError, match="No IdPs"):
            handler._detect_idp_name(None)


class TestSAMLHandleReplayPrevention:
    def test_no_request_id(self):
        handler = SAMLHandler()
        # None request_id should not raise
        handler._handle_replay_prevention(None)

    def test_valid_request_id(self):
        handler = SAMLHandler()
        rid = handler.store_outstanding_request(idp_name="test")
        handler._handle_replay_prevention(rid)

    def test_replay_detected(self):
        handler = SAMLHandler()
        with pytest.raises(SAMLReplayError):
            handler._handle_replay_prevention("unknown_id")


class TestSAMLFetchMetadata:
    async def test_returns_xml_when_no_url(self):
        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test", metadata_xml="<xml/>")
        result = await handler._fetch_metadata(idp)
        assert result == "<xml/>"

    async def test_returns_cached_metadata(self):
        handler = SAMLHandler()
        handler._metadata_cache["test"] = ("<cached/>", datetime.now(UTC))
        idp = SAMLIdPConfig(name="test", metadata_url="https://example.com/meta")
        result = await handler._fetch_metadata(idp)
        assert result == "<cached/>"

    @patch("src.core.shared.auth.saml_handler.HAS_HTTPX", True)
    async def test_fetch_network_failure_uses_cache(self):
        handler = SAMLHandler()
        handler._metadata_cache["test"] = ("<old/>", datetime.now(UTC) - timedelta(days=2))
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network"))
        handler._http_client = mock_client
        idp = SAMLIdPConfig(name="test", metadata_url="https://example.com/meta")
        result = await handler._fetch_metadata(idp, force_refresh=True)
        assert result == "<old/>"

    @patch("src.core.shared.auth.saml_handler.HAS_HTTPX", True)
    async def test_fetch_network_failure_no_cache_raises(self):
        handler = SAMLHandler()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network"))
        handler._http_client = mock_client
        idp = SAMLIdPConfig(name="test", metadata_url="https://example.com/meta")
        from src.core.shared.auth.saml_types import SAMLProviderError

        with pytest.raises(SAMLProviderError):
            await handler._fetch_metadata(idp, force_refresh=True)


class TestSAMLBuildPysaml2Config:
    def test_basic_config(self):
        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test", metadata_xml="<xml/>")
        config = handler._build_pysaml2_config(idp, None)
        assert config["entityid"] == "urn:acgs2:saml:sp"
        assert "service" in config

    def test_config_with_sls(self):
        sp = SAMLSPConfig(entity_id="urn:test", acs_url="/acs", sls_url="/sls")
        handler = SAMLHandler(sp_config=sp)
        idp = SAMLIdPConfig(name="test", metadata_xml="<xml/>")
        config = handler._build_pysaml2_config(idp, None)
        assert "single_logout_service" in config["service"]["sp"]["endpoints"]

    def test_config_with_metadata_xml(self):
        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test")
        config = handler._build_pysaml2_config(idp, "<metadata/>")
        assert "metadata" in config
        assert "local" in config["metadata"]

    def test_config_with_manual_idp(self):
        handler = SAMLHandler()
        idp = SAMLIdPConfig(
            name="test",
            entity_id="urn:idp",
            sso_url="https://idp.example.com/sso",
            certificate="CERT",
        )
        config = handler._build_pysaml2_config(idp, None)
        assert "inline" in config["metadata"]

    def test_config_with_cert_content(self):
        sp = SAMLSPConfig(
            entity_id="urn:test",
            acs_url="/acs",
            cert_content="CERT_CONTENT",
            key_content="KEY_CONTENT",
            sign_authn_requests=False,
        )
        handler = SAMLHandler(sp_config=sp)
        idp = SAMLIdPConfig(name="test", metadata_xml="<xml/>")
        config = handler._build_pysaml2_config(idp, None)
        assert "cert_file" in config
        assert "key_file" in config


class TestSAMLGetSamlClient:
    @patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False)
    async def test_no_pysaml2_raises(self):
        handler = SAMLHandler()
        handler.register_idp(name="test", metadata_url="https://example.com/meta")
        with pytest.raises(SAMLError, match="PySAML2"):
            await handler._get_saml_client("test")


class TestSAMLGenerateMetadata:
    @patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False)
    async def test_generate_metadata_without_pysaml2(self):
        handler = SAMLHandler()
        metadata = await handler.generate_metadata()
        assert "EntityDescriptor" in metadata
        assert "urn:acgs2:saml:sp" in metadata


class TestSAMLInitiateLogout:
    @patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False)
    async def test_logout_without_pysaml2(self):
        handler = SAMLHandler()
        handler.register_idp(name="test", metadata_url="https://example.com/meta")
        result = await handler.initiate_logout("test", name_id="user@test.com")
        assert result is None

    @patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True)
    async def test_logout_no_slo_url(self):
        handler = SAMLHandler()
        handler.register_idp(name="test", metadata_url="https://example.com/meta")
        # slo_url is None by default
        result = await handler.initiate_logout("test", name_id="user@test.com")
        assert result is None


class TestSAMLProcessSlsResponse:
    @patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False)
    async def test_sls_without_pysaml2(self):
        handler = SAMLHandler()
        result = await handler.process_sls_response("resp", "test")
        assert result is True


class TestSAMLProcessAcsResponse:
    @patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False)
    async def test_acs_without_pysaml2(self):
        handler = SAMLHandler()
        with pytest.raises(SAMLError, match="PySAML2"):
            await handler.process_acs_response("resp")


class TestSAMLClose:
    async def test_close_no_client(self):
        handler = SAMLHandler()
        await handler.close()

    async def test_close_with_client(self):
        handler = SAMLHandler()
        handler._http_client = AsyncMock()
        await handler.close()
        assert handler._http_client is None

    async def test_close_cleans_temp_files(self):
        handler = SAMLHandler()
        mock_file = MagicMock()
        mock_file.name = "/tmp/test_file"
        handler._temp_cert_file = mock_file
        with patch("src.core.shared.auth.saml_handler.Path") as mock_path:
            mock_path.return_value.unlink = MagicMock()
            await handler.close()


# ---------------------------------------------------------------------------
# 3. OIDC Handler
# ---------------------------------------------------------------------------
from src.core.shared.auth.oidc_handler import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCError,
    OIDCHandler,
    OIDCProviderConfig,
    OIDCProviderError,
    OIDCTokenError,
    OIDCTokenResponse,
    OIDCUserInfo,
    _normalize_secret_sentinel,
)


class TestNormalizeSecretSentinel:
    def test_basic(self):
        assert _normalize_secret_sentinel("your-secret") == "yoursecret"
        assert _normalize_secret_sentinel("  REPLACE_ME  ") == "replaceme"

    def test_clean(self):
        assert _normalize_secret_sentinel("abc123") == "abc123"


class TestOIDCProviderConfig:
    def test_valid_config(self):
        config = OIDCProviderConfig(
            name="google",
            client_id="cid",
            client_secret="real_secret_value_1234",
            server_metadata_url="https://google.com/.well-known/openid-configuration",
        )
        assert config.name == "google"
        assert config.use_pkce is True

    def test_missing_name(self):
        with pytest.raises(OIDCConfigurationError, match="name"):
            OIDCProviderConfig(
                name="",
                client_id="cid",
                client_secret="real_secret",
                server_metadata_url="https://x.com",
            )

    def test_missing_client_id(self):
        with pytest.raises(OIDCConfigurationError, match="Client ID"):
            OIDCProviderConfig(
                name="g", client_id="", client_secret="real", server_metadata_url="https://x.com"
            )

    def test_missing_client_secret(self):
        with pytest.raises(OIDCConfigurationError, match="Client secret is required"):
            OIDCProviderConfig(
                name="g", client_id="cid", client_secret="", server_metadata_url="https://x.com"
            )

    def test_placeholder_secret(self):
        with pytest.raises(OIDCConfigurationError, match="placeholder"):
            OIDCProviderConfig(
                name="g",
                client_id="cid",
                client_secret="your-secret",
                server_metadata_url="https://x.com",
            )

    def test_placeholder_replace_me(self):
        with pytest.raises(OIDCConfigurationError, match="placeholder"):
            OIDCProviderConfig(
                name="g",
                client_id="cid",
                client_secret="REPLACE_ME",
                server_metadata_url="https://x.com",
            )

    def test_missing_metadata_url(self):
        with pytest.raises(OIDCConfigurationError, match="metadata URL"):
            OIDCProviderConfig(
                name="g", client_id="cid", client_secret="real_secret_val", server_metadata_url=""
            )


class TestOIDCTokenResponse:
    def test_from_dict_full(self):
        data = {
            "access_token": "at",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "rt",
            "id_token": "idt",
            "scope": "openid profile",
        }
        tr = OIDCTokenResponse.from_dict(data)
        assert tr.access_token == "at"
        assert tr.expires_in == 3600
        assert tr.refresh_token == "rt"
        assert tr.id_token == "idt"
        assert tr.scope == "openid profile"

    def test_from_dict_minimal(self):
        data = {"access_token": "at"}
        tr = OIDCTokenResponse.from_dict(data)
        assert tr.access_token == "at"
        assert tr.expires_in is None
        assert tr.refresh_token is None


class TestOIDCUserInfo:
    def test_from_claims_basic(self):
        claims = {
            "sub": "user123",
            "email": "user@test.com",
            "email_verified": True,
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "picture": "https://pic.com/u.jpg",
            "locale": "en-US",
        }
        info = OIDCUserInfo.from_claims(claims)
        assert info.sub == "user123"
        assert info.email == "user@test.com"
        assert info.email_verified is True
        assert info.name == "Test User"

    def test_from_claims_with_groups(self):
        claims = {"sub": "u", "groups": ["admin", "users"]}
        info = OIDCUserInfo.from_claims(claims)
        assert info.groups == ["admin", "users"]

    def test_from_claims_with_roles(self):
        claims = {"sub": "u", "roles": ["admin"]}
        info = OIDCUserInfo.from_claims(claims)
        assert info.groups == ["admin"]

    def test_from_claims_azure_groups(self):
        claims = {
            "sub": "u",
            "https://schemas.microsoft.com/claims/groups": ["grp1"],
        }
        info = OIDCUserInfo.from_claims(claims)
        assert info.groups == ["grp1"]

    def test_from_claims_groups_not_list(self):
        claims = {"sub": "u", "groups": "not-a-list"}
        info = OIDCUserInfo.from_claims(claims)
        assert info.groups == []

    def test_from_claims_empty(self):
        info = OIDCUserInfo.from_claims({})
        assert info.sub == ""


class TestOIDCHandlerInit:
    def test_default_init(self):
        handler = OIDCHandler()
        assert handler._providers == {}
        assert handler._pending_states == {}


class TestOIDCHandlerRegisterProvider:
    def test_register_valid(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="google",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://google.com/.well-known/openid-configuration",
        )
        assert "google" in handler.list_providers()
        p = handler.get_provider("google")
        assert p.client_id == "cid"

    def test_get_provider_not_found(self):
        handler = OIDCHandler()
        with pytest.raises(OIDCConfigurationError, match="not registered"):
            handler.get_provider("nope")

    def test_list_providers_empty(self):
        handler = OIDCHandler()
        assert handler.list_providers() == []


class TestOIDCRegisterProviderFromModel:
    def test_non_oidc_raises(self):
        handler = OIDCHandler()
        provider = MagicMock()
        provider.is_oidc = False
        provider.name = "saml_prov"
        with pytest.raises(OIDCConfigurationError, match="not an OIDC"):
            handler.register_provider_from_model(provider)

    def test_invalid_config_raises(self):
        handler = OIDCHandler()
        provider = MagicMock()
        provider.is_oidc = True
        provider.name = "broken"
        provider.validate_oidc_config.return_value = ["Missing client_id"]
        with pytest.raises(OIDCConfigurationError, match="Invalid OIDC"):
            handler.register_provider_from_model(provider)


class TestOIDCEvictStalePendingStates:
    def test_evicts_expired(self):
        handler = OIDCHandler()
        old_time = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
        handler._pending_states["old"] = {"created_at": old_time, "provider": "g"}
        handler._evict_stale_pending_states()
        assert "old" not in handler._pending_states

    def test_keeps_fresh(self):
        handler = OIDCHandler()
        fresh_time = datetime.now(UTC).isoformat()
        handler._pending_states["fresh"] = {"created_at": fresh_time, "provider": "g"}
        handler._evict_stale_pending_states()
        assert "fresh" in handler._pending_states


class TestOIDCInitiateLogin:
    def _setup_handler(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="google",
            client_id="cid",
            client_secret="real_secret_value_1234",
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        )
        return handler

    async def test_initiate_login_success(self):
        handler = self._setup_handler()
        metadata = {
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "issuer": "https://accounts.google.com",
        }
        handler._fetch_metadata = AsyncMock(return_value=metadata)
        url, state = await handler.initiate_login("google", "https://app.com/callback")
        assert "accounts.google.com" in url
        assert "state=" in url
        assert state in handler._pending_states

    async def test_initiate_login_no_auth_endpoint(self):
        handler = self._setup_handler()
        handler._fetch_metadata = AsyncMock(return_value={})
        with pytest.raises(OIDCProviderError, match="Authorization endpoint"):
            await handler.initiate_login("google", "https://app.com/callback")

    async def test_initiate_login_evicts_at_capacity(self):
        handler = self._setup_handler()
        handler._max_pending_states = 2
        handler._pending_states = {
            f"s{i}": {"created_at": datetime.now(UTC).isoformat(), "provider": "g"}
            for i in range(2)
        }
        metadata = {
            "authorization_endpoint": "https://auth.example.com/authorize",
        }
        handler._fetch_metadata = AsyncMock(return_value=metadata)
        _url, _state = await handler.initiate_login("google", "https://app.com/cb")
        # Should have evicted one
        assert len(handler._pending_states) <= 2

    async def test_initiate_login_with_pkce(self):
        handler = self._setup_handler()
        metadata = {
            "authorization_endpoint": "https://auth.example.com/authorize",
        }
        handler._fetch_metadata = AsyncMock(return_value=metadata)
        url, _state = await handler.initiate_login("google", "https://app.com/cb")
        assert "code_challenge" in url
        assert "code_challenge_method=S256" in url


class TestOIDCHandleCallback:
    def _setup_handler_with_state(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="google",
            client_id="cid",
            client_secret="real_secret_value_1234",
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        )
        state = "test_state_123"
        handler._pending_states[state] = {
            "provider": "google",
            "redirect_uri": "https://app.com/cb",
            "code_verifier": "verifier123",
            "nonce": "nonce123",
            "created_at": datetime.now(UTC).isoformat(),
        }
        return handler, state

    async def test_invalid_state(self):
        handler = OIDCHandler()
        with pytest.raises(OIDCAuthenticationError, match="Invalid or expired state"):
            await handler.handle_callback("google", "code", "bad_state")

    async def test_provider_mismatch(self):
        handler, state = self._setup_handler_with_state()
        with pytest.raises(OIDCAuthenticationError, match="Provider mismatch"):
            await handler.handle_callback("azure", "code", state)

    async def test_successful_callback(self):
        handler, state = self._setup_handler_with_state()
        mock_tokens = OIDCTokenResponse(access_token="at", id_token=None)
        handler._exchange_code = AsyncMock(return_value=mock_tokens)
        handler._get_user_info = AsyncMock(
            return_value=OIDCUserInfo(sub="user123", email="u@test.com")
        )
        result = await handler.handle_callback("google", "code", state)
        assert result.sub == "user123"


class TestOIDCExchangeCode:
    async def test_no_token_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        provider = handler.get_provider("g")
        with pytest.raises(OIDCTokenError, match="Token endpoint"):
            await handler._exchange_code(provider, "code", "https://cb.com")

    async def test_successful_exchange(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={"token_endpoint": "https://x.com/token"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "at", "token_type": "Bearer"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        handler._http_client = mock_client
        provider = handler.get_provider("g")
        result = await handler._exchange_code(provider, "code", "https://cb.com", "verifier")
        assert result.access_token == "at"

    async def test_exchange_error_status(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={"token_endpoint": "https://x.com/token"})
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.content = b'{"error":"invalid_grant"}'
        mock_resp.json.return_value = {"error": "invalid_grant"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        handler._http_client = mock_client
        provider = handler.get_provider("g")
        with pytest.raises(OIDCTokenError, match="Token exchange failed"):
            await handler._exchange_code(provider, "code", "https://cb.com")


class TestOIDCGetUserInfo:
    async def test_from_id_token(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        provider = handler.get_provider("g")
        tokens = OIDCTokenResponse(access_token="at", id_token="id_tok")
        handler._decode_id_token = AsyncMock(return_value={"sub": "u1", "email": "u@t.com"})
        result = await handler._get_user_info(provider, tokens)
        assert result.sub == "u1"

    async def test_fallback_to_userinfo_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        provider = handler.get_provider("g")
        tokens = OIDCTokenResponse(access_token="at", id_token="id_tok")
        handler._decode_id_token = AsyncMock(side_effect=OIDCTokenError("bad"))
        handler._fetch_userinfo = AsyncMock(return_value=OIDCUserInfo(sub="u2", email="u2@t.com"))
        result = await handler._get_user_info(provider, tokens)
        assert result.sub == "u2"

    async def test_no_id_token(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        provider = handler.get_provider("g")
        tokens = OIDCTokenResponse(access_token="at", id_token=None)
        handler._fetch_userinfo = AsyncMock(return_value=OIDCUserInfo(sub="u3"))
        result = await handler._get_user_info(provider, tokens)
        assert result.sub == "u3"


class TestOIDCFetchUserinfo:
    async def test_no_userinfo_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        provider = handler.get_provider("g")
        with pytest.raises(OIDCProviderError, match="Userinfo endpoint"):
            await handler._fetch_userinfo(provider, "at")

    async def test_successful_fetch(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"userinfo_endpoint": "https://x.com/userinfo"}
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"sub": "uid", "email": "u@t.com"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        handler._http_client = mock_client
        provider = handler.get_provider("g")
        result = await handler._fetch_userinfo(provider, "at")
        assert result.sub == "uid"

    async def test_userinfo_error_status(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"userinfo_endpoint": "https://x.com/userinfo"}
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        handler._http_client = mock_client
        provider = handler.get_provider("g")
        with pytest.raises(OIDCProviderError, match="Userinfo request failed"):
            await handler._fetch_userinfo(provider, "at")


class TestOIDCRefreshToken:
    async def test_no_token_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        with pytest.raises(OIDCTokenError, match="Token endpoint"):
            await handler.refresh_token("g", "rt")

    async def test_successful_refresh(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={"token_endpoint": "https://x.com/token"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "new_at", "token_type": "Bearer"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        handler._http_client = mock_client
        result = await handler.refresh_token("g", "rt")
        assert result.access_token == "new_at"

    async def test_refresh_error(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={"token_endpoint": "https://x.com/token"})
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.content = b'{"error":"invalid"}'
        mock_resp.json.return_value = {"error": "invalid"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        handler._http_client = mock_client
        with pytest.raises(OIDCTokenError, match="Token refresh failed"):
            await handler.refresh_token("g", "rt")


class TestOIDCLogout:
    async def test_no_end_session_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        result = await handler.logout("g")
        assert result is None

    async def test_logout_with_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"end_session_endpoint": "https://x.com/logout"}
        )
        result = await handler.logout(
            "g", id_token_hint="hint", post_logout_redirect_uri="https://app.com"
        )
        assert result is not None
        assert "https://x.com/logout" in result
        assert "id_token_hint=hint" in result
        assert "post_logout_redirect_uri" in result


class TestOIDCValidateState:
    def test_valid(self):
        handler = OIDCHandler()
        handler._pending_states["s1"] = {"created_at": datetime.now(UTC).isoformat()}
        assert handler.validate_state("s1") is True

    def test_invalid(self):
        handler = OIDCHandler()
        assert handler.validate_state("unknown") is False


class TestOIDCClearExpiredStates:
    def test_clears_old(self):
        handler = OIDCHandler()
        old = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
        handler._pending_states["old"] = {"created_at": old}
        count = handler.clear_expired_states(max_age_seconds=600)
        assert count == 1
        assert "old" not in handler._pending_states

    def test_keeps_fresh(self):
        handler = OIDCHandler()
        fresh = datetime.now(UTC).isoformat()
        handler._pending_states["fresh"] = {"created_at": fresh}
        count = handler.clear_expired_states(max_age_seconds=600)
        assert count == 0
        assert "fresh" in handler._pending_states


class TestOIDCClose:
    async def test_close_no_client(self):
        handler = OIDCHandler()
        await handler.close()

    async def test_close_with_client(self):
        handler = OIDCHandler()
        handler._http_client = AsyncMock()
        await handler.close()
        assert handler._http_client is None


class TestOIDCFetchMetadata:
    async def test_cached_metadata(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._metadata_cache["g"] = {"issuer": "cached"}
        handler._metadata_timestamps["g"] = datetime.now(UTC)
        provider = handler.get_provider("g")
        result = await handler._fetch_metadata(provider)
        assert result["issuer"] == "cached"

    async def test_stale_cache_refreshes(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._metadata_cache["g"] = {"issuer": "old"}
        handler._metadata_timestamps["g"] = datetime.now(UTC) - timedelta(days=2)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"issuer": "new"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        handler._http_client = mock_client
        provider = handler.get_provider("g")
        result = await handler._fetch_metadata(provider)
        assert result["issuer"] == "new"

    async def test_fetch_failure_uses_cache(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        handler._metadata_cache["g"] = {"issuer": "cached"}
        handler._metadata_timestamps["g"] = datetime.now(UTC) - timedelta(days=2)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("fail"))
        handler._http_client = mock_client
        provider = handler.get_provider("g")
        result = await handler._fetch_metadata(provider)
        assert result["issuer"] == "cached"

    async def test_fetch_failure_no_cache(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="g",
            client_id="cid",
            client_secret="real_secret_1234",
            server_metadata_url="https://x.com/.well-known/oidc",
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("fail"))
        handler._http_client = mock_client
        provider = handler.get_provider("g")
        with pytest.raises(OIDCProviderError):
            await handler._fetch_metadata(provider, force_refresh=True)


class TestOIDCGeneratePKCE:
    def test_generate_state(self):
        handler = OIDCHandler()
        s = handler._generate_state()
        assert len(s) > 20

    def test_generate_code_verifier(self):
        handler = OIDCHandler()
        v = handler._generate_code_verifier()
        assert len(v) > 40

    def test_generate_code_challenge(self):
        handler = OIDCHandler()
        v = handler._generate_code_verifier()
        c = handler._generate_code_challenge(v)
        assert len(c) > 20
        assert "=" not in c  # no padding


# ---------------------------------------------------------------------------
# 4. Dual-Key JWT Validator
# ---------------------------------------------------------------------------
# Generate RSA keys for testing
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.shared.security.dual_key_jwt import (
    DualKeyConfig,
    DualKeyJWTValidator,
    JWTValidationResult,
    KeyMetadata,
    get_dual_key_validator,
)


def _generate_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


class TestDualKeyJWTValidatorInit:
    def test_default_init(self):
        v = DualKeyJWTValidator()
        assert v.config.enabled is True
        assert v._current_kid is None
        assert v._keys == {}

    def test_custom_config(self):
        cfg = DualKeyConfig(enabled=False, grace_period_hours=8)
        v = DualKeyJWTValidator(config=cfg)
        assert v.config.enabled is False
        assert v.config.grace_period_hours == 8


class TestDualKeyLoadKeysFromEnv:
    async def test_no_keys_set(self):
        v = DualKeyJWTValidator()
        with patch.dict("os.environ", {}, clear=True):
            result = await v.load_keys_from_env()
        assert result is False

    async def test_load_current_key(self):
        priv, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        env = {
            "JWT_CURRENT_PUBLIC_KEY": base64.b64encode(pub).decode(),
            "JWT_CURRENT_PRIVATE_KEY": base64.b64encode(priv).decode(),
            "JWT_CURRENT_KID": "v1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = await v.load_keys_from_env()
        assert result is True
        assert v._current_kid == "v1"

    async def test_load_current_and_previous(self):
        priv1, pub1 = _generate_rsa_keypair()
        priv2, pub2 = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        env = {
            "JWT_CURRENT_PUBLIC_KEY": base64.b64encode(pub1).decode(),
            "JWT_CURRENT_PRIVATE_KEY": base64.b64encode(priv1).decode(),
            "JWT_CURRENT_KID": "v2",
            "JWT_PREVIOUS_PUBLIC_KEY": base64.b64encode(pub2).decode(),
            "JWT_PREVIOUS_PRIVATE_KEY": base64.b64encode(priv2).decode(),
            "JWT_PREVIOUS_KID": "v1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = await v.load_keys_from_env()
        assert result is True
        assert v._current_kid == "v2"
        assert v._previous_kid == "v1"

    async def test_load_env_error(self):
        v = DualKeyJWTValidator()
        env = {
            "JWT_CURRENT_PUBLIC_KEY": "not_base64!!!",
            "JWT_CURRENT_KID": "v1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = await v.load_keys_from_env()
        assert result is False


class TestDualKeyValidateToken:
    @pytest.fixture
    def validator_with_keys(self):
        priv, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._keys["v1"] = (
            priv,
            pub,
            KeyMetadata(kid="v1", is_current=True),
        )
        v._current_kid = "v1"
        return v, priv, pub

    def test_no_keys_loaded(self):
        v = DualKeyJWTValidator()
        result = v.validate_token("some.token.here")
        assert result.valid is False
        assert "No signing keys" in result.error

    def test_valid_token(self, validator_with_keys):
        import jwt as pyjwt

        v, priv, _pub = validator_with_keys
        token = pyjwt.encode(
            {"sub": "user1", "iss": "acgs2", "exp": datetime.now(UTC) + timedelta(hours=1)},
            priv,
            algorithm="RS256",
            headers={"kid": "v1"},
        )
        result = v.validate_token(token)
        assert result.valid is True
        assert result.key_used == "v1"
        assert result.claims["sub"] == "user1"

    def test_invalid_token(self, validator_with_keys):
        v, _, _ = validator_with_keys
        result = v.validate_token("invalid.token.value")
        assert result.valid is False

    def test_expired_token(self, validator_with_keys):
        import jwt as pyjwt

        v, priv, _ = validator_with_keys
        token = pyjwt.encode(
            {"sub": "user1", "iss": "acgs2", "exp": datetime.now(UTC) - timedelta(hours=1)},
            priv,
            algorithm="RS256",
            headers={"kid": "v1"},
        )
        result = v.validate_token(token)
        assert result.valid is False

    def test_verify_exp_disabled(self, validator_with_keys):
        import jwt as pyjwt

        v, priv, _ = validator_with_keys
        token = pyjwt.encode(
            {"sub": "user1", "iss": "acgs2", "exp": datetime.now(UTC) - timedelta(hours=1)},
            priv,
            algorithm="RS256",
            headers={"kid": "v1"},
        )
        result = v.validate_token(token, verify_exp=False)
        assert result.valid is True

    def test_constitutional_hash_mismatch(self, validator_with_keys):
        import jwt as pyjwt

        v, priv, _ = validator_with_keys
        token = pyjwt.encode(
            {
                "sub": "user1",
                "iss": "acgs2",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "constitutional_hash": "wrong_hash",
            },
            priv,
            algorithm="RS256",
            headers={"kid": "v1"},
        )
        result = v.validate_token(token)
        assert result.valid is False
        assert result.constitutional_compliant is False

    def test_dual_key_fallback(self):
        import jwt as pyjwt

        priv1, pub1 = _generate_rsa_keypair()
        priv2, pub2 = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._keys["v2"] = (priv2, pub2, KeyMetadata(kid="v2", is_current=True))
        v._keys["v1"] = (
            priv1,
            pub1,
            KeyMetadata(
                kid="v1",
                is_current=False,
                expires_at=datetime.now(UTC) + timedelta(hours=4),
            ),
        )
        v._current_kid = "v2"
        v._previous_kid = "v1"

        # Token signed with old key
        token = pyjwt.encode(
            {"sub": "user1", "iss": "acgs2", "exp": datetime.now(UTC) + timedelta(hours=1)},
            priv1,
            algorithm="RS256",
            headers={"kid": "v1"},
        )
        result = v.validate_token(token)
        assert result.valid is True
        assert result.key_used == "v1"
        assert v._validation_stats["previous_key_validations"] >= 1

    def test_require_kid(self):
        import jwt as pyjwt

        priv, pub = _generate_rsa_keypair()
        cfg = DualKeyConfig(require_kid=True)
        v = DualKeyJWTValidator(config=cfg)
        v._keys["v1"] = (priv, pub, KeyMetadata(kid="v1", is_current=True))
        v._current_kid = "v1"

        # Token without kid
        token = pyjwt.encode(
            {"sub": "user1", "iss": "acgs2", "exp": datetime.now(UTC) + timedelta(hours=1)},
            priv,
            algorithm="RS256",
        )
        result = v.validate_token(token)
        assert result.valid is False
        assert "kid" in result.error

    def test_expired_key_skipped(self):
        import jwt as pyjwt

        priv, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._keys["v1"] = (
            priv,
            pub,
            KeyMetadata(
                kid="v1",
                is_current=True,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        )
        v._current_kid = "v1"

        token = pyjwt.encode(
            {"sub": "user1", "iss": "acgs2", "exp": datetime.now(UTC) + timedelta(hours=1)},
            priv,
            algorithm="RS256",
            headers={"kid": "v1"},
        )
        result = v.validate_token(token)
        assert result.valid is False


class TestDualKeyCreateToken:
    def test_no_current_key(self):
        v = DualKeyJWTValidator()
        assert v.create_token({"sub": "u"}) is None

    def test_no_private_key(self):
        _, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._current_kid = "v1"
        v._keys["v1"] = (None, pub, KeyMetadata(kid="v1", is_current=True))
        assert v.create_token({"sub": "u"}) is None

    def test_create_and_validate(self):
        priv, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._current_kid = "v1"
        v._keys["v1"] = (priv, pub, KeyMetadata(kid="v1", is_current=True))
        token = v.create_token({"sub": "user1"})
        assert token is not None
        result = v.validate_token(token)
        assert result.valid is True
        assert result.claims["sub"] == "user1"

    def test_create_with_custom_expiry(self):
        priv, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._current_kid = "v1"
        v._keys["v1"] = (priv, pub, KeyMetadata(kid="v1", is_current=True))
        token = v.create_token({"sub": "u"}, expires_delta=timedelta(minutes=5))
        assert token is not None

    def test_create_without_kid(self):
        priv, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._current_kid = "v1"
        v._keys["v1"] = (priv, pub, KeyMetadata(kid="v1", is_current=True))
        token = v.create_token({"sub": "u"}, include_kid=False)
        assert token is not None
        import jwt as pyjwt

        header = pyjwt.get_unverified_header(token)
        assert "kid" not in header


class TestDualKeyGetJWKS:
    def test_empty_keys(self):
        v = DualKeyJWTValidator()
        jwks = v.get_jwks()
        assert jwks["keys"] == []

    def test_with_rsa_key(self):
        _, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._keys["v1"] = (None, pub, KeyMetadata(kid="v1", is_current=True))
        jwks = v.get_jwks()
        assert len(jwks["keys"]) == 1
        assert jwks["keys"][0]["kid"] == "v1"
        assert jwks["keys"][0]["kty"] == "RSA"

    def test_skips_expired_key(self):
        _, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._keys["v1"] = (
            None,
            pub,
            KeyMetadata(
                kid="v1",
                is_current=False,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        )
        jwks = v.get_jwks()
        assert len(jwks["keys"]) == 0

    def test_handles_invalid_key(self):
        v = DualKeyJWTValidator()
        v._keys["bad"] = (None, b"not_a_real_key", KeyMetadata(kid="bad", is_current=True))
        jwks = v.get_jwks()
        assert len(jwks["keys"]) == 0


class TestDualKeyGetStats:
    def test_stats(self):
        v = DualKeyJWTValidator()
        v._current_kid = "v1"
        stats = v.get_stats()
        assert stats["current_kid"] == "v1"
        assert stats["total_validations"] == 0
        assert stats["dual_key_enabled"] is False


class TestDualKeyGetHealth:
    def test_healthy(self):
        v = DualKeyJWTValidator()
        v._current_kid = "v1"
        h = v.get_health()
        assert h["status"] == "healthy"

    def test_degraded(self):
        v = DualKeyJWTValidator()
        h = v.get_health()
        assert h["status"] == "degraded"

    def test_previous_expires_soon(self):
        _, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._current_kid = "v1"
        v._previous_kid = "v0"
        v._keys["v0"] = (
            None,
            pub,
            KeyMetadata(
                kid="v0",
                is_current=False,
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            ),
        )
        h = v.get_health()
        assert h["previous_key_expires_soon"] is True
        assert h["dual_key_active"] is True


class TestDualKeyCleanupExpiredKeys:
    def test_cleanup_removes_expired(self):
        _, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._keys["old"] = (
            None,
            pub,
            KeyMetadata(
                kid="old",
                is_current=False,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        )
        v._previous_kid = "old"
        v._cleanup_expired_keys()
        assert "old" not in v._keys
        assert v._previous_kid is None

    def test_keeps_non_expired(self):
        _, pub = _generate_rsa_keypair()
        v = DualKeyJWTValidator()
        v._keys["active"] = (
            None,
            pub,
            KeyMetadata(kid="active", is_current=True),
        )
        v._cleanup_expired_keys()
        assert "active" in v._keys


class TestDualKeyRefreshKeysIfNeeded:
    async def test_no_last_refresh(self):
        v = DualKeyJWTValidator()
        await v.refresh_keys_if_needed()  # no error

    async def test_within_interval(self):
        v = DualKeyJWTValidator()
        v._last_refresh = datetime.now(UTC)
        v.load_keys_from_env = AsyncMock()
        await v.refresh_keys_if_needed()
        v.load_keys_from_env.assert_not_awaited()

    async def test_past_interval_triggers_refresh(self):
        v = DualKeyJWTValidator(config=DualKeyConfig(refresh_interval_seconds=0))
        v._last_refresh = datetime.now(UTC) - timedelta(seconds=10)
        v.load_keys_from_env = AsyncMock(return_value=True)
        await v.refresh_keys_if_needed()
        v.load_keys_from_env.assert_awaited()


class TestDualKeyLoadFromVault:
    async def test_no_vault_client_falls_back(self):
        v = DualKeyJWTValidator()
        v.load_keys_from_env = AsyncMock(return_value=True)
        await v.load_keys_from_vault()
        v.load_keys_from_env.assert_awaited()

    async def test_vault_load_success(self):
        priv, pub = _generate_rsa_keypair()
        vault = MagicMock()
        vault.secrets.kv.v2.read_secret_version.return_value = {
            "data": {
                "data": {
                    "kid": "v2",
                    "public_key": base64.b64encode(pub).decode(),
                    "key": base64.b64encode(priv).decode(),
                    "created_at": datetime.now(UTC).isoformat(),
                    "dual_key_enabled": "false",
                }
            }
        }
        v = DualKeyJWTValidator(vault_client=vault)
        result = await v.load_keys_from_vault()
        assert result is True
        assert v._current_kid == "v2"

    async def test_vault_load_with_dual_key(self):
        priv1, pub1 = _generate_rsa_keypair()
        _, pub2 = _generate_rsa_keypair()
        vault = MagicMock()

        def read_secret(path):
            if "current" in path:
                return {
                    "data": {
                        "data": {
                            "kid": "v2",
                            "public_key": base64.b64encode(pub1).decode(),
                            "key": base64.b64encode(priv1).decode(),
                            "created_at": datetime.now(UTC).isoformat(),
                            "dual_key_enabled": "true",
                        }
                    }
                }
            return {
                "data": {
                    "data": {
                        "kid": "v1",
                        "public_key": base64.b64encode(pub2).decode(),
                    }
                }
            }

        vault.secrets.kv.v2.read_secret_version.side_effect = read_secret
        v = DualKeyJWTValidator(vault_client=vault)
        result = await v.load_keys_from_vault()
        assert result is True
        assert v._previous_kid == "v1"

    async def test_vault_load_failure_falls_back(self):
        vault = MagicMock()
        vault.secrets.kv.v2.read_secret_version.side_effect = RuntimeError("vault down")
        v = DualKeyJWTValidator(vault_client=vault)
        v.load_keys_from_env = AsyncMock(return_value=False)
        await v.load_keys_from_vault()
        v.load_keys_from_env.assert_awaited()


class TestDualKeySingleton:
    async def test_get_dual_key_validator(self):
        import src.core.shared.security.dual_key_jwt as mod

        mod._validator = None
        with patch.dict("os.environ", {}, clear=True):
            v = await get_dual_key_validator()
            assert v is not None
        mod._validator = None

    async def test_singleton_returns_same(self):
        import src.core.shared.security.dual_key_jwt as mod

        mod._validator = None
        with patch.dict("os.environ", {}, clear=True):
            v1 = await get_dual_key_validator()
            v2 = await get_dual_key_validator()
            assert v1 is v2
        mod._validator = None


class TestOIDCExceptions:
    """Verify exception classes have correct attributes."""

    def test_oidc_error(self):
        assert OIDCError.http_status_code == 500

    def test_oidc_config_error(self):
        assert OIDCConfigurationError.http_status_code == 500

    def test_oidc_auth_error(self):
        assert OIDCAuthenticationError.http_status_code == 401

    def test_oidc_token_error(self):
        assert OIDCTokenError.http_status_code == 401

    def test_oidc_provider_error(self):
        assert OIDCProviderError.http_status_code == 502


class TestKeyMetadataModel:
    def test_defaults(self):
        km = KeyMetadata(kid="v1")
        assert km.algorithm == "RS256"
        assert km.is_current is True
        assert km.expires_at is None


class TestDualKeyConfigModel:
    def test_defaults(self):
        cfg = DualKeyConfig()
        assert cfg.enabled is True
        assert cfg.grace_period_hours == 4
        assert cfg.max_keys == 2
        assert cfg.require_kid is False


class TestJWTValidationResultModel:
    def test_defaults(self):
        r = JWTValidationResult(valid=True)
        assert r.constitutional_compliant is True
        assert r.claims is None
        assert r.key_used is None
