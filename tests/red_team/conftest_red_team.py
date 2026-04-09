"""Shared fixtures for red-team governance tests."""

from __future__ import annotations

import pytest

from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine


@pytest.fixture
def default_engine() -> GovernanceEngine:
    return GovernanceEngine(Constitution.default(), strict=False)
