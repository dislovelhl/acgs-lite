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

# CRITICAL: Insert acgs-clean/packages at the FRONT of sys.path before any
# conftest or test imports enhanced_agent_bus. Without this, Python may find
# the package from acgs-main/packages (which is in the user-level sys.path)
# instead of acgs-clean/packages, causing import failures.
_packages_dir = os.path.join(_project_root, "packages")
if _packages_dir not in sys.path:
    sys.path.insert(0, _packages_dir)

from src.core.shared.constants import CONSTITUTIONAL_HASH

# Pre-cache the project-level `tests` package in sys.modules so that sub-directory
# conftest files (e.g. enhanced_agent_bus/tests/conftest.py) cannot shadow it by
# inserting their own `tests/` directory at the front of sys.path.
with contextlib.suppress(ImportError):
    pass


# Preload pydantic modules to fix litellm compatibility

# Now safe to import litellm
# litellm optional

# Avoid import-time service_auth configuration errors during tests.
os.environ.setdefault(
    "ACGS2_SERVICE_SECRET",
    "test-service-secret-key-that-is-at-least-32-characters-long",
)
os.environ.setdefault("SERVICE_JWT_ALGORITHM", "HS256")

# Constitutional hash verification
CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
