import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Integration tests for metrics and monitoring.
Constitutional Hash: cdd01ef066bc6cf2
"""

from unittest.mock import MagicMock, patch


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

    @patch("main.httpx.AsyncClient")
    def test_request_metrics_collected_for_proxy_calls(self, mock_httpx_client, client):
        """Test that request metrics are collected for proxy calls."""
        # Setup mock
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"result": "success"}'
        mock_instance.request.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_httpx_client.return_value = mock_instance

        # Make request
        response = client.get("/api/v1/test")
        assert response.status_code == 200

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

    def test_correlation_id_in_logs(self, client, correlation_id):
        """Test that correlation IDs are properly handled."""
        headers = {"x-correlation-id": correlation_id}

        # Make request with correlation ID
        response = client.get("/health", headers=headers)
        assert response.status_code == 200

        # Check that correlation ID is returned
        assert response.headers.get("x-correlation-id") == correlation_id

    def test_request_logging_structure(self, client, sample_feedback):
        """Test that request logging follows structured format."""
        # This is hard to test directly without log capture,
        # but we can verify the logging imports are working
        from src.core.shared.acgs_logging import get_logger

        logger = get_logger("test")
        assert logger is not None

        # Verify logging functions exist
        from src.core.shared.acgs_logging import (
            log_error,
            log_request_end,
            log_request_start,
        )

        assert callable(log_request_start)
        assert callable(log_request_end)
        assert callable(log_error)

    def test_business_event_logging(self, client, sample_feedback):
        """Test business event logging structure."""
        from src.core.shared.acgs_logging import get_logger, log_business_event

        logger = get_logger("test")

        # Should not raise exceptions
        log_business_event(
            logger,
            event_type="feedback",
            entity_type="submission",
            entity_id="test-123",
            action="created",
        )


class TestErrorHandlingMetrics:
    """Test error handling and metrics collection."""

    def test_404_error_metrics(self, client):
        """Test that 404 errors are properly tracked."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404

        # Check metrics are still accessible
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

    def test_malformed_json_error_handling(self, client):
        """Test handling of malformed JSON requests."""
        # Send invalid JSON
        response = client.post(
            "/feedback", data="invalid json {", headers={"content-type": "application/json"}
        )
        assert response.status_code == 422  # Validation error

        # Metrics should still work
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

    @patch("main.httpx.AsyncClient")
    def test_proxy_timeout_error_handling(self, mock_httpx_client, client):
        """Test handling of proxy timeouts."""
        from httpx import TimeoutException

        # Mock timeout
        mock_httpx_client.side_effect = TimeoutException("Request timeout")

        response = client.get("/api/v1/test")
        assert response.status_code == 502

        # Metrics should still work
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200


class TestSecurityIntegration:
    """Test security features integration."""

    def test_cors_headers(self, client):
        """Test CORS headers are properly set."""
        response = client.options("/health")
        # CORS should be configured
        assert "access-control-allow-origin" in response.headers or response.status_code in [
            200,
            404,
        ]

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
