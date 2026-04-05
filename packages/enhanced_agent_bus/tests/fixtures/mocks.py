"""
Mock fixtures for Enhanced Agent Bus tests.

Provides Redis mocking, rate limiting disabling, and test API key fixtures.

Constitutional Hash: 608508a9bd224290
"""

import pytest


@pytest.fixture(autouse=True)
def _disable_redis_rate_limiting(monkeypatch):
    """Disable Redis-backed rate limiting in all EnhancedAgentBus tests.

    Redis requires authentication in this environment; tests that specifically
    need rate limiting should override this fixture.

    Constitutional Hash: 608508a9bd224290
    """
    try:
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        _original_init = EnhancedAgentBus.__init__

        def _patched_init(self, *args, **kwargs):
            kwargs.setdefault("enable_rate_limiting", False)
            _original_init(self, *args, **kwargs)

        monkeypatch.setattr(EnhancedAgentBus, "__init__", _patched_init)
    except (ImportError, AttributeError):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Test API Key Fixture
# ─────────────────────────────────────────────────────────────────────────────
# Moved from api_key_auth.py to prevent hardcoded test key in production module

TEST_API_KEY = "test-api-key-for-unit-tests"


@pytest.fixture
def test_api_key():
    """Provide test API key for authentication tests."""
    return TEST_API_KEY
