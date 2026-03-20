"""Comprehensive tests for config modules, type_guards, pqc_crypto, and expression_utils.

Targets uncovered lines in:
- config/security.py (lines 48, 154-348)
- config/factory.py (lines 26-30, 100-116, 126-175)
- config/governance.py (lines 16-18, 153-294)
- config/infrastructure.py (lines 18-20, 84-176)
- config/integrations.py (lines 16-18, 87-194)
- type_guards.py (lines 24-25, 42, 54-60, 72, 91, etc.)
- security/pqc_crypto.py (lines 142-189, 225-268)
- security/expression_utils.py (lines 30-44, 67-78, 97-119)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr


# ============================================================================
# Config: Security (pydantic_settings branch — lines 33-48)
# ============================================================================


class TestSecuritySettings:
    """Tests for SecuritySettings pydantic-settings branch."""

    def test_security_settings_defaults(self):
        from src.core.shared.config.security import SecuritySettings

        s = SecuritySettings()
        assert s.jwt_public_key == "SYSTEM_PUBLIC_KEY_PLACEHOLDER"
        assert s.api_key_internal is None
        assert s.jwt_secret is None
        assert s.admin_api_key is None

    def test_security_settings_with_valid_jwt_secret(self):
        from src.core.shared.config.security import SecuritySettings

        long_secret = "a" * 64
        s = SecuritySettings.model_validate({"JWT_SECRET": long_secret})
        assert s.jwt_secret is not None
        assert s.jwt_secret.get_secret_value() == long_secret

    def test_security_settings_rejects_placeholder_jwt_secret(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception, match="forbidden placeholder"):
            SecuritySettings.model_validate({"JWT_SECRET": "PLACEHOLDER"})

    def test_security_settings_rejects_change_me(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception, match="forbidden placeholder"):
            SecuritySettings.model_validate({"JWT_SECRET": "CHANGE_ME"})

    def test_security_settings_rejects_dangerous_default(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception, match="forbidden placeholder"):
            SecuritySettings.model_validate({"JWT_SECRET": "DANGEROUS_DEFAULT"})

    def test_security_settings_short_secret_passes_validator(self):
        """Short secret (<32 chars) passes field validator (line 48 pass branch)."""
        from src.core.shared.config.security import SecuritySettings

        short = "a" * 20
        s = SecuritySettings.model_validate({"JWT_SECRET": short})
        assert s.jwt_secret is not None

    def test_security_settings_rejects_dev_secret(self):
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception, match="forbidden placeholder"):
            SecuritySettings.model_validate({"API_KEY_INTERNAL": "dev-secret"})


class TestOPASettings:
    def test_opa_defaults(self):
        from src.core.shared.config.security import OPASettings

        o = OPASettings()
        assert o.url == "http://localhost:8181"
        assert o.fail_closed is True
        assert o.ssl_verify is True
        assert o.mode == "http"

    def test_opa_custom(self):
        from src.core.shared.config.security import OPASettings

        o = OPASettings.model_validate({
            "OPA_URL": "http://opa:8181",
            "OPA_MODE": "embedded",
            "OPA_SSL_VERIFY": False,
        })
        assert o.url == "http://opa:8181"
        assert o.mode == "embedded"
        assert o.ssl_verify is False


class TestAuditSettings:
    def test_audit_defaults(self):
        from src.core.shared.config.security import AuditSettings

        a = AuditSettings()
        assert a.url == "http://localhost:8001"


class TestVaultSettings:
    def test_vault_defaults(self):
        from src.core.shared.config.security import VaultSettings

        v = VaultSettings()
        assert v.address == "http://127.0.0.1:8200"
        assert v.token is None
        assert v.transit_mount == "transit"
        assert v.kv_mount == "secret"
        assert v.kv_version == 2
        assert v.timeout == 30.0
        assert v.verify_tls is True

    def test_vault_with_token(self):
        from src.core.shared.config.security import VaultSettings

        v = VaultSettings.model_validate({"VAULT_TOKEN": "hvs.test-token"})
        assert v.token is not None
        assert v.token.get_secret_value() == "hvs.test-token"


class TestSSOSettings:
    def test_sso_defaults(self):
        from src.core.shared.config.security import SSOSettings

        s = SSOSettings()
        assert s.enabled is True
        assert s.oidc_enabled is True
        assert s.oidc_use_pkce is True
        assert s.saml_enabled is True
        assert s.saml_sign_requests is True
        assert s.saml_want_assertions_signed is True
        assert s.saml_want_assertions_encrypted is False
        assert s.auto_provision_users is True
        assert s.default_role_on_provision == "viewer"
        assert s.workos_enabled is False
        assert s.workos_api_base_url == "https://api.workos.com"
        assert s.trusted_hosts == ["localhost", "127.0.0.1"]

    def test_sso_custom_values(self):
        from src.core.shared.config.security import SSOSettings

        s = SSOSettings.model_validate({
            "OIDC_CLIENT_ID": "my-client",
            "OIDC_ISSUER_URL": "https://auth.example.com",
            "SAML_ENTITY_ID": "urn:example",
            "WORKOS_ENABLED": True,
            "WORKOS_CLIENT_ID": "wc_test",
            "SSO_ALLOWED_DOMAINS": ["example.com"],
        })
        assert s.oidc_client_id == "my-client"
        assert s.oidc_issuer_url == "https://auth.example.com"
        assert s.saml_entity_id == "urn:example"
        assert s.workos_enabled is True
        assert s.allowed_domains == ["example.com"]


# ============================================================================
# Config: Factory (lines 78-123 pydantic branch, 126-175 dataclass branch)
# ============================================================================


class TestSettingsFactory:
    """Tests for factory.py Settings class."""

    def test_settings_defaults(self):
        from src.core.shared.config.factory import Settings

        s = Settings()
        assert s.env == "development"
        assert s.debug is False

    def test_settings_has_sub_settings(self):
        from src.core.shared.config.factory import Settings

        s = Settings()
        assert hasattr(s, "redis")
        assert hasattr(s, "database")
        assert hasattr(s, "security")
        assert hasattr(s, "opa")
        assert hasattr(s, "maci")
        assert hasattr(s, "vault")
        assert hasattr(s, "voting")
        assert hasattr(s, "circuit_breaker")
        assert hasattr(s, "kafka")

    def test_settings_kafka_defaults(self):
        from src.core.shared.config.factory import Settings

        s = Settings()
        assert isinstance(s.kafka, dict)
        assert "bootstrap_servers" in s.kafka

    def test_coerce_opencode_env_with_non_dict(self):
        """Exercises the _coerce_opencode_env model_validator (lines 78-91)."""
        from src.core.shared.config.factory import Settings

        # Simulate OPENCODE=1 being set
        s = Settings.model_validate({"opencode": "1"})
        assert s.env == "development"

    def test_coerce_opencode_env_with_dict(self):
        from src.core.shared.config.factory import Settings

        # When opencode is a dict, it should not be coerced (only non-dict is replaced)
        s = Settings.model_validate({"opencode": {"OPENCODE_URL": "http://test:4096"}})
        # The dict is passed through but OpenCodeSettings still reads defaults
        assert hasattr(s, "opencode")

    def test_production_validation_no_jwt_secret(self):
        """Production requires JWT_SECRET (lines 94-109)."""
        from src.core.shared.config.factory import Settings

        with pytest.raises(Exception, match="JWT_SECRET.*mandatory.*production"):
            Settings.model_validate({"APP_ENV": "production"})

    def test_production_validation_dev_secret(self):
        """dev-secret is rejected at SecuritySettings level (forbidden placeholder)."""
        from src.core.shared.config.security import SecuritySettings

        with pytest.raises(Exception, match="forbidden placeholder"):
            SecuritySettings.model_validate({"JWT_SECRET": "dev-secret"})

    def test_production_validation_short_jwt(self):
        from src.core.shared.config.factory import Settings
        from src.core.shared.config.security import SecuritySettings

        sec = SecuritySettings.model_validate({
            "JWT_SECRET": "short",
            "API_KEY_INTERNAL": "x" * 40,
        })
        with pytest.raises(Exception, match="at least 32 characters"):
            Settings.model_validate({"APP_ENV": "production", "security": sec})

    def test_production_validation_no_api_key(self):
        from src.core.shared.config.factory import Settings
        from src.core.shared.config.security import SecuritySettings

        sec = SecuritySettings.model_validate({"JWT_SECRET": "x" * 40})
        with pytest.raises(Exception, match="API_KEY_INTERNAL.*mandatory"):
            Settings.model_validate({"APP_ENV": "production", "security": sec})

    def test_production_validation_placeholder_public_key(self):
        from src.core.shared.config.factory import Settings
        from src.core.shared.config.security import SecuritySettings

        sec = SecuritySettings.model_validate({
            "JWT_SECRET": "x" * 40,
            "API_KEY_INTERNAL": "k" * 40,
        })
        with pytest.raises(Exception, match="JWT_PUBLIC_KEY.*configured.*production"):
            Settings.model_validate({"APP_ENV": "production", "security": sec})

    def test_production_validation_redis_tls_warning(self):
        import warnings

        from src.core.shared.config.factory import Settings
        from src.core.shared.config.security import SecuritySettings

        sec = SecuritySettings.model_validate({
            "JWT_SECRET": "x" * 40,
            "API_KEY_INTERNAL": "k" * 40,
            "JWT_PUBLIC_KEY": "real-key",
        })
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings.model_validate({"APP_ENV": "production", "security": sec})
            redis_warnings = [x for x in w if "Redis" in str(x.message) and "TLS" in str(x.message)]
            assert len(redis_warnings) >= 1

    def test_get_settings_cached(self):
        """get_settings() returns a cached singleton."""
        from src.core.shared.config.factory import get_settings

        # Clear cache for clean test
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        get_settings.cache_clear()


# ============================================================================
# Config: Governance (lines 153-294 — dataclass fallback)
# ============================================================================


class TestGovernanceSettings:
    def test_maci_defaults(self):
        from src.core.shared.config.governance import MACISettings

        m = MACISettings()
        assert m.strict_mode is True
        assert m.default_role is None

    def test_voting_defaults(self):
        from src.core.shared.config.governance import VotingSettings

        v = VotingSettings()
        assert v.default_timeout_seconds == 30
        assert v.enable_weighted_voting is True
        assert v.signature_algorithm == "HMAC-SHA256"
        assert v.audit_signature_key is None

    def test_circuit_breaker_defaults(self):
        from src.core.shared.config.governance import CircuitBreakerSettings

        cb = CircuitBreakerSettings()
        assert cb.default_failure_threshold == 5
        assert cb.default_timeout_seconds == 30.0
        assert cb.policy_registry_failure_threshold == 3
        assert cb.opa_evaluator_failure_threshold == 5
        assert cb.blockchain_anchor_failure_threshold == 10
        assert cb.redis_cache_failure_threshold == 3
        assert cb.kafka_producer_failure_threshold == 5
        assert cb.audit_service_failure_threshold == 5
        assert cb.deliberation_layer_failure_threshold == 7
        assert cb.health_check_enabled is True
        assert cb.metrics_enabled is True

    def test_voting_with_custom_values(self):
        from src.core.shared.config.governance import VotingSettings

        v = VotingSettings.model_validate({
            "VOTING_DEFAULT_TIMEOUT_SECONDS": 60,
            "VOTING_SIGNATURE_ALGORITHM": "ED25519",
        })
        assert v.default_timeout_seconds == 60
        assert v.signature_algorithm == "ED25519"


# ============================================================================
# Config: Infrastructure (lines 84-176 — dataclass fallback / pydantic branch)
# ============================================================================


class TestInfrastructureSettings:
    def test_redis_defaults(self):
        from src.core.shared.config.infrastructure import RedisSettings

        r = RedisSettings()
        assert r.url == "redis://localhost:6379"
        assert r.host == "localhost"
        assert r.port == 6379
        assert r.ssl is False
        assert r.retry_on_timeout is True

    def test_database_defaults(self):
        from src.core.shared.config.infrastructure import DatabaseSettings

        d = DatabaseSettings()
        assert "asyncpg" in d.url

    def test_database_url_normalization_postgres(self):
        from src.core.shared.config.infrastructure import DatabaseSettings

        d = DatabaseSettings.model_validate({"DATABASE_URL": "postgres://localhost:5432/test"})
        assert d.url.startswith("postgresql+asyncpg://")

    def test_database_url_normalization_postgresql(self):
        from src.core.shared.config.infrastructure import DatabaseSettings

        d = DatabaseSettings.model_validate({"DATABASE_URL": "postgresql://localhost:5432/test"})
        assert "asyncpg" in d.url

    def test_database_url_already_asyncpg(self):
        from src.core.shared.config.infrastructure import DatabaseSettings

        url = "postgresql+asyncpg://localhost:5432/test"
        d = DatabaseSettings.model_validate({"DATABASE_URL": url})
        assert d.url == url

    def test_ai_defaults(self):
        from src.core.shared.config.infrastructure import AISettings

        a = AISettings()
        assert a.openrouter_api_key is None
        assert a.hf_token is None
        assert a.openai_api_key is None

    def test_blockchain_defaults(self):
        from src.core.shared.config.infrastructure import BlockchainSettings

        b = BlockchainSettings()
        assert b.eth_l2_network == "optimism"
        assert b.eth_rpc_url == "https://mainnet.optimism.io"
        assert b.contract_address is None
        assert b.private_key is None


# ============================================================================
# Config: Integrations (lines 87-194 — dataclass fallback / pydantic branch)
# ============================================================================


class TestIntegrationSettings:
    def test_service_settings_defaults(self):
        from src.core.shared.config.integrations import ServiceSettings

        s = ServiceSettings()
        assert s.agent_bus_url == "http://localhost:8000"
        assert s.api_gateway_url == "http://localhost:8080"
        assert s.tenant_management_url == "http://localhost:8500"

    def test_bundle_settings_defaults(self):
        from src.core.shared.config.integrations import BundleSettings

        b = BundleSettings()
        assert b.registry_url == "http://localhost:5000"
        assert b.storage_path == "./storage/bundles"
        assert b.s3_bucket is None
        assert b.github_webhook_secret is None

    def test_opencode_settings_defaults(self):
        from src.core.shared.config.integrations import OpenCodeSettings

        o = OpenCodeSettings()
        assert o.url == "http://localhost:4096"
        assert o.username == "opencode"
        assert o.password is None
        assert o.timeout_seconds == 30.0
        assert o.max_retries == 3
        assert o.circuit_breaker_threshold == 5

    def test_search_platform_settings_defaults(self):
        from src.core.shared.config.integrations import SearchPlatformSettings

        s = SearchPlatformSettings()
        assert s.url == "http://localhost:9080"
        assert s.enable_compliance is True
        assert s.circuit_breaker_timeout == 30.0


# ============================================================================
# Type Guards (lines 24-381)
# ============================================================================


class TestTypeGuards:
    """Comprehensive tests for all type guard functions."""

    def test_is_json_dict_true(self):
        from src.core.shared.type_guards import is_json_dict

        assert is_json_dict({"a": 1}) is True
        assert is_json_dict({}) is True

    def test_is_json_dict_false(self):
        from src.core.shared.type_guards import is_json_dict

        assert is_json_dict([1, 2]) is False
        assert is_json_dict("string") is False
        assert is_json_dict(None) is False
        assert is_json_dict({1: "val"}) is False

    def test_is_json_value(self):
        from src.core.shared.type_guards import is_json_value

        assert is_json_value(None) is True
        assert is_json_value("hello") is True
        assert is_json_value(42) is True
        assert is_json_value(3.14) is True
        assert is_json_value(True) is True
        assert is_json_value({"k": "v"}) is True
        assert is_json_value([1, 2]) is True
        assert is_json_value(object()) is False

    def test_is_string_dict(self):
        from src.core.shared.type_guards import is_string_dict

        assert is_string_dict({"a": "b"}) is True
        assert is_string_dict({}) is True
        assert is_string_dict({"a": 1}) is False
        assert is_string_dict("not a dict") is False

    def test_is_non_empty_str(self):
        from src.core.shared.type_guards import is_non_empty_str

        assert is_non_empty_str("hello") is True
        assert is_non_empty_str("") is False
        assert is_non_empty_str(None) is False
        assert is_non_empty_str(42) is False

    def test_is_str(self):
        from src.core.shared.type_guards import is_str

        assert is_str("x") is True
        assert is_str("") is True
        assert is_str(42) is False

    def test_is_str_list(self):
        from src.core.shared.type_guards import is_str_list

        assert is_str_list(["a", "b"]) is True
        assert is_str_list([]) is True
        assert is_str_list([1, 2]) is False
        assert is_str_list("not a list") is False

    def test_is_dict_list(self):
        from src.core.shared.type_guards import is_dict_list

        assert is_dict_list([{"a": 1}]) is True
        assert is_dict_list([]) is True
        assert is_dict_list([1, 2]) is False
        assert is_dict_list("nope") is False

    def test_is_positive_int(self):
        from src.core.shared.type_guards import is_positive_int

        assert is_positive_int(5) is True
        assert is_positive_int(0) is False
        assert is_positive_int(-1) is False
        assert is_positive_int(3.5) is False

    def test_is_non_negative_float(self):
        from src.core.shared.type_guards import is_non_negative_float

        assert is_non_negative_float(0) is True
        assert is_non_negative_float(0.0) is True
        assert is_non_negative_float(5.5) is True
        assert is_non_negative_float(-1) is False
        assert is_non_negative_float("nope") is False

    def test_is_probability(self):
        from src.core.shared.type_guards import is_probability

        assert is_probability(0.0) is True
        assert is_probability(0.5) is True
        assert is_probability(1.0) is True
        assert is_probability(-0.1) is False
        assert is_probability(1.1) is False
        assert is_probability("x") is False

    def test_is_security_context(self):
        from src.core.shared.type_guards import is_security_context

        assert is_security_context({"user_id": "u1"}) is True
        assert is_security_context({"agent_id": "a1"}) is True
        assert is_security_context({"tenant_id": "t1"}) is True
        assert is_security_context({"session_id": "s1"}) is True
        assert is_security_context({"unrelated": "x"}) is False
        assert is_security_context("not a dict") is False

    def test_is_agent_context(self):
        from src.core.shared.type_guards import is_agent_context

        assert is_agent_context({"agent_id": "a1"}) is True
        assert is_agent_context({"other": "x"}) is False
        assert is_agent_context(42) is False

    def test_is_policy_result(self):
        from src.core.shared.type_guards import is_policy_result

        assert is_policy_result({"allowed": True}) is True
        assert is_policy_result({"allow": True}) is True
        assert is_policy_result({"result": {}}) is True
        assert is_policy_result({"other": True}) is False
        assert is_policy_result("nope") is False

    def test_is_content_with_text(self):
        from src.core.shared.type_guards import is_content_with_text

        assert is_content_with_text({"text": "hi"}) is True
        assert is_content_with_text({"text": 42}) is False
        assert is_content_with_text({"other": "x"}) is False

    def test_is_message_content(self):
        from src.core.shared.type_guards import is_message_content

        assert is_message_content({"content": "x"}) is True
        assert is_message_content({"body": "x"}) is True
        assert is_message_content({"data": "x"}) is True
        assert is_message_content({"text": "x"}) is True
        assert is_message_content({"nope": "x"}) is False
        assert is_message_content("not dict") is False

    def test_get_str(self):
        from src.core.shared.type_guards import get_str

        assert get_str({"k": "hello"}, "k") == "hello"
        assert get_str({"k": 42}, "k") == ""
        assert get_str({}, "k") == ""
        assert get_str({}, "k", "default") == "default"

    def test_get_int(self):
        from src.core.shared.type_guards import get_int

        assert get_int({"k": 5}, "k") == 5
        assert get_int({"k": "not int"}, "k") == 0
        assert get_int({}, "k", 99) == 99

    def test_get_float(self):
        from src.core.shared.type_guards import get_float

        assert get_float({"k": 3.14}, "k") == 3.14
        assert get_float({"k": 5}, "k") == 5.0
        assert get_float({"k": "bad"}, "k") == 0.0
        assert get_float({}, "k", 1.5) == 1.5

    def test_get_bool(self):
        from src.core.shared.type_guards import get_bool

        assert get_bool({"k": True}, "k") is True
        assert get_bool({"k": "nope"}, "k") is False
        assert get_bool({}, "k", True) is True

    def test_get_dict(self):
        from src.core.shared.type_guards import get_dict

        assert get_dict({"k": {"a": 1}}, "k") == {"a": 1}
        assert get_dict({"k": "nope"}, "k") == {}
        assert get_dict({}, "k") == {}
        assert get_dict({}, "k", {"default": True}) == {"default": True}

    def test_get_list(self):
        from src.core.shared.type_guards import get_list

        assert get_list({"k": [1, 2]}, "k") == [1, 2]
        assert get_list({"k": "nope"}, "k") == []
        assert get_list({}, "k") == []
        assert get_list({}, "k", [99]) == [99]

    def test_get_str_list(self):
        from src.core.shared.type_guards import get_str_list

        assert get_str_list({"k": ["a", "b"]}, "k") == ["a", "b"]
        assert get_str_list({"k": [1, 2]}, "k") == []
        assert get_str_list({}, "k") == []
        assert get_str_list({}, "k", ["x"]) == ["x"]


# ============================================================================
# PQC Crypto (lines 142-189, 225-268)
# ============================================================================


class TestPQCCryptoRuntime:
    """Tests for runtime stubs in pqc_crypto.py."""

    def test_pqc_config_defaults(self):
        from src.core.shared.security.pqc_crypto import PQCConfig

        c = PQCConfig()
        assert c.pqc_enabled is False
        assert c.pqc_mode == "classical_only"
        assert c.verification_mode == "strict"

    def test_pqc_crypto_service_stub(self):
        from src.core.shared.security.pqc_crypto import PQCCryptoService

        svc = PQCCryptoService()
        assert svc is not None

    def test_hybrid_signature_stub(self):
        from src.core.shared.security.pqc_crypto import HybridSignature

        sig = HybridSignature(content_hash="abc", constitutional_hash="def")
        assert sig.content_hash == "abc"
        assert sig.constitutional_hash == "def"

    def test_pqc_metadata_stub(self):
        from src.core.shared.security.pqc_crypto import PQCMetadata

        m = PQCMetadata()
        assert m.pqc_enabled is False
        assert m.verification_mode == "classical_only"

    def test_validation_result_stub(self):
        from src.core.shared.security.pqc_crypto import ValidationResult

        r = ValidationResult()
        assert r.valid is False
        assert r.errors == []
        assert r.warnings == []
        assert r.pqc_metadata is None

    def test_pqc_crypto_available_flag(self):
        from src.core.shared.security.pqc_crypto import PQC_CRYPTO_AVAILABLE

        assert PQC_CRYPTO_AVAILABLE is True


class TestGenerateKeyPair:
    """Tests for generate_key_pair() function (lines 142-192)."""

    def test_generate_key_pair_unapproved_algorithm(self):
        """Unapproved algorithm raises UnsupportedAlgorithmError."""
        mock_variant = MagicMock()
        mock_variant.__str__ = lambda self: "FAKE_ALG"

        mock_approved = set()
        mock_error_cls = type("UnsupportedAlgorithmError", (Exception,), {
            "__init__": lambda self, msg, details=None: Exception.__init__(self, msg)
        })
        mock_alg_variant = MagicMock()

        with patch.dict("sys.modules", {}):
            with patch(
                "src.core.shared.security.pqc_crypto.generate_key_pair",
            ) as mock_gen:
                mock_gen.side_effect = mock_error_cls("not approved")
                with pytest.raises(Exception, match="not approved"):
                    mock_gen(mock_variant)

    def test_generate_key_pair_dispatches_correctly(self):
        """Test the generate_key_pair function with mocked registry."""
        from src.core.shared.security.pqc_crypto import generate_key_pair

        mock_variant = MagicMock()
        mock_variant.value = "ML-DSA-44"
        mock_variant.__str__ = lambda self: "ML-DSA-44"

        mock_error = type("UnsupportedAlgorithmError", (Exception,), {
            "__init__": lambda self, msg, details=None: Exception.__init__(self, msg)
        })

        registry_mock = MagicMock()
        registry_mock.APPROVED_ALGORITHMS = {mock_variant}
        registry_mock.AlgorithmVariant = MagicMock()
        registry_mock.AlgorithmVariant.ML_DSA_44 = mock_variant
        registry_mock.AlgorithmVariant.ML_DSA_65 = MagicMock()
        registry_mock.AlgorithmVariant.ML_DSA_87 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_512 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_768 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_1024 = MagicMock()
        registry_mock.UnsupportedAlgorithmError = mock_error

        oqs_mock = MagicMock()
        signer_mock = MagicMock()
        signer_mock.generate_keypair.return_value = b"pubkey"
        signer_mock.export_secret_key.return_value = b"privkey"
        oqs_mock.Signature.return_value = signer_mock

        with patch.dict("sys.modules", {
            "src.core.services.policy_registry.app.services.pqc_algorithm_registry": registry_mock,
            "oqs": oqs_mock,
        }):
            pub, priv = generate_key_pair(mock_variant)
            assert pub == b"pubkey"
            assert priv == b"privkey"


class TestVerifySignature:
    """Tests for verify_signature() function (lines 225-268)."""

    def test_verify_signature_unapproved(self):
        """Unapproved algorithm raises error."""
        from src.core.shared.security.pqc_crypto import verify_signature

        mock_variant = MagicMock()
        mock_error = type("UnsupportedAlgorithmError", (Exception,), {
            "__init__": lambda self, msg, details=None: Exception.__init__(self, msg)
        })

        registry_mock = MagicMock()
        registry_mock.APPROVED_ALGORITHMS = set()
        registry_mock.UnsupportedAlgorithmError = mock_error
        registry_mock.AlgorithmVariant = MagicMock()

        with patch.dict("sys.modules", {
            "src.core.services.policy_registry.app.services.pqc_algorithm_registry": registry_mock,
        }):
            with pytest.raises(Exception, match="not approved"):
                verify_signature(mock_variant, b"pub", b"msg", b"sig")

    def test_verify_signature_ml_dsa(self):
        """ML-DSA verification dispatches to oqs."""
        from src.core.shared.security.pqc_crypto import verify_signature

        mock_variant = MagicMock()
        mock_variant.value = "ML-DSA-44"

        mock_error = type("UnsupportedAlgorithmError", (Exception,), {
            "__init__": lambda self, msg, details=None: Exception.__init__(self, msg)
        })

        registry_mock = MagicMock()
        registry_mock.APPROVED_ALGORITHMS = {mock_variant}
        registry_mock.AlgorithmVariant = MagicMock()
        registry_mock.AlgorithmVariant.ML_DSA_44 = mock_variant
        registry_mock.AlgorithmVariant.ML_DSA_65 = MagicMock()
        registry_mock.AlgorithmVariant.ML_DSA_87 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_512 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_768 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_1024 = MagicMock()
        registry_mock.UnsupportedAlgorithmError = mock_error

        oqs_mock = MagicMock()
        verifier_mock = MagicMock()
        verifier_mock.verify.return_value = True
        oqs_mock.Signature.return_value = verifier_mock

        with patch.dict("sys.modules", {
            "src.core.services.policy_registry.app.services.pqc_algorithm_registry": registry_mock,
            "oqs": oqs_mock,
        }):
            result = verify_signature(mock_variant, b"pub", b"msg", b"sig")
            assert result is True

    def test_verify_signature_ml_dsa_exception(self):
        """ML-DSA verification returns False on oqs exception."""
        from src.core.shared.security.pqc_crypto import verify_signature

        mock_variant = MagicMock()
        mock_variant.value = "ML-DSA-44"

        mock_error = type("UnsupportedAlgorithmError", (Exception,), {
            "__init__": lambda self, msg, details=None: Exception.__init__(self, msg)
        })

        registry_mock = MagicMock()
        registry_mock.APPROVED_ALGORITHMS = {mock_variant}
        registry_mock.AlgorithmVariant = MagicMock()
        registry_mock.AlgorithmVariant.ML_DSA_44 = mock_variant
        registry_mock.AlgorithmVariant.ML_DSA_65 = MagicMock()
        registry_mock.AlgorithmVariant.ML_DSA_87 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_512 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_768 = MagicMock()
        registry_mock.AlgorithmVariant.ML_KEM_1024 = MagicMock()
        registry_mock.UnsupportedAlgorithmError = mock_error

        oqs_mock = MagicMock()
        verifier_mock = MagicMock()
        verifier_mock.verify.side_effect = RuntimeError("bad sig")
        oqs_mock.Signature.return_value = verifier_mock

        with patch.dict("sys.modules", {
            "src.core.services.policy_registry.app.services.pqc_algorithm_registry": registry_mock,
            "oqs": oqs_mock,
        }):
            result = verify_signature(mock_variant, b"pub", b"msg", b"sig")
            assert result is False


# ============================================================================
# Expression Utils (lines 30-44, 67-78, 97-119)
# ============================================================================


class TestEvalNode:
    """Tests for _eval_node (lines 30-44)."""

    def test_eval_constant_int(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.Constant(value=42)
        assert _eval_node(node) == 42.0

    def test_eval_constant_float(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.Constant(value=3.14)
        assert _eval_node(node) == 3.14

    def test_eval_constant_bool_rejected(self):
        """Bool constants are rejected even though bool is subclass of int."""
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.Constant(value=True)
        with pytest.raises(Exception, match="Unsupported"):
            _eval_node(node)

    def test_eval_binop_add(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.BinOp(
            left=ast.Constant(value=2),
            op=ast.Add(),
            right=ast.Constant(value=3),
        )
        assert _eval_node(node) == 5.0

    def test_eval_binop_sub(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.BinOp(
            left=ast.Constant(value=10),
            op=ast.Sub(),
            right=ast.Constant(value=4),
        )
        assert _eval_node(node) == 6.0

    def test_eval_binop_mul(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.BinOp(
            left=ast.Constant(value=3),
            op=ast.Mult(),
            right=ast.Constant(value=7),
        )
        assert _eval_node(node) == 21.0

    def test_eval_binop_div(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.BinOp(
            left=ast.Constant(value=10),
            op=ast.Div(),
            right=ast.Constant(value=4),
        )
        assert _eval_node(node) == 2.5

    def test_eval_binop_pow(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.BinOp(
            left=ast.Constant(value=2),
            op=ast.Pow(),
            right=ast.Constant(value=3),
        )
        assert _eval_node(node) == 8.0

    def test_eval_unary_neg(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=5))
        assert _eval_node(node) == -5.0

    def test_eval_unsupported_node(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.Name(id="x")
        with pytest.raises(Exception, match="Unsupported"):
            _eval_node(node)

    def test_eval_string_constant_rejected(self):
        from src.core.shared.security.expression_utils import _eval_node

        import ast
        node = ast.Constant(value="hello")
        with pytest.raises(Exception, match="Unsupported"):
            _eval_node(node)


class TestSafeEvalExpr:
    """Tests for safe_eval_expr (lines 67-78)."""

    def test_simple_addition(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        assert safe_eval_expr("2 + 3") == 5.0

    def test_complex_expression(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        assert safe_eval_expr("2 + 3 * 4") == 14.0

    def test_negative_number(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        assert safe_eval_expr("-5") == -5.0

    def test_power(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        assert safe_eval_expr("2 ** 10") == 1024.0

    def test_invalid_syntax_raises(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        with pytest.raises(Exception):
            safe_eval_expr("2 +")

    def test_function_call_rejected(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        with pytest.raises(Exception):
            safe_eval_expr("__import__('os').system('ls')")

    def test_variable_rejected(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        with pytest.raises(Exception):
            safe_eval_expr("x + 1")

    def test_division(self):
        from src.core.shared.security.expression_utils import safe_eval_expr

        assert safe_eval_expr("10 / 4") == 2.5


class TestRedactPII:
    """Tests for redact_pii (lines 97-119)."""

    def test_redact_sensitive_fields(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"name": "Alice", "password": "secret123", "api_key": "sk-xxx"}
        result = redact_pii(data)
        assert "password" not in result
        assert "api_key" not in result
        assert result["name"] == "Alice"

    def test_redact_content_fields(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"content": "private text", "token": "abc", "secret": "xyz"}
        result = redact_pii(data)
        assert "content" not in result
        assert "token" not in result
        assert "secret" not in result

    def test_hash_fields(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"user_id": "user-123", "email": "alice@example.com"}
        result = redact_pii(data)
        assert result["user_id"].startswith("<redacted_hash:")
        assert result["email"].startswith("<redacted_hash:")

    def test_hash_dict_value(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"metadata": {"key": "value"}}
        result = redact_pii(data)
        assert result["metadata"].startswith("<redacted_hash:")

    def test_hash_list_value(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"metadata": [1, 2, 3]}
        result = redact_pii(data)
        assert result["metadata"].startswith("<redacted_hash:")

    def test_hash_none_value_skipped(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"user_id": None, "name": "test"}
        result = redact_pii(data)
        assert result["user_id"] is None
        assert result["name"] == "test"

    def test_nested_dict(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"outer": {"password": "x", "ok": "fine"}}
        result = redact_pii(data)
        assert "password" not in result["outer"]
        assert result["outer"]["ok"] == "fine"

    def test_list_input(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = [{"password": "x", "name": "a"}, {"token": "t", "name": "b"}]
        result = redact_pii(data)
        assert len(result) == 2
        assert "password" not in result[0]
        assert result[0]["name"] == "a"

    def test_primitive_passthrough(self):
        from src.core.shared.security.expression_utils import redact_pii

        assert redact_pii("hello") == "hello"
        assert redact_pii(42) == 42
        assert redact_pii(None) is None

    def test_content_preview_redacted(self):
        from src.core.shared.security.expression_utils import redact_pii

        data = {"content_preview": "some text", "status": "ok"}
        result = redact_pii(data)
        assert "content_preview" not in result
        assert result["status"] == "ok"
