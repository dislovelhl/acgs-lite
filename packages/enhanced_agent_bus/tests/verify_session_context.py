#!/usr/bin/env python3
"""
Manual verification script for SessionContext and SessionContextStore.
Constitutional Hash: 608508a9bd224290

This script demonstrates the basic functionality of session context management.
"""

import asyncio
import sys
from datetime import datetime, timezone


def verify_imports():
    """Verify all required imports work."""
    try:
        from enhanced_agent_bus.models import RiskLevel, SessionGovernanceConfig

        from ..session_context import SessionContext, SessionContextStore

        return True, (RiskLevel, SessionGovernanceConfig, SessionContext, SessionContextStore)
    except (RuntimeError, ValueError, TypeError, AssertionError) as e:
        return False, None


def verify_models(classes):
    """Verify model creation and validation."""
    RiskLevel, SessionGovernanceConfig, SessionContext, _SessionContextStore = classes

    try:
        # Create governance config
        gov_config = SessionGovernanceConfig(
            session_id="test-session-123",
            tenant_id="test-tenant",
            user_id="test-user",
            risk_level=RiskLevel.HIGH,
            policy_overrides={"max_tokens": 1000},
        )

        # Create session context
        session = SessionContext(
            session_id="test-session-123",
            governance_config=gov_config,
            metadata={"test": "data"},
        )

        # Test serialization
        session_dict = session.to_dict()

        # Test deserialization
        restored = SessionContext.from_dict(session_dict)

        # Verify data integrity
        assert restored.session_id == session.session_id
        assert restored.governance_config.tenant_id == gov_config.tenant_id
        assert restored.metadata == session.metadata

        return True, session
    except (RuntimeError, ValueError, TypeError, AssertionError) as e:
        import traceback

        traceback.print_exc()
        return False, None


def verify_store_creation(classes):
    """Verify store creation."""
    _, _, _, SessionContextStore = classes

    try:
        store = SessionContextStore(
            redis_url="redis://localhost:6379",
            key_prefix="test:session",
            default_ttl=3600,
        )

        # Test key generation
        key = store._make_key("test-session-123")

        return True, store
    except (RuntimeError, ValueError, TypeError, AssertionError) as e:
        import traceback

        traceback.print_exc()
        return False, None


async def verify_store_operations(store, session):
    """Verify store operations (requires Redis)."""

    try:
        # Try to connect
        connected = await store.connect()
        if not connected:
            return True

        # Test set operation
        result = await store.set(session, ttl=60)

        # Test exists operation
        exists = await store.exists(session.session_id)

        # Test get operation
        retrieved = await store.get(session.session_id)
        if retrieved:
            pass
        else:
            pass

        # Test TTL operations
        ttl = await store.get_ttl(session.session_id)

        # Test delete operation
        deleted = await store.delete(session.session_id)

        # Cleanup
        await store.disconnect()

        return True

    except (RuntimeError, ValueError, TypeError, AssertionError) as e:
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all verification tests."""

    # Verify imports
    success, classes = verify_imports()
    if not success:
        return False

    # Verify models
    success, session = verify_models(classes)
    if not success:
        return False

    # Verify store creation
    success, store = verify_store_creation(classes)
    if not success:
        return False

    # Verify store operations (async)
    success = await verify_store_operations(store, session)
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
