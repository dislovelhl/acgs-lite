"""
Tests for ACGS-2 Secure Deserialization Utilities

Constitutional Hash: 608508a9bd224290
"""

import io
import pickle

import pytest

from src.core.shared.security.deserialization import (
    safe_pickle_load,
    safe_pickle_loads,
)


class UntrustedClass:
    pass


class TestSafeUnpickler:
    """Test the SafeUnpickler whitelist enforcement."""

    def test_load_whitelisted_class(self):
        """Test that whitelisted classes can be unpickled."""
        # Using a simple whitelisted class: numpy.dtype (if available) or something else
        # Since we might not have all libraries installed in the test env,
        # let's mock the whitelist for this test or use builtins.

        # Test with a builtin type that is explicitly allowed
        data = pickle.dumps({"a": 1})
        loaded = safe_pickle_loads(data)
        assert loaded == {"a": 1}

    def test_reject_untrusted_class(self):
        """Test that non-whitelisted classes are rejected."""
        data = pickle.dumps(UntrustedClass())
        with pytest.raises(pickle.UnpicklingError, match="Unsafe class detected"):
            safe_pickle_loads(data)

    def test_reject_malicious_os_system(self):
        """Test that malicious OS commands are rejected."""

        class Malicious:
            def __reduce__(self):
                import os

                return (os.system, ("echo 'pwned'",))

        data = pickle.dumps(Malicious())
        with pytest.raises(pickle.UnpicklingError, match="Unsafe class detected"):
            safe_pickle_loads(data)

    def test_allow_basic_builtins(self):
        """Test that basic builtins are allowed."""
        basic_types = [{"a": 1}, [1, 2, 3], {1, 2, 3}, 123, 1.23, "string", True, complex(1, 2)]
        for t in basic_types:
            data = pickle.dumps(t)
            assert safe_pickle_loads(data) == t

    def test_safe_pickle_load_file(self):
        """Test loading from a file-like object."""
        data = {"key": "value"}
        buf = io.BytesIO(pickle.dumps(data))
        loaded = safe_pickle_load(buf)
        assert loaded == data
