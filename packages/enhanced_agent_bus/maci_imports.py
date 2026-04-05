"""
MACI Import Management
Constitutional Hash: 608508a9bd224290

Centralizes optional dependency imports for MACI enforcement.
Provides clean fallback handling for imports that may not be available
in all contexts (e.g., standalone testing, minimal deployments).

This module eliminates fragile triple-nested try/except import blocks
by providing a single source of truth for MACI dependencies.
"""

from collections.abc import Callable
from datetime import UTC
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

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
    from enhanced_agent_bus._compat.constants import (
        CONSTITUTIONAL_HASH as _DEFAULT_CONSTITUTIONAL_HASH,
    )
except ImportError:
    _DEFAULT_CONSTITUTIONAL_HASH = "608508a9bd224290"  # pragma: allowlist secret

CONSTITUTIONAL_HASH: str = _DEFAULT_CONSTITUTIONAL_HASH

# =============================================================================
# Global Settings Import
# =============================================================================

global_settings: object = None

try:
    from enhanced_agent_bus._compat.config import settings as _global_settings

    global_settings = _global_settings
    GLOBAL_SETTINGS_AVAILABLE = True
except ImportError as e:
    logger.debug(f"Global settings unavailable: {e}")
    global_settings = None

# =============================================================================
# Core MACI Imports (Exceptions)
# =============================================================================

MACIError: type[Exception] | None = None
MACIRoleViolationError: type[Exception] | None = None
MACISelfValidationError: type[Exception] | None = None
MACICrossRoleValidationError: type[Exception] | None = None
MACIRoleNotAssignedError: type[Exception] | None = None

try:
    from .exceptions import (
        MACICrossRoleValidationError as _MACICrossRoleValidationError,
    )
    from .exceptions import MACIError as _MACIError
    from .exceptions import MACIRoleNotAssignedError as _MACIRoleNotAssignedError
    from .exceptions import MACIRoleViolationError as _MACIRoleViolationError
    from .exceptions import MACISelfValidationError as _MACISelfValidationError

    MACIError = _MACIError
    MACIRoleViolationError = _MACIRoleViolationError
    MACISelfValidationError = _MACISelfValidationError
    MACICrossRoleValidationError = _MACICrossRoleValidationError
    MACIRoleNotAssignedError = _MACIRoleNotAssignedError
    logger.debug("MACI exceptions loaded from relative import")
except ImportError:
    try:
        from exceptions import (  # type: ignore[import-not-found, no-redef]
            MACICrossRoleValidationError as _MACICrossRoleValidationError,
        )
        from exceptions import MACIError as _MACIError  # type: ignore[no-redef]
        from exceptions import (  # type: ignore[no-redef]
            MACIRoleNotAssignedError as _MACIRoleNotAssignedError,
        )
        from exceptions import (
            MACIRoleViolationError as _MACIRoleViolationError,  # type: ignore[no-redef]
        )
        from exceptions import (
            MACISelfValidationError as _MACISelfValidationError,  # type: ignore[no-redef]
        )

        MACIError = _MACIError  # type: ignore[no-redef]
        MACIRoleViolationError = _MACIRoleViolationError  # type: ignore[no-redef]
        MACISelfValidationError = _MACISelfValidationError  # type: ignore[no-redef]
        MACICrossRoleValidationError = _MACICrossRoleValidationError  # type: ignore[no-redef]
        MACIRoleNotAssignedError = _MACIRoleNotAssignedError  # type: ignore[no-redef]
        logger.debug("MACI exceptions loaded from direct import")
    except ImportError as e:
        logger.warning(f"MACI exceptions unavailable, creating stubs: {e}")
        from enhanced_agent_bus._compat.errors import ACGSBaseError

        class _MACIErrorStub(ACGSBaseError):
            http_status_code = 403
            error_code = "MACI_ERROR"

        class _MACIRoleViolationErrorStub(_MACIErrorStub):
            error_code = "MACI_ROLE_VIOLATION"

            def __init__(
                self,
                agent_id: str,
                role: str,
                action: str,
                allowed_roles: list[str] | None = None,
            ) -> None:
                self.agent_id = agent_id
                self.role = role
                self.action = action
                self.allowed_roles = allowed_roles or []
                message = f"Agent '{agent_id}' ({role}) cannot perform '{action}'"
                super().__init__(message=message)

        class _MACISelfValidationErrorStub(_MACIErrorStub):
            error_code = "MACI_SELF_VALIDATION"

            def __init__(
                self,
                agent_id: str,
                action: str,
                output_id: str | None = None,
            ) -> None:
                self.agent_id = agent_id
                self.action = action
                self.output_id = output_id
                message = f"Agent '{agent_id}' cannot {action} its own output"
                super().__init__(message=message)

        class _MACICrossRoleValidationErrorStub(_MACIErrorStub):
            error_code = "MACI_CROSS_ROLE_VALIDATION"

            def __init__(
                self,
                agent_id: str,
                agent_role: str,
                target_id: str,
                target_role: str,
                reason: str,
            ) -> None:
                self.agent_id = agent_id
                self.agent_role = agent_role
                self.target_id = target_id
                self.target_role = target_role
                self.reason = reason
                message = (
                    f"Cross-role validation error: {agent_id} ({agent_role}) "
                    f"cannot validate {target_id} ({target_role}): {reason}"
                )
                super().__init__(message=message)

        class _MACIRoleNotAssignedErrorStub(_MACIErrorStub):
            error_code = "MACI_ROLE_NOT_ASSIGNED"

            def __init__(self, agent_id: str, action: str) -> None:
                self.agent_id = agent_id
                self.action = action
                message = f"Agent '{agent_id}' has no MACI role for: {action}"
                super().__init__(message=message)

        MACIError = _MACIErrorStub  # type: ignore[no-redef]
        MACIRoleViolationError = _MACIRoleViolationErrorStub  # type: ignore[no-redef]
        MACISelfValidationError = _MACISelfValidationErrorStub  # type: ignore[no-redef]
        MACICrossRoleValidationError = _MACICrossRoleValidationErrorStub  # type: ignore[no-redef]
        MACIRoleNotAssignedError = _MACIRoleNotAssignedErrorStub  # type: ignore[no-redef]

