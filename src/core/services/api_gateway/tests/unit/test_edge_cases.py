import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Edge case and error condition tests for API Gateway.
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, patch


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_large_feedback_payload(self, client):
        """Test handling of very large feedback payloads."""
        large_description = "x" * 5000  # max_length is 5000
        large_feedback = {
            "user_id": "test-user",
            "category": "general",
            "rating": 5,
            "title": "Large feedback test",
            "description": large_description,
            "metadata": {"size": "large", "test": True},
        }

        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/gateway/feedback", json=large_feedback)
        assert response.status_code in [200, 413, 422]

        if response.status_code == 200:
            data = response.json()
            assert "feedback_id" in data

    def test_special_characters_in_feedback(self, client):
        """Test feedback with special characters and unicode."""
        special_feedback = {
            "user_id": "test-user",
            "category": "bug",
            "rating": 3,
            "title": "Special chars test",
            "description": "Unicode test content",
            "metadata": {
                "special": "chars",
                "json": {"nested": {"value": 123}},
                "array": [1, 2, "three"],
            },
        }

        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/gateway/feedback", json=special_feedback)
        assert response.status_code == 200

        data = response.json()
        assert "feedback_id" in data

    def test_rapid_succession_requests(self, client, sample_feedback):
        """Test rapid succession of requests."""
        responses = []
        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            for i in range(20):
                feedback = {**sample_feedback, "title": f"Request {i + 1}"}
                response = client.post("/api/v1/gateway/feedback", json=feedback)
                responses.append(response.status_code)

        # All should succeed (rate limiter is disabled in test env)
        assert all(status == 200 for status in responses)

        # Health endpoint should still respond
        health_response = client.get("/health")
        assert health_response.status_code == 200

    def test_health_under_load(self, client):
        """Test health endpoint responds reliably under repeated calls."""
        for _ in range(20):
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"


class TestInputValidation:
    """Test input validation edge cases."""

    def test_empty_feedback_fields(self, client):
        """Test feedback with empty but valid fields (defaults allow empty strings)."""
        empty_feedback = {
            "user_id": "",
            "category": "",
            "rating": 3,
            "title": "",
            "description": "",
        }

        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/gateway/feedback", json=empty_feedback)
        # FeedbackRequest allows empty strings (defaults are "")
        assert response.status_code in [200, 422]

    def test_null_values_in_feedback(self, client):
        """Test feedback with null values."""
        null_feedback = {
            "user_id": None,
            "category": "bug",
            "rating": 3,
            "title": "Null test",
            "description": "Testing null values",
            "metadata": None,
        }

        response = client.post("/api/v1/gateway/feedback", json=null_feedback)
        # Pydantic may reject None for str fields
        assert response.status_code in [200, 422]

    def test_extremely_long_strings(self, client):
        """Test with extremely long string values."""
        long_feedback = {
            "user_id": "test-user",
            "category": "general",
            "rating": 5,
            "title": "a" * 100,
            "description": "a" * 5000,  # max_length is 5000
            "metadata": {"key": "value"},
        }

        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/gateway/feedback", json=long_feedback)
        assert response.status_code in [200, 413, 422]

    def test_nested_metadata_structures(self, client):
        """Test complex nested metadata structures."""
        complex_metadata = {
            "user_id": "test-user",
            "category": "feature",
            "rating": 4,
            "title": "Complex metadata test",
            "description": "Testing nested structures",
            "metadata": {
                "deeply": {
                    "nested": {
                        "structure": {
                            "with": ["arrays", "and", {"objects": "inside"}],
                            "numbers": [1, 2, 3, {"four": 4}],
                            "booleans": [True, False, None],
                        }
                    }
                },
                "performance": {"load_time": 1.23, "memory_usage": 45.67, "cpu_percent": 12.34},
            },
        }

        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/gateway/feedback", json=complex_metadata)
        assert response.status_code == 200

        data = response.json()
        assert "feedback_id" in data


class TestNetworkConditions:
    """Test proxy authentication gate for various network conditions."""

    def test_proxy_connection_requires_auth(self, client):
        """Test proxy returns 401 without authentication."""
        response = client.get("/api/v1/agents/test-endpoint")
        assert response.status_code == 401

    def test_proxy_post_requires_auth(self, client):
        """Test proxy POST returns 401/403 without authentication."""
        response = client.post(
            "/api/v1/agents/test-endpoint",
            json={"action": "test"},
        )
        assert response.status_code in [401, 403]

    def test_proxy_delete_requires_auth(self, client):
        """Test proxy DELETE returns 401/403 without authentication."""
        response = client.delete("/api/v1/agents/test-endpoint")
        assert response.status_code in [401, 403]

    def test_proxy_put_requires_auth(self, client):
        """Test proxy PUT returns 401/403 without authentication."""
        response = client.put(
            "/api/v1/agents/test-endpoint",
            json={"action": "update"},
        )
        assert response.status_code in [401, 403]


class TestResourceLimits:
    """Test resource limit handling."""

    def test_request_size_limits(self, client):
        """Test handling of various request sizes."""
        sizes = [100, 1000, 5000]

        for size in sizes:
            large_payload = {
                "user_id": "test-user",
                "category": "general",
                "rating": 3,
                "title": f"Size test {size}",
                "description": "x" * min(size, 5000),
                "metadata": {"size": size},
            }

            with patch(
                "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
                new_callable=AsyncMock,
            ):
                response = client.post("/api/v1/gateway/feedback", json=large_payload)
            assert response.status_code in [200, 413, 422]

    def test_many_sequential_requests(self, client, sample_feedback):
        """Test handling of many sequential requests."""
        results = []

        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            for i in range(50):
                response = client.post(
                    "/api/v1/gateway/feedback",
                    json={**sample_feedback, "title": f"Sequential {i}"},
                )
                results.append(response.status_code)

        successful_requests = sum(1 for s in results if s == 200)
        assert successful_requests > 0


class TestHealthUnderLoad:
    """Test health endpoints under various load conditions."""

    def test_health_collection_during_load(self, client, sample_feedback):
        """Test that health endpoint works properly during feedback load."""
        with patch(
            "src.core.services.api_gateway.routes.feedback.save_feedback_to_redis",
            new_callable=AsyncMock,
        ):
            for i in range(10):
                feedback = {**sample_feedback, "title": f"Load test {i + 1}"}
                response = client.post("/api/v1/gateway/feedback", json=feedback)
                assert response.status_code == 200

        # Health should still be accessible
        health_response = client.get("/health")
        assert health_response.status_code == 200
        data = health_response.json()
        assert data["status"] == "ok"

    def test_health_after_errors(self, client):
        """Test health endpoint works after error conditions."""
        # Generate some 404s
        for _ in range(5):
            response = client.get("/nonexistent-endpoint")
            # Catch-all proxy returns 401 (auth required)
            assert response.status_code == 401

        # Then verify health still works
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200

        # Liveness should also work
        liveness_response = client.get("/health/live")
        assert liveness_response.status_code == 200
