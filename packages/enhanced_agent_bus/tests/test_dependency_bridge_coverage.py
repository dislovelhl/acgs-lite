# Constitutional Hash: 608508a9bd224290
# Sprint 53 — dependency_bridge.py coverage
"""
Comprehensive tests for src/core/enhanced_agent_bus/dependency_bridge.py.
Target: ≥95% coverage.

Uses asyncio_mode = "auto" — no @pytest.mark.asyncio decorators needed.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus._compat.utilities.dependency_registry import DependencyRegistry, FeatureFlag
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_registry() -> None:
    """Reset DependencyRegistry and re-initialize with defaults so bridge works."""
    DependencyRegistry.reset()
    DependencyRegistry.initialize_defaults()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_registry_before_each():
    """Ensure a clean, initialised registry before every test."""
    _reset_registry()
    yield
    # Leave state clean for subsequent tests too.
    DependencyRegistry.reset()
    DependencyRegistry.initialize_defaults()


# ---------------------------------------------------------------------------
# Module-level import sanity
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Verify that all public symbols are importable from the bridge."""

    def test_import_is_feature_available(self):
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        assert callable(is_feature_available)

    def test_import_get_dependency(self):
        from enhanced_agent_bus.dependency_bridge import get_dependency

        assert callable(get_dependency)

    def test_import_get_feature_flags(self):
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        assert callable(get_feature_flags)

    def test_import_require_feature(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        assert callable(require_feature)

    def test_import_get_status(self):
        from enhanced_agent_bus.dependency_bridge import get_status

        assert callable(get_status)

    def test_import_optional_import(self):
        from enhanced_agent_bus.dependency_bridge import optional_import

        assert callable(optional_import)

    def test_import_initialize(self):
        from enhanced_agent_bus.dependency_bridge import initialize

        assert callable(initialize)

    def test_import_stub_classes(self):
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIEnforcer,
            StubMACIRole,
            StubMACIRoleRegistry,
        )

        assert StubMACIRole is not None
        assert StubMACIEnforcer is not None
        assert StubMACIRoleRegistry is not None

    def test_import_get_maci_helpers(self):
        from enhanced_agent_bus.dependency_bridge import (
            get_maci_enforcer,
            get_maci_role,
            get_maci_role_registry,
        )

        assert callable(get_maci_enforcer)
        assert callable(get_maci_role)
        assert callable(get_maci_role_registry)

    def test_feature_map_contains_all_expected_keys(self):
        from enhanced_agent_bus.dependency_bridge import _FEATURE_MAP

        expected = {
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
        }
        assert expected == set(_FEATURE_MAP.keys())

    def test_legacy_name_map_non_empty(self):
        from enhanced_agent_bus.dependency_bridge import _LEGACY_NAME_MAP

        assert len(_LEGACY_NAME_MAP) > 0


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


class TestInitialize:
    def test_initialize_calls_initialize_defaults(self):
        from enhanced_agent_bus.dependency_bridge import initialize

        # Reset so we can detect the call clearly.
        DependencyRegistry.reset()
        assert DependencyRegistry._initialized is False
        initialize()
        assert DependencyRegistry._initialized is True

    def test_initialize_idempotent(self):
        """Calling initialize twice must not raise."""
        from enhanced_agent_bus.dependency_bridge import initialize

        initialize()
        initialize()  # second call — no-op, no error


# ---------------------------------------------------------------------------
# is_feature_available()
# ---------------------------------------------------------------------------


