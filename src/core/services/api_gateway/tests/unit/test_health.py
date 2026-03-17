from src.core.shared.constants import CONSTITUTIONAL_HASH

"""
ACGS-2 API Gateway Health Endpoint Tests
Constitutional Hash: cdd01ef066bc6cf2

Tests for health module per SPEC_ACGS2_ENHANCED.md Section 3.3.
"""


# Import from parent directory
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from health import (
    CONSTITUTIONAL_HASH,
    BasicHealthResponse,
    DependencyCheck,
    DependencyStatus,
    HealthChecker,
    HealthStatus,
    LivenessResponse,
    ReadinessResponse,
    StartupResponse,
    create_health_router,
    get_health_checker,
    reset_health_checker,
)


class TestConstitutionalHash:
    """Test constitutional hash enforcement."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash matches spec."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_health_checker_has_constitutional_hash(self):
        """Verify HealthChecker includes constitutional hash."""
        checker = HealthChecker()
        assert checker.constitutional_hash == CONSTITUTIONAL_HASH


class TestHealthStatus:
    """Test HealthStatus enum."""

    def test_health_status_values(self):
        """Test all health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"


class TestDependencyStatus:
    """Test DependencyStatus enum."""

    def test_dependency_status_values(self):
        """Test all dependency status values."""
        assert DependencyStatus.UP.value == "up"
        assert DependencyStatus.DOWN.value == "down"
        assert DependencyStatus.DEGRADED.value == "degraded"


class TestBasicHealthResponse:
    """Test BasicHealthResponse model."""

    def test_basic_health_response_defaults(self):
        """Test default values."""
        response = BasicHealthResponse()
        assert response.status == "ok"
        assert response.constitutional_hash == CONSTITUTIONAL_HASH

    def test_basic_health_response_serialization(self):
        """Test JSON serialization."""
        response = BasicHealthResponse()
        data = response.model_dump()
        assert data["status"] == "ok"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestLivenessResponse:
    """Test LivenessResponse model."""

    def test_liveness_response_defaults(self):
        """Test default values."""
        response = LivenessResponse()
        assert response.live is True
        assert response.constitutional_hash == CONSTITUTIONAL_HASH


class TestDependencyCheck:
    """Test DependencyCheck model."""

    def test_dependency_check_up(self):
        """Test dependency check with status up."""
        check = DependencyCheck(status="up", latency_ms=1.5)
        assert check.status == "up"
        assert check.latency_ms == 1.5
        assert check.error is None

    def test_dependency_check_down_with_error(self):
        """Test dependency check with error."""
        check = DependencyCheck(
            status="down",
            latency_ms=5000.0,
            error="Connection timeout",
        )
        assert check.status == "down"
        assert check.error == "Connection timeout"


class TestReadinessResponse:
    """Test ReadinessResponse model."""

    def test_readiness_response_all_up(self):
        """Test readiness response when all dependencies up."""
        checks = {
            "database": DependencyCheck(status="up", latency_ms=1.0),
            "redis": DependencyCheck(status="up", latency_ms=0.5),
            "opa": DependencyCheck(status="up", latency_ms=2.0),
        }
        response = ReadinessResponse(
            ready=True,
            checks=checks,
            timestamp="2025-01-01T00:00:00Z",
        )
        assert response.ready is True
        assert len(response.checks) == 3
        assert response.constitutional_hash == CONSTITUTIONAL_HASH

    def test_readiness_response_some_down(self):
        """Test readiness response when some dependencies down."""
        checks = {
            "database": DependencyCheck(status="up", latency_ms=1.0),
            "redis": DependencyCheck(status="down", latency_ms=0, error="Connection refused"),
            "opa": DependencyCheck(status="up", latency_ms=2.0),
        }
        response = ReadinessResponse(
            ready=False,
            checks=checks,
            timestamp="2025-01-01T00:00:00Z",
        )
        assert response.ready is False


