"""
ACGS-2 Secure Deserialization Utilities
Constitutional Hash: 608508a9bd224290

Provides safer alternatives for pickle and other deserialization methods.
"""

import io
import pickle

# Whitelist of safe modules and classes for unpickling models
# Add more as needed for River, scikit-learn, etc.
SAFE_MODEL_GLOBALS = {
    ("river.ensemble", "AdaptiveRandomForestClassifier"),
    ("river.ensemble", "AdaptiveRandomForestRegressor"),
    ("river.metrics", "Accuracy"),
    ("river.stats", "Mean"),
    ("numpy", "dtype"),
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"),
    ("copyreg", "_reconstructor"),
}


class SafeUnpickler(pickle.Unpickler):
    """
    Pickle unpickler that restricts globals to a whitelist.
    """

    def __init__(self, file, safe_globals: set[tuple] | None = None):
        super().__init__(file)
        self.safe_globals = safe_globals or SAFE_MODEL_GLOBALS

    def find_class(self, module, name):
        """Allow only whitelisted globals and basic builtins; raise on unsafe classes."""
        if (module, name) in self.safe_globals:
            return super().find_class(module, name)
        # Allow basic types
        if module == "builtins" and name in (
            "dict",
            "list",
            "set",
            "int",
            "float",
            "str",
            "bool",
            "complex",
        ):
            return super().find_class(module, name)

        raise pickle.UnpicklingError(f"Unsafe class detected: {module}.{name}")


def safe_pickle_load(file_obj) -> object:
    """Safely load a pickle file using restricted globals.

    Args:
        file_obj: File-like object to read from

    Returns:
        Deserialized Python object (whitelisted types only)
    """
    return SafeUnpickler(file_obj).load()


def safe_pickle_loads(data: bytes) -> object:
    """Safely load pickle data from bytes using restricted globals.

    Args:
        data: Pickled bytes data

    Returns:
        Deserialized Python object (whitelisted types only)
    """
    return SafeUnpickler(io.BytesIO(data)).load()


__all__ = ["SafeUnpickler", "safe_pickle_load", "safe_pickle_loads"]
