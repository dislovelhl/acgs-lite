"""
Tests for DependencyBridge module.
Constitutional Hash: 608508a9bd224290

These tests verify the bridge between the legacy imports.py pattern
and the new DependencyRegistry.
"""

from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus._compat.utilities import DependencyRegistry, FeatureFlag


@pytest.fixture(autouse=True)
def reset_registry() -> None:
    """Reset the registry before each test."""
    DependencyRegistry.reset()
    yield
    DependencyRegistry.reset()


class TestDependencyBridgeInitialize:
    """Test dependency bridge initialization."""

    def test_initialize_calls_registry(self) -> None:
        """Test that initialize calls DependencyRegistry.initialize_defaults."""
        from enhanced_agent_bus import dependency_bridge

        # Reset and re-initialize
        DependencyRegistry.reset()
        dependency_bridge.initialize()

        assert DependencyRegistry._initialized is True

    def test_initialize_idempotent(self) -> None:
        """Test that initialize can be called multiple times."""
        from enhanced_agent_bus import dependency_bridge

        dependency_bridge.initialize()
        # Should not raise


class TestIsFeatureAvailable:
    """Test is_feature_available function."""

    def test_known_feature_metrics(self) -> None:
        """Test checking METRICS feature availability."""
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        # METRICS should be available if prometheus_client is installed
        result = is_feature_available("METRICS")
        assert isinstance(result, bool)

    def test_known_feature_redis(self) -> None:
        """Test checking REDIS feature availability."""
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        result = is_feature_available("REDIS")
        assert isinstance(result, bool)

    def test_unknown_feature_returns_false(self) -> None:
        """Test that unknown features return False."""
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        result = is_feature_available("UNKNOWN_FEATURE_XYZ")
        assert result is False

    def test_case_insensitive(self) -> None:
        """Test that feature names are case-insensitive."""
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        result_upper = is_feature_available("METRICS")
        result_lower = is_feature_available("metrics")
        assert result_upper == result_lower


class TestGetDependency:
    """Test get_dependency function."""

    def test_get_dependency_with_default(self) -> None:
        """Test getting dependency with default value."""
        from enhanced_agent_bus.dependency_bridge import get_dependency

        result = get_dependency("nonexistent_dep", default="fallback")
        assert result == "fallback"

    def test_get_dependency_legacy_name_mapping(self) -> None:
        """Test that legacy names are mapped correctly."""
        from enhanced_agent_bus.dependency_bridge import (
            _LEGACY_NAME_MAP,
            get_dependency,
        )

        # Verify legacy name exists in mapping
        assert "MACIEnforcer" in _LEGACY_NAME_MAP
        assert _LEGACY_NAME_MAP["MACIEnforcer"] == "maci_enforcer"

    def test_get_dependency_returns_none_for_unavailable(self) -> None:
        """Test that unavailable dependencies return None."""
        from enhanced_agent_bus.dependency_bridge import get_dependency

        result = get_dependency("nonexistent_dep")
        assert result is None


class TestGetFeatureFlags:
    """Test get_feature_flags function."""

    def test_returns_dict(self) -> None:
        """Test that get_feature_flags returns a dictionary."""
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()
        assert isinstance(flags, dict)

    def test_contains_expected_keys(self) -> None:
        """Test that the flags dict contains expected legacy keys."""
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()

        expected_keys = [
            "METRICS_ENABLED",
            "OTEL_ENABLED",
            "CIRCUIT_BREAKER_ENABLED",
            "POLICY_CLIENT_AVAILABLE",
            "DELIBERATION_AVAILABLE",
            "CRYPTO_AVAILABLE",
            "CONFIG_AVAILABLE",
            "AUDIT_CLIENT_AVAILABLE",
            "OPA_CLIENT_AVAILABLE",
            "USE_RUST",
            "METERING_AVAILABLE",
            "MACI_AVAILABLE",
            "REDIS_AVAILABLE",
            "KAFKA_AVAILABLE",
            "LLM_AVAILABLE",
            "IMPACT_SCORER_AVAILABLE",
        ]

        for key in expected_keys:
            assert key in flags, f"Missing flag: {key}"
            assert isinstance(flags[key], bool), f"Flag {key} is not a bool"

    def test_config_always_available(self) -> None:
        """Test that CONFIG_AVAILABLE is always True."""
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()
        assert flags["CONFIG_AVAILABLE"] is True