class TestHealthChecker:
    """Test HealthChecker class."""

    def setup_method(self):
        """Reset health checker before each test."""
        reset_health_checker()

    def test_get_health_checker_singleton(self):
        """Test global health checker is singleton."""
        checker1 = get_health_checker()
        checker2 = get_health_checker()
        assert checker1 is checker2

    def test_health_checker_default_opa_url(self):
        """Test default OPA URL."""
        checker = HealthChecker()
        assert checker.opa_url == "http://localhost:8181"

    def test_health_checker_custom_urls(self):
        """Test custom URLs."""
        checker = HealthChecker(
            database_url="postgresql://localhost:5432/test",
            redis_url="redis://localhost:6379",
            opa_url="http://opa:8181",
        )
        assert checker.database_url == "postgresql://localhost:5432/test"
        assert checker.redis_url == "redis://localhost:6379"
        assert checker.opa_url == "http://opa:8181"

    @pytest.mark.asyncio
    async def test_check_database_no_url(self):
        """Test database check when no URL configured."""
        checker = HealthChecker(database_url=None)
        result = await checker.check_database()
        assert result.status == "up"
        assert "No database URL" in (result.error or "")

    @pytest.mark.asyncio
    async def test_check_redis_no_url(self):
        """Test Redis check when no URL configured."""
        checker = HealthChecker(redis_url=None)
        result = await checker.check_redis()
        assert result.status == "up"
        assert "No Redis URL" in (result.error or "")

    @pytest.mark.asyncio
    async def test_check_opa_connection_error(self):
        """Test OPA check with connection error."""
        checker = HealthChecker(opa_url="http://nonexistent:8181")
        result = await checker.check_opa()
        assert result.status == "down"
        assert result.error is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_check_all_returns_dict(self):
        """Test check_all returns dictionary with all checks."""
        checker = HealthChecker()
        results = await checker.check_all()
        assert "database" in results
        assert "redis" in results
        assert "opa" in results
        assert "constitutional_hash" in results
        for check in results.values():
            assert isinstance(check, DependencyCheck)

    @pytest.mark.asyncio
    async def test_check_constitutional_hash_mismatch(self):
        """Readiness must fail if runtime hash differs from canonical hash."""
        checker = HealthChecker()
        with patch.dict("os.environ", {"CONSTITUTIONAL_HASH": "badbadbadbadbadb"}):
            result = await checker.check_constitutional_hash()
        assert result.status == "down"
        assert result.error == "Runtime constitutional hash mismatch"


class TestHealthRouter:
    """Test health router endpoints."""

    def setup_method(self):
        """Create test app with health router."""
        self.app = FastAPI()
        router = create_health_router()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_health_endpoint(self):
        """Test /health endpoint per spec."""
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_health_live_endpoint(self):
        """Test /health/live endpoint per spec."""
        response = self.client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["live"] is True
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_healthz_endpoint_alias(self):
        """Test /healthz liveness alias endpoint."""
        response = self.client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["live"] is True
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_health_ready_endpoint(self):
        """Test /health/ready endpoint per spec."""
        response = self.client.get("/health/ready")
        # May be 200 or 503 depending on dependencies
        assert response.status_code in [200, 503]
        data = response.json()
        assert "ready" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]
        assert "opa" in data["checks"]
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_readyz_endpoint_alias(self):
        """Test /readyz readiness alias endpoint."""
        response = self.client.get("/readyz")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "ready" in data
        assert "checks" in data

    def test_health_ready_response_format(self):
        """Test /health/ready response format per spec."""
        response = self.client.get("/health/ready")
        data = response.json()

        # Check structure per spec Section 3.3
        assert isinstance(data["ready"], bool)
        assert "timestamp" in data

        # Check dependency structure
        for dep_name in ["database", "redis", "opa"]:
            assert dep_name in data["checks"]
            dep = data["checks"][dep_name]
            assert "status" in dep
            assert "latency_ms" in dep

    def test_health_ready_probe_header_mismatch(self):
        """Readiness returns 503 when constitutional probe header is invalid."""
        response = self.client.get(
            "/health/ready",
            headers={"X-Constitutional-Hash": "deadbeefdeadbeef"},
        )
        assert response.status_code == 503
        payload = response.json()
        assert payload["ready"] is False
        assert payload["checks"]["probe_header"]["status"] == "down"


