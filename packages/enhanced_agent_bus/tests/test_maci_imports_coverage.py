# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/maci_imports.py
Covers all import paths, fallback stubs, availability flags, and all branches.
"""

import importlib
import sys
from datetime import UTC, datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


@pytest.fixture(autouse=True)
def _restore_maci_imports_globals():
    """Backup and restore maci_imports module globals AND sys.modules after each test.

    Tests in this file mutate module-level state: _model_cache, CONSTITUTIONAL_HASH,
    MACI_CORE_AVAILABLE, and module __dict__ entries (AgentMessage, MessageType,
    get_enum_value). The _reload_maci_imports() helper also deletes and re-creates
    the sys.modules entry, which can leave a different module object in place.
    Without full restoration, mutations leak to subsequent test files sharing the
    same xdist worker. (PM-012, PM-014 patterns)
    """
    import enhanced_agent_bus.maci_imports as m

    # Snapshot mutable globals before test
    orig_model_cache = dict(m._model_cache)
    orig_constitutional_hash = m.CONSTITUTIONAL_HASH
    orig_maci_core_available = m.MACI_CORE_AVAILABLE
    orig_global_settings_available = m.GLOBAL_SETTINGS_AVAILABLE
    # Snapshot lazy-loaded attrs that get injected into module __dict__
    orig_lazy_attrs = {}
    for attr in ("AgentMessage", "MessageType", "get_enum_value"):
        if attr in m.__dict__:
            orig_lazy_attrs[attr] = m.__dict__[attr]

    # Snapshot sys.modules entries that _reload_maci_imports() and _reload_with_stubs()
    # may delete or replace. Without restoring these, other test files in the same
    # xdist worker see corrupted module entries.
    _maci_mod_key = "enhanced_agent_bus.maci_imports"
    _sysmod_keys_to_protect = [
        _maci_mod_key,
        "enhanced_agent_bus.exceptions",
        "enhanced_agent_bus.exceptions.base",
        "enhanced_agent_bus.exceptions.maci",
        "enhanced_agent_bus.utils",
        "enhanced_agent_bus.utils",
        "src.core.shared.config",
    ]
    orig_sysmodules = {}
    _SENTINEL = object()
    for key in _sysmod_keys_to_protect:
        orig_sysmodules[key] = sys.modules.get(key, _SENTINEL)

    yield

    # Restore sys.modules entries first (before restoring module globals)
    for key, orig_val in orig_sysmodules.items():
        if orig_val is _SENTINEL:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = orig_val

    # Re-import the original module object (in case _reload_maci_imports replaced it)
    m = sys.modules.get(_maci_mod_key)
    if m is None:
        # Module was removed and not restored — force re-import
        import importlib

        m = importlib.import_module(_maci_mod_key)

    # Restore all mutated globals on the canonical module object
    m._model_cache.clear()
    m._model_cache.update(orig_model_cache)
    m.CONSTITUTIONAL_HASH = orig_constitutional_hash
    m.MACI_CORE_AVAILABLE = orig_maci_core_available
    m.GLOBAL_SETTINGS_AVAILABLE = orig_global_settings_available

    # Restore or remove lazy-loaded attrs from module __dict__
    for attr in ("AgentMessage", "MessageType", "get_enum_value"):
        if attr in orig_lazy_attrs:
            m.__dict__[attr] = orig_lazy_attrs[attr]
        else:
            m.__dict__.pop(attr, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_maci_imports() -> ModuleType:
    """Reload maci_imports fresh (clearing module-level caches)."""
    mod_name = "enhanced_agent_bus.maci_imports"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# 1. Module-level imports succeed in normal environment
# ---------------------------------------------------------------------------


class TestModuleLevelImports:
    """Verify that the module imports cleanly in the test environment."""

    def test_module_imports_without_error(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert m is not None

    def test_feature_flags_are_booleans(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert isinstance(m.MACI_CORE_AVAILABLE, bool)
        assert isinstance(m.OBSERVABILITY_AVAILABLE, bool)
        assert isinstance(m.GLOBAL_SETTINGS_AVAILABLE, bool)

    def test_observability_always_false(self) -> None:
        """OBSERVABILITY_AVAILABLE is never set to True in this module."""
        import enhanced_agent_bus.maci_imports as m

        assert m.OBSERVABILITY_AVAILABLE is False

    def test_constitutional_hash_default(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert m.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_exception_classes_not_none(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert m.MACIError is not None
        assert m.MACIRoleViolationError is not None
        assert m.MACISelfValidationError is not None
        assert m.MACICrossRoleValidationError is not None
        assert m.MACIRoleNotAssignedError is not None

    def test_exception_classes_are_exceptions(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        for cls in (
            m.MACIError,
            m.MACIRoleViolationError,
            m.MACISelfValidationError,
            m.MACICrossRoleValidationError,
            m.MACIRoleNotAssignedError,
        ):
            assert issubclass(cls, BaseException)

    def test_get_iso_timestamp_callable(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert callable(m.get_iso_timestamp)

    def test_get_iso_timestamp_returns_string(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        result = m.get_iso_timestamp()
        assert isinstance(result, str)

    def test_all_exports_defined(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        for name in m.__all__:
            # Models are lazy; skip them here
            if name in ("AgentMessage", "MessageType", "get_enum_value"):
                continue
            assert hasattr(m, name), f"Missing export: {name}"


# ---------------------------------------------------------------------------
# 2. Global settings import branch
# ---------------------------------------------------------------------------


class TestGlobalSettingsImport:
    """Test GLOBAL_SETTINGS_AVAILABLE flag behaviour."""

    def test_global_settings_available_when_present(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        # In the test environment the shared config can import
        assert isinstance(m.GLOBAL_SETTINGS_AVAILABLE, bool)

    def test_global_settings_none_when_import_fails(self) -> None:
        """When _compat.config raises ImportError, global_settings is None."""
        # maci_imports imports via _compat.config, not src.core.shared.config directly
        original = sys.modules.get("enhanced_agent_bus._compat.config")
        try:
            sys.modules["enhanced_agent_bus._compat.config"] = None  # type: ignore[assignment]
            mod = _reload_maci_imports()
            assert mod.GLOBAL_SETTINGS_AVAILABLE is False
            assert mod.global_settings is None
        finally:
            if original is None:
                sys.modules.pop("enhanced_agent_bus._compat.config", None)
            else:
                sys.modules["enhanced_agent_bus._compat.config"] = original

    def test_global_settings_set_when_import_succeeds(self) -> None:
        """When _compat.config imports cleanly, global_settings is set and flag is True."""
        fake_settings = MagicMock(name="settings")
        fake_config_module = MagicMock()
        fake_config_module.settings = fake_settings

        original = sys.modules.get("enhanced_agent_bus._compat.config")
        try:
            sys.modules["enhanced_agent_bus._compat.config"] = fake_config_module
            mod = _reload_maci_imports()
            assert mod.GLOBAL_SETTINGS_AVAILABLE is True
            assert mod.global_settings is fake_settings
        finally:
            if original is None:
                sys.modules.pop("enhanced_agent_bus._compat.config", None)
            else:
                sys.modules["enhanced_agent_bus._compat.config"] = original


# ---------------------------------------------------------------------------
# 3. _load_models — lazy model loader
# ---------------------------------------------------------------------------


class TestLoadModels:
    """Test the _load_models() function directly."""

    def test_load_models_returns_true_when_models_available(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        # Reset cache so _load_models runs fresh
        m._model_cache.clear()
        m.MACI_CORE_AVAILABLE = False
        result = m._load_models()
        assert result is True
        assert m.MACI_CORE_AVAILABLE is True

    def test_load_models_early_return_when_already_loaded(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache["_loaded"] = True
        result = m._load_models()
        assert result is True

    def test_load_models_returns_false_when_all_paths_fail(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m.MACI_CORE_AVAILABLE = False

        from unittest.mock import patch

        # Override builtins.__import__ to always raise ImportError inside _load_models
        original_import = __import__

        def failing_import(name, *args, **kwargs):
            raise ImportError(f"Simulated failure for {name}")

        with patch("builtins.__import__", side_effect=failing_import):
            result = m._load_models()
            assert result is False

    def test_load_models_populates_cache(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m.MACI_CORE_AVAILABLE = False
        m._load_models()
        assert m._model_cache.get("_loaded") is True
        assert "AgentMessage" in m._model_cache
        assert "MessageType" in m._model_cache
        assert "get_enum_value" in m._model_cache
        assert "CONSTITUTIONAL_HASH" in m._model_cache


# ---------------------------------------------------------------------------
# 4. Lazy accessor functions
# ---------------------------------------------------------------------------


class TestLazyAccessors:
    """Test get_agent_message, get_message_type, get_enum_value_func."""

    def test_get_agent_message_returns_class(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        result = m.get_agent_message()
        assert result is not None

    def test_get_message_type_returns_class(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        result = m.get_message_type()
        assert result is not None

    def test_get_enum_value_func_returns_callable(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        result = m.get_enum_value_func()
        assert callable(result)

    def test_get_agent_message_triggers_load_when_cache_empty(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        result = m.get_agent_message()
        assert result is not None

    def test_get_message_type_triggers_load_when_cache_empty(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        result = m.get_message_type()
        assert result is not None

    def test_get_enum_value_func_triggers_load_when_cache_empty(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        result = m.get_enum_value_func()
        assert result is not None

    def test_accessors_return_none_when_models_unavailable(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        # _loaded stays False — no models in cache
        with patch.object(m, "_load_models", return_value=False):
            assert m.get_agent_message() is None
            assert m.get_message_type() is None
            assert m.get_enum_value_func() is None

    def test_get_agent_message_skips_load_when_already_cached(self) -> None:
        """Cover the 304->306 branch: _loaded True skips _load_models call."""
        import enhanced_agent_bus.maci_imports as m

        sentinel = object()
        m._model_cache["_loaded"] = True
        m._model_cache["AgentMessage"] = sentinel
        result = m.get_agent_message()
        assert result is sentinel
        # Clean up
        del m._model_cache["AgentMessage"]
        m._model_cache.clear()


# ---------------------------------------------------------------------------
# 5. __getattr__ module-level lazy loading
# ---------------------------------------------------------------------------


class TestModuleGetattr:
    """Test module-level __getattr__ for lazy model attributes."""

    def test_getattr_agent_message(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        ag = m.__getattr__("AgentMessage")
        assert ag is not None

    def test_getattr_message_type(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        mt = m.__getattr__("MessageType")
        assert mt is not None

    def test_getattr_get_enum_value(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        ev = m.__getattr__("get_enum_value")
        assert callable(ev)

    def test_getattr_unknown_lazy_attr_raises_attribute_error(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        # Force _load_models to fail so value is not in cache
        with patch.object(m, "_load_models", return_value=False):
            try:
                m.__getattr__("AgentMessage")
                raise AssertionError("Should have raised AttributeError")
            except AttributeError as exc:
                assert "MACI model" in str(exc)

    def test_getattr_completely_unknown_attr_raises_attribute_error(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        try:
            m.__getattr__("CompletelyNonExistent")
            raise AssertionError("Should have raised AttributeError")
        except AttributeError as exc:
            assert "has no attribute" in str(exc)

    def test_getattr_caches_value_in_globals(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        # Remove from globals so __getattr__ is exercised
        m.__dict__.pop("AgentMessage", None)
        m._model_cache.clear()
        result = m.__getattr__("AgentMessage")
        assert result is not None
        # Should now be present in globals
        assert "AgentMessage" in m.__dict__


# ---------------------------------------------------------------------------
# 6. ensure_maci_models_loaded
# ---------------------------------------------------------------------------


class TestEnsureMaciModelsLoaded:
    """Test ensure_maci_models_loaded()."""

    def test_returns_true_when_models_loadable(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m.MACI_CORE_AVAILABLE = False
        result = m.ensure_maci_models_loaded()
        assert result is True

    def test_returns_true_early_when_already_loaded(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache["_loaded"] = True
        result = m.ensure_maci_models_loaded()
        assert result is True

    def test_populates_globals_on_success(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        for attr in ("AgentMessage", "MessageType", "get_enum_value"):
            m.__dict__.pop(attr, None)

        result = m.ensure_maci_models_loaded()
        assert result is True
        assert m.__dict__.get("AgentMessage") is not None
        assert m.__dict__.get("MessageType") is not None
        assert m.__dict__.get("get_enum_value") is not None

    def test_returns_false_when_load_fails(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        with patch.object(m, "_load_models", return_value=False):
            result = m.ensure_maci_models_loaded()
            assert result is False

    def test_constitutional_hash_updated_on_success(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m.CONSTITUTIONAL_HASH = "old_hash"
        m.ensure_maci_models_loaded()
        assert m.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_maci_core_available_set_on_success(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m.MACI_CORE_AVAILABLE = False
        m.ensure_maci_models_loaded()
        assert m.MACI_CORE_AVAILABLE is True


# ---------------------------------------------------------------------------
# 7. Stub exception classes (triggered when exceptions module is absent)
# ---------------------------------------------------------------------------


class TestStubExceptionClasses:
    """
    Exercise the stub exception classes that are created in the innermost
    except block.  We trigger them by reloading the module with the
    exceptions sub-module blocked AND with 'exceptions' (bare) blocked.
    """

    @staticmethod
    def _reload_with_stubs() -> ModuleType:
        """Reload maci_imports with all exceptions import paths blocked."""
        to_block = [
            "enhanced_agent_bus.exceptions",
            "enhanced_agent_bus.exceptions.base",
            "enhanced_agent_bus.exceptions.maci",
            "exceptions",
        ]
        originals = {k: sys.modules.get(k) for k in to_block}
        for k in to_block:
            sys.modules[k] = None  # type: ignore[assignment]
        try:
            return _reload_maci_imports()
        finally:
            for k, orig in originals.items():
                if orig is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = orig

    def test_stub_maci_error_is_exception(self) -> None:
        mod = self._reload_with_stubs()
        assert mod.MACIError is not None
        assert issubclass(mod.MACIError, BaseException)

    def test_stub_maci_role_violation_error(self) -> None:
        mod = self._reload_with_stubs()
        cls = mod.MACIRoleViolationError
        assert cls is not None
        err = cls(
            agent_id="agent-1",
            role="PROPOSER",
            action="validate",
            allowed_roles=["VERIFIER"],
        )
        assert err.agent_id == "agent-1"
        assert err.role == "PROPOSER"
        assert err.action == "validate"
        assert "VERIFIER" in err.allowed_roles

    def test_stub_maci_role_violation_no_allowed_roles(self) -> None:
        mod = self._reload_with_stubs()
        cls = mod.MACIRoleViolationError
        err = cls(agent_id="agent-2", role="PROPOSER", action="validate")
        assert err.allowed_roles == []

    def test_stub_maci_self_validation_error(self) -> None:
        mod = self._reload_with_stubs()
        cls = mod.MACISelfValidationError
        err = cls(agent_id="agent-1", action="approve", output_id="out-99")
        assert err.agent_id == "agent-1"
        assert err.action == "approve"
        assert err.output_id == "out-99"

    def test_stub_maci_cross_role_validation_error(self) -> None:
        mod = self._reload_with_stubs()
        cls = mod.MACICrossRoleValidationError
        err = cls(
            agent_id="a1",
            agent_role="PROPOSER",
            target_id="a2",
            target_role="PROPOSER",
            reason="same role",
        )
        assert err.agent_id == "a1"
        assert err.agent_role == "PROPOSER"
        assert err.target_id == "a2"
        assert err.target_role == "PROPOSER"
        assert err.reason == "same role"

    def test_stub_maci_role_not_assigned_error(self) -> None:
        mod = self._reload_with_stubs()
        cls = mod.MACIRoleNotAssignedError
        err = cls(agent_id="agent-x", action="submit")
        assert err.agent_id == "agent-x"
        assert err.action == "submit"

    def test_stub_error_codes(self) -> None:
        mod = self._reload_with_stubs()
        assert mod.MACIError.error_code == "MACI_ERROR"
        assert mod.MACIRoleViolationError.error_code == "MACI_ROLE_VIOLATION"
        assert mod.MACISelfValidationError.error_code == "MACI_SELF_VALIDATION"
        assert mod.MACICrossRoleValidationError.error_code == "MACI_CROSS_ROLE_VALIDATION"
        assert mod.MACIRoleNotAssignedError.error_code == "MACI_ROLE_NOT_ASSIGNED"

    def test_stub_http_status_codes(self) -> None:
        mod = self._reload_with_stubs()
        for cls in (
            mod.MACIError,
            mod.MACIRoleViolationError,
            mod.MACISelfValidationError,
            mod.MACICrossRoleValidationError,
            mod.MACIRoleNotAssignedError,
        ):
            assert cls.http_status_code == 403

    def test_stub_exceptions_are_raisable(self) -> None:
        mod = self._reload_with_stubs()
        # MACIError with a plain message
        with patch("enhanced_agent_bus.maci_imports.MACIError", mod.MACIError):
            try:
                raise mod.MACIError("test error")
            except BaseException as exc:
                assert "test error" in str(exc)


# ---------------------------------------------------------------------------
# 8. get_iso_timestamp fallback
# ---------------------------------------------------------------------------


class TestGetIsoTimestampFallback:
    """Exercise the fallback get_iso_timestamp when utils is unavailable."""

    def test_fallback_produces_iso_format_string(self) -> None:
        """Reload with all utils paths blocked to force the datetime fallback."""
        to_block = [
            "enhanced_agent_bus.utils",
            "enhanced_agent_bus.utils",
            "utils",
        ]
        originals = {k: sys.modules.get(k) for k in to_block}
        for k in to_block:
            sys.modules[k] = None  # type: ignore[assignment]
        try:
            mod = _reload_maci_imports()
            result = mod.get_iso_timestamp()
            # Should be a valid ISO-8601 string
            assert isinstance(result, str)
            # datetime.fromisoformat should not raise
            datetime.fromisoformat(result)
        finally:
            for k, orig in originals.items():
                if orig is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = orig

    def test_fallback_returns_utc_time(self) -> None:
        to_block = [
            "enhanced_agent_bus.utils",
            "enhanced_agent_bus.utils",
            "utils",
        ]
        originals = {k: sys.modules.get(k) for k in to_block}
        for k in to_block:
            sys.modules[k] = None  # type: ignore[assignment]
        try:
            mod = _reload_maci_imports()
            before = datetime.now(UTC)
            ts = mod.get_iso_timestamp()
            after = datetime.now(UTC)
            parsed = datetime.fromisoformat(ts)
            assert before <= parsed <= after
        finally:
            for k, orig in originals.items():
                if orig is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = orig


# ---------------------------------------------------------------------------
# 9. __all__ completeness
# ---------------------------------------------------------------------------


class TestDunderAll:
    """Verify __all__ correctness."""

    def test_all_is_defined(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert hasattr(m, "__all__")

    def test_all_contains_expected_names(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        expected = {
            "MACI_CORE_AVAILABLE",
            "OBSERVABILITY_AVAILABLE",
            "GLOBAL_SETTINGS_AVAILABLE",
            "global_settings",
            "CONSTITUTIONAL_HASH",
            "MACIError",
            "MACIRoleViolationError",
            "MACISelfValidationError",
            "MACICrossRoleValidationError",
            "MACIRoleNotAssignedError",
            "AgentMessage",
            "MessageType",
            "get_enum_value",
            "get_iso_timestamp",
        }
        for name in expected:
            assert name in m.__all__, f"{name!r} missing from __all__"


# ---------------------------------------------------------------------------
# 10. _DEFAULT_CONSTITUTIONAL_HASH constant
# ---------------------------------------------------------------------------


class TestDefaultHash:
    def test_default_hash_value(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert m._DEFAULT_CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# 11. LAZY_MODEL_ATTRS set
# ---------------------------------------------------------------------------


class TestLazyModelAttrs:
    def test_lazy_model_attrs_contains_expected(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        assert "AgentMessage" in m._LAZY_MODEL_ATTRS
        assert "MessageType" in m._LAZY_MODEL_ATTRS
        assert "get_enum_value" in m._LAZY_MODEL_ATTRS


# ---------------------------------------------------------------------------
# 12. Model cache reset and re-load
# ---------------------------------------------------------------------------


class TestModelCacheReload:
    """Test _model_cache reset and CONSTITUTIONAL_HASH update path."""

    def test_constitutional_hash_updated_after_load(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m.CONSTITUTIONAL_HASH = "placeholder"
        m._load_models()
        assert m.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_maci_core_available_after_successful_load(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m.MACI_CORE_AVAILABLE = False
        m._load_models()
        assert m.MACI_CORE_AVAILABLE is True

    def test_load_models_sets_loaded_flag(self) -> None:
        import enhanced_agent_bus.maci_imports as m

        m._model_cache.clear()
        m._load_models()
        assert m._model_cache["_loaded"] is True
