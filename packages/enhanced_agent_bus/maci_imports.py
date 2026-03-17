"""
MACI Import Management
Constitutional Hash: cdd01ef066bc6cf2

Centralizes optional dependency imports for MACI enforcement.
Provides clean fallback handling for imports that may not be available
in all contexts (e.g., standalone testing, minimal deployments).

This module eliminates fragile triple-nested try/except import blocks
by providing a single source of truth for MACI dependencies.
"""

from collections.abc import Callable
from datetime import UTC
from typing import TYPE_CHECKING

from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

# TYPE_CHECKING imports for proper static type analysis
if TYPE_CHECKING:
    from .models import AgentMessage as AgentMessage
    from .models import MessageType as MessageType

logger = get_logger(__name__)
# =============================================================================
# Feature Availability Flags
# =============================================================================

MACI_CORE_AVAILABLE: bool = False
OBSERVABILITY_AVAILABLE: bool = False
GLOBAL_SETTINGS_AVAILABLE: bool = False

# =============================================================================
# Default Values for Fallbacks
# =============================================================================

# Constitutional hash fallback (canonical value)
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH as _DEFAULT_CONSTITUTIONAL_HASH
except ImportError:
    _DEFAULT_CONSTITUTIONAL_HASH = "cdd01ef066bc6cf2"  # pragma: allowlist secret

# =============================================================================
# Global Settings Import
# =============================================================================

global_settings: object = None

try:
    from src.core.shared.config import settings as _global_settings

    global_settings = _global_settings
    GLOBAL_SETTINGS_AVAILABLE = True
except ImportError as e:
    logger.debug(f"Global settings unavailable: {e}")
    global_settings = None

# =============================================================================
# Core MACI Imports (Exceptions)
# =============================================================================

# Exception classes - these are critical for MACI operation
MACIError: type[Exception] | None = None
MACIRoleViolationError: type[Exception] | None = None
MACISelfValidationError: type[Exception] | None = None
MACICrossRoleValidationError: type[Exception] | None = None
MACIRoleNotAssignedError: type[Exception] | None = None

try:
    from .exceptions import (
        MACICrossRoleValidationError as _MACICrossRoleValidationError,
    )
    from .exceptions import (
        MACIError as _MACIError,
    )
    from .exceptions import (
        MACIRoleNotAssignedError as _MACIRoleNotAssignedError,
    )
    from .exceptions import (
        MACIRoleViolationError as _MACIRoleViolationError,
    )
    from .exceptions import (
        MACISelfValidationError as _MACISelfValidationError,
    )

    MACIError = _MACIError
    MACIRoleViolationError = _MACIRoleViolationError
    MACISelfValidationError = _MACISelfValidationError
    MACICrossRoleValidationError = _MACICrossRoleValidationError
    MACIRoleNotAssignedError = _MACIRoleNotAssignedError
    logger.debug("MACI exceptions loaded from relative import")
