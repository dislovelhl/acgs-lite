"""
ACGS-2 Enhanced Agent Bus - Shared Test Fixtures
Constitutional Hash: 608508a9bd224290

Thin root conftest that delegates to the fixtures subpackage.
All sys.modules aliasing, singleton resets, and mock fixtures live
in packages/enhanced_agent_bus/tests/fixtures/.
"""

import os

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

_DEFAULT_EAB_TEST_ENVIRONMENT = "test"
_EAB_TEST_ENVIRONMENT_WAS_MISSING = "ENVIRONMENT" not in os.environ

# Some imported test support modules expect a sandbox-safe environment during
# import, but we do not want that default to leak to non-EAB tests later in the
# same worker process.
if _EAB_TEST_ENVIRONMENT_WAS_MISSING:
    os.environ["ENVIRONMENT"] = _DEFAULT_EAB_TEST_ENVIRONMENT

# ── Import fixtures subpackage ────────────────────────────────────────────────
# module_aliases side effects (sys.modules patching) run at import time.
# Fixture functions are re-exported so pytest discovers them in this conftest.
from .fixtures import (
    CONSTITUTIONAL_HASH,
    RUST_AVAILABLE,
    TEST_API_KEY,
    AgentMessage,
    EnhancedAgentBus,
    MessageProcessor,
    MessageStatus,
    MessageType,
    Priority,
    ValidationResult,
    _disable_redis_rate_limiting,
    reset_global_state,
    test_api_key,
)

if _EAB_TEST_ENVIRONMENT_WAS_MISSING:
    os.environ.pop("ENVIRONMENT", None)

logger = get_logger(__name__)


@pytest.fixture(autouse=True)
def _default_environment_for_eab_tests(monkeypatch):
    """Provide the legacy EAB test default without leaking it across packages."""
    if _EAB_TEST_ENVIRONMENT_WAS_MISSING:
        monkeypatch.setenv("ENVIRONMENT", _DEFAULT_EAB_TEST_ENVIRONMENT)


# ── Pytest hooks ──────────────────────────────────────────────────────────────


def pytest_collection_modifyitems(config, items):
    """Reorder test items to run polluting tests last.

    The test_integration_coverage_expansion.py file uses _load_module to create
    fresh module instances which pollutes sys.modules. Running it last prevents
    it from affecting other test files.

    Constitutional Hash: 608508a9bd224290
    """
    regular_tests = []
    polluting_tests = []

    for item in items:
        if "test_integration_coverage_expansion" in str(item.fspath):
            polluting_tests.append(item)
        else:
            regular_tests.append(item)

    items[:] = regular_tests + polluting_tests
