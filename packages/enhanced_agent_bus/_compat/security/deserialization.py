"""Shim for src.core.shared.security.deserialization."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.security.deserialization import *  # noqa: F403
except ImportError:
    import io
    import pickle

    SAFE_MODEL_GLOBALS: set[str] = set()

    class SafeUnpickler(pickle.Unpickler):
        """Restrictive unpickler that rejects all non-safe globals."""

        def find_class(self, module: str, name: str) -> Any:
            key = f"{module}.{name}"
            if key not in SAFE_MODEL_GLOBALS:
                raise pickle.UnpicklingError(f"Forbidden global: {key}")
            return super().find_class(module, name)

    def safe_loads(data: bytes) -> Any:
        """Load pickled data using SafeUnpickler."""
        return SafeUnpickler(io.BytesIO(data)).load()


# Stub constant: set of (module_name, class_name) tuples allowed during unpickling
SAFE_MODEL_GLOBALS: set[tuple[str, str]] = {
    ("builtins", "dict"),
    ("builtins", "list"),
    ("collections", "OrderedDict"),
    ("datetime", "datetime"),
    ("datetime", "date"),
}
