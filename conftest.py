"""Pytest configuration with pydantic/litellm compatibility fix.

Constitutional Hash: cdd01ef066bc6cf2
"""

import contextlib
import os
import sys

# Ensure project root is on sys.path so `tests.*` shim imports resolve
# (e.g. src/core/shared/tests/ shims that import tests.core.* or tests.unit.*)
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.core.shared.constants import CONSTITUTIONAL_HASH

# Pre-cache the project-level `tests` package in sys.modules so that sub-directory
# conftest files (e.g. enhanced_agent_bus/tests/conftest.py) cannot shadow it by
# inserting their own `tests/` directory at the front of sys.path.
with contextlib.suppress(ImportError):
    import tests
    import tests.core
    import tests.unit

# Preload pydantic modules to fix litellm compatibility

# Now safe to import litellm
# litellm optional

# Avoid import-time service_auth development-secret warnings during tests.
os.environ.setdefault(
    "ACGS2_SERVICE_SECRET",
    "test-service-secret-key-that-is-at-least-32-characters-long",
)

# Constitutional hash verification
CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
