"""
sys.modules aliasing logic for Enhanced Agent Bus tests.

This module runs import-time side effects that register flat-name and
qualified-name aliases in sys.modules so that test files can use short
import paths.  It MUST be imported before any test code runs.

Constitutional Hash: 608508a9bd224290
"""

import os
import sys
from typing import Any
from unittest.mock import MagicMock

# Only mock torch if it's not installed - torch is now a real dependency
try:
    import torch
except ImportError:
    sys.modules["torch"] = MagicMock()

# ``packages/enhanced_agent_bus/tests/conftest.py`` provides the temporary
# import-time ``ENVIRONMENT=test`` default needed by the sandbox guard before
# this module is loaded, then restores the worker process environment afterward.
# Keep this module free of direct runtime-environment mutation so it does not
# pollute non-EAB tests that execute later in the same worker.

# CRITICAL: Block Rust imports BEFORE any module imports
_test_with_rust = os.environ.get("TEST_WITH_RUST", "0") == "1"
if not _test_with_rust:
    sys.modules["enhanced_agent_bus_rust"] = None

# Add enhanced_agent_bus directory to path if not already there
enhanced_agent_bus_dir = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)


def _patch_optional(pkg_name: str, flat_name: str | None = None) -> Any | None:
    """Import a module and register both flat and qualified names in sys.modules.

    Args:
        pkg_name: Fully-qualified module name (e.g. "enhanced_agent_bus.api").
        flat_name: Short alias for sys.modules (e.g. "api"). If None, derived from pkg_name.

    Returns:
        The imported module, or None if ImportError.
    """
    if flat_name is None:
        flat_name = pkg_name.rsplit(".", 1)[-1]
    try:
        mod = __import__(pkg_name, fromlist=[flat_name])
        sys.modules[flat_name] = mod
        # Also register as enhanced_agent_bus.X for tests that use that path
        eab_name = f"enhanced_agent_bus.{flat_name}"
        sys.modules[eab_name] = mod
        # pytest importlib mode creates 'core.enhanced_agent_bus' prefix; register there too
        core_eab_name = f"core.enhanced_agent_bus.{flat_name}"
        sys.modules[core_eab_name] = mod
        return mod
    except ImportError:
        return None


# ── Core module imports (required) ──────────────────────────────────────────
_PKG = "packages.enhanced_agent_bus"


import enhanced_agent_bus.audit_client as _audit_client
import enhanced_agent_bus.dependency_bridge as _dependency_bridge

# imports.py deleted (v3.1 cleanup) — dependency_bridge.py is the canonical source
import enhanced_agent_bus.exceptions as _exceptions
import enhanced_agent_bus.interfaces as _interfaces
import enhanced_agent_bus.maci_enforcement as _maci_enforcement
import enhanced_agent_bus.models as _models
import enhanced_agent_bus.registry as _registry
import enhanced_agent_bus.utils as _utils
import enhanced_agent_bus.validators as _validators


# PM-015 core-module fix: `import packages.enhanced_agent_bus.X as _X` uses the
# IMPORT_FROM opcode which follows the attribute chain on M_PEAB.  Because
# M_PEAB.__init__ re-registers itself as sys.modules["enhanced_agent_bus"] and
# subsequent flat imports (from enhanced_agent_bus.X) overwrite M_PEAB.X with
# M_X_EA, the attribute chain returns M_X_EA — not M_X_PEAB from sys.modules.
# Resolve canonical M_X_PEAB directly from sys.modules after the import has
# triggered loading.
def _canonical(submod: str) -> object:
    """Return sys.modules["enhanced_agent_bus.<submod>"] (M_X_PEAB)."""
    return sys.modules.get(f"enhanced_agent_bus.{submod}") or sys.modules.get(
        f"enhanced_agent_bus.{submod}"
    )


_audit_client = _canonical("audit_client") or _audit_client
_dependency_bridge = _canonical("dependency_bridge") or _dependency_bridge
_exceptions = _canonical("exceptions") or _exceptions
_interfaces = _canonical("interfaces") or _interfaces
_maci_enforcement = _canonical("maci_enforcement") or _maci_enforcement
_models = _canonical("models") or _models
_registry = _canonical("registry") or _registry
_utils = _canonical("utils") or _utils
_validators = _canonical("validators") or _validators