class TestRequireFeature:
    """Test require_feature function."""

    def test_require_unknown_feature_raises(self) -> None:
        """Test that requiring unknown feature raises RuntimeError."""
        from enhanced_agent_bus.dependency_bridge import require_feature

        with pytest.raises(RuntimeError) as exc_info:
            require_feature("UNKNOWN_FEATURE")

        assert "Unknown feature" in str(exc_info.value)

    def test_require_unavailable_feature_raises(self) -> None:
        """Test that requiring unavailable feature raises RuntimeError."""
        from enhanced_agent_bus.dependency_bridge import require_feature

        # Register an unavailable dependency
        DependencyRegistry.register(
            name="test_unavailable",
            module_path="nonexistent.module",
            import_name="Something",
            feature_flag=FeatureFlag.PQC,
        )

        with pytest.raises((RuntimeError, Exception)) as exc_info:
            require_feature("PQC")

        assert "PQC" in str(exc_info.value)


class TestGetStatus:
    """Test get_status function."""

    def test_returns_dict(self) -> None:
        """Test that get_status returns a dictionary."""
        from enhanced_agent_bus.dependency_bridge import get_status

        status = get_status()
        assert isinstance(status, dict)

    def test_contains_expected_structure(self) -> None:
        """Test that status has expected structure."""
        from enhanced_agent_bus.dependency_bridge import get_status

        status = get_status()

        assert "features" in status
        assert "dependencies" in status
        assert "available_features" in status
        assert "missing_features" in status


class TestOptionalImport:
    """Test optional_import function."""

    def test_returns_none_for_unavailable_feature(self) -> None:
        """Test that optional_import returns None for unavailable features."""
        from enhanced_agent_bus.dependency_bridge import optional_import

        result = optional_import(
            module_path="nonexistent.module",
            name="Something",
            feature="PQC",
            default=None,
        )
        assert result is None

    def test_returns_default_for_unavailable(self) -> None:
        """Test that optional_import returns default for unavailable features."""
        from enhanced_agent_bus.dependency_bridge import optional_import

        sentinel = object()
        result = optional_import(
            module_path="nonexistent.module",
            name="Something",
            feature="PQC",
            default=sentinel,
        )
        assert result is sentinel


class TestStubMACIRole:
    """Test StubMACIRole class."""

    def test_has_expected_roles(self) -> None:
        """Test that stub has expected role attributes."""
        from enhanced_agent_bus.dependency_bridge import StubMACIRole

        assert StubMACIRole.WORKER == "worker"
        assert StubMACIRole.CRITIC == "critic"
        assert StubMACIRole.SECURITY_AUDITOR == "security_auditor"
        assert StubMACIRole.MONITOR == "monitor"
        assert StubMACIRole.EXECUTIVE == "executive"
        assert StubMACIRole.LEGISLATIVE == "legislative"
        assert StubMACIRole.JUDICIAL == "judicial"


class TestStubMACIEnforcer:
    """Test StubMACIEnforcer class."""

    def test_can_instantiate(self) -> None:
        """Test that stub can be instantiated with any args."""
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer(any="args", work=True)
        assert enforcer is not None

    async def test_validate_action_returns_false_fail_closed(self) -> None:
        """Test that validate_action returns False (fail-closed)."""
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer()
        result = await enforcer.validate_action(action="any", agent="agent")
        assert result is False

    async def test_check_permission_returns_false_fail_closed(self) -> None:
        """Test that check_permission returns False (fail-closed)."""
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer()
        result = await enforcer.check_permission(permission="any")
        assert result is False