class TestIsFeatureAvailable:
    def test_known_feature_returns_bool(self):
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        result = is_feature_available("METRICS")
        assert isinstance(result, bool)

    def test_case_insensitive(self):
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        assert is_feature_available("metrics") == is_feature_available("METRICS")

    def test_unknown_feature_returns_false(self, caplog):
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        with caplog.at_level(logging.WARNING):
            result = is_feature_available("NON_EXISTENT_FEATURE_XYZ")

        assert result is False
        assert "Unknown feature requested" in caplog.text

    def test_all_known_features_do_not_raise(self):
        from enhanced_agent_bus.dependency_bridge import (
            _FEATURE_MAP,
            is_feature_available,
        )

        for name in _FEATURE_MAP:
            result = is_feature_available(name)
            assert isinstance(result, bool)

    def test_delegates_to_registry_is_available(self):
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        with patch.object(DependencyRegistry, "is_available", return_value=True) as mock_avail:
            result = is_feature_available("MACI")

        assert result is True
        mock_avail.assert_called_once_with(FeatureFlag.MACI)


# ---------------------------------------------------------------------------
# get_dependency()
# ---------------------------------------------------------------------------


class TestGetDependency:
    def test_known_new_name_delegates_to_registry(self):
        from enhanced_agent_bus.dependency_bridge import get_dependency

        sentinel = object()
        with patch.object(DependencyRegistry, "get", return_value=sentinel) as mock_get:
            result = get_dependency("maci_enforcer")

        assert result is sentinel
        mock_get.assert_called_once_with("maci_enforcer", default=None)

    def test_legacy_name_translated(self):
        from enhanced_agent_bus.dependency_bridge import get_dependency

        sentinel = object()
        # "MACIEnforcer" → "maci_enforcer"
        with patch.object(DependencyRegistry, "get", return_value=sentinel) as mock_get:
            result = get_dependency("MACIEnforcer")

        assert result is sentinel
        mock_get.assert_called_once_with("maci_enforcer", default=None)

    def test_default_returned_when_unavailable(self):
        from enhanced_agent_bus.dependency_bridge import get_dependency

        result = get_dependency("completely_unknown_dep_xyz", default="fallback")
        assert result == "fallback"

    def test_all_legacy_names_translate_without_error(self):
        from enhanced_agent_bus.dependency_bridge import (
            _LEGACY_NAME_MAP,
            get_dependency,
        )

        for legacy_name in _LEGACY_NAME_MAP:
            # Should not raise; return value doesn't matter here.
            get_dependency(legacy_name, default=None)

    def test_name_not_in_legacy_map_passed_through(self):
        """Names not in _LEGACY_NAME_MAP are forwarded verbatim."""
        from enhanced_agent_bus.dependency_bridge import get_dependency

        with patch.object(DependencyRegistry, "get", return_value=None) as mock_get:
            get_dependency("some_new_name_not_in_map")

        mock_get.assert_called_once_with("some_new_name_not_in_map", default=None)

    def test_custom_default_forwarded(self):
        from enhanced_agent_bus.dependency_bridge import get_dependency

        sentinel = object()
        with patch.object(DependencyRegistry, "get", return_value=sentinel) as mock_get:
            get_dependency("maci_role", default=42)

        mock_get.assert_called_once_with("maci_role", default=42)


# ---------------------------------------------------------------------------
# get_feature_flags()
# ---------------------------------------------------------------------------


class TestGetFeatureFlags:
    def test_returns_dict(self):
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()
        assert isinstance(flags, dict)

    def test_all_expected_keys_present(self):
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()
        expected_keys = {
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
        }
        assert expected_keys == set(flags.keys())

    def test_all_values_are_bool(self):
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()
        for key, value in flags.items():
            assert isinstance(value, bool), f"Flag {key!r} should be bool, got {type(value)}"

    def test_config_available_always_true(self):
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()
        assert flags["CONFIG_AVAILABLE"] is True

    def test_auto_initializes_if_not_initialized(self):
        """get_feature_flags() must initialize the registry when it isn't yet."""
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        DependencyRegistry.reset()
        assert DependencyRegistry._initialized is False

        flags = get_feature_flags()

        assert DependencyRegistry._initialized is True
        assert isinstance(flags, dict)

    def test_does_not_reinitialize_if_already_initialized(self):
        """When registry is already initialized, initialize() should NOT be called again."""
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        # Ensure it's initialized.
        assert DependencyRegistry._initialized is True

        with patch("enhanced_agent_bus.dependency_bridge.initialize") as mock_init:
            get_feature_flags()

        mock_init.assert_not_called()


