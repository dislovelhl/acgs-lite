import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Integration tests for feedback submission flow.
Constitutional Hash: 608508a9bd224290
"""

import json

import pytest

from src.core.shared.security.auth import UserClaims, get_current_user_optional


class _FakeFeedbackRedis:
    def __init__(self) -> None:
        self.records: dict[str, str] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.records[key] = value

    async def get(self, key: str) -> str | None:
        return self.records.get(key)

    async def scan_iter(self, match: str | None = None):
        prefix = match.rstrip("*") if match else ""
        for key in list(self.records):
            if key.startswith(prefix):
                yield key


@pytest.fixture
def mock_feedback_redis(monkeypatch):
    fake_redis = _FakeFeedbackRedis()

    async def _get_feedback_redis():
        return fake_redis

    monkeypatch.setattr(
        "src.core.services.api_gateway.routes.feedback.get_feedback_redis",
        _get_feedback_redis,
    )
    return fake_redis


def _admin_user() -> UserClaims:
    return UserClaims(
        sub="admin-feedback",
        tenant_id="tenant-test",
        roles=["admin"],
        permissions=[],
        exp=9_999_999_999,
        iat=1_000_000_000,
    )


class TestFeedbackIntegration:
    """Integration tests for complete feedback workflow."""

    def test_feedback_submission_and_storage(self, client, sample_feedback, mock_feedback_redis):
        """Test complete feedback submission and Redis persistence flow."""
        # Submit feedback
        response = client.post("/api/v1/gateway/feedback", json=sample_feedback)
        assert response.status_code == 200

        data = response.json()
        feedback_id = data["feedback_id"]

        # Verify response structure
        assert data["status"] == "submitted"
        assert data["message"] == "Thank you for your feedback! We'll review it shortly."
        assert "timestamp" in data

        assert len(mock_feedback_redis.records) == 1
        stored_data = json.loads(next(iter(mock_feedback_redis.records.values())))

        assert stored_data["feedback_id"] == feedback_id
        assert stored_data["user_id"] == sample_feedback["user_id"]
        assert stored_data["category"] == sample_feedback["category"]
        assert stored_data["rating"] == sample_feedback["rating"]
        assert stored_data["title"] == sample_feedback["title"]
        assert stored_data["description"] == sample_feedback["description"]
        assert stored_data["environment"] == "development"  # From settings

        # Verify additional metadata
        assert "ip_address_hash" in stored_data
        assert "timestamp" in stored_data
        assert stored_data["metadata"] == sample_feedback["metadata"]
        assert stored_data["submission_auth_mode"] == "anonymous"
        assert stored_data["authenticated_user_id"] is None

    def test_multiple_feedback_submissions(self, client, sample_feedback, mock_feedback_redis):
        """Test multiple feedback submissions are stored as separate Redis entries."""
        feedbacks = []

        # Submit multiple feedbacks
        for i in range(3):
            feedback_data = sample_feedback.copy()
            feedback_data["title"] = f"Test Feedback {i + 1}"
            feedback_data["rating"] = (i % 5) + 1

            response = client.post("/api/v1/gateway/feedback", json=feedback_data)
            assert response.status_code == 200
            feedbacks.append(response.json()["feedback_id"])

        assert len(mock_feedback_redis.records) == 3

        stored_ids = {
            json.loads(value)["feedback_id"] for value in mock_feedback_redis.records.values()
        }

        assert len(stored_ids) == 3
        assert set(feedbacks) == stored_ids

    def test_feedback_stats_calculation(self, app, client, sample_feedback, mock_feedback_redis):
        """Test feedback statistics calculation from Redis-backed storage."""
        # Submit various feedbacks
        test_feedbacks = [
            {"category": "bug", "rating": 2},
            {"category": "feature", "rating": 4},
            {"category": "bug", "rating": 1},
            {"category": "general", "rating": 5},
            {"category": "feature", "rating": 3},
        ]

        for feedback_data in test_feedbacks:
            full_feedback = {
                **sample_feedback,
                "category": feedback_data["category"],
                "rating": feedback_data["rating"],
            }
            client.post("/api/v1/gateway/feedback", json=full_feedback)

        app.dependency_overrides[get_current_user_optional] = lambda: _admin_user()
        try:
            response = client.get("/api/v1/gateway/feedback/stats")
        finally:
            app.dependency_overrides.pop(get_current_user_optional, None)
        assert response.status_code == 200

        stats = response.json()

        # Verify total count
        assert stats["total_feedback"] == 5

        # Verify category breakdown
        categories = stats["categories"]
        assert categories["bug"] == 2
        assert categories["feature"] == 2
        assert categories["general"] == 1

        # Verify rating distribution
        ratings = stats["ratings"]
        assert ratings["1"] == 1  # One 1-star rating
        assert ratings["2"] == 1  # One 2-star rating
        assert ratings["3"] == 1  # One 3-star rating
        assert ratings["4"] == 1  # One 4-star rating
        assert ratings["5"] == 1  # One 5-star rating

        # Verify average calculation
        expected_avg = (2 + 4 + 1 + 5 + 3) / 5  # 15/5 = 3.0
        assert stats["average_rating"] == expected_avg

    def test_feedback_with_minimal_data(self, client, mock_feedback_redis):
        """Test feedback submission with minimal required data."""
        minimal_feedback = {
            "user_id": "minimal-user",
            "category": "general",
            "rating": 3,
            "title": "Minimal feedback",
            "description": "Just the basics",
        }

        response = client.post("/api/v1/gateway/feedback", json=minimal_feedback)
        assert response.status_code == 200

        data = response.json()
        assert "feedback_id" in data
        assert data["status"] == "submitted"

        assert len(mock_feedback_redis.records) == 1
        stored_data = json.loads(next(iter(mock_feedback_redis.records.values())))

        assert stored_data["user_agent"] == "testclient"  # Filled from request headers
        assert stored_data["url"] == ""  # Default empty
        assert stored_data["metadata"] == {}  # Default empty dict

    def test_feedback_persistence_across_requests(self, client, sample_feedback, mock_feedback_redis):
        """Test that feedback persists correctly across multiple requests."""
        # First request
        response1 = client.post("/api/v1/gateway/feedback", json=sample_feedback)
        assert response1.status_code == 200
        id1 = response1.json()["feedback_id"]

        # Second request with different data
        feedback2 = sample_feedback.copy()
        feedback2["title"] = "Second feedback"
        feedback2["rating"] = 5

        response2 = client.post("/api/v1/gateway/feedback", json=feedback2)
        assert response2.status_code == 200
        id2 = response2.json()["feedback_id"]

        # Verify both exist and are different
        assert id1 != id2

        assert len(mock_feedback_redis.records) == 2
        contents = [json.loads(value) for value in mock_feedback_redis.records.values()]

        titles = {content["title"] for content in contents}
        assert "Test feedback" in titles
        assert "Second feedback" in titles

        ids = {content["feedback_id"] for content in contents}
        assert id1 in ids
        assert id2 in ids
