import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ENABLE_RATE_LIMITING"] = "false"
os.environ["SAML_ENABLED"] = "false"
"""
Test configuration and fixtures for API Gateway service.
Constitutional Hash: cdd01ef066bc6cf2
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.shared.acgs_logging import init_service_logging

# Initialize test logging
init_service_logging("api-gateway-test", level="WARNING", json_format=False)


@pytest.fixture
def app():
    """Create test FastAPI application."""
    from src.core.services.api_gateway.main import app

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def _bypass_feedback_rate_limit(monkeypatch):
    """Bypass the per-route feedback rate limiter for all unit tests."""
    from src.core.shared.security.rate_limiter import RateLimitResult

    always_allowed = RateLimitResult(
        allowed=True,
        limit=1000,
        remaining=999,
        retry_after=0,
        reset_at=0,
    )

    async def _always_allow(**kwargs):
        return always_allowed

    monkeypatch.setattr(
        "src.core.services.api_gateway.routes.feedback.rate_limiter.is_allowed",
        _always_allow,
    )


@pytest.fixture
def sample_feedback():
    """Sample feedback data for testing."""
    return {
        "user_id": "test-user-123",
        "category": "bug",
        "rating": 4,
        "title": "Test feedback",
        "description": "This is a test feedback submission",
        "user_agent": "TestAgent/1.0",
        "url": "http://test.com/page",
        "metadata": {"browser": "chrome", "version": "91.0"},
    }


@pytest.fixture
def mock_httpx():
    """Mock httpx for testing external requests."""
    with pytest.MonkeyPatch().context() as m:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"status": "healthy"}'

        mock_client.request.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        # Mock the proxy client
        m.setattr(
            "src.core.services.api_gateway.routes.proxy.get_proxy_client",
            AsyncMock(return_value=mock_client),
        )

        yield mock_client


@pytest.fixture
async def async_client(app):
    """Create async test client using httpx."""
    from httpx import AsyncClient

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def correlation_id():
    """Sample correlation ID for testing."""
    return "test-correlation-id-12345"


@pytest.fixture
def test_headers(correlation_id):
    """Standard test headers."""
    return {
        "x-correlation-id": correlation_id,
        "user-agent": "TestClient/1.0",
        "content-type": "application/json",
    }
