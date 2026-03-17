"""
Shared fixtures for MCP Integration tests.
Constitutional Hash: cdd01ef066bc6cf2
"""

import pytest

# Constitutional hash for all tests
from src.core.shared.constants import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]