# Patch flat names for tests that import without package prefix
# CRITICAL: DO NOT hijack sys.modules["core"]
sys.modules["audit_client"] = _audit_client
sys.modules["models"] = _models
sys.modules["validators"] = _validators
sys.modules["exceptions"] = _exceptions
sys.modules["interfaces"] = _interfaces
sys.modules["registry"] = _registry
sys.modules["maci_enforcement"] = _maci_enforcement
sys.modules["utils"] = _utils
sys.modules["imports"] = _dependency_bridge  # backward compat alias

# ── Optional module imports (may not have all deps installed) ───────────────
_agent_bus = _patch_optional(f"{_PKG}.agent_bus")
_message_processor = _patch_optional(f"{_PKG}.message_processor")
_processing_strategies = _patch_optional(f"{_PKG}.processing_strategies")
_online_learning = _patch_optional(f"{_PKG}.online_learning")
_ab_testing = _patch_optional(f"{_PKG}.ab_testing")
_ml_versioning = _patch_optional(f"{_PKG}.ml_versioning")
_feedback_handler = _patch_optional(f"{_PKG}.feedback_handler")
_drift_monitoring = _patch_optional(f"{_PKG}.drift_monitoring")
_api = _patch_optional(f"{_PKG}.api")
_batch_processor = _patch_optional(f"{_PKG}.batch_processor")
_context_memory = _patch_optional(f"{_PKG}.context_memory")
_runtime_security = _patch_optional(f"{_PKG}.runtime_security")
_enums = _patch_optional(f"{_PKG}.enums")
_config = _patch_optional(f"{_PKG}.config")
sys.modules["config"] = _config  # flat import alias for test_config.py and importlib mode
_cb_factory = _patch_optional(f"{_PKG}.cb_factory")
# PM-015 cb_factory: Python's import machinery sets
# sys.modules["enhanced_agent_bus"].cb_factory = M_CBF_EA when enhanced_agent_bus.cb_factory
# is loaded, overwriting the attribute that was M_CBF_PEAB.  This causes
# 'import packages.enhanced_agent_bus.cb_factory as cbf' to return M_CBF_EA (via the
# IMPORT_FROM attribute chain) while 'from packages.enhanced_agent_bus.cb_factory import fn'
# returns fn from M_CBF_PEAB — two different module dicts, breaking singleton patching.
# Fix: restore the canonical M_CBF_PEAB as the attribute on the package object.
if _cb_factory is not None:
    _eab_pkg = sys.modules.get("packages.enhanced_agent_bus") or sys.modules.get(
        "enhanced_agent_bus"
    )
    if _eab_pkg is not None:
        _eab_pkg.cb_factory = _cb_factory
_deliberation_layer = _patch_optional(f"{_PKG}.deliberation_layer")
_constitutional = _patch_optional(f"{_PKG}.constitutional")
_middlewares = _patch_optional(f"{_PKG}.middlewares", flat_name="middleware")

# Deliberation layer sub-modules need patching for flat-name imports.
# Under pytest --import-mode=importlib the deliberation_layer package is already
# loaded via the 'core.enhanced_agent_bus' prefix which prevents normal
# sub-module imports.  Use importlib.import_module to force the correct path.
if _deliberation_layer is not None:
    import importlib as _il

    try:
        _impact_scorer = _il.import_module("enhanced_agent_bus.deliberation_layer.impact_scorer")
        sys.modules["enhanced_agent_bus.deliberation_layer.impact_scorer"] = _impact_scorer
        sys.modules["core.enhanced_agent_bus.deliberation_layer.impact_scorer"] = _impact_scorer
    except ImportError:
        pass

# Observability has sub-modules that also need patching
try:
    import enhanced_agent_bus.observability as _observability

    sys.modules["observability"] = _observability
    sys.modules["enhanced_agent_bus.observability"] = _observability
    import enhanced_agent_bus.observability.telemetry as _telemetry

    sys.modules["observability.telemetry"] = _telemetry
    sys.modules["enhanced_agent_bus.observability.telemetry"] = _telemetry
