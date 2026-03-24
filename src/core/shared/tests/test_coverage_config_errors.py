"""
Tests for under-covered src/core/shared modules.

Covers: config/, errors/, feature_flags, schema_registry, interfaces,
        types/protocol_types, constants, di_container, api_versioning.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError

from src.core.shared.constants import (
    COMPLIANCE_TARGET,
    CONSTITUTIONAL_HASH,
    CONSTITUTIONAL_HASH_VERSIONED,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MESSAGE_TTL_SECONDS,
    DEFAULT_REDIS_DB,
    DEFAULT_REDIS_URL,
    DEFAULT_TIMEOUT_MS,
    HOTL_OVERRIDE_WINDOW_SECONDS,
    MIN_CACHE_HIT_RATE,
    MIN_THROUGHPUT_RPS,
    P99_LATENCY_TARGET_MS,
    RISK_TIER_HIGH_MIN,
    RISK_TIER_LOW_MAX,
    MACIRole,
    RiskTier,
    classify_risk_tier,
    get_constitutional_hash,
)

# ============================================================================
# constants.py
# ============================================================================


class TestConstants:
    def test_constitutional_hash_value(self):
        assert CONSTITUTIONAL_HASH == "cdd01ef066bc6cf2"

    def test_constitutional_hash_versioned(self):
        assert CONSTITUTIONAL_HASH_VERSIONED == "sha256:v1:cdd01ef066bc6cf2"

    def test_get_constitutional_hash(self):
        assert get_constitutional_hash() == CONSTITUTIONAL_HASH

    def test_default_redis_url(self):
        assert DEFAULT_REDIS_URL == "redis://localhost:6379"

    def test_default_redis_db(self):
        assert DEFAULT_REDIS_DB == 0

    def test_performance_targets(self):
        assert P99_LATENCY_TARGET_MS == 5.0
        assert MIN_THROUGHPUT_RPS == 100
        assert MIN_CACHE_HIT_RATE == 0.85

    def test_message_bus_defaults(self):
        assert DEFAULT_MESSAGE_TTL_SECONDS == 3600
        assert DEFAULT_MAX_RETRIES == 3
        assert DEFAULT_TIMEOUT_MS == 5000

    def test_compliance_target(self):
        assert COMPLIANCE_TARGET == 1.0

    def test_hotl_override_window(self):
        assert HOTL_OVERRIDE_WINDOW_SECONDS == 900

    def test_risk_tier_thresholds(self):
        assert RISK_TIER_LOW_MAX == 0.3
        assert RISK_TIER_HIGH_MIN == 0.8


class TestRiskTier:
    def test_enum_values(self):
        assert RiskTier.LOW == "low"
        assert RiskTier.MEDIUM == "medium"
        assert RiskTier.HIGH == "high"

    def test_classify_low(self):
        assert classify_risk_tier(0.0) == RiskTier.LOW
        assert classify_risk_tier(0.29) == RiskTier.LOW

    def test_classify_medium(self):
        assert classify_risk_tier(0.3) == RiskTier.MEDIUM
        assert classify_risk_tier(0.5) == RiskTier.MEDIUM
        assert classify_risk_tier(0.79) == RiskTier.MEDIUM

    def test_classify_high(self):
        assert classify_risk_tier(0.8) == RiskTier.HIGH
        assert classify_risk_tier(1.0) == RiskTier.HIGH


class TestMACIRole:
    def test_all_roles(self):
        assert MACIRole.EXECUTIVE == "EXECUTIVE"
        assert MACIRole.LEGISLATIVE == "LEGISLATIVE"
        assert MACIRole.JUDICIAL == "JUDICIAL"
        assert MACIRole.MONITOR == "MONITOR"
        assert MACIRole.AUDITOR == "AUDITOR"
        assert MACIRole.CONTROLLER == "CONTROLLER"
        assert MACIRole.IMPLEMENTER == "IMPLEMENTER"

    def test_case_insensitive_construction(self):
        assert MACIRole("executive") == MACIRole.EXECUTIVE
        assert MACIRole("Executive") == MACIRole.EXECUTIVE

    def test_parse_from_string(self):
        assert MACIRole.parse("EXECUTIVE") == MACIRole.EXECUTIVE
        assert MACIRole.parse("judicial") == MACIRole.JUDICIAL

    def test_parse_from_enum(self):
        assert MACIRole.parse(MACIRole.MONITOR) == MACIRole.MONITOR

    def test_missing_invalid(self):
        with pytest.raises(ValueError):
            MACIRole("nonexistent_role")

    def test_missing_empty_string(self):
        with pytest.raises(ValueError):
            MACIRole("")


# ============================================================================
# config/profiles.py
# ============================================================================


class TestConfigProfile:
    def test_dev_profile(self):
        from src.core.shared.config.profiles import ConfigProfile

        profile = ConfigProfile.dev()
        assert profile.name == "dev"
        assert profile.debug is True
        assert profile.log_level == "DEBUG"
        assert profile.security_strict is False
        assert profile.hsts_enabled is False
        assert profile.hsts_max_age == 0
        assert profile.cors_allow_all is True
        assert profile.rate_limit_multiplier == 10.0
        assert profile.enable_profiling is True

    def test_staging_profile(self):
        from src.core.shared.config.profiles import ConfigProfile

        profile = ConfigProfile.staging()
        assert profile.name == "staging"
        assert profile.debug is False
        assert profile.log_level == "INFO"
        assert profile.security_strict is True
        assert profile.hsts_enabled is True
        assert profile.hsts_max_age == 86400
        assert profile.cors_allow_all is False
        assert profile.rate_limit_multiplier == 2.0

    def test_production_profile(self):
        from src.core.shared.config.profiles import ConfigProfile

        profile = ConfigProfile.production()
        assert profile.name == "production"
        assert profile.debug is False
        assert profile.log_level == "WARNING"
        assert profile.security_strict is True
        assert profile.hsts_enabled is True
        assert profile.hsts_max_age == 31536000
        assert profile.cors_allow_all is False
        assert profile.rate_limit_multiplier == 1.0

    def test_from_env_dev(self):
        from src.core.shared.config.profiles import ConfigProfile

        with patch.dict(os.environ, {"ACGS_ENV": "dev"}):
            profile = ConfigProfile.from_env()
            assert profile.name == "dev"

    def test_from_env_development(self):
        from src.core.shared.config.profiles import ConfigProfile

        with patch.dict(os.environ, {"ACGS_ENV": "development"}):
            profile = ConfigProfile.from_env()
            assert profile.name == "dev"

    def test_from_env_staging(self):
        from src.core.shared.config.profiles import ConfigProfile

        with patch.dict(os.environ, {"ACGS_ENV": "staging"}):
            profile = ConfigProfile.from_env()
            assert profile.name == "staging"

    def test_from_env_production(self):
        from src.core.shared.config.profiles import ConfigProfile

        with patch.dict(os.environ, {"ACGS_ENV": "prod"}):
            profile = ConfigProfile.from_env()
            assert profile.name == "production"

    def test_from_env_production_full(self):
        from src.core.shared.config.profiles import ConfigProfile

        with patch.dict(os.environ, {"ACGS_ENV": "production"}):
            profile = ConfigProfile.from_env()
            assert profile.name == "production"

    def test_from_env_unknown_falls_back(self):
        from src.core.shared.config.profiles import ConfigProfile

        with patch.dict(os.environ, {"ACGS_ENV": "unknown_env"}):
            profile = ConfigProfile.from_env()
            assert profile.name == "dev"

    def test_from_env_unset_falls_back(self):
        from src.core.shared.config.profiles import ConfigProfile

        with patch.dict(os.environ, {}, clear=False):
            env_backup = os.environ.pop("ACGS_ENV", None)
            try:
                profile = ConfigProfile.from_env()
                assert profile.name == "dev"
            finally:
                if env_backup is not None:
                    os.environ["ACGS_ENV"] = env_backup

    def test_frozen_dataclass(self):
        from src.core.shared.config.profiles import ConfigProfile

        profile = ConfigProfile.dev()
        with pytest.raises(AttributeError):
            profile.name = "modified"


# ============================================================================
# config/redis.py
# ============================================================================


class TestRedisConfig:
    def test_defaults(self):
        from src.core.shared.config.redis import RedisConfig, RedisTopology

        cfg = RedisConfig()
        assert cfg.topology == RedisTopology.STANDALONE
        assert cfg.url == "redis://localhost:6379"
        assert cfg.db == 0
        assert cfg.sentinel_master is None
        assert cfg.sentinel_nodes == []
        assert cfg.cluster_nodes == []
        assert cfg.password is None
        assert cfg.ssl is False
        assert cfg.socket_timeout == 5.0
        assert cfg.retry_on_timeout is True
        assert cfg.max_connections == 50
        assert cfg.health_check_interval == 30

    def test_topology_enum(self):
        from src.core.shared.config.redis import RedisTopology

        assert RedisTopology.STANDALONE == "standalone"
        assert RedisTopology.SENTINEL == "sentinel"
        assert RedisTopology.CLUSTER == "cluster"

    def test_csv_parsing_string(self):
        from src.core.shared.config.redis import RedisConfig

        cfg = RedisConfig(sentinel_nodes="host1:26379, host2:26379, host3:26379")
        assert cfg.sentinel_nodes == ["host1:26379", "host2:26379", "host3:26379"]

    def test_csv_parsing_list(self):
        from src.core.shared.config.redis import RedisConfig

        cfg = RedisConfig(cluster_nodes=["r1:6379", "r2:6379"])
        assert cfg.cluster_nodes == ["r1:6379", "r2:6379"]

    def test_csv_parsing_other_type(self):
        from src.core.shared.config.redis import RedisConfig

        cfg = RedisConfig(sentinel_nodes=123)
        assert cfg.sentinel_nodes == []

    def test_get_connection_kwargs_basic(self):
        from src.core.shared.config.redis import RedisConfig

        cfg = RedisConfig()
        kwargs = cfg.get_connection_kwargs()
        assert "socket_timeout" in kwargs
        assert "retry_on_timeout" in kwargs
        assert "password" not in kwargs
        assert "ssl" not in kwargs

    def test_get_connection_kwargs_with_password_and_ssl(self):
        from src.core.shared.config.redis import RedisConfig

        cfg = RedisConfig(password="secret", ssl=True)
        kwargs = cfg.get_connection_kwargs()
        assert kwargs["password"] == "secret"
        assert kwargs["ssl"] is True

    def test_from_env_defaults(self):
        from src.core.shared.config.redis import RedisConfig

        with patch.dict(os.environ, {}, clear=False):
            for key in [
                "REDIS_TOPOLOGY", "REDIS_URL", "REDIS_DB", "REDIS_PASSWORD",
                "REDIS_SSL", "REDIS_SENTINEL_MASTER", "REDIS_SENTINEL_NODES",
                "REDIS_SENTINEL_PASSWORD", "REDIS_CLUSTER_NODES",
                "REDIS_MAX_CONNECTIONS", "REDIS_SOCKET_TIMEOUT",
                "REDIS_SOCKET_CONNECT_TIMEOUT", "REDIS_RETRY_ON_TIMEOUT",
                "REDIS_HEALTH_CHECK_INTERVAL",
            ]:
                os.environ.pop(key, None)
            cfg = RedisConfig.from_env()
            assert cfg.topology.value == "standalone"

    def test_from_env_sentinel(self):
        from src.core.shared.config.redis import RedisConfig, RedisTopology

        env = {
            "REDIS_TOPOLOGY": "sentinel",
            "REDIS_SENTINEL_MASTER": "mymaster",
            "REDIS_SENTINEL_NODES": "s1:26379,s2:26379",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = RedisConfig.from_env()
            assert cfg.topology == RedisTopology.SENTINEL
            assert cfg.sentinel_master == "mymaster"
            assert len(cfg.sentinel_nodes) == 2

    def test_from_env_unknown_topology(self):
        from src.core.shared.config.redis import RedisConfig, RedisTopology

        with patch.dict(os.environ, {"REDIS_TOPOLOGY": "invalid_mode"}, clear=False):
            cfg = RedisConfig.from_env()
            assert cfg.topology == RedisTopology.STANDALONE


# ============================================================================
# config/overrides.py
# ============================================================================


class TestOverrides:
    def setup_method(self):
        from src.core.shared.config.overrides import clear_overrides
        clear_overrides()

    def teardown_method(self):
        from src.core.shared.config.overrides import clear_overrides
        clear_overrides()

    def test_set_and_get_override(self):
        from src.core.shared.config.overrides import get_override, set_override

        set_override("key1", "value1")
        assert get_override("key1") == "value1"

    def test_get_override_missing(self):
        from src.core.shared.config.overrides import get_override

        assert get_override("nonexistent") is None

    def test_clear_overrides(self):
        from src.core.shared.config.overrides import (
            clear_overrides,
            get_override,
            set_override,
        )

        set_override("k", "v")
        clear_overrides()
        assert get_override("k") is None

    def test_get_all_overrides(self):
        from src.core.shared.config.overrides import (
            get_all_overrides,
            set_override,
        )

        set_override("a", 1)
        set_override("b", 2)
        all_ov = get_all_overrides()
        assert all_ov == {"a": 1, "b": 2}

    def test_override_config_context_manager(self):
        from src.core.shared.config.overrides import (
            get_override,
            override_config,
            set_override,
        )

        set_override("x", "original")
        with override_config(x="temporary", y="new"):
            assert get_override("x") == "temporary"
            assert get_override("y") == "new"
        assert get_override("x") == "original"
        assert get_override("y") is None

    def test_config_override_class(self):
        from src.core.shared.config.overrides import (
            ConfigOverride,
            get_override,
            set_override,
        )

        set_override("a", "orig")
        with ConfigOverride(a="temp", b="temp2"):
            assert get_override("a") == "temp"
            assert get_override("b") == "temp2"
        assert get_override("a") == "orig"
        assert get_override("b") is None


# ============================================================================
# config/integrations.py
# ============================================================================


class TestIntegrations:
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

    def test_opencode_settings_defaults(self):
        from src.core.shared.config.integrations import OpenCodeSettings

        oc = OpenCodeSettings()
        assert oc.url == "http://localhost:4096"
        assert oc.username == "opencode"
        assert oc.timeout_seconds == 30.0
        assert oc.max_connections == 50
        assert oc.max_retries == 3
        assert oc.circuit_breaker_threshold == 5

    def test_search_platform_settings_defaults(self):
        from src.core.shared.config.integrations import SearchPlatformSettings

        sp = SearchPlatformSettings()
        assert sp.url == "http://localhost:9080"
        assert sp.timeout_seconds == 30.0
        assert sp.max_connections == 100
        assert sp.enable_compliance is True


# ============================================================================
# config/infrastructure.py
# ============================================================================


class TestInfrastructure:
    def test_redis_settings_defaults(self):
        from src.core.shared.config.infrastructure import RedisSettings

        r = RedisSettings()
        assert r.url == "redis://localhost:6379"
        assert r.host == "localhost"
        assert r.port == 6379
        assert r.db == 0
        assert r.ssl is False

    def test_database_settings_defaults(self):
        from src.core.shared.config.infrastructure import DatabaseSettings

        db = DatabaseSettings()
        assert "asyncpg" in db.url
        assert db.pool_pre_ping is True

    def test_database_url_normalization_postgres(self):
        from src.core.shared.config.infrastructure import HAS_PYDANTIC_SETTINGS, DatabaseSettings

        if HAS_PYDANTIC_SETTINGS:
            # Use validation_alias-based env var or direct field assignment
            with patch.dict(os.environ, {"DATABASE_URL": "postgres://localhost/test"}):
                db = DatabaseSettings()
            assert db.url.startswith("postgresql+asyncpg://")
        else:
            db = DatabaseSettings()
            db.url = "postgres://localhost/test"
            db.__post_init__()
            assert db.url.startswith("postgresql+asyncpg://")

    def test_database_url_normalization_postgresql(self):
        from src.core.shared.config.infrastructure import HAS_PYDANTIC_SETTINGS, DatabaseSettings

        if HAS_PYDANTIC_SETTINGS:
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"}):
                db = DatabaseSettings()
            assert "asyncpg" in db.url
        else:
            db = DatabaseSettings()
            db.url = "postgresql://localhost/test"
            db.__post_init__()
            assert "asyncpg" in db.url

    def test_ai_settings_defaults(self):
        from src.core.shared.config.infrastructure import AISettings

        ai = AISettings()
        assert ai.constitutional_hash == CONSTITUTIONAL_HASH

    def test_blockchain_settings_defaults(self):
        from src.core.shared.config.infrastructure import BlockchainSettings

        bc = BlockchainSettings()
        assert bc.eth_l2_network == "optimism"
        assert bc.eth_rpc_url == "https://mainnet.optimism.io"
        assert bc.contract_address is None
        assert bc.private_key is None


# ============================================================================
# config/security.py
# ============================================================================


class TestSecurity:
    def test_security_settings_defaults(self):
        from src.core.shared.config.security import SecuritySettings

        s = SecuritySettings()
        assert s.jwt_public_key == "SYSTEM_PUBLIC_KEY_PLACEHOLDER"
        assert s.api_key_internal is None

    def test_opa_settings_defaults(self):
        from src.core.shared.config.security import OPASettings

        opa = OPASettings()
        assert opa.url == "http://localhost:8181"
        assert opa.fail_closed is True

    def test_opa_fail_closed_always_true(self):
        from src.core.shared.config.security import OPASettings

        opa = OPASettings()
        assert opa.fail_closed is True

    def test_audit_settings_defaults(self):
        from src.core.shared.config.security import AuditSettings

        a = AuditSettings()
        assert a.url == "http://localhost:8001"

    def test_vault_settings_defaults(self):
        from src.core.shared.config.security import VaultSettings

        v = VaultSettings()
        assert v.address == "http://127.0.0.1:8200"
        assert v.token is None
        assert v.transit_mount == "transit"
        assert v.kv_mount == "secret"
        assert v.kv_version == 2
        assert v.timeout == 30.0
        assert v.verify_tls is True

    def test_sso_settings_defaults(self, monkeypatch: pytest.MonkeyPatch):
        from src.core.shared.config.security import SSOSettings

        for env_var in (
            "SSO_ENABLED",
            "OIDC_ENABLED",
            "OIDC_USE_PKCE",
            "SAML_ENABLED",
            "SAML_SIGN_REQUESTS",
            "SSO_AUTO_PROVISION",
            "SSO_DEFAULT_ROLE",
        ):
            monkeypatch.delenv(env_var, raising=False)

        sso = SSOSettings()
        assert sso.enabled is True
        assert sso.session_lifetime_seconds == 3600
        assert sso.oidc_enabled is True
        assert sso.oidc_use_pkce is True
        assert sso.saml_enabled is True
        assert sso.saml_sign_requests is True
        assert sso.auto_provision_users is True
        assert sso.default_role_on_provision == "viewer"

    def test_security_placeholder_validator(self):
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS, SecuritySettings

        if HAS_PYDANTIC_SETTINGS:
            with pytest.raises(PydanticValidationError):
                SecuritySettings(jwt_secret=SecretStr("PLACEHOLDER"))


# ============================================================================
# config/governance.py
# ============================================================================


class TestGovernance:
    def test_maci_settings_defaults(self):
        from src.core.shared.config.governance import MACISettings

        m = MACISettings()
        assert m.strict_mode is True
        assert m.default_role is None
        assert m.config_path is None

    def test_voting_settings_defaults(self):
        from src.core.shared.config.governance import VotingSettings

        v = VotingSettings()
        assert v.default_timeout_seconds == 30
        assert "tenant_id" in v.vote_topic_pattern
        assert v.enable_weighted_voting is True
        assert v.signature_algorithm == "HMAC-SHA256"
        assert v.timeout_check_interval_seconds == 5

    def test_circuit_breaker_settings_defaults(self):
        from src.core.shared.config.governance import CircuitBreakerSettings

        cb = CircuitBreakerSettings()
        assert cb.default_failure_threshold == 5
        assert cb.default_timeout_seconds == 30.0
        assert cb.default_half_open_requests == 3
        assert cb.policy_registry_failure_threshold == 3
        assert cb.opa_evaluator_failure_threshold == 5
        assert cb.opa_evaluator_timeout_seconds == 5.0
        assert cb.blockchain_anchor_failure_threshold == 10
        assert cb.redis_cache_failure_threshold == 3
        assert cb.kafka_producer_failure_threshold == 5
        assert cb.audit_service_failure_threshold == 5
        assert cb.deliberation_layer_failure_threshold == 7
        assert cb.health_check_enabled is True
        assert cb.metrics_enabled is True


# ============================================================================
# config/operations.py
# ============================================================================


class TestOperations:
    def test_telemetry_settings_defaults(self):
        from src.core.shared.config.operations import TelemetrySettings

        t = TelemetrySettings()
        assert t.otlp_endpoint == "http://localhost:4317"
        assert t.service_name == "acgs2"
        assert t.export_traces is True
        assert t.export_metrics is True
        assert t.trace_sample_rate == 0.1

    def test_aws_settings_defaults(self):
        from src.core.shared.config.operations import AWSSettings

        a = AWSSettings()
        assert a.region == "us-east-1"
        assert a.access_key_id is None
        assert a.s3_endpoint_url is None

    def test_quality_settings_defaults(self):
        from src.core.shared.config.operations import QualitySettings

        q = QualitySettings()
        assert q.sonarqube_url == "http://localhost:9000"
        assert q.sonarqube_token is None
        assert q.enable_local_analysis is True


# ============================================================================
# config/communication.py
# ============================================================================


class TestCommunication:
    def test_smtp_settings_defaults(self):
        from src.core.shared.config.communication import SMTPSettings

        smtp = SMTPSettings()
        assert smtp.host == "localhost"
        assert smtp.port == 587
        assert smtp.username is None
        assert smtp.password is None
        assert smtp.use_tls is True
        assert smtp.use_ssl is False
        assert smtp.from_email == "noreply@example.com"
        assert smtp.from_name == "ACGS-2 Audit Service"
        assert smtp.timeout == 30.0
        assert smtp.enabled is False


# ============================================================================
# config/factory.py
# ============================================================================


class TestFactory:
    def test_settings_defaults(self):
        from src.core.shared.config.factory import Settings

        s = Settings()
        assert s.env == "development"
        assert s.debug is False
        assert hasattr(s, "redis")
        assert hasattr(s, "database")
        assert hasattr(s, "security")
        assert hasattr(s, "maci")
        assert hasattr(s, "opa")
        assert hasattr(s, "kafka")

    def test_settings_kafka_defaults(self):
        from src.core.shared.config.factory import Settings

        s = Settings()
        assert "bootstrap_servers" in s.kafka
        assert "security_protocol" in s.kafka

    def test_get_settings_returns_singleton(self):
        from src.core.shared.config.factory import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_settings_subsystems_instantiated(self):
        from src.core.shared.config.factory import Settings

        s = Settings()
        assert s.redis is not None
        assert s.database is not None
        assert s.ai is not None
        assert s.blockchain is not None
        assert s.security is not None
        assert s.sso is not None
        assert s.smtp is not None
        assert s.opa is not None
        assert s.audit is not None
        assert s.bundle is not None
        assert s.services is not None
        assert s.telemetry is not None
        assert s.aws is not None
        assert s.search_platform is not None
        assert s.opencode is not None
        assert s.quality is not None
        assert s.maci is not None
        assert s.vault is not None
        assert s.voting is not None
        assert s.circuit_breaker is not None

    def test_settings_coerce_opencode_env(self):
        from src.core.shared.config.factory import HAS_PYDANTIC_SETTINGS, Settings

        if HAS_PYDANTIC_SETTINGS:
            # The model_validator should handle OPENCODE=1
            s = Settings.model_validate({"opencode": "1"})
            assert s.opencode is not None

    def test_production_validation_missing_jwt(self):
        from src.core.shared.config.factory import HAS_PYDANTIC_SETTINGS, Settings

        if HAS_PYDANTIC_SETTINGS:
            with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
                with pytest.raises(PydanticValidationError):
                    Settings()


# ============================================================================
# config/tenant_config.py
# ============================================================================


class TestTenantConfig:
    def test_quota_config_defaults(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        q = TenantQuotaConfig()
        assert q.cpu == "2"
        assert q.memory == "4Gi"
        assert q.storage == "20Gi"
        assert q.rate_limit_requests == 1000
        assert q.rate_limit_window_seconds == 60
        assert q.max_pvcs == 10
        assert q.max_pods == 50

    def test_cpu_format_integer(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        q = TenantQuotaConfig(cpu="4")
        assert q.cpu == "4"

    def test_cpu_format_millicores(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        q = TenantQuotaConfig(cpu="2000m")
        assert q.cpu == "2000m"

    def test_cpu_format_float(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        q = TenantQuotaConfig(cpu="0.5")
        assert q.cpu == "0.5"

    def test_cpu_format_invalid(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        with pytest.raises(PydanticValidationError):
            TenantQuotaConfig(cpu="abc")

    def test_memory_format_valid(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        q = TenantQuotaConfig(memory="8Gi")
        assert q.memory == "8Gi"
        q2 = TenantQuotaConfig(memory="4096Mi")
        assert q2.memory == "4096Mi"
        q3 = TenantQuotaConfig(memory="4096")
        assert q3.memory == "4096"

    def test_memory_format_invalid(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        with pytest.raises(PydanticValidationError):
            TenantQuotaConfig(memory="invalid")

    def test_storage_format_invalid(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        with pytest.raises(PydanticValidationError):
            TenantQuotaConfig(storage="bad_format")

    def test_tenant_config_defaults(self):
        from src.core.shared.config.tenant_config import TenantConfig

        tc = TenantConfig()
        assert tc.tenant_id == "acgs-dev"
        assert tc.namespace_prefix == "tenant-"
        assert tc.enabled is True

    def test_namespace_name_property(self):
        from src.core.shared.config.tenant_config import TenantConfig

        tc = TenantConfig(tenant_id="myorg")
        assert tc.namespace_name == "tenant-myorg"

    def test_tenant_id_validation_valid(self):
        from src.core.shared.config.tenant_config import TenantConfig

        tc = TenantConfig(tenant_id="valid-tenant_123")
        assert tc.tenant_id == "valid-tenant_123"

    def test_tenant_id_single_char(self):
        from src.core.shared.config.tenant_config import TenantConfig

        tc = TenantConfig(tenant_id="x")
        assert tc.tenant_id == "x"

    def test_tenant_id_invalid_special_chars(self):
        from src.core.shared.config.tenant_config import TenantConfig

        with pytest.raises(PydanticValidationError):
            TenantConfig(tenant_id="bad!@#tenant")

    def test_tenant_id_path_traversal(self):
        from src.core.shared.config.tenant_config import TenantConfig

        with pytest.raises(PydanticValidationError):
            TenantConfig(tenant_id="tenant/../admin")

    def test_tenant_quota_registry_default(self):
        from src.core.shared.config.tenant_config import TenantQuotaRegistry

        reg = TenantQuotaRegistry()
        q = reg.get_quota_for_tenant("unknown")
        assert q.cpu == "2"

    def test_tenant_quota_registry_override(self):
        from src.core.shared.config.tenant_config import (
            TenantQuotaConfig,
            TenantQuotaRegistry,
        )

        reg = TenantQuotaRegistry()
        custom = TenantQuotaConfig(cpu="8", memory="16Gi")
        reg.register_tenant_quota("premium", custom)
        assert reg.get_quota_for_tenant("premium").cpu == "8"
        assert reg.get_quota_for_tenant("other").cpu == "2"

    def test_create_tenant_config_factory(self):
        from src.core.shared.config.tenant_config import create_tenant_config

        tc = create_tenant_config(
            "myorg",
            cpu="4",
            memory="8Gi",
            storage="50Gi",
            rate_limit_requests=5000,
            rate_limit_window_seconds=120,
        )
        assert tc.tenant_id == "myorg"
        assert tc.quotas.cpu == "4"
        assert tc.quotas.memory == "8Gi"
        assert tc.quotas.rate_limit_requests == 5000

    def test_create_tenant_config_minimal(self):
        from src.core.shared.config.tenant_config import create_tenant_config

        tc = create_tenant_config("simple")
        assert tc.tenant_id == "simple"
        assert tc.quotas.cpu == "2"

    def test_get_default_tenant_quotas(self):
        from src.core.shared.config.tenant_config import get_default_tenant_quotas

        q = get_default_tenant_quotas()
        assert q.cpu == "2"

    def test_rate_limit_bounds(self):
        from src.core.shared.config.tenant_config import TenantQuotaConfig

        with pytest.raises(PydanticValidationError):
            TenantQuotaConfig(rate_limit_requests=0)
        with pytest.raises(PydanticValidationError):
            TenantQuotaConfig(rate_limit_requests=1_000_001)


# ============================================================================
# errors/exceptions.py
# ============================================================================


class TestACGSBaseError:
    def test_basic_instantiation(self):
        from src.core.shared.errors.exceptions import ACGSBaseError

        err = ACGSBaseError("something failed")
        assert err.message == "something failed"
        assert err.error_code == "ACGS_ERROR"
        assert err.http_status_code == 500
        assert err.constitutional_hash == CONSTITUTIONAL_HASH
        assert err.correlation_id is not None
        assert err.details == {}
        assert err.cause is None
        assert err.timestamp is not None

    def test_custom_parameters(self):
        from src.core.shared.errors.exceptions import ACGSBaseError

        cause = ValueError("root cause")
        err = ACGSBaseError(
            "custom error",
            error_code="CUSTOM_001",
            correlation_id="corr-123",
            details={"key": "value"},
            cause=cause,
            http_status_code=422,
        )
        assert err.error_code == "CUSTOM_001"
        assert err.correlation_id == "corr-123"
        assert err.details == {"key": "value"}
        assert err.cause is cause
        assert err.__cause__ is cause
        assert err.http_status_code == 422

    def test_to_dict(self):
        from src.core.shared.errors.exceptions import ACGSBaseError

        cause = ValueError("cause")
        err = ACGSBaseError("test", cause=cause, details={"d": 1})
        d = err.to_dict()
        assert d["error"] == "ACGS_ERROR"
        assert d["message"] == "test"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert d["details"] == {"d": 1}
        assert d["cause"]["type"] == "ValueError"

    def test_to_dict_no_cause_no_details(self):
        from src.core.shared.errors.exceptions import ACGSBaseError

        err = ACGSBaseError("test")
        d = err.to_dict()
        assert "cause" not in d
        assert "details" not in d

    def test_to_log_dict(self):
        from src.core.shared.errors.exceptions import ACGSBaseError

        cause = ValueError("c")
        err = ACGSBaseError("test", cause=cause)
        ld = err.to_log_dict()
        assert ld["exception_type"] == "ACGSBaseError"
        assert ld["http_status_code"] == 500
        assert "cause_traceback" in ld

    def test_str_representation(self):
        from src.core.shared.errors.exceptions import ACGSBaseError

        err = ACGSBaseError("msg", correlation_id="12345678-abcd")
        s = str(err)
        assert CONSTITUTIONAL_HASH in s
        assert "ACGS_ERROR" in s
        assert "msg" in s

    def test_repr_representation(self):
        from src.core.shared.errors.exceptions import ACGSBaseError

        err = ACGSBaseError("msg")
        r = repr(err)
        assert "ACGSBaseError(" in r
        assert "message='msg'" in r


class TestExceptionSubclasses:
    def test_constitutional_violation(self):
        from src.core.shared.errors.exceptions import ConstitutionalViolationError

        err = ConstitutionalViolationError(
            "violation",
            violations=["rule1", "rule2"],
            policy_id="pol-1",
            action="delete",
        )
        assert err.http_status_code == 403
        assert err.error_code == "CONSTITUTIONAL_VIOLATION"
        assert err.violations == ["rule1", "rule2"]
        assert err.policy_id == "pol-1"
        assert err.action == "delete"
        assert "violations" in err.details

    def test_constitutional_violation_minimal(self):
        from src.core.shared.errors.exceptions import ConstitutionalViolationError

        err = ConstitutionalViolationError("simple violation")
        assert err.violations == []
        assert err.policy_id is None

    def test_maci_enforcement_error(self):
        from src.core.shared.errors.exceptions import MACIEnforcementError

        err = MACIEnforcementError(
            "self-validation",
            agent_id="agent-1",
            role="EXECUTIVE",
            action="validate",
            target_agent_id="agent-1",
        )
        assert err.http_status_code == 403
        assert err.error_code == "MACI_ENFORCEMENT_FAILURE"
        assert err.agent_id == "agent-1"
        assert err.role == "EXECUTIVE"
        assert err.target_agent_id == "agent-1"

    def test_tenant_isolation_error(self):
        from src.core.shared.errors.exceptions import TenantIsolationError

        err = TenantIsolationError(
            "cross-tenant access",
            tenant_id="t1",
            resource_tenant_id="t2",
            resource_type="policy",
            resource_id="p-123",
        )
        assert err.http_status_code == 403
        assert err.error_code == "TENANT_ISOLATION_VIOLATION"
        assert err.details["tenant_id"] == "t1"
        assert err.details["resource_tenant_id"] == "t2"

    def test_validation_error(self):
        from src.core.shared.errors.exceptions import ValidationError

        err = ValidationError(
            "bad input",
            field="email",
            value="not-an-email",
            constraint="email_format",
            validation_errors=[{"field": "email", "msg": "invalid"}],
        )
        assert err.http_status_code == 400
        assert err.error_code == "VALIDATION_ERROR"
        assert err.field == "email"
        assert err.constraint == "email_format"
        assert len(err.validation_errors) == 1

    def test_validation_error_value_truncation(self):
        from src.core.shared.errors.exceptions import ValidationError

        long_value = "x" * 200
        err = ValidationError("bad", value=long_value)
        assert err.details["value"].endswith("...")
        assert len(err.details["value"]) == 103  # 100 + "..."

    def test_service_unavailable(self):
        from src.core.shared.errors.exceptions import ServiceUnavailableError

        err = ServiceUnavailableError(
            "down",
            service_name="opa",
            endpoint="/v1/data",
            retry_after=30,
        )
        assert err.http_status_code == 503
        assert err.service_name == "opa"
        assert err.retry_after == 30

    def test_rate_limit_exceeded(self):
        from src.core.shared.errors.exceptions import RateLimitExceededError

        err = RateLimitExceededError(
            "too fast",
            limit=100,
            window_seconds=60,
            retry_after=30,
            limit_type="per_tenant",
        )
        assert err.http_status_code == 429
        assert err.limit == 100
        assert err.limit_type == "per_tenant"

    def test_authentication_error(self):
        from src.core.shared.errors.exceptions import AuthenticationError

        err = AuthenticationError(
            "invalid token",
            auth_method="jwt",
            reason="expired",
        )
        assert err.http_status_code == 401
        assert err.auth_method == "jwt"
        assert err.reason == "expired"

    def test_authorization_error(self):
        from src.core.shared.errors.exceptions import AuthorizationError

        err = AuthorizationError(
            "denied",
            action="delete",
            resource="policy/123",
            required_permission="admin",
        )
        assert err.http_status_code == 403
        assert err.action == "delete"
        assert err.required_permission == "admin"

    def test_resource_not_found(self):
        from src.core.shared.errors.exceptions import ResourceNotFoundError

        err = ResourceNotFoundError(
            "not found",
            resource_type="Policy",
            resource_id="p-999",
        )
        assert err.http_status_code == 404
        assert err.resource_type == "Policy"
        assert err.resource_id == "p-999"

    def test_data_integrity_error(self):
        from src.core.shared.errors.exceptions import DataIntegrityError

        err = DataIntegrityError(
            "duplicate",
            entity_type="User",
            entity_id="u-1",
            constraint_name="unique_email",
        )
        assert err.http_status_code == 409
        assert err.constraint_name == "unique_email"

    def test_configuration_error(self):
        from src.core.shared.errors.exceptions import ConfigurationError

        err = ConfigurationError(
            "missing key",
            config_key="REDIS_URL",
            expected_type="str",
            actual_value="<not set>",
        )
        assert err.http_status_code == 500
        assert err.config_key == "REDIS_URL"

    def test_timeout_error(self):
        from src.core.shared.errors.exceptions import TimeoutError

        err = TimeoutError(
            "timed out",
            operation="policy_eval",
            timeout_seconds=5.0,
        )
        assert err.http_status_code == 504
        assert err.operation == "policy_eval"
        assert err.timeout_seconds == 5.0

    def test_all_inherit_from_base(self):
        from src.core.shared.errors.exceptions import (
            ACGSBaseError,
            AuthenticationError,
            AuthorizationError,
            ConfigurationError,
            ConstitutionalViolationError,
            DataIntegrityError,
            MACIEnforcementError,
            RateLimitExceededError,
            ResourceNotFoundError,
            ServiceUnavailableError,
            TenantIsolationError,
            TimeoutError,
            ValidationError,
        )

        for cls in [
            ConstitutionalViolationError,
            MACIEnforcementError,
            TenantIsolationError,
            ValidationError,
            ServiceUnavailableError,
            RateLimitExceededError,
            AuthenticationError,
            AuthorizationError,
            ResourceNotFoundError,
            DataIntegrityError,
            ConfigurationError,
            TimeoutError,
        ]:
            err = cls("test")
            assert isinstance(err, ACGSBaseError)
            assert isinstance(err, Exception)


# ============================================================================
# errors/context_poisoning.py
# ============================================================================


class TestContextPoisoning:
    def test_basic(self):
        from src.core.shared.errors.context_poisoning import ContextPoisoningError

        err = ContextPoisoningError(
            "injection detected",
            source_id="agent-42",
            source_type="agent",
            matched_patterns=["ignore previous", "system:"],
            severity="high",
            confidence=0.95,
        )
        assert err.http_status_code == 403
        assert err.error_code == "CONTEXT_POISONING"
        assert err.source_id == "agent-42"
        assert err.source_type == "agent"
        assert err.matched_patterns == ["ignore previous", "system:"]
        assert err.severity == "high"
        assert err.confidence == 0.95
        assert err.details["owasp_category"] == "AA05"

    def test_minimal(self):
        from src.core.shared.errors.context_poisoning import ContextPoisoningError

        err = ContextPoisoningError("test")
        assert err.source_id == ""
        assert err.matched_patterns == []
        assert err.confidence == 0.0


# ============================================================================
# errors/circuit_breaker.py
# ============================================================================


class TestCircuitBreaker:
    def setup_method(self):
        from src.core.shared.errors.circuit_breaker import _circuit_breakers
        _circuit_breakers.clear()

    def test_circuit_breaker_state_enum(self):
        from src.core.shared.errors.circuit_breaker import CircuitBreakerState

        assert CircuitBreakerState.CLOSED == "closed"
        assert CircuitBreakerState.OPEN == "open"
        assert CircuitBreakerState.HALF_OPEN == "half_open"

    def test_circuit_breaker_open_error(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerOpenError,
            CircuitBreakerState,
        )

        err = CircuitBreakerOpenError(
            "service down",
            service_name="redis",
            state=CircuitBreakerState.OPEN,
            retry_after=30.0,
        )
        assert err.http_status_code == 503
        assert err.error_code == "CIRCUIT_BREAKER_OPEN"
        assert err.service_name == "redis"
        assert err.retry_after == 30.0
        d = err.to_dict()
        assert d["service_name"] == "redis"
        assert d["state"] == "open"

    def test_circuit_breaker_config(self):
        from src.core.shared.errors.circuit_breaker import CircuitBreakerConfig

        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.reset_timeout == 30.0
        assert cfg.half_open_max_calls == 3
        assert cfg.success_threshold == 2
        assert cfg.fallback is None
        d = cfg.to_dict()
        assert d["failure_threshold"] == 5
        assert d["has_fallback"] is False

    def test_circuit_breaker_config_with_exclude(self):
        from src.core.shared.errors.circuit_breaker import CircuitBreakerConfig

        cfg = CircuitBreakerConfig(exclude_exceptions=(ValueError, TypeError))
        d = cfg.to_dict()
        assert "ValueError" in d["exclude_exceptions"]

    def test_simple_circuit_breaker_lifecycle(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerState,
            SimpleCircuitBreaker,
        )

        cfg = CircuitBreakerConfig(failure_threshold=2, reset_timeout=0.01)
        cb = SimpleCircuitBreaker("test-svc", cfg)

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.can_execute() is True

        # Record successes - should stay closed
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

        # Record failures up to threshold
        cb.record_failure(RuntimeError("fail1"))
        assert cb.state == CircuitBreakerState.CLOSED
        cb.record_failure(RuntimeError("fail2"))
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.can_execute() is False

    def test_half_open_recovery(self):
        import time

        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerState,
            SimpleCircuitBreaker,
        )

        cfg = CircuitBreakerConfig(
            failure_threshold=1,
            reset_timeout=0.01,
            success_threshold=1,
            half_open_max_calls=2,
        )
        cb = SimpleCircuitBreaker("test-recovery", cfg)

        cb.record_failure(RuntimeError("fail"))
        assert cb.state == CircuitBreakerState.OPEN

        time.sleep(0.02)
        assert cb.state == CircuitBreakerState.HALF_OPEN
        assert cb.can_execute() is True

        cb.before_call()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_failure_reopens(self):
        import time

        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerState,
            SimpleCircuitBreaker,
        )

        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.01)
        cb = SimpleCircuitBreaker("test-reopen", cfg)
        cb.record_failure(RuntimeError("f"))
        time.sleep(0.02)
        assert cb.state == CircuitBreakerState.HALF_OPEN
        cb.record_failure(RuntimeError("f2"))
        assert cb.state == CircuitBreakerState.OPEN

    def test_excluded_exceptions_not_counted(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerState,
            SimpleCircuitBreaker,
        )

        cfg = CircuitBreakerConfig(
            failure_threshold=1,
            exclude_exceptions=(ValueError,),
        )
        cb = SimpleCircuitBreaker("test-exclude", cfg)
        cb.record_failure(ValueError("ok"))
        assert cb.state == CircuitBreakerState.CLOSED

    def test_reset(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerState,
            SimpleCircuitBreaker,
        )

        cfg = CircuitBreakerConfig(failure_threshold=1)
        cb = SimpleCircuitBreaker("test-reset", cfg)
        cb.record_failure(RuntimeError("f"))
        assert cb.state == CircuitBreakerState.OPEN
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_get_status(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            SimpleCircuitBreaker,
        )

        cb = SimpleCircuitBreaker("test-status", CircuitBreakerConfig())
        status = cb.get_status()
        assert status["service_name"] == "test-status"
        assert status["state"] == "closed"
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_circuit_breaker_registry(self):
        from src.core.shared.errors.circuit_breaker import get_circuit_breaker

        cb1 = get_circuit_breaker("svc-a")
        cb2 = get_circuit_breaker("svc-a")
        assert cb1 is cb2

    def test_reset_circuit_breaker(self):
        from src.core.shared.errors.circuit_breaker import (
            get_circuit_breaker,
            reset_circuit_breaker,
        )

        get_circuit_breaker("svc-b")
        assert reset_circuit_breaker("svc-b") is True
        assert reset_circuit_breaker("nonexistent") is False

    def test_reset_all(self):
        from src.core.shared.errors.circuit_breaker import (
            get_circuit_breaker,
            reset_all_circuit_breakers,
        )

        get_circuit_breaker("svc-c")
        get_circuit_breaker("svc-d")
        reset_all_circuit_breakers()

    def test_get_all_states(self):
        from src.core.shared.errors.circuit_breaker import (
            get_all_circuit_breaker_states,
            get_circuit_breaker,
        )

        get_circuit_breaker("svc-e")
        states = get_all_circuit_breaker_states()
        assert "svc-e" in states

    def test_sync_decorator(self):
        from src.core.shared.errors.circuit_breaker import circuit_breaker

        @circuit_breaker("sync-test")
        def my_func(x: int) -> int:
            return x * 2

        result = my_func(5)
        assert result == 10

    def test_sync_decorator_with_fallback(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            circuit_breaker,
        )

        @circuit_breaker(
            "sync-fb",
            fallback=lambda: -1,
            config=CircuitBreakerConfig(failure_threshold=1),
        )
        def failing_func() -> int:
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            failing_func()

        # Now circuit is open, should use fallback
        assert failing_func() == -1

    @pytest.mark.asyncio
    async def test_async_decorator(self):
        from src.core.shared.errors.circuit_breaker import circuit_breaker

        @circuit_breaker("async-test")
        async def my_async_func(x: int) -> int:
            return x + 1

        result = await my_async_func(10)
        assert result == 11

    @pytest.mark.asyncio
    async def test_async_decorator_open_no_fallback(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerOpenError,
            circuit_breaker,
        )

        @circuit_breaker("async-open", config=CircuitBreakerConfig(failure_threshold=1))
        async def fails():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await fails()

        with pytest.raises(CircuitBreakerOpenError):
            await fails()

    @pytest.mark.asyncio
    async def test_async_decorator_with_fallback(self):
        from src.core.shared.errors.circuit_breaker import (
            CircuitBreakerConfig,
            circuit_breaker,
        )

        @circuit_breaker(
            "async-fb",
            fallback=lambda: 42,
            config=CircuitBreakerConfig(failure_threshold=1),
        )
        async def fails():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await fails()

        result = await fails()
        assert result == 42


# ============================================================================
# errors/logging.py
# ============================================================================


class TestErrorLogging:
    def test_error_severity_enum(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorSeverity

        assert ErrorSeverity.DEBUG == 10
        assert ErrorSeverity.INFO == 20
        assert ErrorSeverity.WARNING == 30
        assert ErrorSeverity.ERROR == 40
        assert ErrorSeverity.CRITICAL == 50
        assert ErrorSeverity.EMERGENCY == 60

    def test_error_context_defaults(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorContext

        ctx = ErrorContext(operation="test_op", service="test_svc")
        assert ctx.operation == "test_op"
        assert ctx.service == "test_svc"
        assert ctx.correlation_id != ""
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_error_context_to_dict(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorContext

        ctx = ErrorContext(
            operation="op",
            service="svc",
            tenant_id="t1",
            agent_id="a1",
            message_id="m1",
            request_id="r1",
            user_id="u1",
            metadata={"k": "v"},
        )
        d = ctx.to_dict()
        assert d["operation"] == "op"
        assert d["service"] == "svc"
        assert d["tenant_id"] == "t1"
        assert d["metadata"] == {"k": "v"}

    def test_correlation_id_management(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                get_correlation_id,
                set_correlation_id,
            )

        set_correlation_id("test-corr-123")
        assert get_correlation_id() == "test-corr-123"

    def test_set_tenant_and_request_id(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                ErrorContext,
                set_request_id,
                set_tenant_id,
            )

        set_tenant_id("t-99")
        set_request_id("req-42")
        ctx = ErrorContext()
        assert ctx.tenant_id == "t-99"
        assert ctx.request_id == "req-42"

    def test_build_error_context(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                ErrorSeverity,
                build_error_context,
            )

        ctx = build_error_context(
            operation="validate",
            service="bus",
            severity=ErrorSeverity.WARNING,
            agent_id="a-1",
            custom_key="custom_val",
        )
        assert ctx.operation == "validate"
        assert ctx.agent_id == "a-1"
        assert ctx.metadata == {"custom_key": "custom_val"}

    def test_log_error(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorContext, log_error

        err = RuntimeError("test error")
        log_error(err, context=ErrorContext(operation="test"))

    def test_log_error_no_context(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import log_error

        log_error(RuntimeError("test"))

    def test_log_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import log_warning

        log_warning("something suspicious")

    def test_log_critical(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorContext, ErrorSeverity, log_critical

        err = RuntimeError("critical failure")
        log_critical(err, context=ErrorContext(severity=ErrorSeverity.WARNING))

    def test_log_critical_no_context(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import log_critical

        log_critical(RuntimeError("crit"))

    def test_log_error_with_acgs_error(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import log_error

        from src.core.shared.errors.exceptions import ACGSBaseError

        err = ACGSBaseError("acgs error")
        log_error(err)

    def test_severity_to_log_level(self):
        import logging

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                ErrorSeverity,
                _severity_to_log_level,
            )

        assert _severity_to_log_level(ErrorSeverity.DEBUG) == logging.DEBUG
        assert _severity_to_log_level(ErrorSeverity.INFO) == logging.INFO
        assert _severity_to_log_level(ErrorSeverity.WARNING) == logging.WARNING
        assert _severity_to_log_level(ErrorSeverity.ERROR) == logging.ERROR
        assert _severity_to_log_level(ErrorSeverity.CRITICAL) == logging.CRITICAL
        assert _severity_to_log_level(ErrorSeverity.EMERGENCY) == logging.CRITICAL


# ============================================================================
# feature_flags.py
# ============================================================================


class TestFeatureFlags:
    def test_get_bool_env_true_values(self):
        from src.core.shared.feature_flags import _get_bool_env

        for val in ("true", "1", "yes", "on"):
            with patch.dict(os.environ, {"TEST_FLAG": val}):
                assert _get_bool_env("TEST_FLAG") is True

    def test_get_bool_env_false_values(self):
        from src.core.shared.feature_flags import _get_bool_env

        for val in ("false", "0", "no", "off"):
            with patch.dict(os.environ, {"TEST_FLAG": val}):
                assert _get_bool_env("TEST_FLAG") is False

    def test_get_bool_env_default(self):
        from src.core.shared.feature_flags import _get_bool_env

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NONEXISTENT_FLAG", None)
            assert _get_bool_env("NONEXISTENT_FLAG", default=True) is True
            assert _get_bool_env("NONEXISTENT_FLAG", default=False) is False

    def test_feature_flags_defaults(self):
        from src.core.shared.feature_flags import FeatureFlags

        ff = FeatureFlags()
        assert ff.mamba_enabled is True
        assert ff.maci_enabled is True
        assert ff.langgraph_enabled is True
        assert ff.safla_enabled is True
        assert ff.swarm_enabled is True
        assert ff.workflow_evolution_enabled is True
        assert ff.research_enabled is True
        assert ff.optimization_enabled is True
        assert ff.cache_warming_enabled is True

    def test_feature_flags_frozen(self):
        from src.core.shared.feature_flags import FeatureFlags

        ff = FeatureFlags()
        with pytest.raises(AttributeError):
            ff.mamba_enabled = False

    def test_log_status(self):
        from src.core.shared.feature_flags import FeatureFlags

        ff = FeatureFlags(mamba_enabled=False)
        ff.log_status()  # Should not raise

    def test_get_feature_flags(self):
        from src.core.shared.feature_flags import get_feature_flags

        get_feature_flags.cache_clear()
        flags = get_feature_flags()
        assert flags.maci_enabled is True

    def test_guarded_import_disabled(self):
        from src.core.shared.feature_flags import get_feature_flags, guarded_import

        get_feature_flags.cache_clear()
        with patch.dict(os.environ, {"ACGS_FEATURE_MAMBA": "false"}):
            get_feature_flags.cache_clear()
            result, available = guarded_import(
                "mamba_enabled",
                lambda: "module",
                "Mamba-2",
            )
            assert result is None
            assert available is False
        get_feature_flags.cache_clear()

    def test_guarded_import_import_fails(self):
        from src.core.shared.feature_flags import get_feature_flags, guarded_import

        get_feature_flags.cache_clear()

        def bad_import():
            raise ImportError("no such module")

        result, available = guarded_import("maci_enabled", bad_import, "MACI")
        assert result is None
        assert available is False
        get_feature_flags.cache_clear()

    def test_guarded_import_success(self):
        from src.core.shared.feature_flags import get_feature_flags, guarded_import

        get_feature_flags.cache_clear()
        result, available = guarded_import(
            "maci_enabled",
            lambda: "the_module",
            "MACI",
        )
        assert result == "the_module"
        assert available is True
        get_feature_flags.cache_clear()


# ============================================================================
# schema_registry.py
# ============================================================================


class TestSchemaRegistry:
    def test_schema_status_enum(self):
        from src.core.shared.schema_registry import SchemaStatus

        assert SchemaStatus.ACTIVE == "active"
        assert SchemaStatus.DEPRECATED == "deprecated"
        assert SchemaStatus.EXPERIMENTAL == "experimental"

    def test_event_schema_base(self):
        from src.core.shared.schema_registry import EventSchemaBase

        evt = EventSchemaBase(event_type="test.event")
        assert evt.event_type == "test.event"
        assert evt.constitutional_hash == CONSTITUTIONAL_HASH
        assert evt.schema_version is not None

    def test_event_schema_base_auto_version(self):
        from src.core.shared.schema_registry import EventSchemaBase

        evt = EventSchemaBase()
        assert evt.schema_version.startswith("v")

    def test_schema_registry_singleton(self):
        from src.core.shared.schema_registry import SchemaRegistry

        r1 = SchemaRegistry()
        r2 = SchemaRegistry()
        assert r1 is r2

    def test_get_schema_registry(self):
        from src.core.shared.schema_registry import SchemaRegistry, get_schema_registry

        reg = get_schema_registry()
        assert isinstance(reg, SchemaRegistry)

    def test_register_and_get(self):
        from typing import ClassVar

        from packages.enhanced_agent_bus.schema_evolution import SchemaVersion
        from src.core.shared.schema_registry import (
            EventSchemaBase,
            SchemaRegistry,
        )

        reg = SchemaRegistry()

        class MyEvent(EventSchemaBase):
            SCHEMA_NAME: ClassVar[str] = "my_event_test_unique"
            SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

        reg.register(MyEvent)
        cls = reg.get("my_event_test_unique")
        assert cls is MyEvent

    def test_get_nonexistent(self):
        from src.core.shared.schema_registry import SchemaRegistry

        reg = SchemaRegistry()
        assert reg.get("nonexistent_schema_xyz") is None

    def test_get_specific_version(self):
        from typing import ClassVar

        from packages.enhanced_agent_bus.schema_evolution import SchemaVersion
        from src.core.shared.schema_registry import EventSchemaBase, SchemaRegistry

        reg = SchemaRegistry()

        class MyEventV2(EventSchemaBase):
            SCHEMA_NAME: ClassVar[str] = "my_event_v2_test"
            SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(2, 0, 0)

        reg.register(MyEventV2)
        assert reg.get("my_event_v2_test", SchemaVersion(2, 0, 0)) is MyEventV2
        assert reg.get("my_event_v2_test", SchemaVersion(9, 9, 9)) is None

    def test_register_and_get_migration(self):
        from packages.enhanced_agent_bus.schema_evolution import SchemaVersion
        from src.core.shared.schema_registry import SchemaRegistry

        reg = SchemaRegistry()

        def migrate(data: dict) -> dict:
            return {**data, "migrated": True}

        reg.register_migration("evt_mig", SchemaVersion(1, 0, 0), SchemaVersion(2, 0, 0), migrate)
        fn = reg.get_migration("evt_mig", SchemaVersion(1, 0, 0), SchemaVersion(2, 0, 0))
        assert fn is not None
        assert fn({"a": 1}) == {"a": 1, "migrated": True}

        assert reg.get_migration("evt_mig", SchemaVersion(1, 0, 0), SchemaVersion(3, 0, 0)) is None


# ============================================================================
# interfaces.py
# ============================================================================


class TestInterfaces:
    def test_cache_client_protocol(self):
        from src.core.shared.interfaces import CacheClient

        assert hasattr(CacheClient, "get")
        assert hasattr(CacheClient, "set")
        assert hasattr(CacheClient, "delete")

    def test_policy_evaluator_protocol(self):
        from src.core.shared.interfaces import PolicyEvaluator

        assert hasattr(PolicyEvaluator, "evaluate")
        assert hasattr(PolicyEvaluator, "evaluate_batch")

    def test_audit_service_protocol(self):
        from src.core.shared.interfaces import AuditService

        assert hasattr(AuditService, "log_event")
        assert hasattr(AuditService, "verify_integrity")

    def test_retry_strategy_is_abstract(self):
        from src.core.shared.interfaces import RetryStrategy

        with pytest.raises(TypeError):
            RetryStrategy()

    def test_all_protocols_importable(self):
        from src.core.shared.interfaces import (
            AuditService,
            CacheClient,
            CircuitBreaker,
            DatabaseSession,
            MessageProcessor,
            MetricsCollector,
            NotificationService,
            PolicyEvaluator,
        )

        # Verify they are all types
        for proto in [
            CacheClient, PolicyEvaluator, AuditService, DatabaseSession,
            NotificationService, MessageProcessor, CircuitBreaker, MetricsCollector,
        ]:
            assert isinstance(proto, type)


# ============================================================================
# types/protocol_types.py
# ============================================================================


class TestProtocolTypes:
    def test_all_protocols_importable(self):
        from src.core.shared.types.protocol_types import (
            AgentBus,
            GovernanceService,
            SupportsAudit,
            SupportsAuthentication,
            SupportsCache,
            SupportsCircuitBreaker,
            SupportsCompensation,
            SupportsExecution,
            SupportsHealthCheck,
            SupportsLogging,
            SupportsMiddleware,
            SupportsRegistry,
            SupportsSerialization,
            SupportsValidation,
        )

        for proto in [
            SupportsCache, SupportsValidation, SupportsAuthentication,
            SupportsSerialization, SupportsLogging, SupportsMiddleware,
            SupportsHealthCheck, SupportsCircuitBreaker, SupportsAudit,
            AgentBus, GovernanceService, SupportsRegistry,
            SupportsExecution, SupportsCompensation,
        ]:
            assert isinstance(proto, type)

    def test_type_vars(self):
        from src.core.shared.types.protocol_types import (
            ConfigT,
            ContextT,
            EventT,
            ModelT,
            ResponseT,
            StateT,
            T,
            T_co,
            T_contra,
        )

        assert T is not None
        assert T_co is not None
        assert T_contra is not None
        assert ModelT is not None
        assert ConfigT is not None
        assert ResponseT is not None
        assert EventT is not None
        assert StateT is not None
        assert ContextT is not None

    def test_type_aliases(self):
        from src.core.shared.types.protocol_types import (
            ArgsType,
            AsyncFunc,
            DecoratorFunc,
            KwargsType,
            ModelContext,
            TransformFunc,
            ValidatorContext,
            ValidatorFunc,
            ValidatorValue,
        )

        assert ValidatorValue is not None
        assert ValidatorContext is not None
        assert ModelContext is not None
        assert ArgsType is not None
        assert KwargsType is not None
        assert DecoratorFunc is not None
        assert AsyncFunc is not None
        assert TransformFunc is not None
        assert ValidatorFunc is not None


# ============================================================================
# di_container.py
# ============================================================================


class TestDIContainer:
    def setup_method(self):
        from src.core.shared.di_container import DIContainer
        DIContainer.reset()

    def teardown_method(self):
        from src.core.shared.di_container import DIContainer
        DIContainer.reset()

    def test_singleton(self):
        from src.core.shared.di_container import DIContainer

        c1 = DIContainer()
        c2 = DIContainer()
        assert c1 is c2

    def test_register_and_get(self):
        from src.core.shared.di_container import DIContainer

        class MyService:
            pass

        svc = MyService()
        DIContainer.register(MyService, svc)
        assert DIContainer.get(MyService) is svc

    def test_get_unregistered_raises(self):
        from src.core.shared.di_container import DIContainer

        class Unknown:
            pass

        with pytest.raises(KeyError, match="Service not registered"):
            DIContainer.get(Unknown)

    def test_register_named_and_get(self):
        from src.core.shared.di_container import DIContainer

        DIContainer.register_named("my_svc", {"key": "val"})
        assert DIContainer.get_named("my_svc") == {"key": "val"}

    def test_get_named_unregistered(self):
        from src.core.shared.di_container import DIContainer

        with pytest.raises(KeyError, match="Named service not registered"):
            DIContainer.get_named("nonexistent")

    def test_reset(self):
        from src.core.shared.di_container import DIContainer

        DIContainer.register_named("x", 1)
        DIContainer.reset()
        with pytest.raises(KeyError):
            DIContainer.get_named("x")

    def test_convenience_accessors(self):
        from src.core.shared.di_container import DIContainer

        DIContainer.register_named("identity_provider", "idp")
        DIContainer.register_named("metering_service", "meter")
        DIContainer.register_named("policy_service", "policy")
        assert DIContainer.get_identity_provider() == "idp"
        assert DIContainer.get_metering_service() == "meter"
        assert DIContainer.get_policy_service() == "policy"

    def test_inject_helper(self):
        from src.core.shared.di_container import DIContainer, inject

        class Svc:
            pass

        instance = Svc()
        DIContainer.register(Svc, instance)
        assert inject(Svc) is instance

    def test_inject_named_helper(self):
        from src.core.shared.di_container import DIContainer, inject_named

        DIContainer.register_named("helper", 42)
        assert inject_named("helper") == 42


# ============================================================================
# api_versioning.py
# ============================================================================


class TestAPIVersioning:
    def test_versioning_config_defaults(self):
        from src.core.shared.api_versioning import VersioningConfig

        cfg = VersioningConfig()
        assert cfg.default_version == "v1"
        assert cfg.supported_versions == ("v1",)
        assert cfg.deprecated_versions == ()
        assert cfg.strict_versioning is False
        assert cfg.enable_metrics is False

    def test_supported_versions_constant(self):
        from src.core.shared.api_versioning import SUPPORTED_VERSIONS

        assert "v1" in SUPPORTED_VERSIONS

    def test_deprecated_versions_constant(self):
        from src.core.shared.api_versioning import DEPRECATED_VERSIONS

        assert DEPRECATED_VERSIONS == ()

    def test_deprecated_routes_constant(self):
        from src.core.shared.api_versioning import DEPRECATED_ROUTES

        assert isinstance(DEPRECATED_ROUTES, frozenset)

    def test_create_versioned_router(self):
        from src.core.shared.api_versioning import create_versioned_router

        router = create_versioned_router(prefix="policies")
        assert "/api/v1/policies" in router.prefix

    def test_create_versioned_router_with_leading_slash(self):
        from src.core.shared.api_versioning import create_versioned_router

        router = create_versioned_router(prefix="/health")
        assert "/api/v1/health" in router.prefix

    def test_create_versioned_router_custom_version(self):
        from src.core.shared.api_versioning import create_versioned_router

        router = create_versioned_router(prefix="data", version="v2")
        assert "/api/v2/data" in router.prefix

    def test_extract_version_from_path(self):
        from src.core.shared.api_versioning import _extract_version_from_path

        assert _extract_version_from_path("/api/v1/policies") == "v1"
        assert _extract_version_from_path("/api/v2/data") == "v2"
        assert _extract_version_from_path("/health") is None
        assert _extract_version_from_path("/") is None

    def test_get_versioning_documentation(self):
        from src.core.shared.api_versioning import get_versioning_documentation

        doc = get_versioning_documentation()
        assert doc["strategy"] == "stub"
        assert doc["default_version"] == "v1"
        assert doc["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_create_version_info_endpoint(self):
        from fastapi import APIRouter

        from src.core.shared.api_versioning import create_version_info_endpoint

        router = APIRouter()
        result = create_version_info_endpoint(router)
        assert result is router
        route_paths = [r.path for r in router.routes]
        assert "/version" in route_paths

    def test_create_version_metrics_endpoint(self):
        from fastapi import APIRouter

        from src.core.shared.api_versioning import create_version_metrics_endpoint

        router = APIRouter()
        result = create_version_metrics_endpoint(router)
        assert result is router
        route_paths = [r.path for r in router.routes]
        assert "/version/metrics" in route_paths


# ============================================================================
# config/settings.py
# ============================================================================


class TestRateLimitErrorHandler:
    @pytest.mark.asyncio
    async def test_rate_limit_error_handler_full(self):
        from src.core.shared.errors.exceptions import (
            RateLimitExceededError,
            rate_limit_error_handler,
        )

        exc = RateLimitExceededError(
            "rate limited",
            limit=100,
            window_seconds=60,
            retry_after=30,
            limit_type="per_user",
        )
        request = MagicMock()
        response = await rate_limit_error_handler(request, exc)
        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "30"
        assert response.headers.get("X-RateLimit-Limit") == "100"

    @pytest.mark.asyncio
    async def test_rate_limit_error_handler_minimal(self):
        from src.core.shared.errors.exceptions import (
            RateLimitExceededError,
            rate_limit_error_handler,
        )

        exc = RateLimitExceededError("rate limited")
        request = MagicMock()
        response = await rate_limit_error_handler(request, exc)
        assert response.status_code == 429
        assert response.headers.get("X-RateLimit-Limit") == "60"


class TestAPIVersioningMiddleware:
    @pytest.mark.asyncio
    async def test_dispatch_adds_version_header(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.core.shared.api_versioning import APIVersioningMiddleware, VersioningConfig

        app = FastAPI()

        @app.get("/api/v1/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(APIVersioningMiddleware, config=VersioningConfig())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/test")
            assert resp.status_code == 200
            assert resp.headers.get("x-api-version") == "v1"
            assert resp.headers.get("x-constitutional-hash") == CONSTITUTIONAL_HASH

    @pytest.mark.asyncio
    async def test_dispatch_deprecated_version(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.core.shared.api_versioning import APIVersioningMiddleware, VersioningConfig

        app = FastAPI()

        @app.get("/api/v0/old")
        async def old_endpoint():
            return {"old": True}

        cfg = VersioningConfig(deprecated_versions=("v0",))
        app.add_middleware(APIVersioningMiddleware, config=cfg)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v0/old")
            assert resp.headers.get("x-api-deprecated") == "true"

    @pytest.mark.asyncio
    async def test_dispatch_default_version_no_path(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.core.shared.api_versioning import APIVersioningMiddleware

        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        app.add_middleware(APIVersioningMiddleware)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
            assert resp.headers.get("x-api-version") == "v1"


class TestDeprecationNoticeMiddleware:
    @pytest.mark.asyncio
    async def test_deprecated_route_header(self):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.core.shared.api_versioning import DeprecationNoticeMiddleware

        app = FastAPI()

        @app.get("/old-endpoint")
        async def old():
            return {"old": True}

        @app.get("/new-endpoint")
        async def new():
            return {"new": True}

        app.add_middleware(
            DeprecationNoticeMiddleware,
            deprecated_routes={"/old-endpoint"},
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp_old = await client.get("/old-endpoint")
            assert resp_old.headers.get("x-api-deprecated") == "true"

            resp_new = await client.get("/new-endpoint")
            assert resp_new.headers.get("x-api-deprecated") is None


class TestVersionEndpoints:
    @pytest.mark.asyncio
    async def test_version_info_response(self):
        from fastapi import APIRouter, FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.core.shared.api_versioning import create_version_info_endpoint

        app = FastAPI()
        router = APIRouter()
        create_version_info_endpoint(router)
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/version")
            assert resp.status_code == 200
            data = resp.json()
            assert data["default_version"] == "v1"
            assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    @pytest.mark.asyncio
    async def test_version_metrics_response(self):
        from fastapi import APIRouter, FastAPI
        from httpx import ASGITransport, AsyncClient

        from src.core.shared.api_versioning import create_version_metrics_endpoint

        app = FastAPI()
        router = APIRouter()
        create_version_metrics_endpoint(router)
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/version/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False
            assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# config/settings.py
# ============================================================================


class TestSettings:
    def test_get_runtime_environment_default(self):
        from src.core.shared.config.settings import _get_runtime_environment

        with patch.dict(os.environ, {}, clear=False):
            for k in ("AGENT_RUNTIME_ENVIRONMENT", "ENVIRONMENT"):
                os.environ.pop(k, None)
            assert _get_runtime_environment() == "development"

    def test_get_runtime_environment_from_env(self):
        from src.core.shared.config.settings import _get_runtime_environment

        # Clear AGENT_RUNTIME_ENVIRONMENT so ENVIRONMENT takes effect
        env = {"ENVIRONMENT": "staging"}
        with patch.dict(os.environ, env):
            os.environ.pop("AGENT_RUNTIME_ENVIRONMENT", None)
            assert _get_runtime_environment() == "staging"

    def test_get_secret_key_from_env(self):
        from src.core.shared.config.settings import _get_secret_key

        with patch.dict(os.environ, {"SECRET_KEY": "my-secret-key-123"}):
            assert _get_secret_key() == "my-secret-key-123"

    def test_get_secret_key_dev_fallback(self):
        from src.core.shared.config.settings import _get_secret_key

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            os.environ.pop("SECRET_KEY", None)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                key = _get_secret_key()
            assert key == "dev-only-secret-key-not-for-production"

    def test_get_secret_key_production_missing_raises(self):
        from src.core.shared.config.settings import _get_secret_key

        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            os.environ.pop("SECRET_KEY", None)
            os.environ.pop("AGENT_RUNTIME_ENVIRONMENT", None)
            with pytest.raises(ValueError, match="SECRET_KEY"):
                _get_secret_key()

    def test_redis_settings_defaults(self):
        from src.core.shared.config.settings import RedisSettings

        r = RedisSettings()
        assert r.host == "localhost"
        assert r.port == 6379
        assert r.db == 0

    def test_database_settings_defaults(self):
        from src.core.shared.config.settings import DatabaseSettings

        db = DatabaseSettings()
        assert db.host == "localhost"
        assert db.port == 5432
        assert db.name == "acgs2"

    def test_settings_class(self):
        from src.core.shared.config.settings import Settings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            s = Settings()
        assert s.app_name == "ACGS-2"
        assert s.constitutional_hash == CONSTITUTIONAL_HASH
        assert s.jwt_algorithm == "RS256"
        assert s.access_token_expire_minutes == 30
