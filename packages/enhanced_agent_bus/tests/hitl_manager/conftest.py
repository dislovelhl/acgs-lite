"""
ACGS-2 Enhanced Agent Bus - HITL Manager Test Fixtures
Constitutional Hash: 608508a9bd224290

Shared fixtures for all HITL Manager tests.
Mock classes are defined in hitl_test_helpers.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from .hitl_test_helpers import (
    MockAuditLedger,
    MockDeliberationQueue,
    MockDeliberationStatus,
    MockQueueItem,
)


@pytest.fixture
def mock_queue() -> MockDeliberationQueue:
    """Create a mock deliberation queue."""
    queue = MockDeliberationQueue()
    item = MockQueueItem(id="item-123")
    queue.add_item("item-123", item)
    return queue


@pytest.fixture
def mock_audit_ledger() -> MockAuditLedger:
    """Create a mock audit ledger."""
    return MockAuditLedger()


# We need to patch the imports before importing HITLManager
@pytest.fixture
def hitl_manager_class():
    """Get HITLManager class with mocked dependencies."""
    with patch.dict(
        "sys.modules",
        {
            "deliberation_queue": MagicMock(),
        },
    ):
        # Create mock modules
        mock_deliberation_queue = MagicMock()
        mock_deliberation_queue.DeliberationStatus = MockDeliberationStatus
        mock_deliberation_queue.DeliberationQueue = MockDeliberationQueue

        with patch.object(
            __import__("sys"),
            "modules",
            {**__import__("sys").modules, "deliberation_queue": mock_deliberation_queue},
        ):
            from deliberation_layer.hitl_manager import HITLManager

            return HITLManager
