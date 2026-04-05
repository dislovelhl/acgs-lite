"""
ACGS-2 Enhanced Agent Bus - Configuration Tests
Constitutional Hash: 608508a9bd224290

Tests for BusConfiguration dataclass with builder pattern.
"""

import os
from typing import ClassVar
from unittest.mock import patch

import pytest

try:
    from config import CONSTITUTIONAL_HASH, DEFAULT_REDIS_URL, BusConfiguration
except ImportError:
    from ..config import CONSTITUTIONAL_HASH, DEFAULT_REDIS_URL, BusConfiguration


class TestBusConfigurationDefaults:
    """Tests for BusConfiguration default values."""

    def test_default_redis_url(self):
        """Test default Redis URL."""
        config = BusConfiguration()
        assert config.redis_url == DEFAULT_REDIS_URL

    def test_default_kafka_servers(self):
        """Test default Kafka servers."""
        config = BusConfiguration()
        assert config.kafka_bootstrap_servers == "localhost:9092"

    def test_default_audit_service_url(self):
        """Test default audit service URL."""
        config = BusConfiguration()
        assert config.audit_service_url == "http://localhost:8001"

    def test_default_feature_flags(self):
        """Test default feature flag values."""
        config = BusConfiguration()
        assert config.use_dynamic_policy is False
        # SECURITY FIX (2025-12): Default to fail-closed for security-first behavior
        assert config.policy_fail_closed is True
        assert config.use_kafka is False
        assert config.use_redis_registry is False
        assert config.use_rust is True
        assert config.enable_metering is True

    def test_default_maci_settings(self):
        """Test default MACI settings - enabled by default per audit finding 2025-12."""
        config = BusConfiguration()
        # SECURITY: MACI enabled by default to prevent Gödel bypass attacks
        assert config.enable_maci is True
        assert config.maci_strict_mode is True

    def test_default_session_governance_settings(self):
        """Test default session governance settings - disabled by default."""
        config = BusConfiguration()
        assert config.enable_session_governance is False
        assert config.session_policy_cache_ttl == 300  # 5 minutes
        assert config.session_context_ttl == 3600  # 1 hour
        assert config.require_independent_validator is False
        assert config.independent_validator_threshold == 0.8

    def test_default_governance_core_settings(self):
        """Test governance core settings default to legacy shell mode."""
        config = BusConfiguration()
        assert config.governance_core_mode == "legacy"
        assert config.governance_swarm_peer_validation_enabled is True
        assert config.governance_swarm_use_manifold is False

    def test_default_optional_dependencies(self):
        """Test default optional dependencies are None."""
        config = BusConfiguration()
        assert config.registry is None
        assert config.router is None
        assert config.validator is None
        assert config.processor is None
        assert config.metering_config is None

    def test_constitutional_hash_default(self):
        """Test constitutional hash defaults correctly."""
        config = BusConfiguration()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH


class TestBusConfigurationCustomValues:
    """Tests for BusConfiguration with custom values."""

    def test_custom_redis_url(self):
        """Test custom Redis URL."""
        config = BusConfiguration(redis_url="redis://custom:6379")
        assert config.redis_url == "redis://custom:6379"

    def test_custom_kafka_servers(self):
        """Test custom Kafka servers."""
        config = BusConfiguration(kafka_bootstrap_servers="kafka1:9092,kafka2:9092")
        assert config.kafka_bootstrap_servers == "kafka1:9092,kafka2:9092"

    def test_custom_feature_flags(self):
        """Test custom feature flags."""
        config = BusConfiguration(
            use_dynamic_policy=True,
            policy_fail_closed=True,
            use_kafka=True,
            use_redis_registry=True,
            use_rust=False,
            enable_metering=False,
        )
        assert config.use_dynamic_policy is True
        assert config.policy_fail_closed is True
        assert config.use_kafka is True
        assert config.use_redis_registry is True
        assert config.use_rust is False
        assert config.enable_metering is False

    def test_custom_maci_settings(self):
        """Test custom MACI settings."""
        config = BusConfiguration(enable_maci=True, maci_strict_mode=False)
        assert config.enable_maci is True
        assert config.maci_strict_mode is False

    def test_custom_session_governance_settings(self):
        """Test custom session governance settings."""
        config = BusConfiguration(
            enable_session_governance=True,
            session_policy_cache_ttl=600,
            session_context_ttl=7200,
        )
        assert config.enable_session_governance is True
        assert config.session_policy_cache_ttl == 600
        assert config.session_context_ttl == 7200

    def test_custom_governance_core_settings(self):
        """Test custom governance core routing settings."""
        config = BusConfiguration(
            governance_core_mode="shadow",
            governance_swarm_peer_validation_enabled=False,
            governance_swarm_use_manifold=True,
        )
        assert config.governance_core_mode == "shadow"
        assert config.governance_swarm_peer_validation_enabled is False
        assert config.governance_swarm_use_manifold is True