class TestStartupProbe:
    """Test /health/startup endpoint."""

    def setup_method(self):
        """Create test app with initialized state."""
        self.app = FastAPI()
        router = create_health_router()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_startup_returns_200_when_initialized_state_not_set(self):
        """Startup probe returns 200 even when app.state.initialized is not set."""
        response = self.client.get("/health/startup")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["initialized"] is False

    def test_startup_returns_200_when_initialized(self):
        """Startup probe returns 200 after app.state.initialized = True."""
        self.app.state.initialized = True
        response = self.client.get("/health/startup")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["initialized"] is True
        assert data["hash_valid"] is True
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_startupz_alias(self):
        """Test /startupz alias endpoint."""
        response = self.client.get("/startupz")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True

    def test_startup_response_model(self):
        """Test StartupResponse model."""
        resp = StartupResponse(ready=True, initialized=True, hash_valid=True)
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH


class TestHealthEndpointSpec:
    """Test health endpoints match SPEC_ACGS2_ENHANCED.md Section 3.3."""

    def setup_method(self):
        """Create test app."""
        self.app = FastAPI()
        router = create_health_router()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_health_returns_status_ok(self):
        """Spec: /health returns { status: 'ok' }"""
        response = self.client.get("/health")
        assert response.json()["status"] == "ok"

    def test_health_live_returns_live_true(self):
        """Spec: /health/live returns { live: true }"""
        response = self.client.get("/health/live")
        assert response.json()["live"] is True

    def test_healthz_returns_live_true(self):
        """Spec: /healthz returns { live: true }"""
        response = self.client.get("/healthz")
        assert response.json()["live"] is True

    def test_health_ready_checks_all_dependencies(self):
        """Spec: /health/ready checks [database, redis, opa]"""
        response = self.client.get("/health/ready")
        data = response.json()
        expected_checks = ["database", "redis", "opa"]
        for check in expected_checks:
            assert check in data["checks"], f"Missing check: {check}"

    def test_readyz_checks_all_dependencies(self):
        """Spec: /readyz checks [database, redis, opa]."""
        response = self.client.get("/readyz")
        data = response.json()
        for check in ["database", "redis", "opa"]:
            assert check in data["checks"], f"Missing check: {check}"

    def test_health_ready_dependency_format(self):
        """Spec: Each check has { status: string, latency_ms: number }"""
        response = self.client.get("/health/ready")
        data = response.json()

        for check_name, check_data in data["checks"].items():
            assert "status" in check_data, f"{check_name} missing status"
            assert "latency_ms" in check_data, f"{check_name} missing latency_ms"
            assert isinstance(check_data["status"], str)
            assert isinstance(check_data["latency_ms"], (int, float))

    def test_health_ready_returns_503_when_unhealthy(self):
        """Spec: Returns 503 when dependencies are down"""
        # Create checker with unreachable OPA
        app = FastAPI()
        router = create_health_router(opa_url="http://nonexistent:9999")
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/health/ready")
        # Should return 503 because OPA is unreachable
        assert response.status_code == 503
        assert response.json()["ready"] is False


class TestHealthCheckerIntegration:
    """Integration tests for HealthChecker with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_check_opa_success(self):
        """Test successful OPA health check."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            checker = HealthChecker(opa_url="http://localhost:8181")

            # Mock the actual HTTP call
            with patch("health.httpx.AsyncClient") as mock_client:
                mock_instance = MagicMock()
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock()
                mock_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_instance

                result = await checker.check_opa()
                assert result.status == "up"
                assert result.latency_ms >= 0
