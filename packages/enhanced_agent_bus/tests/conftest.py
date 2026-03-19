"""
ACGS-2 Enhanced Agent Bus - Shared Test Fixtures
Constitutional Hash: cdd01ef066bc6cf2

Thin root conftest that delegates to the fixtures subpackage.
All sys.modules aliasing, singleton resets, and mock fixtures live
in packages/enhanced_agent_bus/tests/fixtures/.
"""

from enhanced_agent_bus.observability.structured_logging import get_logger

# ── Import fixtures subpackage ────────────────────────────────────────────────
# module_aliases side effects (sys.modules patching) run at import time.
# Fixture functions are re-exported so pytest discovers them in this conftest.
from .fixtures import (  # noqa: F401
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

logger = get_logger(__name__)


# ── Pytest hooks ──────────────────────────────────────────────────────────────


def pytest_collection_modifyitems(config, items):
    """Reorder test items to run polluting tests last.

    The test_integration_coverage_expansion.py file uses _load_module to create
    fresh module instances which pollutes sys.modules. Running it last prevents
    it from affecting other test files.

    Constitutional Hash: cdd01ef066bc6cf2
    """
    regular_tests = []
    polluting_tests = []

    for item in items:
        if "test_integration_coverage_expansion" in str(item.fspath):
            polluting_tests.append(item)
        else:
            regular_tests.append(item)

    items[:] = regular_tests + polluting_tests
