"""
Shared fixtures for MCP Integration tests.
Constitutional Hash: 608508a9bd224290
"""

import pytest

# Constitutional hash for all tests
from src.core.shared.constants import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]