except ImportError:
    try:
        # Fallback for standalone execution context
        from exceptions import (  # type: ignore[import-not-found, no-redef]
            MACICrossRoleValidationError as _MACICrossRoleValidationError,
        )
        from exceptions import (  # type: ignore[no-redef]
            MACIError as _MACIError,
        )
        from exceptions import (  # type: ignore[no-redef]
            MACIRoleNotAssignedError as _MACIRoleNotAssignedError,
        )
        from exceptions import (  # type: ignore[no-redef]
            MACIRoleViolationError as _MACIRoleViolationError,
        )
        from exceptions import (  # type: ignore[no-redef]
            MACISelfValidationError as _MACISelfValidationError,
        )

        MACIError = _MACIError  # type: ignore[no-redef]
        MACIRoleViolationError = _MACIRoleViolationError  # type: ignore[no-redef]
        MACISelfValidationError = _MACISelfValidationError  # type: ignore[no-redef]
        MACICrossRoleValidationError = _MACICrossRoleValidationError  # type: ignore[no-redef]
        MACIRoleNotAssignedError = _MACIRoleNotAssignedError  # type: ignore[no-redef]
        logger.debug("MACI exceptions loaded from direct import")
    except ImportError as e:
        logger.warning(f"MACI exceptions unavailable, creating stubs: {e}")

        # Import ACGSBaseError for fallback stubs
        from src.core.shared.errors.exceptions import ACGSBaseError

        # Create stub exception classes for environments where exceptions module is missing
        class _MACIErrorStub(ACGSBaseError):
            """Stub for MACIError when exceptions module unavailable."""

            http_status_code = 403
            error_code = "MACI_ERROR"

        class _MACIRoleViolationErrorStub(_MACIErrorStub):
            """Stub for MACIRoleViolationError."""

            http_status_code = 403
            error_code = "MACI_ROLE_VIOLATION"

            def __init__(
                self,
                agent_id: str,
                role: str,
                action: str,
                allowed_roles: list | None = None,
            ):
                self.agent_id = agent_id
                self.role = role
                self.action = action
                self.allowed_roles = allowed_roles or []
                super().__init__(
                    f"Agent {agent_id} with role {role} cannot perform {action}",
                    details={
                        "agent_id": agent_id,
                        "role": role,
                        "action": action,
                        "allowed_roles": allowed_roles or [],
                    },
                )

        class _MACISelfValidationErrorStub(_MACIErrorStub):
            """Stub for MACISelfValidationError."""

            http_status_code = 403
            error_code = "MACI_SELF_VALIDATION"

            def __init__(self, agent_id: str, action: str, output_id: str):
                self.agent_id = agent_id
                self.action = action
                self.output_id = output_id
                super().__init__(
                    f"Agent {agent_id} cannot {action} own output {output_id}",
                    details={"agent_id": agent_id, "action": action, "output_id": output_id},
                )

        class _MACICrossRoleValidationErrorStub(_MACIErrorStub):
            """Stub for MACICrossRoleValidationError."""

            http_status_code = 403
            error_code = "MACI_CROSS_ROLE_VALIDATION"

            def __init__(
                self,
                agent_id: str,
                agent_role: str,
                target_id: str,
                target_role: str,
                reason: str,
            ):
                self.agent_id = agent_id
                self.agent_role = agent_role
                self.target_id = target_id
                self.target_role = target_role
                self.reason = reason
                msg = f"Agent {agent_id} ({agent_role}) cannot validate {target_id} ({target_role}): {reason}"  # noqa: E501
                super().__init__(
                    msg,
                    details={
                        "agent_id": agent_id,
                        "agent_role": agent_role,
                        "target_id": target_id,
                        "target_role": target_role,
                        "reason": reason,
                    },
                )

        class _MACIRoleNotAssignedErrorStub(_MACIErrorStub):
            """Stub for MACIRoleNotAssignedError."""

            http_status_code = 403
            error_code = "MACI_ROLE_NOT_ASSIGNED"

            def __init__(self, agent_id: str, action: str):
                self.agent_id = agent_id
                self.action = action
                super().__init__(
                    f"Agent {agent_id} has no assigned role for action {action}",
                    details={"agent_id": agent_id, "action": action},
                )

        MACIError = _MACIErrorStub  # type: ignore[no-redef]
        MACIRoleViolationError = _MACIRoleViolationErrorStub  # type: ignore[no-redef]
        MACISelfValidationError = _MACISelfValidationErrorStub  # type: ignore[no-redef]
        MACICrossRoleValidationError = _MACICrossRoleValidationErrorStub  # type: ignore[no-redef]
        MACIRoleNotAssignedError = _MACIRoleNotAssignedErrorStub  # type: ignore[no-redef]

# =============================================================================
# Core MACI Imports (Models) - Lazy Loading
# =============================================================================

# Use default constitutional hash until models are loaded
CONSTITUTIONAL_HASH: str = _DEFAULT_CONSTITUTIONAL_HASH

# Lazy loading cache for models
_model_cache: JSONDict = {}


def _load_models() -> bool:
    """Lazily load models to avoid circular imports.

    This function attempts to import models from various paths and caches
    them to avoid repeated import attempts. Called automatically when
    accessing model-dependent attributes.

    Returns:
        True if models were loaded successfully, False otherwise
    """
    global CONSTITUTIONAL_HASH, MACI_CORE_AVAILABLE

    # Return early if already loaded
    if _model_cache.get("_loaded", False):
        return True

    import_paths = [
        # Try absolute imports first
        ("packages.enhanced_agent_bus.models", "src.core import"),
        ("enhanced_agent_bus.models", "enhanced_agent_bus import"),
        # Try relative imports
        (".models", "relative import"),
        ("models", "direct import"),
    ]

    for module_path, label in import_paths:
        try:
            if module_path.startswith("."):
                # Relative import
                models_module = __import__(
                    module_path,
                    fromlist=[
                        "CONSTITUTIONAL_HASH",
                        "AgentMessage",
                        "MessageType",
                        "get_enum_value",
                    ],
                )
            else:
                # Absolute import
                models_module = __import__(
                    module_path,
                    fromlist=[
                        "CONSTITUTIONAL_HASH",
                        "AgentMessage",
                        "MessageType",
                        "get_enum_value",
                    ],
                )

            # Cache the imported values
            _model_cache["CONSTITUTIONAL_HASH"] = models_module.CONSTITUTIONAL_HASH
            _model_cache["AgentMessage"] = models_module.AgentMessage
            _model_cache["MessageType"] = models_module.MessageType
            _model_cache["get_enum_value"] = models_module.get_enum_value
            _model_cache["_loaded"] = True

            # Update global constants
            CONSTITUTIONAL_HASH = _model_cache["CONSTITUTIONAL_HASH"]
            MACI_CORE_AVAILABLE = True

            logger.debug(f"MACI models loaded from {label}")
            return True

        except ImportError:
            continue

    logger.warning("MACI models unavailable: could not import from any path")
    return False