except ImportError:
    _observability = None

# Canonicalize multi_tenancy ORM imports to avoid duplicate mappers in parallel runs
try:
    import enhanced_agent_bus.multi_tenancy as _multi_tenancy
    import enhanced_agent_bus.multi_tenancy.orm_models as _orm_models

    sys.modules["enhanced_agent_bus.multi_tenancy"] = _multi_tenancy
    sys.modules["core.enhanced_agent_bus.multi_tenancy"] = _multi_tenancy
    sys.modules["enhanced_agent_bus.multi_tenancy.orm_models"] = _orm_models
    sys.modules["core.enhanced_agent_bus.multi_tenancy.orm_models"] = _orm_models
    if hasattr(_orm_models, "_dedupe_class_registry"):
        _orm_models._dedupe_class_registry()
except ImportError:
    pass

# Set the agent_bus alias (prefer agent_bus module)
if sys.modules.get("enhanced_agent_bus.agent_bus"):
    sys.modules["agent_bus"] = sys.modules["enhanced_agent_bus.agent_bus"]

# Canonicalize all core module sys.modules aliases (PM-015 extended).
# Optional module imports above may trigger re-loading of EAB's __init__ which
# sets sys.modules["enhanced_agent_bus"] = M_PEAB and may overwrite
# sys.modules["enhanced_agent_bus.X"] or flat aliases back to M_X_EA.
# Re-assert M_X_PEAB as canonical for all three alias forms.
# PM-015: Canonicalize session_context, multi_tenancy.context, sdpc.pacar_manager,
# deliberation_layer.llm_assistant, and pipeline.legacy_wrapper to fix xdist flakes
# caused by dual module identity (packages.enhanced_agent_bus.X vs enhanced_agent_bus.X).
for _submod in [
    "session_context",
    "multi_tenancy.context",
    "sdpc.pacar_manager",
    "deliberation_layer.llm_assistant",
    "pipeline.legacy_wrapper",
]:
    _canon = sys.modules.get(f"enhanced_agent_bus.{_submod}")
    if _canon is not None:
        sys.modules[f"enhanced_agent_bus.{_submod}"] = _canon
        sys.modules[f"core.enhanced_agent_bus.{_submod}"] = _canon

for _cmod_name, _cmod in [
    ("audit_client", _audit_client),
    ("dependency_bridge", _dependency_bridge),
    ("exceptions", _exceptions),
    ("interfaces", _interfaces),
    ("maci_enforcement", _maci_enforcement),
    ("models", _models),
    ("registry", _registry),
    ("utils", _utils),
    ("validators", _validators),
]:
    if _cmod is not None:
        sys.modules[f"enhanced_agent_bus.{_cmod_name}"] = _cmod
        sys.modules[f"core.enhanced_agent_bus.{_cmod_name}"] = _cmod
        sys.modules[_cmod_name] = _cmod  # re-assert flat alias

# ── Rust availability ───────────────────────────────────────────────────────
if not _test_with_rust:
    # Disable Rust for tests by default; dependency_bridge doesn't expose a
    # mutable USE_RUST attribute, so we set it on the aliased module directly
    # and mark the feature flag unavailable in DependencyRegistry.
    _dependency_bridge.USE_RUST = False
    RUST_AVAILABLE = False
else:
    try:
        RUST_AVAILABLE = True
        _dependency_bridge.USE_RUST = True
    except ImportError:
        RUST_AVAILABLE = False
        _dependency_bridge.USE_RUST = False

# ── Re-export commonly used items (public API for test files) ───────────────
AgentMessage = _models.AgentMessage
MessageType = _models.MessageType
Priority = _models.Priority
MessageStatus = _models.MessageStatus
CONSTITUTIONAL_HASH = _models.CONSTITUTIONAL_HASH
ValidationResult = _validators.ValidationResult
try:
    from enhanced_agent_bus.message_processor import MessageProcessor
except ImportError:
    try:
        import message_processor

        MessageProcessor = message_processor.MessageProcessor
    except (ImportError, AttributeError):
        MessageProcessor = None
try:
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
except ImportError:
    EnhancedAgentBus = None
