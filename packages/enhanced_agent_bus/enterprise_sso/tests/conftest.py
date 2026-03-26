"""
Enterprise SSO Tests - Conftest
Constitutional Hash: 608508a9bd224290

Provides import setup for enterprise_sso tests, inheriting the parent
enhanced_agent_bus test conftest setup.
"""

import os
import sys

# Ensure repo root is on the path so src.* imports work
_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_here, "..", "..", "..", "..", ".."))
_eab_dir = os.path.abspath(os.path.join(_here, "..", "..", ".."))

for _path in (_repo_root, _eab_dir):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Mock problematic dependencies BEFORE any imports
try:
    import torch
except (ImportError, RuntimeError):
    from unittest.mock import MagicMock

    sys.modules["torch"] = MagicMock()

# Block Rust extension unless explicitly enabled
_test_with_rust = os.environ.get("TEST_WITH_RUST", "0") == "1"
if not _test_with_rust:
    sys.modules["enhanced_agent_bus_rust"] = None  # type: ignore[assignment]

# Mock scipy.stats to avoid Python 3.14 compatibility issues
try:
    import scipy.stats
except (ImportError, TypeError):
    from unittest.mock import MagicMock

    _scipy_mock = MagicMock()
    sys.modules["scipy"] = _scipy_mock
    sys.modules["scipy.stats"] = _scipy_mock.stats