def get_agent_message() -> object:
    """Get AgentMessage class (lazy loaded)."""
    if not _model_cache.get("_loaded"):
        _load_models()
    return _model_cache.get("AgentMessage")


def get_message_type() -> object:
    """Get MessageType class (lazy loaded)."""
    if not _model_cache.get("_loaded"):
        _load_models()
    return _model_cache.get("MessageType")


def get_enum_value_func() -> Callable[..., object] | None:
    """Get get_enum_value function (lazy loaded)."""
    if not _model_cache.get("_loaded"):
        _load_models()
    return _model_cache.get("get_enum_value")  # type: ignore[no-any-return]


# Lazy-loaded model names resolved via __getattr__ to avoid circular imports.
_LAZY_MODEL_ATTRS = {"AgentMessage", "MessageType", "get_enum_value"}


def __getattr__(name: str) -> object:
    """Module-level lazy loading for model classes to break circular imports."""
    if name in _LAZY_MODEL_ATTRS:
        _load_models()
        value = _model_cache.get(name)
        if value is not None:
            # Cache in module globals so __getattr__ is only called once per name
            globals()[name] = value
            return value
        raise AttributeError(f"MACI model {name!r} could not be loaded")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def ensure_maci_models_loaded() -> bool:
    """Explicitly load MACI models after module initialization.

    This function should be called after all modules are loaded to avoid
    circular import issues. It populates the module-level AgentMessage,
    MessageType, and get_enum_value references via the model cache.

    Returns:
        True if models were loaded successfully
    """
    global CONSTITUTIONAL_HASH, MACI_CORE_AVAILABLE

    if _model_cache.get("_loaded"):
        return True

    success = _load_models()
    if success:
        # Populate globals so __getattr__ is skipped for subsequent access
        globals()["AgentMessage"] = _model_cache.get("AgentMessage")
        globals()["MessageType"] = _model_cache.get("MessageType")
        globals()["get_enum_value"] = _model_cache.get("get_enum_value")
        CONSTITUTIONAL_HASH = _model_cache.get("CONSTITUTIONAL_HASH", _DEFAULT_CONSTITUTIONAL_HASH)
        MACI_CORE_AVAILABLE = True

    return success


# =============================================================================
# Utility Imports
# =============================================================================

get_iso_timestamp: Callable[..., object] | None = None

try:
    from packages.enhanced_agent_bus.utils import get_iso_timestamp as _get_iso_timestamp

    get_iso_timestamp = _get_iso_timestamp  # type: ignore[no-redef]
    logger.debug("MACI utils loaded from src.core import")
except ImportError:
    try:
        from enhanced_agent_bus.utils import get_iso_timestamp as _get_iso_timestamp

        get_iso_timestamp = _get_iso_timestamp  # type: ignore[no-redef]
        logger.debug("MACI utils loaded from enhanced_agent_bus import")
    except ImportError:
        try:
            from .utils import get_iso_timestamp as _get_iso_timestamp

            get_iso_timestamp = _get_iso_timestamp  # type: ignore[no-redef]
            logger.debug("MACI utils loaded from relative import")
        except ImportError:
            try:
                from utils import (  # type: ignore[import-not-found, no-redef]
                    get_iso_timestamp as _get_iso_timestamp,
                )

                get_iso_timestamp = _get_iso_timestamp  # type: ignore[no-redef]
                logger.debug("MACI utils loaded from direct import")
            except ImportError as e:
                logger.debug(f"MACI utils unavailable, using fallback: {e}")
                from datetime import datetime

                def _get_iso_timestamp_fallback() -> str:
                    """Fallback implementation for get_iso_timestamp."""
                    return datetime.now(UTC).isoformat()

                get_iso_timestamp = _get_iso_timestamp_fallback  # type: ignore[no-redef]

# =============================================================================
# Export Interface
# =============================================================================

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "GLOBAL_SETTINGS_AVAILABLE",
    # Feature flags
    "MACI_CORE_AVAILABLE",
    "OBSERVABILITY_AVAILABLE",
    # Model classes (lazy-loaded via __getattr__ → globals()[name] assignment)
    "AgentMessage",
    "MACICrossRoleValidationError",
    # Exception classes
    "MACIError",
    "MACIRoleNotAssignedError",
    "MACIRoleViolationError",
    "MACISelfValidationError",
    "MessageType",
    "get_enum_value",  # noqa: F822
    # Utilities
    "get_iso_timestamp",
    # Global settings
    "global_settings",
]
