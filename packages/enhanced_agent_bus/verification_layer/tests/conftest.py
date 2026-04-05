"""
Pytest Configuration for Verification Layer Tests
Constitutional Hash: 608508a9bd224290

Provides common fixtures and configuration for Layer 2 verification tests.
"""

import asyncio

import pytest

# Constitutional hash for compliance validation
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict


@pytest.fixture
def constitutional_hash() -> str:
    """Fixture providing the constitutional hash."""
    return CONSTITUTIONAL_HASH


@pytest.fixture
def sample_context() -> JSONDict:
    """Fixture providing a sample decision context."""
    return {
        "action": "test_action",
        "resource_id": "res-001",
        "user_id": "user-001",
        "timestamp": "2025-01-24T00:00:00Z",
    }


@pytest.fixture
def high_risk_context() -> JSONDict:
    """Fixture providing a high-risk decision context."""
    return {
        "action": "sensitive_action",
        "involves_sensitive_data": True,
        "high_impact": True,
        "requires_human_approval": True,
        "crosses_jurisdictions": True,
    }


@pytest.fixture
def violation_context() -> JSONDict:
    """Fixture providing a context that should trigger violations."""
    return {
        "action": "violation_action",
        "excessive_permissions": True,
        "data_unprotected": True,
        "policy_compliant": False,
        "auditable": False,
    }


@pytest.fixture
def sample_policy_text() -> str:
    """Fixture providing sample policy text."""
    return """
    All users must authenticate before accessing resources.
    Sensitive data must be encrypted at rest and in transit.
    Users cannot access resources without proper authorization.
    Session timeout must be at most 30 minutes.
    All access requests may be subject to audit.
    """


@pytest.fixture
def simple_policy_text() -> str:
    """Fixture providing simple policy text."""
    return "Users must authenticate."


@pytest.fixture
def conflicting_policy_text() -> str:
    """Fixture providing conflicting policy text."""
    return """
    Access level must be greater than 10.
    Access level must be less than 5.
    """


@pytest.fixture
def sample_saga_steps() -> list:
    """Fixture providing sample saga steps."""

    async def step1(ctx, data):
        return {"step": 1, "success": True}

    async def compensate1(result):
        return {"step": 1, "compensated": True}

    async def step2(ctx, data):
        return {"step": 2, "success": True}

    async def compensate2(result):
        return {"step": 2, "compensated": True}

    return [
        {
            "name": "Step 1 - Initialize",
            "description": "Initialize the operation",
            "execute": step1,
            "compensate": compensate1,
        },
        {
            "name": "Step 2 - Execute",
            "description": "Execute the main operation",
            "execute": step2,
            "compensate": compensate2,
        },
    ]


@pytest.fixture
def failing_saga_steps() -> list:
    """Fixture providing saga steps that will fail."""

    async def step1(ctx, data):
        return {"step": 1, "success": True}

    async def compensate1(result):
        return {"step": 1, "compensated": True}

    async def failing_step(ctx, data):
        raise Exception("Step failed intentionally")

    return [
        {
            "name": "Step 1 - Success",
            "execute": step1,
            "compensate": compensate1,
        },
        {
            "name": "Step 2 - Failure",
            "execute": failing_step,
            "compensate": None,
        },
    ]


# Markers for test categorization
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "constitutional: Tests related to constitutional compliance")
    config.addinivalue_line("markers", "maci: Tests for MACI verification")
    config.addinivalue_line("markers", "saga: Tests for Saga coordination")
    config.addinivalue_line("markers", "z3: Tests for Z3 policy verification")
    config.addinivalue_line("markers", "transition: Tests for state transitions")
    config.addinivalue_line("markers", "pipeline: Tests for verification pipeline")
    config.addinivalue_line("markers", "slow: Tests that take longer to run")
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring multiple components"
    )
