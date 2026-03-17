import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Integration tests for feedback submission flow.
Constitutional Hash: cdd01ef066bc6cf2
"""

import json


class TestFeedbackIntegration:
    """Integration tests for complete feedback workflow."""

    def test_feedback_submission_and_storage(self, client, sample_feedback, mock_feedback_dir):
        """Test complete feedback submission and storage flow."""
        # Submit feedback
        response = client.post("/feedback", json=sample_feedback)
        assert response.status_code == 200

        data = response.json()
        feedback_id = data["feedback_id"]

        # Verify response structure
        assert data["status"] == "submitted"
        assert data["message"] == "Thank you for your feedback! We'll review it shortly."
        assert "timestamp" in data

        # Verify file was created
        feedback_files = list(mock_feedback_dir.glob("*.json"))
        assert len(feedback_files) == 1

        # Verify file contents
        feedback_file = feedback_files[0]
        with open(feedback_file) as f:
            stored_data = json.load(f)

        assert stored_data["feedback_id"] == feedback_id
        assert stored_data["user_id"] == sample_feedback["user_id"]
        assert stored_data["category"] == sample_feedback["category"]
        assert stored_data["rating"] == sample_feedback["rating"]
        assert stored_data["title"] == sample_feedback["title"]
        assert stored_data["description"] == sample_feedback["description"]
        assert stored_data["environment"] == "development"  # From settings

        # Verify additional metadata
        assert "ip_address" in stored_data
        assert "timestamp" in stored_data
        assert stored_data["metadata"] == sample_feedback["metadata"]

    def test_multiple_feedback_submissions(self, client, sample_feedback, mock_feedback_dir):
        """Test multiple feedback submissions are stored separately."""
        feedbacks = []

        # Submit multiple feedbacks
        for i in range(3):
            feedback_data = sample_feedback.copy()
            feedback_data["title"] = f"Test Feedback {i + 1}"
            feedback_data["rating"] = (i % 5) + 1

            response = client.post("/feedback", json=feedback_data)
            assert response.status_code == 200
            feedbacks.append(response.json()["feedback_id"])

        # Verify all files were created
        feedback_files = list(mock_feedback_dir.glob("*.json"))
        assert len(feedback_files) == 3

        # Verify each feedback has unique ID
        stored_ids = set()
        for feedback_file in feedback_files:
            with open(feedback_file) as f:
                data = json.load(f)
                stored_ids.add(data["feedback_id"])

        assert len(stored_ids) == 3
        assert set(feedbacks) == stored_ids

    def test_feedback_stats_calculation(self, client, sample_feedback, mock_feedback_dir):
        """Test feedback statistics calculation."""
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
            client.post("/feedback", json=full_feedback)

        # Get stats
        response = client.get("/feedback/stats")
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
        assert ratings[1] == 1  # One 1-star rating
        assert ratings[2] == 1  # One 2-star rating
        assert ratings[3] == 1  # One 3-star rating
        assert ratings[4] == 1  # One 4-star rating
        assert ratings[5] == 1  # One 5-star rating

        # Verify average calculation
        expected_avg = (2 + 4 + 1 + 5 + 3) / 5  # 15/5 = 3.0
        assert stats["average_rating"] == expected_avg

    def test_feedback_with_minimal_data(self, client, mock_feedback_dir):
        """Test feedback submission with minimal required data."""
        minimal_feedback = {
            "user_id": "minimal-user",
            "category": "general",
            "rating": 3,
            "title": "Minimal feedback",
            "description": "Just the basics",
        }

        response = client.post("/feedback", json=minimal_feedback)
        assert response.status_code == 200

        data = response.json()
        assert "feedback_id" in data
        assert data["status"] == "submitted"

        # Verify optional fields have defaults
        feedback_files = list(mock_feedback_dir.glob("*.json"))
        assert len(feedback_files) == 1

        with open(feedback_files[0]) as f:
            stored_data = json.load(f)

        assert stored_data["user_agent"] == ""  # Default empty
        assert stored_data["url"] == ""  # Default empty
        assert stored_data["metadata"] == {}  # Default empty dict

    def test_feedback_persistence_across_requests(self, client, sample_feedback, mock_feedback_dir):
        """Test that feedback persists correctly across multiple requests."""
        # First request
        response1 = client.post("/feedback", json=sample_feedback)
        assert response1.status_code == 200
        id1 = response1.json()["feedback_id"]

        # Second request with different data
        feedback2 = sample_feedback.copy()
        feedback2["title"] = "Second feedback"
        feedback2["rating"] = 5

        response2 = client.post("/feedback", json=feedback2)
        assert response2.status_code == 200
        id2 = response2.json()["feedback_id"]

        # Verify both exist and are different
        assert id1 != id2

        feedback_files = list(mock_feedback_dir.glob("*.json"))
        assert len(feedback_files) == 2

        # Verify content of both files
        contents = []
        for feedback_file in feedback_files:
            with open(feedback_file) as f:
                contents.append(json.load(f))

        titles = {content["title"] for content in contents}
        assert "Test feedback" in titles
        assert "Second feedback" in titles

        ids = {content["feedback_id"] for content in contents}
        assert id1 in ids
        assert id2 in ids
