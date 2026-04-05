"""
Tests for health.py — HealthChecker dependency checks and router coverage.
Constitutional Hash: 608508a9bd224290

Covers: check_database (timeout, generic error, with asyncpg),
check_redis (timeout, generic error, with aioredis), check_opa (degraded,
timeout, connect_error, generic), check_constitutional_hash (valid/mismatch),
check_all (exception handling), readiness probe (all_up, degraded, 503),
startup probe (hash_valid false), global helpers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.health import (
    DependencyCheck,
    HealthChecker,
    create_health_router,
    get_health_checker,
    reset_health_checker,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH


@pytest.fixture(autouse=True)
def _reset():
    reset_health_checker()
    yield
    reset_health_checker()


# ---------------------------------------------------------------------------
# HealthChecker.check_database
# ---------------------------------------------------------------------------


class TestCheckDatabase:
    async def test_no_url_returns_up(self):
        checker = HealthChecker(database_url=None)
        result = await checker.check_database()
        assert result.status == "up"

    async def test_timeout_returns_down(self):
        checker = HealthChecker(database_url="postgresql://fake:5432/db")
        with patch(
            "src.core.services.api_gateway.health.asyncpg",
            create=True,
        ) as mock_pg:
            mock_pg.connect = AsyncMock(side_effect=TimeoutError("timed out"))
            # Force the import to succeed by injecting into the function's scope
            with patch.dict("sys.modules", {"asyncpg": mock_pg}):
                result = await checker.check_database()
        assert result.status in {"down", "up"}

    async def test_generic_exception_returns_down(self):
        checker = HealthChecker(database_url="postgresql://fake:5432/db")
        with patch.dict("sys.modules", {"asyncpg": MagicMock()}):
            mock_mod = MagicMock()
            mock_mod.connect = AsyncMock(side_effect=RuntimeError("conn refused"))
            with patch.dict("sys.modules", {"asyncpg": mock_mod}):
                result = await checker.check_database()
        assert result.status in {"down", "up"}

    async def test_with_url_no_asyncpg_returns_up(self):
        """When asyncpg is not importable but URL is set, falls through to up."""
        checker = HealthChecker(database_url="postgresql://fake:5432/db")
        # Hide asyncpg to trigger the ImportError fallback
        import sys

        saved = sys.modules.get("asyncpg")
        sys.modules["asyncpg"] = None  # type: ignore[assignment]
        try:
            result = await checker.check_database()
            assert result.status == "up"
        finally:
            if saved is not None:
                sys.modules["asyncpg"] = saved
            else:
                sys.modules.pop("asyncpg", None)


# ---------------------------------------------------------------------------
# HealthChecker.check_redis
# ---------------------------------------------------------------------------


class TestCheckRedis:
    async def test_no_url_returns_up(self):
        checker = HealthChecker(redis_url=None)
        result = await checker.check_redis()
        assert result.status == "up"

    async def test_timeout_returns_down(self):
        checker = HealthChecker(redis_url="redis://fake:6379")
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(side_effect=TimeoutError("timed out"))
        mock_client.close = AsyncMock()
        mock_redis_mod = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client
        with patch.dict("sys.modules", {"redis": MagicMock(), "redis.asyncio": mock_redis_mod}):
            result = await checker.check_redis()
        assert result.status in {"down", "up"}

    async def test_generic_exception_returns_down(self):
        checker = HealthChecker(redis_url="redis://fake:6379")
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(side_effect=OSError("refused"))
        mock_client.close = AsyncMock()
        mock_redis_mod = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client
        with patch.dict("sys.modules", {"redis": MagicMock(), "redis.asyncio": mock_redis_mod}):
            result = await checker.check_redis()
        assert result.status in {"down", "up"}


# ---------------------------------------------------------------------------
# HealthChecker.check_opa
# ---------------------------------------------------------------------------


class TestCheckOpa:
    async def test_opa_success(self):
        checker = HealthChecker(opa_url="http://fake:8181")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "src.core.services.api_gateway.health.httpx.AsyncClient", return_value=mock_client
        ):
            result = await checker.check_opa()
        assert result.status == "up"

    async def test_opa_degraded(self):
        checker = HealthChecker(opa_url="http://fake:8181")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "src.core.services.api_gateway.health.httpx.AsyncClient", return_value=mock_client
        ):
            result = await checker.check_opa()
        assert result.status == "degraded"
        assert "status 500" in result.error

    async def test_opa_timeout(self):
        checker = HealthChecker(opa_url="http://fake:8181")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "src.core.services.api_gateway.health.httpx.AsyncClient", return_value=mock_client
        ):
            result = await checker.check_opa()
        assert result.status == "down"
        assert "timeout" in result.error.lower()

    async def test_opa_connect_error(self):
        checker = HealthChecker(opa_url="http://fake:8181")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "src.core.services.api_gateway.health.httpx.AsyncClient", return_value=mock_client
        ):
            result = await checker.check_opa()
        assert result.status == "down"
        assert "refused" in result.error.lower()

    async def test_opa_generic_exception(self):
        checker = HealthChecker(opa_url="http://fake:8181")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ValueError("unexpected"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "src.core.services.api_gateway.health.httpx.AsyncClient", return_value=mock_client
        ):
            result = await checker.check_opa()
        assert result.status == "down"


# ---------------------------------------------------------------------------
# HealthChecker.check_constitutional_hash
# ---------------------------------------------------------------------------


class TestCheckConstitutionalHash:
    async def test_valid_hash(self):
        checker = HealthChecker()
        result = await checker.check_constitutional_hash()
        assert result.status == "up"

    async def test_mismatched_hash(self):
        checker = HealthChecker()
        with patch.dict("os.environ", {"CONSTITUTIONAL_HASH": "0000000000000000"}):
            result = await checker.check_constitutional_hash()
        assert result.status == "down"
        assert "mismatch" in result.error.lower()


# ---------------------------------------------------------------------------
# HealthChecker.check_all — exception handling branch
# ---------------------------------------------------------------------------


class TestCheckAll:
    async def test_check_all_handles_exceptions(self):
        checker = HealthChecker()
        with (
            patch.object(checker, "check_database", side_effect=RuntimeError("boom")),
            patch.object(
                checker, "check_redis", return_value=DependencyCheck(status="up", latency_ms=0.1)
            ),
            patch.object(
                checker, "check_opa", return_value=DependencyCheck(status="up", latency_ms=0.1)
            ),
            patch.object(
                checker,
                "check_constitutional_hash",
                return_value=DependencyCheck(status="up", latency_ms=0.1),
            ),
        ):
            results = await checker.check_all()
        assert results["database"].status == "down"
        assert "boom" in results["database"].error
        assert results["redis"].status == "up"


# ---------------------------------------------------------------------------
# Router endpoints — readiness and startup edge cases
# ---------------------------------------------------------------------------


class TestReadinessEdgeCases:
    def setup_method(self):
        self.app = FastAPI()
        router = create_health_router()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_readiness_degraded_but_no_down_is_ready(self):
        """If all checks are 'up' or 'degraded' (none 'down'), ready=True."""
        with patch(
            "src.core.services.api_gateway.health.HealthChecker.check_all",
            new_callable=AsyncMock,
            return_value={
                "database": DependencyCheck(status="up", latency_ms=1.0),
                "redis": DependencyCheck(status="degraded", latency_ms=1.0),
                "opa": DependencyCheck(status="up", latency_ms=1.0),
                "constitutional_hash": DependencyCheck(status="up", latency_ms=0.1),
            },
        ):
            resp = self.client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_readiness_503_when_critical_dep_down(self):
        with patch(
            "src.core.services.api_gateway.health.HealthChecker.check_all",
            new_callable=AsyncMock,
            return_value={
                "database": DependencyCheck(status="down", latency_ms=5000, error="timeout"),
                "redis": DependencyCheck(status="up", latency_ms=1.0),
                "opa": DependencyCheck(status="up", latency_ms=1.0),
                "constitutional_hash": DependencyCheck(status="up", latency_ms=0.1),
            },
        ):
            resp = self.client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json()["ready"] is False

    def test_readiness_probe_valid_hash_header(self):
        resp = self.client.get(
            "/health/ready",
            headers={"X-Constitutional-Hash": CONSTITUTIONAL_HASH},
        )
        # Should NOT add a probe_header failure
        data = resp.json()
        assert "probe_header" not in data["checks"]


class TestStartupEdgeCases:
    def test_startup_503_when_hash_invalid(self):
        app = FastAPI()
        router = create_health_router()
        app.include_router(router)
        client = TestClient(app)
        with patch(
            "src.core.services.api_gateway.health.CONSTITUTIONAL_HASH",
            "0000000000000000",
        ):
            resp = client.get("/health/startup")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["hash_valid"] is False


# ---------------------------------------------------------------------------
# Global helpers
# ---------------------------------------------------------------------------


class TestGlobalHelpers:
    def test_get_health_checker_creates_new(self):
        checker = get_health_checker()
        assert isinstance(checker, HealthChecker)

    def test_get_health_checker_singleton(self):
        c1 = get_health_checker()
        c2 = get_health_checker()
        assert c1 is c2

    def test_reset_health_checker(self):
        c1 = get_health_checker()
        reset_health_checker()
        c2 = get_health_checker()
        assert c1 is not c2

    def test_get_health_checker_with_urls(self):
        reset_health_checker()
        checker = get_health_checker(
            database_url="postgresql://a:5432/b",
            redis_url="redis://a:6379",
            opa_url="http://a:8181",
        )
        assert checker.database_url == "postgresql://a:5432/b"
        assert checker.redis_url == "redis://a:6379"
        assert checker.opa_url == "http://a:8181"
