"""conftest.py for enhanced_agent_bus coverage tests.

Disables the slowapi rate-limiter so that coverage tests calling route
handlers directly don't trigger slowapi's request-type validation. Tests
that need a Starlette Request pass MagicMock() directly; the disabled
limiter means no isinstance(request, Request) guard is enforced.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_slowapi_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set limiter.enabled=False to skip slowapi request validation."""
    try:
        from enhanced_agent_bus.api.rate_limiting import limiter

        monkeypatch.setattr(limiter, "enabled", False)
    except ImportError:
        pass