# ---------------------------------------------------------------------------
# require_feature()
# ---------------------------------------------------------------------------


class TestRequireFeature:
    def test_raises_for_unknown_feature(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        with pytest.raises(RuntimeError, match="Unknown feature"):
            require_feature("DOES_NOT_EXIST")

    def test_raises_runtime_error_for_unavailable_feature(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        # Make registry report the feature as unavailable.
        with patch.object(DependencyRegistry, "is_available", return_value=False):
            with pytest.raises((RuntimeError, Exception)):
                require_feature("MACI")

    def test_does_not_raise_when_feature_available(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        with patch.object(DependencyRegistry, "is_available", return_value=True):
            require_feature("REDIS")  # Should not raise.

    def test_case_insensitive_lookup(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        with patch.object(DependencyRegistry, "is_available", return_value=True):
            require_feature("redis")  # lowercase

    def test_unknown_feature_does_not_call_registry(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        with patch.object(DependencyRegistry, "require") as mock_req:
            with pytest.raises(RuntimeError):
                require_feature("BOGUS_FEATURE")
        mock_req.assert_not_called()

    def test_known_feature_delegates_to_registry_require(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        with patch.object(DependencyRegistry, "require") as mock_req:
            require_feature("OTEL")

        mock_req.assert_called_once_with(FeatureFlag.OTEL)


# ---------------------------------------------------------------------------
# get_status()
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_dict(self):
        from enhanced_agent_bus.dependency_bridge import get_status

        status = get_status()
        assert isinstance(status, dict)

    def test_contains_features_key(self):
        from enhanced_agent_bus.dependency_bridge import get_status

        status = get_status()
        assert "features" in status

    def test_contains_dependencies_key(self):
        from enhanced_agent_bus.dependency_bridge import get_status

        status = get_status()
        assert "dependencies" in status

    def test_delegates_to_registry_get_status(self):
        from enhanced_agent_bus.dependency_bridge import get_status

        fake_status: dict = {"features": {}, "dependencies": {}}
        with patch.object(DependencyRegistry, "get_status", return_value=fake_status) as mock_gs:
            result = get_status()

        assert result is fake_status
        mock_gs.assert_called_once()


# ---------------------------------------------------------------------------
# optional_import()
# ---------------------------------------------------------------------------


class TestOptionalImport:
    def test_returns_default_when_feature_unavailable(self):
        from enhanced_agent_bus.dependency_bridge import optional_import

        with patch(
            "enhanced_agent_bus.dependency_bridge.is_feature_available",
            return_value=False,
        ):
            result = optional_import("some.module", "SomeClass", "MACI", default="stub")

        assert result == "stub"

    def test_returns_default_none_when_feature_unavailable_and_no_default(self):
        from enhanced_agent_bus.dependency_bridge import optional_import

        with patch(
            "enhanced_agent_bus.dependency_bridge.is_feature_available",
            return_value=False,
        ):
            result = optional_import("some.module", "SomeClass", "MACI")

        assert result is None

    def test_calls_get_dependency_when_feature_available(self):
        from enhanced_agent_bus.dependency_bridge import optional_import

        sentinel = object()
        with (
            patch(
                "enhanced_agent_bus.dependency_bridge.is_feature_available",
                return_value=True,
            ),
            patch(
                "enhanced_agent_bus.dependency_bridge.get_dependency",
                return_value=sentinel,
            ) as mock_gd,
        ):
            result = optional_import("some.module", "SomeClass", "MACI", default="stub")

        assert result is sentinel
        mock_gd.assert_called_once_with("SomeClass", default="stub")

    def test_passes_default_to_get_dependency(self):
        from enhanced_agent_bus.dependency_bridge import optional_import

        with (
            patch(
                "enhanced_agent_bus.dependency_bridge.is_feature_available",
                return_value=True,
            ),
            patch(
                "enhanced_agent_bus.dependency_bridge.get_dependency",
                return_value=None,
            ) as mock_gd,
        ):
            optional_import("mod", "Cls", "REDIS", default=42)

        mock_gd.assert_called_once_with("Cls", default=42)


# ---------------------------------------------------------------------------
# StubMACIRole
# ---------------------------------------------------------------------------


class TestStubMACIRole:
    def test_role_constants_exist(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIRole

        assert StubMACIRole.WORKER == "worker"
        assert StubMACIRole.CRITIC == "critic"
        assert StubMACIRole.SECURITY_AUDITOR == "security_auditor"
        assert StubMACIRole.MONITOR == "monitor"
        assert StubMACIRole.EXECUTIVE == "executive"
        assert StubMACIRole.LEGISLATIVE == "legislative"
        assert StubMACIRole.JUDICIAL == "judicial"


# ---------------------------------------------------------------------------
# StubMACIEnforcer
# ---------------------------------------------------------------------------


class TestStubMACIEnforcer:
    def test_instantiation_no_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer()
        assert enforcer is not None

    def test_instantiation_with_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer("arg1", kwarg1="val")
        assert enforcer is not None

    async def test_validate_action_returns_true(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer()
        result = await enforcer.validate_action("agent", "action")
        assert result is False

    async def test_validate_action_no_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer()
        result = await enforcer.validate_action()
        assert result is False

    async def test_check_permission_returns_true(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer()
        result = await enforcer.check_permission("agent", "resource")
        assert result is False

    async def test_check_permission_no_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIEnforcer

        enforcer = StubMACIEnforcer()
        result = await enforcer.check_permission()
        assert result is False


# ---------------------------------------------------------------------------
# StubMACIRoleRegistry
# ---------------------------------------------------------------------------


class TestStubMACIRoleRegistry:
    def test_instantiation_no_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        reg = StubMACIRoleRegistry()
        assert reg is not None

    def test_instantiation_with_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        reg = StubMACIRoleRegistry("arg1", kwarg1="v")
        assert reg is not None

    async def test_register_agent_returns_none(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        reg = StubMACIRoleRegistry()
        result = await reg.register_agent("agent_id", role="worker")
        assert result is None

    async def test_register_agent_no_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        reg = StubMACIRoleRegistry()
        result = await reg.register_agent()
        assert result is None

    async def test_get_role_returns_worker(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        reg = StubMACIRoleRegistry()
        result = await reg.get_role("agent_id")
        assert result == "worker"

    async def test_get_role_no_args(self):
        from enhanced_agent_bus.dependency_bridge import StubMACIRoleRegistry

        reg = StubMACIRoleRegistry()
        result = await reg.get_role()
        assert result == "worker"


# ---------------------------------------------------------------------------
# get_maci_enforcer()
# ---------------------------------------------------------------------------


class TestGetMACIEnforcer:
    def test_returns_stub_when_dependency_is_none(self):
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIEnforcer,
            get_maci_enforcer,
        )

        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=None,
        ):
            result = get_maci_enforcer()

        assert result is StubMACIEnforcer

    def test_returns_real_dependency_when_available(self):
        from enhanced_agent_bus.dependency_bridge import get_maci_enforcer

        fake_enforcer = MagicMock()
        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=fake_enforcer,
        ):
            result = get_maci_enforcer()

        assert result is fake_enforcer

    def test_requests_correct_dependency_name(self):
        from enhanced_agent_bus.dependency_bridge import get_maci_enforcer

        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=None,
        ) as mock_gd:
            get_maci_enforcer()

        mock_gd.assert_called_once_with("maci_enforcer")


# ---------------------------------------------------------------------------
# get_maci_role()
# ---------------------------------------------------------------------------


class TestGetMACIRole:
    def test_returns_stub_when_dependency_is_none(self):
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIRole,
            get_maci_role,
        )

        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=None,
        ):
            result = get_maci_role()

        assert result is StubMACIRole

    def test_returns_real_dependency_when_available(self):
        from enhanced_agent_bus.dependency_bridge import get_maci_role

        fake_role = MagicMock()
        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=fake_role,
        ):
            result = get_maci_role()

        assert result is fake_role

    def test_requests_correct_dependency_name(self):
        from enhanced_agent_bus.dependency_bridge import get_maci_role

        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=None,
        ) as mock_gd:
            get_maci_role()

        mock_gd.assert_called_once_with("maci_role")


# ---------------------------------------------------------------------------
# get_maci_role_registry()
# ---------------------------------------------------------------------------


class TestGetMACIRoleRegistry:
    def test_returns_stub_when_dependency_is_none(self):
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIRoleRegistry,
            get_maci_role_registry,
        )

        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=None,
        ):
            result = get_maci_role_registry()

        assert result is StubMACIRoleRegistry

    def test_returns_real_dependency_when_available(self):
        from enhanced_agent_bus.dependency_bridge import get_maci_role_registry

        fake_registry = MagicMock()
        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=fake_registry,
        ):
            result = get_maci_role_registry()

        assert result is fake_registry

    def test_requests_correct_dependency_name(self):
        from enhanced_agent_bus.dependency_bridge import get_maci_role_registry

        with patch(
            "enhanced_agent_bus.dependency_bridge.get_dependency",
            return_value=None,
        ) as mock_gd:
            get_maci_role_registry()

        mock_gd.assert_called_once_with("maci_role_registry")


