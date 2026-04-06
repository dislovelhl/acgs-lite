# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/__init__.py
Target: ≥95% line coverage on the __init__ module (71 stmts)
"""

import importlib
import sys
import warnings
from typing import ClassVar

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helper: import the package under test (already cached in sys.modules)
# ---------------------------------------------------------------------------


def get_bus():
    """Return the already-imported enhanced_agent_bus package."""
    return importlib.import_module("packages.enhanced_agent_bus")


# ===========================================================================
# 1. Module-level metadata
# ===========================================================================


class TestModuleMetadata:
    """Verify __version__ and __constitutional_hash__ are set correctly."""

    def test_version_string(self):
        bus = get_bus()
        assert bus.__version__ == "3.0.2"

    def test_constitutional_hash_attribute(self):
        bus = get_bus()
        assert bus.__constitutional_hash__ == CONSTITUTIONAL_HASH

    def test_constitutional_hash_is_string(self):
        bus = get_bus()
        assert isinstance(bus.__constitutional_hash__, str)

    def test_version_is_string(self):
        bus = get_bus()
        assert isinstance(bus.__version__, str)


# ===========================================================================
# 2. sys.modules aliasing
# ===========================================================================


class TestSysModulesAliasing:
    """Module aliases are registered in sys.modules during import."""

    def test_enhanced_agent_bus_alias_in_sys_modules(self):
        bus = get_bus()
        assert "enhanced_agent_bus" in sys.modules
        assert sys.modules["enhanced_agent_bus"] is bus

    def test_src_core_enhanced_agent_bus_alias(self):
        bus = get_bus()
        assert "packages.enhanced_agent_bus" in sys.modules
        assert sys.modules["packages.enhanced_agent_bus"] is bus

    def test_core_enhanced_agent_bus_alias(self):
        bus = get_bus()
        assert "core.enhanced_agent_bus" in sys.modules
        assert sys.modules["core.enhanced_agent_bus"] is bus

    def test_aliases_point_to_same_object(self):
        bus = get_bus()
        aliases = ["enhanced_agent_bus", "core.enhanced_agent_bus"]
        for alias in aliases:
            assert sys.modules.get(alias) is bus, f"Alias '{alias}' mismatch"


# ===========================================================================
# 3. CONSTITUTIONAL_HASH import
# ===========================================================================


class TestConstitutionalHashImport:
    """CONSTITUTIONAL_HASH must be importable and correct."""

    def test_constitutional_hash_exported(self):
        bus = get_bus()
        assert hasattr(bus, "CONSTITUTIONAL_HASH")

    def test_constitutional_hash_value(self):
        bus = get_bus()
        assert bus.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_model_hash_exported(self):
        bus = get_bus()
        # MODEL_HASH is also re-exported from models
        assert hasattr(bus, "MODEL_HASH")

    def test_model_hash_matches(self):
        bus = get_bus()
        assert bus.MODEL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ===========================================================================
# 4. Init class
# ===========================================================================


class TestInitClass:
    """Test the Init helper class defined in __init__.py."""

    def test_init_class_exists(self):
        bus = get_bus()
        assert hasattr(bus, "Init")

    def test_init_instantiation_no_args(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance is not None

    def test_init_uses_constitutional_hash_by_default(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance._constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_init_custom_hash(self):
        bus = get_bus()
        custom = "deadbeef12345678"  # pragma: allowlist secret
        instance = bus.Init(constitutional_hash=custom)
        assert instance._constitutional_hash == custom

    def test_init_process_none_returns_none(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance.process(None) is None

    def test_init_process_string_returns_string(self):
        bus = get_bus()
        instance = bus.Init()
        result = instance.process("hello")
        assert result == "hello"

    def test_init_process_integer_returns_none(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance.process(123) is None  # type: ignore[arg-type]

    def test_init_process_list_returns_none(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance.process(["a", "b"]) is None  # type: ignore[arg-type]

    def test_init_process_empty_string(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance.process("") == ""

    def test_init_process_unicode_string(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance.process("héllo wörld") == "héllo wörld"

    def test_init_process_dict_returns_none(self):
        bus = get_bus()
        instance = bus.Init()
        assert instance.process({}) is None  # type: ignore[arg-type]

    def test_init_process_bool_returns_none(self):
        # bool is a subclass of int, not str
        bus = get_bus()
        instance = bus.Init()
        assert instance.process(True) is None  # type: ignore[arg-type]


# ===========================================================================
# 5. Feature flag constants
# ===========================================================================


class TestFeatureFlagConstants:
    """Feature flags are boolean constants derived from dependency_bridge."""

    def test_circuit_breaker_enabled_is_bool(self):
        bus = get_bus()
        assert isinstance(bus.CIRCUIT_BREAKER_ENABLED, bool)

    def test_deliberation_available_is_bool(self):
        bus = get_bus()
        assert isinstance(bus.DELIBERATION_AVAILABLE, bool)

    def test_metering_available_is_bool(self):
        bus = get_bus()
        assert isinstance(bus.METERING_AVAILABLE, bool)

    def test_metrics_enabled_is_bool(self):
        bus = get_bus()
        assert isinstance(bus.METRICS_ENABLED, bool)

    def test_use_rust_is_bool(self):
        bus = get_bus()
        assert isinstance(bus.USE_RUST, bool)

    def test_feature_flags_not_none(self):
        bus = get_bus()
        for flag in (
            "CIRCUIT_BREAKER_ENABLED",
            "DELIBERATION_AVAILABLE",
            "METERING_AVAILABLE",
            "METRICS_ENABLED",
            "USE_RUST",
        ):
            assert getattr(bus, flag) is not None

    def test_feature_flags_in_all(self):
        bus = get_bus()
        for flag in (
            "CIRCUIT_BREAKER_ENABLED",
            "DELIBERATION_AVAILABLE",
            "METERING_AVAILABLE",
            "METRICS_ENABLED",
            "USE_RUST",
        ):
            assert flag in bus.__all__, f"{flag} not in __all__"

    def test_feature_flags_use_dependency_bridge_key_names(self, monkeypatch):
        bus = get_bus()
        original_values = {
            "CIRCUIT_BREAKER_ENABLED": bus.CIRCUIT_BREAKER_ENABLED,
            "DELIBERATION_AVAILABLE": bus.DELIBERATION_AVAILABLE,
            "METERING_AVAILABLE": bus.METERING_AVAILABLE,
            "METRICS_ENABLED": bus.METRICS_ENABLED,
        }

        import enhanced_agent_bus.dependency_bridge as bridge

        monkeypatch.setattr(
            bridge,
            "get_feature_flags",
            lambda: {
                "CIRCUIT_BREAKER_ENABLED": True,
                "DELIBERATION_AVAILABLE": True,
                "METERING_AVAILABLE": True,
                "METRICS_ENABLED": True,
                "USE_RUST": True,
            },
        )

        reloaded = importlib.reload(importlib.import_module("packages.enhanced_agent_bus"))

        assert reloaded.CIRCUIT_BREAKER_ENABLED is True
        assert reloaded.DELIBERATION_AVAILABLE is True
        assert reloaded.METERING_AVAILABLE is True
        assert reloaded.METRICS_ENABLED is True

        reloaded.CIRCUIT_BREAKER_ENABLED = original_values["CIRCUIT_BREAKER_ENABLED"]
        reloaded.DELIBERATION_AVAILABLE = original_values["DELIBERATION_AVAILABLE"]
        reloaded.METERING_AVAILABLE = original_values["METERING_AVAILABLE"]
        reloaded.METRICS_ENABLED = original_values["METRICS_ENABLED"]


# ===========================================================================
# 7. Core exception exports
# ===========================================================================


class TestExceptionExports:
    """All exception classes from exceptions.py must be importable."""

    EXCEPTION_NAMES: ClassVar[list] = [
        "AgentAlreadyRegisteredError",
        "AgentBusError",
        "AgentCapabilityError",
        "AgentError",
        "AgentNotRegisteredError",
        "BusAlreadyStartedError",
        "BusNotStartedError",
        "BusOperationError",
        "ConfigurationError",
        "ConstitutionalError",
        "ConstitutionalHashMismatchError",
        "ConstitutionalValidationError",
        "DeliberationError",
        "DeliberationTimeoutError",
        "HandlerExecutionError",
        "MessageDeliveryError",
        "MessageError",
        "MessageRoutingError",
        "MessageTimeoutError",
        "MessageValidationError",
        "OPAConnectionError",
        "OPANotInitializedError",
        "PolicyError",
        "PolicyEvaluationError",
        "PolicyNotFoundError",
        "ReviewConsensusError",
        "SignatureCollectionError",
    ]

    @pytest.mark.parametrize("exc_name", EXCEPTION_NAMES)
    def test_exception_exported(self, exc_name):
        bus = get_bus()
        assert hasattr(bus, exc_name), f"Missing exception: {exc_name}"

    @pytest.mark.parametrize("exc_name", EXCEPTION_NAMES)
    def test_exception_is_class(self, exc_name):
        bus = get_bus()
        obj = getattr(bus, exc_name)
        assert isinstance(obj, type)

    @pytest.mark.parametrize("exc_name", EXCEPTION_NAMES)
    def test_exception_inherits_from_exception(self, exc_name):
        bus = get_bus()
        obj = getattr(bus, exc_name)
        assert issubclass(obj, Exception)

    @pytest.mark.parametrize("exc_name", EXCEPTION_NAMES)
    def test_exception_in_all(self, exc_name):
        bus = get_bus()
        assert exc_name in bus.__all__, f"{exc_name} not in __all__"


# ===========================================================================
# 8. Interface exports
# ===========================================================================


class TestInterfaceExports:
    """Protocol interfaces must be exported."""

    INTERFACE_NAMES: ClassVar[list] = [
        "AgentRegistry",
        "MessageHandler",
        "MessageRouter",
        "MetricsCollector",
        "ValidationStrategy",
    ]

    @pytest.mark.parametrize("name", INTERFACE_NAMES)
    def test_interface_exported(self, name):
        bus = get_bus()
        assert hasattr(bus, name), f"Missing interface: {name}"

    @pytest.mark.parametrize("name", INTERFACE_NAMES)
    def test_interface_in_all(self, name):
        bus = get_bus()
        assert name in bus.__all__, f"{name} not in __all__"


# ===========================================================================
# 9. Model exports
# ===========================================================================


class TestModelExports:
    """Data models from models.py must be exported."""

    MODEL_NAMES: ClassVar[list] = [
        "AgentMessage",
        "MessageStatus",
        "MessageType",
        "Priority",
        "RiskLevel",
        "RoutingContext",
        "SessionGovernanceConfig",
        "ValidationStatus",
        "ModelPQCMetadata",
    ]

    @pytest.mark.parametrize("name", MODEL_NAMES)
    def test_model_exported(self, name):
        bus = get_bus()
        assert hasattr(bus, name), f"Missing model: {name}"


# ===========================================================================
# 10. Registry exports
# ===========================================================================


class TestRegistryExports:
    """Registry and routing classes must be exported."""

    REGISTRY_NAMES: ClassVar[list] = [
        "CapabilityBasedRouter",
        "CompositeValidationStrategy",
        "DirectMessageRouter",
        "DynamicPolicyValidationStrategy",
        "InMemoryAgentRegistry",
        "RedisAgentRegistry",
        "RustValidationStrategy",
        "StaticHashValidationStrategy",
    ]

    @pytest.mark.parametrize("name", REGISTRY_NAMES)
    def test_registry_exported(self, name):
        bus = get_bus()
        assert hasattr(bus, name), f"Missing registry item: {name}"

    @pytest.mark.parametrize("name", REGISTRY_NAMES)
    def test_registry_in_all(self, name):
        bus = get_bus()
        assert name in bus.__all__, f"{name} not in __all__"


# ===========================================================================
# 11. Runtime security exports
# ===========================================================================


class TestRuntimeSecurityExports:
    """Runtime security symbols must be exported."""

    SECURITY_NAMES: ClassVar[list] = [
        "RuntimeSecurityConfig",
        "RuntimeSecurityScanner",
        "SecurityEvent",
        "SecurityEventType",
        "SecurityScanResult",
        "SecuritySeverity",
        "get_runtime_security_scanner",
        "scan_content",
    ]

    @pytest.mark.parametrize("name", SECURITY_NAMES)
    def test_security_exported(self, name):
        bus = get_bus()
        assert hasattr(bus, name), f"Missing security export: {name}"

    @pytest.mark.parametrize("name", SECURITY_NAMES)
    def test_security_in_all(self, name):
        bus = get_bus()
        assert name in bus.__all__, f"{name} not in __all__"


# ===========================================================================
# 12. SIEM integration exports
# ===========================================================================


class TestSIEMExports:
    """SIEM integration symbols must be exported."""

    SIEM_NAMES: ClassVar[list] = [
        "AlertLevel",
        "AlertManager",
        "AlertThreshold",
        "EventCorrelator",
        "SIEMConfig",
        "SIEMEventFormatter",
        "SIEMFormat",
        "SIEMIntegration",
        "close_siem",
        "get_siem_integration",
        "initialize_siem",
        "log_security_event",
        "security_audit",
    ]

    @pytest.mark.parametrize("name", SIEM_NAMES)
    def test_siem_exported(self, name):
        bus = get_bus()
        assert hasattr(bus, name), f"Missing SIEM export: {name}"

    @pytest.mark.parametrize("name", SIEM_NAMES)
    def test_siem_in_all(self, name):
        bus = get_bus()
        assert name in bus.__all__, f"{name} not in __all__"


# ===========================================================================
# 13. Session context exports
# ===========================================================================


class TestSessionContextExports:
    """Session context classes must be exported."""

    SESSION_NAMES: ClassVar[list] = [
        "SessionContext",
        "SessionContextManager",
        "SessionContextStore",
    ]

    @pytest.mark.parametrize("name", SESSION_NAMES)
    def test_session_exported(self, name):
        bus = get_bus()
        assert hasattr(bus, name), f"Missing session export: {name}"

    @pytest.mark.parametrize("name", SESSION_NAMES)
    def test_session_in_all(self, name):
        bus = get_bus()
        assert name in bus.__all__, f"{name} not in __all__"


# ===========================================================================
# 14. Policy resolver exports
# ===========================================================================


class TestPolicyResolverExports:
    def test_policy_resolver_exported(self):
        bus = get_bus()
        assert hasattr(bus, "PolicyResolver")

    def test_policy_resolution_result_exported(self):
        bus = get_bus()
        assert hasattr(bus, "PolicyResolutionResult")

    def test_policy_resolver_in_all(self):
        bus = get_bus()
        assert "PolicyResolver" in bus.__all__

    def test_policy_resolution_result_in_all(self):
        bus = get_bus()
        assert "PolicyResolutionResult" in bus.__all__


# ===========================================================================
# 15. Core class exports
# ===========================================================================


class TestCoreClassExports:
    def test_enhanced_agent_bus_exported(self):
        bus = get_bus()
        assert hasattr(bus, "EnhancedAgentBus")

    def test_message_processor_exported(self):
        bus = get_bus()
        assert hasattr(bus, "MessageProcessor")

    def test_bus_configuration_exported(self):
        bus = get_bus()
        assert hasattr(bus, "BusConfiguration")

    def test_metering_manager_exported(self):
        bus = get_bus()
        assert hasattr(bus, "MeteringManager")

    def test_create_metering_manager_exported(self):
        bus = get_bus()
        assert hasattr(bus, "create_metering_manager")

    def test_validation_result_exported(self):
        bus = get_bus()
        assert hasattr(bus, "ValidationResult")

    def test_enhanced_agent_bus_in_all(self):
        bus = get_bus()
        assert "EnhancedAgentBus" in bus.__all__

    def test_message_processor_in_all(self):
        bus = get_bus()
        assert "MessageProcessor" in bus.__all__

    def test_bus_configuration_in_all(self):
        bus = get_bus()
        assert "BusConfiguration" in bus.__all__


# ===========================================================================
# 16. _ext_* module EXT_ALL exports
# ===========================================================================


class TestExtModuleExports:
    """Each _ext_* module contributes names to __all__ via *_ALL constants."""

    EXT_ALL_NAMES: ClassVar[list] = [
        "_CB_ALL",
        "_PQC_ALL",
        "_CW_ALL",
        "_COG_ALL",
        "_PER_ALL",
        "_CBC_ALL",
        "_DS_ALL",
        "_ES_ALL",
        "_MCP_ALL",
        "_CM_ALL",
        "_LG_ALL",
        "_CHAOS_ALL",
    ]

    @pytest.mark.parametrize("list_name", EXT_ALL_NAMES)
    def test_ext_list_is_list(self, list_name):
        bus = get_bus()
        val = getattr(bus, list_name, None)
        assert isinstance(val, list), f"{list_name} should be a list"

    def test_all_ext_names_in_all(self):
        """Every name contributed by _ext_* lists must appear in __all__."""
        bus = get_bus()
        for list_name in self.EXT_ALL_NAMES:
            ext_list = getattr(bus, list_name, [])
            for name in ext_list:
                assert name in bus.__all__, f"'{name}' from {list_name} not in __all__"


# ===========================================================================
# 17. __all__ completeness
# ===========================================================================


class TestAllCompleteness:
    """__all__ must declare all exported names and they must exist."""

    def test_all_is_list(self):
        bus = get_bus()
        assert isinstance(bus.__all__, list)

    def test_all_is_non_empty(self):
        bus = get_bus()
        assert len(bus.__all__) > 50

    def test_all_contains_strings(self):
        # __all__ may contain duplicates contributed by _ext_* modules;
        # we simply verify all entries are strings.
        bus = get_bus()
        assert all(isinstance(n, str) for n in bus.__all__)

    def test_every_name_in_all_is_accessible(self):
        bus = get_bus()
        for name in bus.__all__:
            assert hasattr(bus, name), f"__all__ declares '{name}' but attribute missing"

    def test_all_strings_only(self):
        bus = get_bus()
        assert all(isinstance(n, str) for n in bus.__all__)

    def test_core_exceptions_in_all(self):
        bus = get_bus()
        for exc in ("AgentBusError", "ConstitutionalError", "MessageError"):
            assert exc in bus.__all__

    def test_constitutional_hash_in_all(self):
        bus = get_bus()
        assert "CONSTITUTIONAL_HASH" in bus.__all__


# ===========================================================================
# 18. Import alias deprecation warnings
# ===========================================================================


class TestImportAliasDeprecation:
    """Import alias registration emits DeprecationWarning."""

    def test_module_already_registered_in_sys_modules(self):
        # The module is already imported; verify aliases exist
        bus = get_bus()
        for alias in ("enhanced_agent_bus", "core.enhanced_agent_bus"):
            assert alias in sys.modules
            assert sys.modules[alias] is bus

    def test_src_core_alias_registered(self):
        bus = get_bus()
        assert sys.modules.get("packages.enhanced_agent_bus") is bus


# ===========================================================================
# 19. Full import via importlib
# ===========================================================================


class TestImportViaImportlib:
    """Package can be imported via importlib without errors."""

    def test_importlib_import(self):
        mod = importlib.import_module("packages.enhanced_agent_bus")
        assert mod is not None

    def test_importlib_import_returns_same_object(self):
        mod1 = importlib.import_module("packages.enhanced_agent_bus")
        mod2 = importlib.import_module("packages.enhanced_agent_bus")
        assert mod1 is mod2

    def test_package_has_file_attribute(self):
        bus = get_bus()
        assert hasattr(bus, "__file__")
        assert bus.__file__ is not None
        assert "__init__" in bus.__file__

    def test_package_has_name_attribute(self):
        bus = get_bus()
        # The package name is the last two components: enhanced_agent_bus
        assert "enhanced_agent_bus" in bus.__name__

    def test_package_has_spec(self):
        bus = get_bus()
        assert hasattr(bus, "__spec__")


# ===========================================================================
# 20. _feature_flags temporary variable cleaned up
# ===========================================================================


class TestFeatureFlagsCleanup:
    """The _feature_flags temporary variable must be deleted after use."""

    def test_feature_flags_temp_deleted(self):
        bus = get_bus()
        # After `del _feature_flags`, _feature_flags should NOT be an attribute
        assert not hasattr(bus, "_feature_flags")

    def test_get_feature_flags_private_not_exported(self):
        bus = get_bus()
        # _get_feature_flags is private; it should not appear in __all__
        assert "_get_feature_flags" not in bus.__all__


# ===========================================================================
# 21. Specific types from models
# ===========================================================================


class TestSpecificModelTypes:
    """Spot-check a few model types for expected attributes."""

    def test_message_type_is_enum(self):
        bus = get_bus()
        import enum

        assert issubclass(bus.MessageType, enum.Enum)

    def test_priority_is_enum(self):
        bus = get_bus()
        import enum

        assert issubclass(bus.Priority, enum.Enum)

    def test_message_status_is_enum(self):
        bus = get_bus()
        import enum

        assert issubclass(bus.MessageStatus, enum.Enum)

    def test_risk_level_is_enum(self):
        bus = get_bus()
        import enum

        assert issubclass(bus.RiskLevel, enum.Enum)

    def test_validation_status_is_enum(self):
        bus = get_bus()
        import enum

        assert issubclass(bus.ValidationStatus, enum.Enum)