# =============================================================================
# Core MACI Imports (Models) - Lazy Loading
# =============================================================================

_model_cache: JSONDict = {}


def _load_models() -> bool:
    """Lazy-load MACI model classes into _model_cache.

    Returns True if models are available, False on ImportError.
    """
    global MACI_CORE_AVAILABLE, CONSTITUTIONAL_HASH

    if _model_cache.get("_loaded"):
        return True

    try:
        from .core_models import get_enum_value as _get_enum_value
        from .models import AgentMessage as _AgentMessage
        from .models import MessageType as _MessageType

        _model_cache["AgentMessage"] = _AgentMessage
        _model_cache["MessageType"] = _MessageType
        _model_cache["get_enum_value"] = _get_enum_value
        _model_cache["_loaded"] = True

        MACI_CORE_AVAILABLE = True

        # Refresh CONSTITUTIONAL_HASH from canonical source if available
        try:
            from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as _ch

            CONSTITUTIONAL_HASH = _ch
        except ImportError:
            pass
        _model_cache["CONSTITUTIONAL_HASH"] = CONSTITUTIONAL_HASH

        logger.debug("MACI models loaded successfully")
        return True
    except ImportError as e:
        logger.warning(f"MACI models unavailable: {e}")
        return False


def get_agent_message() -> object:
    if not _model_cache.get("_loaded"):
        _load_models()
    return _model_cache.get("AgentMessage")


def get_message_type() -> object:
    if not _model_cache.get("_loaded"):
        _load_models()
    return _model_cache.get("MessageType")


def get_enum_value_func() -> Callable[..., object] | None:
    if not _model_cache.get("_loaded"):
        _load_models()
    return _model_cache.get("get_enum_value")  # type: ignore[no-any-return]


_LAZY_MODEL_ATTRS = {"AgentMessage", "MessageType", "get_enum_value"}


def __getattr__(name: str) -> object:
    if name in _LAZY_MODEL_ATTRS:
        if not _model_cache.get("_loaded"):
            _load_models()
        value = _model_cache.get(name)
        if value is not None:
            globals()[name] = value
            return value
        raise AttributeError(f"MACI model {name!r} could not be loaded")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def ensure_maci_models_loaded() -> bool:
    result = _load_models()
    if result:
        # Populate module globals for direct attribute access
        for attr in _LAZY_MODEL_ATTRS:
            value = _model_cache.get(attr)
            if value is not None:
                globals()[attr] = value
    return result


# =============================================================================
# Utility Imports
# =============================================================================

get_iso_timestamp: Callable[..., object] | None = None

try:
    from enhanced_agent_bus.utils import get_iso_timestamp as _get_iso_timestamp

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
    "get_enum_value",  # noqa: F822 — resolved lazily via __getattr__
    # Utilities
    "get_iso_timestamp",
    # Global settings
    "global_settings",
]