# ---------------------------------------------------------------------------
# Integration: round-trip through bridge with real registry
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end checks that exercise the bridge against the live registry."""

    def test_get_feature_flags_uses_real_registry(self):
        from enhanced_agent_bus.dependency_bridge import get_feature_flags

        flags = get_feature_flags()
        # At minimum CONFIG_AVAILABLE must be True.
        assert flags["CONFIG_AVAILABLE"] is True

    def test_get_status_includes_all_registered_deps(self):
        from enhanced_agent_bus.dependency_bridge import get_status

        status = get_status()
        assert len(status["dependencies"]) > 0

    def test_get_dependency_unknown_returns_none_by_default(self):
        from enhanced_agent_bus.dependency_bridge import get_dependency

        result = get_dependency("__this_dep_does_not_exist__")
        assert result is None

    def test_is_feature_available_returns_false_for_unknown(self):
        from enhanced_agent_bus.dependency_bridge import is_feature_available

        assert is_feature_available("__unknown__feature__") is False

    def test_require_feature_raises_for_unknown(self):
        from enhanced_agent_bus.dependency_bridge import require_feature

        with pytest.raises(RuntimeError, match="Unknown feature"):
            require_feature("__this_is_unknown__")

    def test_optional_import_returns_default_for_unknown_feature(self):
        from enhanced_agent_bus.dependency_bridge import optional_import

        result = optional_import("json", "dumps", "__UNKNOWN_FEATURE__", default="default_val")
        assert result == "default_val"

    def test_get_maci_enforcer_is_stub_or_class(self):
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIEnforcer,
            get_maci_enforcer,
        )

        result = get_maci_enforcer()
        # Either the real enforcer class or the stub.
        assert result is not None
        if result is StubMACIEnforcer:
            # Ensure stub is usable.
            enforcer = result()
            assert enforcer is not None

    def test_get_maci_role_is_stub_or_class(self):
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIRole,
            get_maci_role,
        )

        result = get_maci_role()
        assert result is not None
        if result is StubMACIRole:
            assert result.WORKER == "worker"

    def test_get_maci_role_registry_is_stub_or_class(self):
        from enhanced_agent_bus.dependency_bridge import (
            StubMACIRoleRegistry,
            get_maci_role_registry,
        )

        result = get_maci_role_registry()
        assert result is not None
        if result is StubMACIRoleRegistry:
            reg = result()
            assert reg is not None
