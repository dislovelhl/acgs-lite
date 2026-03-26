"""Tests for adaptive load shedding middleware.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.core.services.api_gateway.middleware.load_shedding import (
    NEVER_SHED,
    AdaptiveLoadShedder,
    LoadSheddingMiddleware,
    ShedPriority,
    _classify_path,
)

# ---------------------------------------------------------------------------
# ShedPriority enum
# ---------------------------------------------------------------------------


class TestShedPriority:
    def test_governance_in_never_shed(self):
        assert ShedPriority.GOVERNANCE in NEVER_SHED

    def test_health_in_never_shed(self):
        assert ShedPriority.HEALTH in NEVER_SHED

    def test_analytics_not_in_never_shed(self):
        assert ShedPriority.ANALYTICS not in NEVER_SHED

    def test_messages_normal_not_in_never_shed(self):
        assert ShedPriority.MESSAGES_NORMAL not in NEVER_SHED


# ---------------------------------------------------------------------------
# _classify_path
# ---------------------------------------------------------------------------


class TestClassifyPath:
    def test_health_path(self):
        assert _classify_path("/health") == ShedPriority.HEALTH

    def test_healthz_path(self):
        assert _classify_path("/healthz") == ShedPriority.HEALTH

    def test_readyz_path(self):
        assert _classify_path("/readyz") == ShedPriority.HEALTH

    def test_startupz_path(self):
        assert _classify_path("/startupz") == ShedPriority.HEALTH

    def test_governance_validate_path(self):
        assert _classify_path("/api/v1/validate") == ShedPriority.GOVERNANCE

    def test_governance_decisions_path(self):
        assert _classify_path("/api/v1/decisions") == ShedPriority.GOVERNANCE

    def test_governance_policies_path(self):
        assert _classify_path("/api/v1/policies") == ShedPriority.GOVERNANCE

    def test_data_subject_path(self):
        assert _classify_path("/api/v1/data-subject") == ShedPriority.GOVERNANCE

    def test_analytics_stats_path(self):
        assert _classify_path("/api/v1/stats") == ShedPriority.ANALYTICS

    def test_analytics_analytics_path(self):
        assert _classify_path("/api/v1/analytics") == ShedPriority.ANALYTICS

    def test_metrics_path(self):
        assert _classify_path("/metrics") == ShedPriority.ANALYTICS

    def test_feedback_path(self):
        assert _classify_path("/api/v1/feedback") == ShedPriority.FEEDBACK

    def test_messages_path(self):
        assert _classify_path("/api/v1/messages") == ShedPriority.MESSAGES_NORMAL

    def test_sso_path(self):
        assert _classify_path("/api/v1/sso") == ShedPriority.MESSAGES_NORMAL

    def test_admin_path(self):
        assert _classify_path("/api/v1/admin") == ShedPriority.MESSAGES_NORMAL

    def test_unknown_path_defaults_to_messages_normal(self):
        assert _classify_path("/api/v1/unknown") == ShedPriority.MESSAGES_NORMAL

    def test_root_path_defaults(self):
        assert _classify_path("/") == ShedPriority.MESSAGES_NORMAL

    def test_prefix_matching_works(self):
        """Paths that START with a known prefix should match."""
        assert _classify_path("/health/ready") == ShedPriority.HEALTH
        assert _classify_path("/api/v1/governance/rules") == ShedPriority.GOVERNANCE


# ---------------------------------------------------------------------------
# AdaptiveLoadShedder
# ---------------------------------------------------------------------------


class TestAdaptiveLoadShedder:
    @pytest.fixture
    def shedder(self):
        return AdaptiveLoadShedder(p99_target_ms=5.0, window_seconds=30)

    @pytest.mark.asyncio
    async def test_initial_shed_percentage_is_zero(self, shedder):
        pct = await shedder.get_shed_percentage()
        assert pct == 0.0

    @pytest.mark.asyncio
    async def test_governance_never_shed(self, shedder):
        """CI-2 invariant: governance requests are never shed."""
        # Push shed_pct to 1.0 by recording high latencies
        for _ in range(20):
            await shedder.record_latency(100.0)
            await shedder.should_shed(ShedPriority.ANALYTICS)

        result = await shedder.should_shed(ShedPriority.GOVERNANCE)
        assert result is False

    @pytest.mark.asyncio
    async def test_health_never_shed(self, shedder):
        """CI-2 invariant: health requests are never shed."""
        for _ in range(20):
            await shedder.record_latency(100.0)
            await shedder.should_shed(ShedPriority.ANALYTICS)

        result = await shedder.should_shed(ShedPriority.HEALTH)
        assert result is False

    @pytest.mark.asyncio
    async def test_shed_pct_increases_when_p99_exceeds_target(self, shedder):
        """Shed percentage should increase when latency exceeds SLO."""
        for _ in range(10):
            await shedder.record_latency(50.0)  # 50ms >> 5ms target

        # Call should_shed to trigger the shed_pct update
        await shedder.should_shed(ShedPriority.ANALYTICS)

        pct = await shedder.get_shed_percentage()
        assert pct > 0.0

    @pytest.mark.asyncio
    async def test_shed_pct_decreases_when_below_target(self, shedder):
        """Shed percentage should decrease when latency is within SLO."""
        # First, push it up
        for _ in range(10):
            await shedder.record_latency(50.0)
        await shedder.should_shed(ShedPriority.ANALYTICS)

        pct_high = await shedder.get_shed_percentage()
        assert pct_high > 0.0

        # Now record low latencies — clear old ones by manipulating window
        shedder._latencies.clear()
        for _ in range(10):
            await shedder.record_latency(0.1)

        await shedder.should_shed(ShedPriority.ANALYTICS)
        pct_low = await shedder.get_shed_percentage()
        assert pct_low < pct_high

    @pytest.mark.asyncio
    async def test_record_latency_adds_sample(self, shedder):
        await shedder.record_latency(2.5)
        assert len(shedder._latencies) == 1

    @pytest.mark.asyncio
    async def test_compute_p99_empty_returns_zero(self, shedder):
        result = shedder._compute_p99()
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_compute_p99_single_sample(self, shedder):
        await shedder.record_latency(10.0)
        result = shedder._compute_p99()
        assert result == 10.0

    @pytest.mark.asyncio
    async def test_shed_pct_capped_at_one(self, shedder):
        """Shed percentage should never exceed 1.0."""
        for _ in range(200):
            await shedder.record_latency(1000.0)
            await shedder.should_shed(ShedPriority.ANALYTICS)

        pct = await shedder.get_shed_percentage()
        assert pct <= 1.0

    @pytest.mark.asyncio
    async def test_shed_pct_floor_at_zero(self, shedder):
        """Shed percentage should never go below 0.0."""
        for _ in range(200):
            await shedder.record_latency(0.001)
            await shedder.should_shed(ShedPriority.ANALYTICS)

        pct = await shedder.get_shed_percentage()
        assert pct >= 0.0


# ---------------------------------------------------------------------------
# LoadSheddingMiddleware (ASGI)
# ---------------------------------------------------------------------------


class TestLoadSheddingMiddleware:
    @pytest.fixture
    def mock_app(self):
        """A simple ASGI app that returns 200."""

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"ok",
                }
            )

        return app

    @pytest.fixture
    def shedder(self):
        return AdaptiveLoadShedder(p99_target_ms=5.0, window_seconds=30)

    def _make_scope(self, path="/test"):
        return {
            "type": "http",
            "path": path,
            "method": "GET",
            "headers": [],
            "query_string": b"",
        }

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self, mock_app, shedder):
        """Non-HTTP scopes (e.g. websocket) should pass through."""
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)
        scope = {"type": "websocket", "path": "/ws"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        # The inner app should be called for non-http
        assert send.call_count > 0

    @pytest.mark.asyncio
    async def test_normal_request_passes_through(self, mock_app, shedder):
        """Requests should pass through when shed_pct is 0."""
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)
        scope = self._make_scope("/api/v1/messages")
        receive = AsyncMock()
        responses = []

        async def capture_send(msg):
            responses.append(msg)

        await middleware(scope, receive, capture_send)
        statuses = [r["status"] for r in responses if r.get("type") == "http.response.start"]
        assert 200 in statuses

    @pytest.mark.asyncio
    async def test_shed_returns_503(self, mock_app, shedder):
        """When shedder decides to shed, middleware returns 503."""
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)
        scope = self._make_scope("/api/v1/stats")
        receive = AsyncMock()
        responses = []

        async def capture_send(msg):
            responses.append(msg)

        with patch.object(shedder, "should_shed", return_value=True):
            await middleware(scope, receive, capture_send)

        start = next(r for r in responses if r.get("type") == "http.response.start")
        assert start["status"] == 503

        body_msg = next(r for r in responses if r.get("type") == "http.response.body")
        body = json.loads(body_msg["body"])
        assert body["error"] == "service_overloaded"
        assert body["retry_after_seconds"] == 5

    @pytest.mark.asyncio
    async def test_shed_response_includes_retry_after_header(self, mock_app, shedder):
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)
        scope = self._make_scope("/api/v1/stats")
        receive = AsyncMock()
        responses = []

        async def capture_send(msg):
            responses.append(msg)

        with patch.object(shedder, "should_shed", return_value=True):
            await middleware(scope, receive, capture_send)

        start = next(r for r in responses if r.get("type") == "http.response.start")
        headers = dict(start["headers"])
        assert headers[b"retry-after"] == b"5"
        assert headers[b"x-shed-reason"] == b"latency_slo_breach"

    @pytest.mark.asyncio
    async def test_records_latency_after_successful_request(self, mock_app, shedder):
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)
        scope = self._make_scope("/api/v1/messages")
        receive = AsyncMock()

        async def noop_send(msg):
            pass

        await middleware(scope, receive, noop_send)
        assert len(shedder._latencies) == 1

    @pytest.mark.asyncio
    async def test_governance_path_not_shed(self, mock_app, shedder):
        """Governance paths should never be shed even under high load."""
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)

        # Push shed_pct up
        for _ in range(50):
            await shedder.record_latency(1000.0)
            await shedder.should_shed(ShedPriority.ANALYTICS)

        scope = self._make_scope("/api/v1/governance/check")
        receive = AsyncMock()
        responses = []

        async def capture_send(msg):
            responses.append(msg)

        await middleware(scope, receive, capture_send)
        statuses = [r["status"] for r in responses if r.get("type") == "http.response.start"]
        assert 200 in statuses

    @pytest.mark.asyncio
    async def test_health_path_not_shed(self, mock_app, shedder):
        """Health paths should never be shed even under high load."""
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)

        for _ in range(50):
            await shedder.record_latency(1000.0)
            await shedder.should_shed(ShedPriority.ANALYTICS)

        scope = self._make_scope("/health")
        receive = AsyncMock()
        responses = []

        async def capture_send(msg):
            responses.append(msg)

        await middleware(scope, receive, capture_send)
        statuses = [r["status"] for r in responses if r.get("type") == "http.response.start"]
        assert 200 in statuses

    @pytest.mark.asyncio
    async def test_custom_path_classifier(self, mock_app, shedder):
        """Custom path classifier is used when provided."""

        def always_analytics(path: str) -> ShedPriority:
            return ShedPriority.ANALYTICS

        middleware = LoadSheddingMiddleware(
            mock_app, shedder=shedder, path_classifier=always_analytics
        )
        assert middleware._classify is always_analytics

    @pytest.mark.asyncio
    async def test_default_shedder_created_when_none(self, mock_app):
        """A default shedder is created when none is provided."""
        middleware = LoadSheddingMiddleware(mock_app)
        assert isinstance(middleware.shedder, AdaptiveLoadShedder)

    @pytest.mark.asyncio
    async def test_shed_body_includes_priority(self, mock_app, shedder):
        middleware = LoadSheddingMiddleware(mock_app, shedder=shedder)
        scope = self._make_scope("/api/v1/stats")
        receive = AsyncMock()
        responses = []

        async def capture_send(msg):
            responses.append(msg)

        with patch.object(shedder, "should_shed", return_value=True):
            await middleware(scope, receive, capture_send)

        body_msg = next(r for r in responses if r.get("type") == "http.response.body")
        body = json.loads(body_msg["body"])
        assert body["shed_priority"] == "analytics"