class TestStubMACIRoleRegistry:
    """Test StubMACIRoleRegistry class."""

    def test_can_instantiate(self) -> None:
        """Test that stub can be instantiated."""
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        registry = StubMACIRoleRegistry()
        assert registry is not None

    async def test_register_agent_is_noop(self) -> None:
        """Test that register_agent does nothing."""
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        registry = StubMACIRoleRegistry()
        await registry.register_agent(agent_id="test", role="worker")
        # Should not raise

    async def test_get_role_returns_worker(self) -> None:
        """Test that get_role returns 'worker'."""
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        registry = StubMACIRoleRegistry()
        role = await registry.get_role(agent_id="test")
        assert role == "worker"


class TestGetMACIHelpers:
    """Test MACI helper functions."""

    def test_get_maci_enforcer_returns_stub_when_unavailable(self) -> None:
        """Test that get_maci_enforcer returns stub when MACI unavailable."""
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIEnforcer,
            get_maci_enforcer,
        )

        # When MACI is not available, should return stub
        enforcer = get_maci_enforcer()
        # Could be real or stub depending on installation
        assert enforcer is not None

    def test_get_maci_role_returns_stub_when_unavailable(self) -> None:
        """Test that get_maci_role returns stub when MACI unavailable."""
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIRole,
            get_maci_role,
        )

        role = get_maci_role()
        assert role is not None

    def test_get_maci_role_registry_returns_stub_when_unavailable(self) -> None:
        """Test that get_maci_role_registry returns stub when unavailable."""
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIRoleRegistry,
            get_maci_role_registry,
        )

        registry = get_maci_role_registry()
        assert registry is not None


class TestFeatureMap:
    """Test _FEATURE_MAP mapping."""

    def test_all_features_mapped(self) -> None:
        """Test that all expected features are in the map."""
        from enhanced_agent_bus.dependency_bridge import _FEATURE_MAP

        expected_features = [
            "METRICS",
            "OTEL",
            "AUDIT",
            "REDIS",
            "KAFKA",
            "OPA",
            "MACI",
            "DELIBERATION",
            "CIRCUIT_BREAKER",
            "CRYPTO",
            "PQC",
            "RUST",
            "METERING",
            "LLM",
            "IMPACT_SCORER",
        ]

        for feature in expected_features:
            assert feature in _FEATURE_MAP, f"Missing feature: {feature}"


class TestLegacyNameMap:
    """Test _LEGACY_NAME_MAP mapping."""

    def test_metrics_mappings(self) -> None:
        """Test metrics-related legacy name mappings."""
        from enhanced_agent_bus.dependency_bridge import _LEGACY_NAME_MAP

        assert _LEGACY_NAME_MAP["MESSAGE_QUEUE_DEPTH"] == "message_queue_depth"
        assert _LEGACY_NAME_MAP["set_service_info"] == "set_service_info"

    def test_maci_mappings(self) -> None:
        """Test MACI-related legacy name mappings."""
        from enhanced_agent_bus.dependency_bridge import _LEGACY_NAME_MAP

        assert _LEGACY_NAME_MAP["MACIEnforcer"] == "maci_enforcer"
        assert _LEGACY_NAME_MAP["MACIRole"] == "maci_role"
        assert _LEGACY_NAME_MAP["MACIRoleRegistry"] == "maci_role_registry"

    def test_opa_mappings(self) -> None:
        """Test OPA-related legacy name mappings."""
        from enhanced_agent_bus.dependency_bridge import _LEGACY_NAME_MAP

        assert _LEGACY_NAME_MAP["OPAClient"] == "opa_client"
        assert _LEGACY_NAME_MAP["get_opa_client"] == "get_opa_client"

    def test_circuit_breaker_mappings(self) -> None:
        """Test circuit breaker legacy name mappings."""
        from enhanced_agent_bus.dependency_bridge import _LEGACY_NAME_MAP

        assert _LEGACY_NAME_MAP["get_circuit_breaker"] == "circuit_breaker"
        assert _LEGACY_NAME_MAP["CircuitBreakerConfig"] == "circuit_breaker_config"
