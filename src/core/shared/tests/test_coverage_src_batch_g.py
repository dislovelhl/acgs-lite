"""
Comprehensive tests for:
  - src.core.shared.security.encryption
  - src.core.shared.security.service_auth
  - src.core.shared.security.auth_dependency
  - src.core.shared.metrics.rocs
"""

import base64
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.core.shared.errors.exceptions import ConfigurationError

# ---------------------------------------------------------------------------
# encryption.py
# ---------------------------------------------------------------------------
from src.core.shared.security import encryption as enc_mod
from src.core.shared.security.encryption import EncryptionManager


class TestRuntimeEnvironment:
    def test_defaults_to_development(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("AGENT_RUNTIME_ENVIRONMENT", None)
            os.environ.pop("ENVIRONMENT", None)
            assert enc_mod._runtime_environment() == "development"

    def test_agent_runtime_takes_precedence(self):
        with patch.dict(
            os.environ, {"AGENT_RUNTIME_ENVIRONMENT": " Staging ", "ENVIRONMENT": "prod"}
        ):
            assert enc_mod._runtime_environment() == "staging"

    def test_falls_back_to_environment(self):
        with patch.dict(os.environ, {"ENVIRONMENT": " Production "}, clear=True):
            os.environ.pop("AGENT_RUNTIME_ENVIRONMENT", None)
            assert enc_mod._runtime_environment() == "production"


class TestIsProductionLikeEnvironment:
    @pytest.mark.parametrize("env_val", ["development", "dev", "test", "testing", "local", "ci"])
    def test_non_production_envs(self, env_val):
        with patch.object(enc_mod, "_runtime_environment", return_value=env_val):
            assert enc_mod._is_production_like_environment() is False

    def test_production_env(self):
        with patch.object(enc_mod, "_runtime_environment", return_value="production"):
            assert enc_mod._is_production_like_environment() is True

    def test_staging_env(self):
        with patch.object(enc_mod, "_runtime_environment", return_value="staging"):
            assert enc_mod._is_production_like_environment() is True


class TestParseBoolEnv:
    @pytest.mark.parametrize(
        "val,expected",
        [
            ("true", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("True", True),
            (" YES ", True),
            ("false", False),
            ("0", False),
            ("no", False),
            ("", False),
            (None, False),
        ],
    )
    def test_values(self, val, expected):
        assert enc_mod._parse_bool_env(val) is expected


class TestAllowEphemeralMasterKey:
    def test_production_always_false(self):
        with patch.object(enc_mod, "_is_production_like_environment", return_value=True):
            assert enc_mod._allow_ephemeral_master_key() is False

    def test_dev_with_env_flag(self):
        with (
            patch.object(enc_mod, "_is_production_like_environment", return_value=False),
            patch.dict(os.environ, {"ACGS2_ALLOW_EPHEMERAL_ENCRYPTION_KEY": "true"}),
        ):
            assert enc_mod._allow_ephemeral_master_key() is True

    def test_dev_with_pytest_module(self):
        with (
            patch.object(enc_mod, "_is_production_like_environment", return_value=False),
            patch.dict(os.environ, {}, clear=True),
        ):
            os.environ.pop("ACGS2_ALLOW_EPHEMERAL_ENCRYPTION_KEY", None)
            os.environ.pop("PYTEST_CURRENT_TEST", None)
            # pytest is in sys.modules during test runs
            assert enc_mod._allow_ephemeral_master_key() is True


class TestLoadMasterKey:
    def setup_method(self):
        enc_mod._MASTER_KEY_CACHE = None

    def teardown_method(self):
        enc_mod._MASTER_KEY_CACHE = None

    def test_returns_cached_key(self):
        enc_mod._MASTER_KEY_CACHE = b"x" * 32
        assert enc_mod._load_master_key() == b"x" * 32

    def test_loads_from_env(self):
        key = os.urandom(32)
        encoded = base64.b64encode(key).decode()
        with patch.dict(os.environ, {"ACGS2_ENCRYPTION_KEY": encoded}):
            result = enc_mod._load_master_key()
            assert result == key

    def test_invalid_base64_raises(self):
        with patch.dict(os.environ, {"ACGS2_ENCRYPTION_KEY": "not-valid-base64!!!"}):
            with pytest.raises(OSError, match="valid base64"):
                enc_mod._load_master_key()

    def test_wrong_key_length_raises(self):
        short_key = base64.b64encode(b"short").decode()
        with patch.dict(os.environ, {"ACGS2_ENCRYPTION_KEY": short_key}):
            with pytest.raises(OSError, match="32 bytes"):
                enc_mod._load_master_key()

    def test_ephemeral_key_in_dev(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(enc_mod, "_allow_ephemeral_master_key", return_value=True),
        ):
            os.environ.pop("ACGS2_ENCRYPTION_KEY", None)
            key = enc_mod._load_master_key()
            assert len(key) == 32

    def test_no_key_in_production_raises(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(enc_mod, "_allow_ephemeral_master_key", return_value=False),
        ):
            os.environ.pop("ACGS2_ENCRYPTION_KEY", None)
            with pytest.raises(OSError, match="required in production"):
                enc_mod._load_master_key()


class TestEncryptionManager:
    def setup_method(self):
        enc_mod._MASTER_KEY_CACHE = None

    def teardown_method(self):
        enc_mod._MASTER_KEY_CACHE = None

    def test_encrypt_decrypt_roundtrip(self):
        payload = {"user": "alice", "action": "deploy", "count": 42}
        encrypted = EncryptionManager.encrypt_payload(payload)
        assert isinstance(encrypted, str)
        decrypted = EncryptionManager.decrypt_payload(encrypted)
        assert decrypted == payload

    def test_encrypt_empty_payload(self):
        encrypted = EncryptionManager.encrypt_payload({})
        decrypted = EncryptionManager.decrypt_payload(encrypted)
        assert decrypted == {}

    def test_decrypt_corrupted_data_raises(self):
        payload = {"test": True}
        encrypted = EncryptionManager.encrypt_payload(payload)
        raw = base64.b64decode(encrypted)
        corrupted = base64.b64encode(raw[:-1] + bytes([raw[-1] ^ 0xFF])).decode()
        with pytest.raises(ConfigurationError, match="Decryption failure"):
            EncryptionManager.decrypt_payload(corrupted)

    def test_decrypt_invalid_base64_raises(self):
        with pytest.raises(ConfigurationError, match="Decryption failure"):
            EncryptionManager.decrypt_payload("not-valid!!!")

    def test_encrypt_raises_on_key_failure(self):
        with patch.object(enc_mod, "_load_master_key", side_effect=OSError("no key")):
            with pytest.raises(ConfigurationError, match="Encryption failure"):
                EncryptionManager.encrypt_payload({"a": 1})

    def test_decrypt_raises_on_key_failure(self):
        with patch.object(enc_mod, "_load_master_key", side_effect=OSError("no key")):
            fake = base64.b64encode(b"\x00" * 100).decode()
            with pytest.raises(ConfigurationError, match="Decryption failure"):
                EncryptionManager.decrypt_payload(fake)


# ---------------------------------------------------------------------------
# service_auth.py
# ---------------------------------------------------------------------------
from src.core.shared.security import service_auth as sa_mod
from src.core.shared.security.service_auth import ServiceAuth, require_service_auth


class TestGetServiceSecret:
    def test_returns_env_secret(self):
        with patch.dict(os.environ, {"ACGS2_SERVICE_SECRET": "my-secret"}):
            assert sa_mod._get_service_secret() == "my-secret"

    def test_dev_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ACGS2_SERVICE_SECRET", None)
            os.environ.pop("ACGS2_ENV", None)
            os.environ.pop("ENVIRONMENT", None)
            result = sa_mod._get_service_secret()
            assert "dev-service-secret" in result

    def test_production_without_secret_raises(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            os.environ.pop("ACGS2_SERVICE_SECRET", None)
            os.environ.pop("ACGS2_ENV", None)
            with pytest.raises(ConfigurationError, match="SERVICE_SECRET_MISSING"):
                sa_mod._get_service_secret()

    def test_acgs2_env_production_raises(self):
        with patch.dict(os.environ, {"ACGS2_ENV": "production"}, clear=True):
            os.environ.pop("ACGS2_SERVICE_SECRET", None)
            os.environ.pop("ENVIRONMENT", None)
            with pytest.raises(ConfigurationError, match="SERVICE_SECRET_MISSING"):
                sa_mod._get_service_secret()


class TestConfiguredServiceAlgorithm:
    def test_default_rs256(self):
        with patch.dict(os.environ, {"SERVICE_JWT_ALGORITHM": "RS256"}):
            assert sa_mod._configured_service_algorithm() == "RS256"

    def test_hs256(self):
        with patch.dict(os.environ, {"SERVICE_JWT_ALGORITHM": "HS256"}):
            assert sa_mod._configured_service_algorithm() == "HS256"

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"SERVICE_JWT_ALGORITHM": "es256"}):
            assert sa_mod._configured_service_algorithm() == "ES256"

    def test_invalid_algorithm_raises(self):
        with patch.dict(os.environ, {"SERVICE_JWT_ALGORITHM": "NONE"}):
            with pytest.raises(ConfigurationError, match="SERVICE_JWT_ALGORITHM_INVALID"):
                sa_mod._configured_service_algorithm()


class TestGetServicePrivatePublicKey:
    def test_private_key_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JWT_PRIVATE_KEY", None)
            assert sa_mod._get_service_private_key() is None

    def test_public_key_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JWT_PUBLIC_KEY", None)
            assert sa_mod._get_service_public_key() is None

    def test_private_key_loads(self):
        with (
            patch.dict(os.environ, {"JWT_PRIVATE_KEY": "raw-key-data"}),
            patch.object(sa_mod, "load_key_material", return_value="loaded-key"),
        ):
            assert sa_mod._get_service_private_key() == "loaded-key"

    def test_private_key_returns_none_when_load_empty(self):
        with (
            patch.dict(os.environ, {"JWT_PRIVATE_KEY": "raw-key-data"}),
            patch.object(sa_mod, "load_key_material", return_value=""),
        ):
            assert sa_mod._get_service_private_key() is None


class TestResolveServiceJwtMaterial:
    def test_hs256_returns_secret(self):
        with (
            patch.object(sa_mod, "_configured_service_algorithm", return_value="HS256"),
        ):
            key, algo = sa_mod._resolve_service_jwt_material(for_signing=True)
            assert algo == "HS256"
            assert key == sa_mod.SERVICE_SECRET

    def test_asymmetric_with_keys_signing(self):
        with (
            patch.object(sa_mod, "_configured_service_algorithm", return_value="RS256"),
            patch.object(sa_mod, "_get_service_private_key", return_value="priv"),
            patch.object(sa_mod, "_get_service_public_key", return_value="pub"),
        ):
            key, algo = sa_mod._resolve_service_jwt_material(for_signing=True)
            assert key == "priv"
            assert algo == "RS256"

    def test_asymmetric_with_keys_verification(self):
        with (
            patch.object(sa_mod, "_configured_service_algorithm", return_value="RS256"),
            patch.object(sa_mod, "_get_service_private_key", return_value="priv"),
            patch.object(sa_mod, "_get_service_public_key", return_value="pub"),
        ):
            key, algo = sa_mod._resolve_service_jwt_material(for_signing=False)
            assert key == "pub"
            assert algo == "RS256"

    def test_rs256_without_keys_raises(self):
        with (
            patch.object(sa_mod, "_configured_service_algorithm", return_value="RS256"),
            patch.object(sa_mod, "_get_service_private_key", return_value=None),
            patch.object(sa_mod, "_get_service_public_key", return_value=None),
        ):
            with pytest.raises(ConfigurationError, match="RSA keys are not configured"):
                sa_mod._resolve_service_jwt_material(for_signing=True)

    def test_non_rs256_asymmetric_without_keys_raises(self):
        with (
            patch.object(sa_mod, "_configured_service_algorithm", return_value="ES256"),
            patch.object(sa_mod, "_get_service_private_key", return_value=None),
            patch.object(sa_mod, "_get_service_public_key", return_value=None),
        ):
            with pytest.raises(ConfigurationError, match="asymmetric keys are not configured"):
                sa_mod._resolve_service_jwt_material(for_signing=True)


class TestServiceAuth:
    def test_create_and_verify_token_hs256(self):
        with (
            patch.object(sa_mod, "_resolve_service_jwt_material") as mock_resolve,
        ):
            secret = "test-secret-that-is-long-enough-32"
            mock_resolve.return_value = (secret, "HS256")

            token = ServiceAuth.create_service_token("my-service", expires_in=60)
            assert isinstance(token, str)

            service_name = ServiceAuth.verify_service_token(token)
            assert service_name == "my-service"

    def test_verify_expired_token(self):
        import jwt as pyjwt

        secret = "test-secret-that-is-long-enough-32"
        payload = {
            "sub": "svc",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
            "iss": "acgs2-internal",
            "type": "service",
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")
        with patch.object(
            sa_mod,
            "_resolve_service_jwt_material",
            return_value=(secret, "HS256"),
        ):
            assert ServiceAuth.verify_service_token(token) is None

    def test_verify_wrong_type(self):
        import jwt as pyjwt

        secret = "test-secret-that-is-long-enough-32"
        payload = {
            "sub": "svc",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "acgs2-internal",
            "type": "user",
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")
        with patch.object(
            sa_mod,
            "_resolve_service_jwt_material",
            return_value=(secret, "HS256"),
        ):
            assert ServiceAuth.verify_service_token(token) is None

    def test_verify_wrong_issuer(self):
        import jwt as pyjwt

        secret = "test-secret-that-is-long-enough-32"
        payload = {
            "sub": "svc",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "wrong-issuer",
            "type": "service",
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")
        with patch.object(
            sa_mod,
            "_resolve_service_jwt_material",
            return_value=(secret, "HS256"),
        ):
            assert ServiceAuth.verify_service_token(token) is None


class TestRequireServiceAuth:
    @pytest.mark.asyncio
    async def test_valid_token(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")
        with patch.object(ServiceAuth, "verify_service_token", return_value="my-svc"):
            result = await require_service_auth(credentials=creds)
            assert result == "my-svc"

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
        with patch.object(ServiceAuth, "verify_service_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await require_service_auth(credentials=creds)
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# auth_dependency.py
# ---------------------------------------------------------------------------
from src.core.shared.security import auth_dependency as ad_mod
from src.core.shared.security.auth_dependency import (
    configure_revocation_service,
    initialize_revocation_service,
    require_auth,
    require_auth_optional,
    shutdown_revocation_service,
)


class TestConfigureRevocationService:
    def teardown_method(self):
        ad_mod._revocation_service = None

    def test_sets_service(self):
        svc = MagicMock()
        configure_revocation_service(svc)
        assert ad_mod._revocation_service is svc


class TestInitializeRevocationService:
    def teardown_method(self):
        ad_mod._revocation_service = None

    @pytest.mark.asyncio
    async def test_with_redis_url(self):
        mock_svc = MagicMock()
        with patch(
            "src.core.shared.security.token_revocation.create_token_revocation_service",
            new_callable=AsyncMock,
            return_value=mock_svc,
        ):
            result = await initialize_revocation_service(redis_url="redis://localhost")
            assert result is mock_svc
            assert ad_mod._revocation_service is mock_svc

    @pytest.mark.asyncio
    async def test_without_redis_url_degraded(self):
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "src.core.shared.security.token_revocation.TokenRevocationService",
                mock_cls,
            ),
            patch(
                "src.core.shared.security.token_revocation.create_token_revocation_service",
                new_callable=AsyncMock,
            ),
        ):
            os.environ.pop("TOKEN_REVOCATION_REDIS_URL", None)
            os.environ.pop("REDIS_URL", None)
            result = await initialize_revocation_service(redis_url=None)
            assert result is mock_instance
            mock_cls.assert_called_once_with(redis_client=None)


class TestShutdownRevocationService:
    def teardown_method(self):
        ad_mod._revocation_service = None

    @pytest.mark.asyncio
    async def test_clears_and_closes(self):
        svc = AsyncMock()
        ad_mod._revocation_service = svc
        await shutdown_revocation_service()
        assert ad_mod._revocation_service is None
        svc.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_when_none(self):
        ad_mod._revocation_service = None
        await shutdown_revocation_service()
        assert ad_mod._revocation_service is None


class TestIsProductionEnvironment:
    def test_dev_is_not_production(self):
        with patch.object(ad_mod, "settings") as mock_settings:
            mock_settings.env = "development"
            assert ad_mod._is_production_environment() is False

    def test_production_is_production(self):
        with patch.object(ad_mod, "settings") as mock_settings:
            mock_settings.env = "production"
            assert ad_mod._is_production_environment() is True

    def test_missing_settings_env_defaults_to_non_production(self):
        with (
            patch.object(ad_mod, "settings", SimpleNamespace()),
            patch.dict(os.environ, {}, clear=True),
        ):
            os.environ.pop("AGENT_RUNTIME_ENVIRONMENT", None)
            os.environ.pop("ENVIRONMENT", None)
            os.environ.pop("ACGS2_ENV", None)
            assert ad_mod._is_production_environment() is False


class TestAuthDisabledRequested:
    def test_disabled_true(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
            assert ad_mod._auth_disabled_requested() is True

    def test_disabled_false(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": "false"}):
            assert ad_mod._auth_disabled_requested() is False

    def test_disabled_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("AUTH_DISABLED", None)
            assert ad_mod._auth_disabled_requested() is False


class TestCheckRevocation:
    def teardown_method(self):
        ad_mod._revocation_service = None

    @pytest.mark.asyncio
    async def test_no_service_skips(self):
        ad_mod._revocation_service = None
        await ad_mod._check_revocation("some-jti")

    @pytest.mark.asyncio
    async def test_no_jti_skips(self):
        ad_mod._revocation_service = MagicMock()
        await ad_mod._check_revocation(None)

    @pytest.mark.asyncio
    async def test_empty_jti_skips(self):
        ad_mod._revocation_service = MagicMock()
        await ad_mod._check_revocation("")

    @pytest.mark.asyncio
    async def test_revoked_raises_401(self):
        svc = AsyncMock()
        svc.is_token_revoked.return_value = True
        ad_mod._revocation_service = svc
        with pytest.raises(HTTPException) as exc_info:
            await ad_mod._check_revocation("revoked-jti-12345678")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_not_revoked_passes(self):
        svc = AsyncMock()
        svc.is_token_revoked.return_value = False
        ad_mod._revocation_service = svc
        await ad_mod._check_revocation("valid-jti")

    @pytest.mark.asyncio
    async def test_exception_non_blocking(self):
        svc = AsyncMock()
        svc.is_token_revoked.side_effect = RuntimeError("redis down")
        ad_mod._revocation_service = svc
        # Should not raise
        await ad_mod._check_revocation("some-jti")


class TestRequireAuth:
    def teardown_method(self):
        ad_mod._revocation_service = None

    @pytest.mark.asyncio
    async def test_auth_disabled_in_dev(self):
        with (
            patch.object(ad_mod, "_auth_disabled_requested", return_value=True),
            patch.object(ad_mod, "_is_production_environment", return_value=False),
        ):
            result = await require_auth(credentials=None)
            assert result["sub"] == "dev-user"
            assert "viewer" in result["roles"]

    @pytest.mark.asyncio
    async def test_auth_disabled_blocked_in_prod(self):
        creds = None
        with (
            patch.object(ad_mod, "_auth_disabled_requested", return_value=True),
            patch.object(ad_mod, "_is_production_environment", return_value=True),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(credentials=creds)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_credentials_raises_401(self):
        with (
            patch.object(ad_mod, "_auth_disabled_requested", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(credentials=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_jwt_verification_material_raises_500(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
        with (
            patch.object(ad_mod, "_auth_disabled_requested", return_value=False),
            patch.object(ad_mod, "has_jwt_verification_material", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(credentials=creds)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid")
        mock_claims = MagicMock()
        mock_claims.model_dump.return_value = {
            "sub": "user1",
            "tenant_id": "t1",
            "roles": ["admin"],
            "jti": "jti-123",
        }
        with (
            patch.object(ad_mod, "_auth_disabled_requested", return_value=False),
            patch.object(ad_mod, "has_jwt_verification_material", return_value=True),
            patch.object(ad_mod, "verify_token", return_value=mock_claims),
            patch.object(ad_mod, "_check_revocation", new_callable=AsyncMock) as mock_revoke,
        ):
            result = await require_auth(credentials=creds)
            assert result["sub"] == "user1"
            mock_revoke.assert_awaited_once_with("jti-123")


class TestRequireAuthOptional:
    def test_no_credentials_returns_none(self):
        result = require_auth_optional(credentials=None)
        assert result is None

    def test_no_jwt_verification_material_returns_none(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
        with patch.object(ad_mod, "has_jwt_verification_material", return_value=False):
            result = require_auth_optional(credentials=creds)
            assert result is None

    def test_valid_token_returns_payload(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid")
        mock_claims = MagicMock()
        mock_claims.model_dump.return_value = {"sub": "user1"}
        with (
            patch.object(ad_mod, "has_jwt_verification_material", return_value=True),
            patch.object(ad_mod, "verify_token", return_value=mock_claims),
        ):
            result = require_auth_optional(credentials=creds)
            assert result == {"sub": "user1"}

    def test_invalid_token_raises_401(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad")
        with (
            patch.object(ad_mod, "has_jwt_verification_material", return_value=True),
            patch.object(
                ad_mod,
                "verify_token",
                side_effect=HTTPException(status_code=401, detail="expired"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                require_auth_optional(credentials=creds)
            assert exc_info.value.status_code == 401

    def test_server_error_re_raises(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad")
        with (
            patch.object(ad_mod, "has_jwt_verification_material", return_value=True),
            patch.object(
                ad_mod,
                "verify_token",
                side_effect=HTTPException(status_code=500, detail="boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                require_auth_optional(credentials=creds)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# metrics/rocs.py
# ---------------------------------------------------------------------------
from src.core.shared.metrics.rocs import (
    SEVERITY_WEIGHTS,
    GovernanceSpend,
    GovernanceValue,
    RoCSSnapshot,
    RoCSTracker,
    get_rocs_tracker,
    reset_rocs_tracker,
)


class TestGovernanceSpend:
    def test_defaults(self):
        s = GovernanceSpend()
        assert s.validation_ns == 0
        assert s.scoring_ns == 0
        assert s.total_ns == 0
        assert s.total_seconds == 0.0

    def test_total_ns(self):
        s = GovernanceSpend(validation_ns=1_000_000, scoring_ns=2_000_000)
        assert s.total_ns == 3_000_000

    def test_total_seconds(self):
        s = GovernanceSpend(validation_ns=1_000_000_000, scoring_ns=500_000_000)
        assert s.total_seconds == 1.5


class TestGovernanceValue:
    def test_defaults(self):
        v = GovernanceValue()
        assert v.total_weighted == 0.0
        assert v.decisions == 0
        assert v.violations_caught == 0


class TestRoCSSnapshot:
    def test_creation(self):
        snap = RoCSSnapshot(
            rocs=5.0,
            spend=GovernanceSpend(),
            value=GovernanceValue(),
        )
        assert snap.rocs == 5.0
        assert snap.timestamp_ns > 0


class TestSeverityWeights:
    def test_expected_weights(self):
        assert SEVERITY_WEIGHTS["critical"] == 10.0
        assert SEVERITY_WEIGHTS["high"] == 5.0
        assert SEVERITY_WEIGHTS["medium"] == 2.0
        assert SEVERITY_WEIGHTS["low"] == 1.0
        assert SEVERITY_WEIGHTS["allow"] == 1.0


class TestRoCSTracker:
    def test_empty_snapshot(self):
        tracker = RoCSTracker()
        snap = tracker.snapshot()
        assert snap.rocs == 0.0
        assert snap.spend.total_ns == 0
        assert snap.value.decisions == 0

    def test_record_validation_correct(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=1000, severity="critical", correct=True)
        snap = tracker.snapshot()
        assert snap.value.decisions == 1
        assert snap.value.total_weighted == 10.0
        assert snap.value.violations_caught == 1
        assert snap.spend.validation_ns == 1000

    def test_record_validation_incorrect(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=1000, severity="high", correct=False)
        snap = tracker.snapshot()
        assert snap.value.total_weighted == 0.0
        assert snap.value.decisions == 1
        assert snap.value.violations_caught == 0

    def test_record_validation_allow_no_violation(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=500, severity="allow", correct=True)
        snap = tracker.snapshot()
        assert snap.value.violations_caught == 0
        assert snap.value.total_weighted == 1.0

    def test_record_validation_unknown_severity(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=100, severity="unknown", correct=True)
        snap = tracker.snapshot()
        assert snap.value.total_weighted == 1.0  # default weight

    def test_record_validation_case_insensitive(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=100, severity="CRITICAL", correct=True)
        snap = tracker.snapshot()
        assert snap.value.total_weighted == 10.0

    def test_record_scoring(self):
        tracker = RoCSTracker()
        tracker.record_scoring(elapsed_ns=5000)
        snap = tracker.snapshot()
        assert snap.spend.scoring_ns == 5000

    def test_rocs_calculation(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=1_000_000_000, severity="critical", correct=True)
        snap = tracker.snapshot()
        # rocs = 10.0 / 1.0 seconds = 10.0
        assert snap.rocs == 10.0

    def test_to_dict(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=1_000_000_000, severity="high", correct=True)
        tracker.record_scoring(elapsed_ns=500_000_000)
        d = tracker.to_dict()
        assert d["rocs"] == pytest.approx(5.0 / 1.5)
        assert d["governance_value_weighted"] == 5.0
        assert d["governance_decisions"] == 1
        assert d["violations_caught"] == 1
        assert d["validation_ns"] == 1_000_000_000
        assert d["scoring_ns"] == 500_000_000
        assert d["total_compute_seconds"] == 1.5

    def test_reset(self):
        tracker = RoCSTracker()
        tracker.record_validation(elapsed_ns=1000, severity="low", correct=True)
        tracker.reset()
        snap = tracker.snapshot()
        assert snap.value.decisions == 0
        assert snap.spend.total_ns == 0

    def test_thread_safety(self):
        tracker = RoCSTracker()
        errors = []

        def record_many():
            try:
                for _ in range(100):
                    tracker.record_validation(elapsed_ns=1, severity="low", correct=True)
                    tracker.record_scoring(elapsed_ns=1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        snap = tracker.snapshot()
        assert snap.value.decisions == 400
        assert snap.spend.validation_ns == 400
        assert snap.spend.scoring_ns == 400


class TestGlobalTracker:
    def teardown_method(self):
        reset_rocs_tracker()

    def test_get_rocs_tracker_singleton(self):
        t1 = get_rocs_tracker()
        t2 = get_rocs_tracker()
        assert t1 is t2

    def test_reset_rocs_tracker(self):
        t1 = get_rocs_tracker()
        reset_rocs_tracker()
        t2 = get_rocs_tracker()
        assert t1 is not t2

    def test_get_tracker_thread_safe(self):
        trackers = []

        def get_it():
            trackers.append(get_rocs_tracker())

        threads = [threading.Thread(target=get_it) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(t is trackers[0] for t in trackers)
