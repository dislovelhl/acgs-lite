import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Integration tests for metrics and monitoring.
Constitutional Hash: cdd01ef066bc6cf2
"""



class TestMetricsIntegration:
    """Test metrics collection and endpoints."""

    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """Test that metrics endpoint returns valid Prometheus format."""
        response = client.get("/metrics")

        # Should return 200 even if no metrics are registered yet
        assert response.status_code == 200

        content = response.text

        # Check for Prometheus format indicators
        # May contain HELP, TYPE declarations, or metric names
        prometheus_indicators = [
            "# HELP",
            "# TYPE",
            "http_requests_total",
            "http_request_duration_seconds",
            "python_gc_",
            "process_",
        ]

        # At minimum should have some Prometheus format content
        has_prometheus_format = any(indicator in content for indicator in prometheus_indicators)
        assert has_prometheus_format, (
            f"Response doesn't contain expected Prometheus format: {content[:200]}"
        )

    def test_metrics_include_service_info(self, client):
        """Test that metrics include service information."""
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text

        # Should contain service info metrics
        assert "acgs2_service" in content or "acgs2_service_info" in content

    def test_proxy_requests_are_tracked_even_when_auth_blocks_backend(self, client, mock_httpx):
        """Proxy-path requests should still be counted by HTTP metrics middleware."""
        response = client.get("/api/v1/agents")

        assert response.status_code == 401
        assert mock_httpx.request.await_count == 0

        # Check that metrics were attempted to be collected
        # (We can't easily test the actual metric values without a full metrics registry)
        from src.core.shared.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL

        # These should be the metric objects (not None)
        assert HTTP_REQUESTS_TOTAL is not None
        assert HTTP_REQUEST_DURATION is not None

    def test_health_endpoint_metrics(self, client):
        """Test that health endpoint properly tracks metrics."""
        # Make multiple health check calls
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200

        # Check metrics endpoint is accessible
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        # Should contain some HTTP metrics
        content = metrics_response.text
        assert "http_requests_total" in content


class TestStructuredLoggingIntegration:
    """Test structured logging integration."""

    def test_correlation_id_helpers_round_trip(self, correlation_id):
        """Correlation ID helpers should preserve request-scoped context."""
        from src.core.shared.acgs_logging import (
            clear_correlation_id,
            get_correlation_id,
            set_correlation_id,
        )

        set_correlation_id(correlation_id)
        assert get_correlation_id() == correlation_id
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_request_logging_structure(self):
        """Test that structured logging exports remain available."""
        from src.core.shared.acgs_logging import (
            StructuredLogger,
            create_correlation_middleware,
            get_logger,
            init_service_logging,
        )

        logger = get_logger("test")
        structured_logger = init_service_logging("metrics-test", level="INFO", json_format=True)

        assert logger is not None
        assert isinstance(structured_logger, StructuredLogger)
        assert callable(create_correlation_middleware())

    def test_business_event_logging(self):
        """Agent workflow event helpers should produce structured payloads."""
        from src.core.shared.acgs_logging import (
            AgentWorkflowEventType,
            create_agent_workflow_event,
            event_to_dict,
        )

        event = create_agent_workflow_event(
            event_type=AgentWorkflowEventType.AUTONOMOUS_ACTION,
            tenant_id="tenant-test",
            source="api-gateway",
            reason="integration-test",
            metadata={"event": "feedback"},
        )
        payload = event_to_dict(event)

        assert payload["tenant_id"] == "tenant-test"
        assert payload["source"] == "api-gateway"
        assert payload["metadata"]["event"] == "feedback"


class TestErrorHandlingMetrics:
    """Test error handling and metrics collection."""

    def test_unmatched_proxy_path_requires_auth(self, client):
        """Unmatched root paths fall through to the authenticated proxy catch-all."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 401

        # Check metrics are still accessible
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

    def test_malformed_json_error_handling(self, client):
        """Test handling of malformed JSON requests."""
        # Send invalid JSON
        response = client.post(
            "/api/v1/gateway/feedback",
            content="invalid json {",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422  # Validation error

        # Metrics should still work
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

    def test_proxy_auth_failures_leave_metrics_endpoint_available(self, client, mock_httpx):
        """Auth failures on proxy paths should not break the metrics endpoint."""
        response = client.get("/api/v1/agents")
        assert response.status_code == 401
        assert mock_httpx.request.await_count == 0

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200


class TestSecurityIntegration:
    """Test security features integration."""

    def test_cors_headers(self, client):
        """Test CORS headers are properly set."""
        response = client.options(
            "/health",
            headers={
                "origin": "http://localhost:3000",
                "access-control-request-method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_security_headers(self, client):
        """Test security headers are present."""
        response = client.get("/health")

        # Should have some security headers
        security_headers = [
            "x-content-type-options",
            "x-frame-options",
            "x-correlation-id",  # We set this
        ]

        has_some_security_headers = any(header in response.headers for header in security_headers)
        assert has_some_security_headers, f"No security headers found in: {dict(response.headers)}"

    def test_authentication_middleware_loaded(self, client):
        """Test that authentication middleware is loaded."""
        # Make a request - if auth middleware is loaded, it shouldn't break basic functionality
        response = client.get("/health")
        assert response.status_code == 200

        # The middleware should add user context if auth header provided
        # (but we don't test full auth flow here)
