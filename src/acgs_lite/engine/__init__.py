"""Public engine exports with compatibility-preserving lazy seams.

`acgs_lite.engine` has historically re-exported symbols that now live in more
focused modules such as `core`, `models`, `audit_runtime`, and `batch`.
Keep those legacy imports stable while deferring module imports until a symbol
is actually requested.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .audit_runtime import (
        _ANON as _ANON,
    )
    from .audit_runtime import (
        _FastAuditLog as _FastAuditLog,
    )
    from .audit_runtime import (
        _NoopRecorder as _NoopRecorder,
    )
    from .audit_runtime import (
        _request_counter as _request_counter,
    )
    from .batch import (
        BatchValidationMixin as BatchValidationMixin,
    )
    from .batch import (
        BatchValidationResult as BatchValidationResult,
    )
    from .bundle_binding import BundleAwareGovernanceEngine as BundleAwareGovernanceEngine
    from .core import GovernanceEngine as GovernanceEngine
    from .models import (
        CustomValidator as CustomValidator,
    )
    from .models import (
        Severity as Severity,
    )
    from .models import (
        ValidationResult as ValidationResult,
    )
    from .models import (
        Violation as Violation,
    )
    from .models import (
        _dedup_violations as _dedup_violations,
    )

_EXPORTS: dict[str, tuple[str, str]] = {
    "BatchValidationMixin": ("batch", "BatchValidationMixin"),
    "BatchValidationResult": ("batch", "BatchValidationResult"),
    "BundleAwareGovernanceEngine": ("bundle_binding", "BundleAwareGovernanceEngine"),
    "CustomValidator": ("models", "CustomValidator"),
    "GovernanceEngine": ("core", "GovernanceEngine"),
    "Severity": ("models", "Severity"),
    "ValidationResult": ("models", "ValidationResult"),
    "Violation": ("models", "Violation"),
    "_ANON": ("audit_runtime", "_ANON"),
    "_FastAuditLog": ("audit_runtime", "_FastAuditLog"),
    "_NoopRecorder": ("audit_runtime", "_NoopRecorder"),
    "_dedup_violations": ("models", "_dedup_violations"),
    "_request_counter": ("audit_runtime", "_request_counter"),
}

_SUBMODULES = frozenset({"models", "types"})
_MODULE_CACHE: dict[str, Any] = {}


def _load_module(module_name: str) -> Any:
    module = _MODULE_CACHE.get(module_name)
    if module is None:
        module = import_module(f".{module_name}", __name__)
        _MODULE_CACHE[module_name] = module
    return module


__all__ = [
    "BatchValidationMixin",
    "BatchValidationResult",
    "BundleAwareGovernanceEngine",
    "CustomValidator",
    "GovernanceEngine",
    "Severity",
    "ValidationResult",
    "Violation",
    "_ANON",
    "_FastAuditLog",
    "_NoopRecorder",
    "_dedup_violations",
    "_request_counter",
]


def __getattr__(name: str) -> object:
    if name in _SUBMODULES:
        module = _load_module(name)
        globals()[name] = module
        return module

    entry = _EXPORTS.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, symbol_name = entry
    value = getattr(_load_module(module_name), symbol_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__) | _SUBMODULES)
