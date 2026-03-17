import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Unit tests for API Gateway endpoints.
Constitutional Hash: cdd01ef066bc6cf2
"""

import json
from unittest.mock import MagicMock, patch


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "api-gateway"
        assert "environment" in data

    def test_health_check_with_correlation_id(self, client, correlation_id):
        """Test health check with correlation ID header."""
        headers = {"x-correlation-id": correlation_id}
        response = client.get("/health", headers=headers)
        assert response.status_code == 200

        # Check that correlation ID is returned in response headers
        assert response.headers.get("x-correlation-id") == correlation_id


class TestFeedbackEndpoints:
    """Test feedback submission and retrieval endpoints."""

    def test_submit_feedback_success(self, client, sample_feedback, mock_feedback_dir):
        """Test successful feedback submission."""
        response = client.post("/feedback", json=sample_feedback)
        assert response.status_code == 200

        data = response.json()
        assert "feedback_id" in data
        assert data["status"] == "submitted"
        assert "timestamp" in data
        assert "Thank you for your feedback" in data["message"]

        # Check that feedback file was created
        feedback_files = list(mock_feedback_dir.glob("*.json"))
        assert len(feedback_files) == 1

        # Check file contents
        with open(feedback_files[0]) as f:
            saved_data = json.load(f)
            assert saved_data["user_id"] == sample_feedback["user_id"]
            assert saved_data["category"] == sample_feedback["category"]
            assert saved_data["rating"] == sample_feedback["rating"]
            assert saved_data["feedback_id"] == data["feedback_id"]

    def test_submit_feedback_missing_required_field(self, client):
        """Test feedback submission with missing required fields."""
        incomplete_feedback = {
            "user_id": "test-user",
            # Missing required fields
        }

        response = client.post("/feedback", json=incomplete_feedback)
        assert response.status_code == 422  # Validation error

    def test_submit_feedback_with_correlation_id(self, client, sample_feedback, correlation_id):
        """Test feedback submission preserves correlation ID."""
        headers = {"x-correlation-id": correlation_id}
        response = client.post("/feedback", json=sample_feedback, headers=headers)
        assert response.status_code == 200
        assert response.headers.get("x-correlation-id") == correlation_id

    def test_get_feedback_stats(self, client, mock_feedback_dir, sample_feedback):
        """Test feedback statistics endpoint."""
        # First submit some feedback
        client.post("/feedback", json=sample_feedback)

        # Modify sample for different categories
        sample_feedback["category"] = "feature"
        sample_feedback["rating"] = 5
        client.post("/feedback", json=sample_feedback)

        # Get stats
        response = client.get("/feedback/stats")
        assert response.status_code == 200

        data = response.json()
        assert "total_feedback" in data
        assert data["total_feedback"] >= 2
        assert "categories" in data
        assert "ratings" in data
        assert "average_rating" in data
        assert data["average_rating"] > 0


class TestServiceDiscovery:
    """Test service discovery endpoints."""

    @patch("main.httpx.AsyncClient")
    def test_list_services(self, mock_httpx_client, client):
        """Test service listing endpoint."""
        # Mock the httpx client
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_instance.request.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_httpx_client.return_value = mock_instance

        response = client.get("/services")
        assert response.status_code == 200

        data = response.json()
        assert "agent-bus" in data
        assert "api-gateway" in data

        # Check service structure
        agent_bus = data["agent-bus"]
        assert "url" in agent_bus
        assert "status" in agent_bus

    @patch("main.httpx.AsyncClient")
    def test_list_services_unreachable(self, mock_httpx_client, client):
        """Test service listing when services are unreachable."""
        # Mock httpx to raise exception
        mock_httpx_client.side_effect = Exception("Connection failed")

        response = client.get("/services")
        assert response.status_code == 200

        data = response.json()
        # Should still return services but with unreachable status
        assert "agent-bus" in data


class TestProxyEndpoints:
    """Test proxy functionality to backend services."""

    @patch("main.httpx.AsyncClient")
    def test_proxy_to_agent_bus_success(self, mock_httpx_client, client):
        """Test successful proxy request to agent bus."""
        # Mock the httpx client
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

        response = client.get("/api/v1/test-endpoint")
        assert response.status_code == 200
        assert response.json() == {"result": "success"}

    @patch("main.httpx.AsyncClient")
    def test_proxy_to_agent_bus_with_query_params(self, mock_httpx_client, client):
        """Test proxy request with query parameters."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "filtered"}
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"data": "filtered"}'
        mock_instance.request.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_httpx_client.return_value = mock_instance

        response = client.get("/api/v1/search?query=test&page=1")
        assert response.status_code == 200

    @patch("main.httpx.AsyncClient")
    def test_proxy_to_agent_bus_service_unavailable(self, mock_httpx_client, client):
        """Test proxy request when backend service is unavailable."""
        # Mock httpx to raise RequestError
        from httpx import RequestError

        mock_httpx_client.side_effect = RequestError("Connection failed")

        response = client.get("/api/v1/test-endpoint")
        assert response.status_code == 502
        assert "Service unavailable" in response.json()["detail"]

    @patch("main.httpx.AsyncClient")
    def test_proxy_preserves_correlation_id(self, mock_httpx_client, client, correlation_id):
        """Test that proxy preserves correlation ID."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"status": "ok"}'
        mock_instance.request.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_httpx_client.return_value = mock_instance

        headers = {"x-correlation-id": correlation_id}
        response = client.get("/api/v1/test", headers=headers)
        assert response.status_code == 200
        assert response.headers.get("x-correlation-id") == correlation_id


class TestMetrics:
    """Test metrics endpoint."""

    def test_metrics_endpoint(self, client):
        """Test that metrics endpoint is accessible."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Should return Prometheus format metrics
        content = response.text
        assert "http_requests_total" in content or "# Prometheus" in content
