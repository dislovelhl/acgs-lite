import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Unit tests for API Gateway endpoints.
Constitutional Hash: cdd01ef066bc6cf2
"""

from unittest.mock import AsyncMock, patch


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "constitutional_hash" in data

    def test_health_check_with_liveness(self, client):
        """Test liveness probe endpoint."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["live"] is True
        assert "constitutional_hash" in data


class TestFeedbackEndpoints:
    """Test feedback submission and retrieval endpoints."""

    def test_submit_feedback_success(self, client, sample_feedback):
        """Test successful feedback submission."""
        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/gateway/feedback", json=sample_feedback)
        assert response.status_code == 200

        data = response.json()
        assert "feedback_id" in data
        assert data["status"] == "submitted"
        assert "timestamp" in data
        assert "Thank you for your feedback" in data["message"]

    def test_submit_feedback_defaults(self, client):
        """Test feedback submission with minimal/default fields."""
        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/gateway/feedback", json={})
        assert response.status_code == 200
        data = response.json()
        assert "feedback_id" in data
        assert data["status"] == "submitted"

    def test_submit_feedback_invalid_rating(self, client):
        """Test feedback submission with invalid rating triggers validation error."""
        invalid_feedback = {
            "user_id": "test-user",
            "category": "general",
            "rating": 10,  # Max is 5
            "title": "Invalid rating test",
            "description": "Rating out of range",
        }
        response = client.post("/api/v1/gateway/feedback", json=invalid_feedback)
        assert response.status_code == 422  # Validation error

    def test_get_feedback_stats_requires_auth(self, client):
        """Test feedback statistics endpoint requires authentication."""
        response = client.get("/api/v1/gateway/feedback/stats")
        # Without auth token, returns 403 (get_current_user_optional returns None)
        assert response.status_code == 403


class TestServiceDiscovery:
    """Test service discovery endpoints."""

    def test_list_services_requires_auth(self, client):
        """Test service listing endpoint requires authentication."""
        response = client.get("/api/v1/gateway/services")
        # get_current_user (required) raises 401/403 without Bearer token
        assert response.status_code in [401, 403]

    def test_list_services_structure(self, client):
        """Test that version/docs endpoint returns expected structure."""
        response = client.get("/api/v1/gateway/version/docs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestProxyEndpoints:
    """Test proxy functionality to backend services."""

    def test_proxy_requires_authentication(self, client):
        """Test that proxy requests require authentication."""
        response = client.get("/api/v1/agents/test")
        assert response.status_code == 401

    def test_proxy_rejects_unauthenticated_post(self, client):
        """Test that proxy POST requests require authentication."""
        response = client.post("/api/v1/agents/test", json={"action": "test"})
        # POST without auth: either 401 from proxy auth check or 403 from CSRF
        assert response.status_code in [401, 403]


class TestVersionEndpoints:
    """Test version and documentation endpoints."""

    def test_version_docs_endpoint(self, client):
        """Test that version docs endpoint is accessible."""
        response = client.get("/api/v1/gateway/version/docs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_version_info_endpoint(self, client):
        """Test that version info endpoint is accessible."""
        response = client.get("/api/v1/gateway/version")
        assert response.status_code == 200