class TestBusConfigurationPostInit:
    """Tests for BusConfiguration __post_init__ validation."""

    def test_empty_constitutional_hash_filled(self):
        """Test that empty constitutional hash is filled with default."""
        config = BusConfiguration(constitutional_hash="")
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_provided_constitutional_hash_kept(self):
        """Test that provided constitutional hash is kept."""
        custom_hash = "custom123456789"
        config = BusConfiguration(constitutional_hash=custom_hash)
        assert config.constitutional_hash == custom_hash

    def test_invalid_governance_core_mode_rejected(self):
        """Test invalid governance core mode raises a validation error."""
        with pytest.raises(ValueError, match="governance_core_mode"):
            BusConfiguration(governance_core_mode="invalid")


class TestBusConfigurationFromEnvironment:
    """Tests for BusConfiguration.from_environment factory method."""

    # Env vars that from_environment() reads — must be removed for defaults test
    _FROM_ENV_KEYS: ClassVar[list] = [
        "REDIS_URL",
        "KAFKA_BOOTSTRAP_SERVERS",
        "AUDIT_SERVICE_URL",
        "USE_DYNAMIC_POLICY",
        "POLICY_FAIL_CLOSED",
        "USE_KAFKA",
        "USE_REDIS_REGISTRY",
        "USE_RUST",
        "ENABLE_METERING",
        "ENABLE_MACI",
        "MACI_STRICT_MODE",
        "ENABLE_PQC",
        "PQC_MODE",
        "PQC_VERIFICATION_MODE",
        "PQC_KEY_ALGORITHM",
        "PQC_MIGRATION_PHASE",
        "LLM_MODEL",
        "LLM_CACHE_TTL",
        "LLM_CONFIDENCE_THRESHOLD",
        "LLM_MAX_TOKENS",
        "LLM_USE_CACHE",
        "LLM_ENABLED",
        "ENABLE_AB_TESTING",
        "AB_TEST_LLM_PERCENTAGE",
        "ENABLE_SESSION_GOVERNANCE",
        "SESSION_POLICY_CACHE_TTL",
        "SESSION_CONTEXT_TTL",
        "REQUIRE_INDEPENDENT_VALIDATOR",
        "INDEPENDENT_VALIDATOR_THRESHOLD",
        "GOVERNANCE_CORE_MODE",
        "GOVERNANCE_SWARM_PEER_VALIDATION_ENABLED",
        "GOVERNANCE_SWARM_USE_MANIFOLD",
        "MAX_QUEUE_SIZE",
        "MAX_MESSAGE_SIZE_BYTES",
        "QUEUE_FULL_BEHAVIOR",
        "WUYING_ENABLED",
        "WUYING_API_KEY",
        "WUYING_ACCESS_KEY_ID",
        "WUYING_ACCESS_KEY_SECRET",
        "WUYING_REGION_ID",
    ]

    def test_from_environment_defaults(self):
        """Test from_environment with no env vars set."""
        # Explicitly remove env vars that from_environment() reads to avoid
        # xdist contamination from other tests setting env vars.
        clean_env = {k: v for k, v in os.environ.items() if k not in self._FROM_ENV_KEYS}
        with patch.dict(os.environ, clean_env, clear=True):
            config = BusConfiguration.from_environment()
            assert config.redis_url == BusConfiguration().redis_url
            assert config.use_dynamic_policy is False
            assert config.policy_fail_closed is True

    def test_from_environment_redis_url(self):
        """Test from_environment reads REDIS_URL."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://env:6379"}, clear=False):
            config = BusConfiguration.from_environment()
            assert config.redis_url == "redis://env:6379"

    def test_from_environment_kafka_servers(self):
        """Test from_environment reads KAFKA_BOOTSTRAP_SERVERS."""
        with patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": "kafka:9092"}, clear=False):
            config = BusConfiguration.from_environment()
            assert config.kafka_bootstrap_servers == "kafka:9092"

    def test_from_environment_audit_service(self):
        """Test from_environment reads AUDIT_SERVICE_URL."""
        with patch.dict(os.environ, {"AUDIT_SERVICE_URL": "http://audit:8001"}, clear=False):
            config = BusConfiguration.from_environment()
            assert config.audit_service_url == "http://audit:8001"

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("random", False),
        ],
    )
    def test_from_environment_bool_parsing(self, env_value, expected):
        """Test boolean parsing for environment variables."""
        with patch.dict(os.environ, {"USE_DYNAMIC_POLICY": env_value}, clear=False):
            config = BusConfiguration.from_environment()
            assert config.use_dynamic_policy is expected

    def test_from_environment_all_bool_flags(self):
        """Test all boolean flags from environment."""
        env_vars = {
            "USE_DYNAMIC_POLICY": "true",
            "POLICY_FAIL_CLOSED": "true",
            "USE_KAFKA": "true",
            "USE_REDIS_REGISTRY": "true",
            "USE_RUST": "false",
            "ENABLE_METERING": "false",
            "ENABLE_MACI": "true",
            "MACI_STRICT_MODE": "false",
            "REQUIRE_INDEPENDENT_VALIDATOR": "true",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            config = BusConfiguration.from_environment()
            assert config.use_dynamic_policy is True
            assert config.policy_fail_closed is True
            assert config.use_kafka is True
            assert config.use_redis_registry is True
            assert config.use_rust is False
            assert config.enable_metering is False
            assert config.enable_maci is True
            assert config.maci_strict_mode is False
            assert config.require_independent_validator is True

    def test_from_environment_session_governance(self):
        """Test session governance settings from environment."""
        env_vars = {
            "ENABLE_SESSION_GOVERNANCE": "true",
            "SESSION_POLICY_CACHE_TTL": "600",
            "SESSION_CONTEXT_TTL": "7200",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            config = BusConfiguration.from_environment()
            assert config.enable_session_governance is True
            assert config.session_policy_cache_ttl == 600
            assert config.session_context_ttl == 7200

    def test_from_environment_session_governance_defaults(self):
        """Test session governance defaults when not set in environment."""
        with patch.dict(os.environ, {}, clear=False):
            config = BusConfiguration.from_environment()
            assert config.enable_session_governance is False
            assert config.session_policy_cache_ttl == 300
            assert config.session_context_ttl == 3600

    def test_from_environment_independent_validator_threshold(self):
        """Test independent validator threshold parsing from environment."""
        with patch.dict(os.environ, {"INDEPENDENT_VALIDATOR_THRESHOLD": "0.93"}, clear=False):
            config = BusConfiguration.from_environment()
            assert config.independent_validator_threshold == 0.93

    def test_from_environment_governance_core_settings(self):
        """Test governance core settings from environment."""
        env_vars = {
            "GOVERNANCE_CORE_MODE": "shadow",
            "GOVERNANCE_SWARM_PEER_VALIDATION_ENABLED": "false",
            "GOVERNANCE_SWARM_USE_MANIFOLD": "true",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            config = BusConfiguration.from_environment()
            assert config.governance_core_mode == "shadow"
            assert config.governance_swarm_peer_validation_enabled is False
            assert config.governance_swarm_use_manifold is True

    def test_from_environment_invalid_governance_core_mode_falls_back_to_legacy(self):
        """Test invalid governance core mode falls back to legacy."""
        with patch.dict(os.environ, {"GOVERNANCE_CORE_MODE": "unsupported"}, clear=False):
            config = BusConfiguration.from_environment()
            assert config.governance_core_mode == "legacy"


class TestBusConfigurationForTesting:
    """Tests for BusConfiguration.for_testing factory method."""

    def test_for_testing_minimal_config(self):
        """Test for_testing creates minimal configuration."""
        config = BusConfiguration.for_testing()
        assert config.use_dynamic_policy is False
        assert config.policy_fail_closed is False
        assert config.use_kafka is False
        assert config.use_redis_registry is False
        assert config.use_rust is False
        assert config.enable_metering is False
        assert config.enable_maci is False
        assert config.maci_strict_mode is False

    def test_for_testing_constitutional_hash_present(self):
        """Test for_testing still has constitutional hash."""
        config = BusConfiguration.for_testing()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_for_testing_session_governance_disabled(self):
        """Test for_testing disables session governance."""
        config = BusConfiguration.for_testing()
        assert config.enable_session_governance is False
        assert config.require_independent_validator is False

    def test_for_testing_governance_core_defaults(self):
        """Test for_testing keeps governance shell in legacy mode."""
        config = BusConfiguration.for_testing()
        assert config.governance_core_mode == "legacy"
        assert config.governance_swarm_peer_validation_enabled is True
        assert config.governance_swarm_use_manifold is False


class TestBusConfigurationForProduction:
    """Tests for BusConfiguration.for_production factory method."""

    def test_for_production_all_features_enabled(self):
        """Test for_production enables all features."""
        config = BusConfiguration.for_production()
        assert config.use_dynamic_policy is True
        assert config.policy_fail_closed is True
        assert config.use_kafka is True
        assert config.use_redis_registry is True
        assert config.use_rust is True
        assert config.enable_metering is True
        assert config.enable_maci is True
        assert config.maci_strict_mode is True

    def test_for_production_constitutional_hash_present(self):
        """Test for_production has constitutional hash."""
        config = BusConfiguration.for_production()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_for_production_session_governance_enabled(self):
        """Test for_production enables session governance."""
        config = BusConfiguration.for_production()
        assert config.enable_session_governance is True
        assert config.require_independent_validator is True

    def test_for_production_governance_core_defaults(self):
        """Test for_production still defaults to legacy shell routing."""
        config = BusConfiguration.for_production()
        assert config.governance_core_mode == "legacy"
        assert config.governance_swarm_peer_validation_enabled is True
        assert config.governance_swarm_use_manifold is False


class TestBusConfigurationBuilderMethods:
    """Tests for BusConfiguration builder pattern methods."""

    def test_with_registry(self):
        """Test with_registry returns new config."""
        original = BusConfiguration()
        mock_registry = object()
        new_config = original.with_registry(mock_registry)

        assert new_config is not original
        assert new_config.registry is mock_registry
        assert original.registry is None

    def test_with_registry_preserves_other_values(self):
        """Test with_registry preserves other configuration."""
        original = BusConfiguration(
            redis_url="redis://custom:6379",
            use_dynamic_policy=True,
        )
        mock_registry = object()
        new_config = original.with_registry(mock_registry)

        assert new_config.redis_url == "redis://custom:6379"
        assert new_config.use_dynamic_policy is True

    def test_with_validator(self):
        """Test with_validator returns new config."""
        original = BusConfiguration()
        mock_validator = object()
        new_config = original.with_validator(mock_validator)

        assert new_config is not original
        assert new_config.validator is mock_validator
        assert original.validator is None

    def test_with_validator_preserves_other_values(self):
        """Test with_validator preserves other configuration."""
        original = BusConfiguration(
            enable_maci=True,
            maci_strict_mode=True,
        )
        mock_validator = object()
        new_config = original.with_validator(mock_validator)

        assert new_config.enable_maci is True
        assert new_config.maci_strict_mode is True

    def test_builder_method_chaining(self):
        """Test builder methods can be chained."""
        mock_registry = object()
        mock_validator = object()

        config = BusConfiguration().with_registry(mock_registry).with_validator(mock_validator)

        assert config.registry is mock_registry
        assert config.validator is mock_validator


class TestBusConfigurationToDict:
    """Tests for BusConfiguration.to_dict method."""

    def test_to_dict_basic_fields(self):
        """Test to_dict includes basic fields."""
        config = BusConfiguration()
        result = config.to_dict()

        assert "redis_url" in result
        assert "kafka_bootstrap_servers" in result
        assert "audit_service_url" in result
        assert "constitutional_hash" in result

    def test_to_dict_feature_flags(self):
        """Test to_dict includes feature flags."""
        config = BusConfiguration()
        result = config.to_dict()

        assert "use_dynamic_policy" in result
        assert "policy_fail_closed" in result
        assert "use_kafka" in result
        assert "use_redis_registry" in result
        assert "use_rust" in result
        assert "enable_metering" in result
        assert "enable_maci" in result
        assert "maci_strict_mode" in result

    def test_to_dict_optional_dependencies_as_booleans(self):
        """Test to_dict shows optional dependencies as booleans."""
        config = BusConfiguration()
        result = config.to_dict()

        assert result["has_custom_registry"] is False
        assert result["has_custom_router"] is False
        assert result["has_custom_validator"] is False
        assert result["has_custom_processor"] is False
        assert result["has_metering_config"] is False

    def test_to_dict_with_custom_dependencies(self):
        """Test to_dict shows True for custom dependencies."""
        config = BusConfiguration(registry=object(), validator=object())
        result = config.to_dict()

        assert result["has_custom_registry"] is True
        assert result["has_custom_validator"] is True
        assert result["has_custom_router"] is False

    def test_to_dict_values_match_config(self):
        """Test to_dict values match configuration."""
        config = BusConfiguration(
            redis_url="redis://test:6379",
            use_dynamic_policy=True,
            enable_maci=True,
        )
        result = config.to_dict()

        assert result["redis_url"] == "redis://test:6379"
        assert result["use_dynamic_policy"] is True
        assert result["enable_maci"] is True
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_session_governance_fields(self):
        """Test to_dict includes session governance fields."""
        config = BusConfiguration(
            enable_session_governance=True,
            session_policy_cache_ttl=600,
            session_context_ttl=7200,
            require_independent_validator=True,
            independent_validator_threshold=0.91,
        )
        result = config.to_dict()

        assert "enable_session_governance" in result
        assert "session_policy_cache_ttl" in result
        assert "session_context_ttl" in result
        assert "require_independent_validator" in result
        assert "independent_validator_threshold" in result
        assert result["enable_session_governance"] is True
        assert result["session_policy_cache_ttl"] == 600
        assert result["session_context_ttl"] == 7200
        assert result["require_independent_validator"] is True
        assert result["independent_validator_threshold"] == 0.91


class TestBusConfigurationImmutability:
    """Tests for configuration immutability with builder pattern."""

    def test_builder_creates_new_instance(self):
        """Test builder methods create new instances."""
        config1 = BusConfiguration()
        config2 = config1.with_registry(object())
        config3 = config2.with_validator(object())

        assert config1 is not config2
        assert config2 is not config3
        assert config1 is not config3

    def test_original_unchanged_after_builder(self):
        """Test original configuration unchanged after builder."""
        original = BusConfiguration(
            use_dynamic_policy=True,
            enable_maci=True,
        )
        _ = original.with_registry(object())

        assert original.registry is None
        assert original.use_dynamic_policy is True
        assert original.enable_maci is True
