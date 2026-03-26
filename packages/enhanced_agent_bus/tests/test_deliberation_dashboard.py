"""Tests for deliberation_layer.dashboard module.

The dashboard is Streamlit-based UI code. We test the helper functions
by mocking all Streamlit calls and the underlying services.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

# Pre-load mock streamlit + pandas so the dashboard module can import cleanly
_mock_st = MagicMock()
_mock_pd = MagicMock()
sys.modules.setdefault("streamlit", _mock_st)

# Now import the dashboard module directly (bypassing __init__.__getattr__)
from enhanced_agent_bus.deliberation_layer import dashboard as dash_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_queue_status(items=None, stats=None):
    return {
        "queue_size": len(items or []),
        "processing_count": 0,
        "items": items or [],
        "stats": stats
        or {
            "deliberation_count": 10,
            "deliberation_approved": 7,
            "avg_processing_time": 2.5,
        },
    }


def _make_item(item_id="item-1", status="pending"):
    return {
        "item_id": item_id,
        "status": status,
    }


def _make_item_details(item_id="item-1"):
    return {
        "item_id": item_id,
        "message_id": "msg-12345678-abcd",
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "message": {
            "content": {"text": "test content"},
            "message_type": "governance",
            "from_agent": "agent-a",
            "to_agent": "agent-b",
            "priority": "high",
        },
        "impact_score": 0.85,
        "votes": [],
    }


def _fresh_st():
    """Return a fresh MagicMock to use as the st module."""
    return MagicMock()


# ---------------------------------------------------------------------------
# show_pending_reviews
# ---------------------------------------------------------------------------


class TestShowPendingReviews:
    def test_no_pending_items_shows_success(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            queue = MagicMock()
            queue.get_queue_status.return_value = _make_queue_status(items=[])
            dash_mod.show_pending_reviews(queue, MagicMock())
            mock_st.success.assert_called_once()

    def test_pending_items_displayed(self):
        mock_st = _fresh_st()
        items = [_make_item("i1", "pending"), _make_item("i2", "under_review")]
        with patch.object(dash_mod, "st", mock_st):
            # expander context manager
            mock_st.expander.return_value.__enter__ = MagicMock()
            mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)

            # columns is called with [2,1] (2 cols) and later with 3 (3 cols)
            # Return enough mocks for any call
            def make_cols(spec):
                n = spec if isinstance(spec, int) else len(spec)
                cols = []
                for _ in range(n):
                    c = MagicMock()
                    c.__enter__ = MagicMock(return_value=c)
                    c.__exit__ = MagicMock(return_value=False)
                    cols.append(c)
                return cols

            mock_st.columns.side_effect = make_cols

            # tabs for show_item_details
            tab_mocks = [MagicMock() for _ in range(4)]
            for t in tab_mocks:
                t.__enter__ = MagicMock(return_value=t)
                t.__exit__ = MagicMock(return_value=False)
            mock_st.tabs.return_value = tab_mocks

            # Defaults for show_review_actions (called internally)
            mock_st.radio.return_value = "Approve"
            mock_st.text_area.return_value = ""
            mock_st.text_input.return_value = ""
            mock_st.button.return_value = False

            queue = MagicMock()
            queue.get_queue_status.return_value = _make_queue_status(items=items)
            queue.get_item_details.return_value = _make_item_details()

            dash_mod.show_pending_reviews(queue, MagicMock())
            mock_st.info.assert_called_once()
            assert "2" in mock_st.info.call_args[0][0]

    def test_non_pending_items_filtered(self):
        mock_st = _fresh_st()
        items = [_make_item("i1", "approved"), _make_item("i2", "rejected")]
        with patch.object(dash_mod, "st", mock_st):
            queue = MagicMock()
            queue.get_queue_status.return_value = _make_queue_status(items=items)
            dash_mod.show_pending_reviews(queue, MagicMock())
            mock_st.success.assert_called_once()


# ---------------------------------------------------------------------------
# show_item_details
# ---------------------------------------------------------------------------


class TestShowItemDetails:
    def test_item_not_found(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            queue = MagicMock()
            queue.get_item_details.return_value = None
            dash_mod.show_item_details(_make_item(), MagicMock(), queue)
            mock_st.error.assert_called_once()

    def test_item_found_renders_details(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            queue = MagicMock()
            queue.get_item_details.return_value = _make_item_details()

            tab_mocks = [MagicMock() for _ in range(4)]
            for t in tab_mocks:
                t.__enter__ = MagicMock(return_value=t)
                t.__exit__ = MagicMock(return_value=False)
            mock_st.tabs.return_value = tab_mocks

            col_mocks = [MagicMock() for _ in range(3)]
            for c in col_mocks:
                c.__enter__ = MagicMock(return_value=c)
                c.__exit__ = MagicMock(return_value=False)
            mock_st.columns.return_value = col_mocks

            dash_mod.show_item_details(_make_item(), MagicMock(), queue)
            mock_st.subheader.assert_called()


# ---------------------------------------------------------------------------
# show_review_actions
# ---------------------------------------------------------------------------


class TestShowReviewActions:
    def test_submit_without_reasoning_shows_error(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            mock_st.radio.return_value = "Approve"
            mock_st.text_area.return_value = ""
            mock_st.text_input.return_value = "reviewer-1"
            mock_st.button.return_value = True

            dash_mod.show_review_actions("item-1", MagicMock())
            mock_st.error.assert_called()

    def test_submit_without_reviewer_shows_error(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            mock_st.radio.return_value = "Approve"
            mock_st.text_area.return_value = "good reasoning"
            mock_st.text_input.return_value = ""
            mock_st.button.return_value = True

            dash_mod.show_review_actions("item-1", MagicMock())
            mock_st.error.assert_called()

    def test_successful_submit(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            mock_st.radio.return_value = "Approve"
            mock_st.text_area.return_value = "looks good"
            mock_st.text_input.return_value = "reviewer-1"
            mock_st.button.return_value = True

            queue = MagicMock()
            queue.submit_human_decision.return_value = True

            dash_mod.show_review_actions("item-1", queue)

            queue.submit_human_decision.assert_called_once_with(
                item_id="item-1",
                reviewer="reviewer-1",
                decision="approved",
                reasoning="looks good",
            )
            mock_st.success.assert_called()

    def test_failed_submit(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            mock_st.radio.return_value = "Reject"
            mock_st.text_area.return_value = "bad"
            mock_st.text_input.return_value = "rev"
            mock_st.button.return_value = True

            queue = MagicMock()
            queue.submit_human_decision.return_value = False

            dash_mod.show_review_actions("item-1", queue)
            mock_st.error.assert_called()


# ---------------------------------------------------------------------------
# show_queue_status
# ---------------------------------------------------------------------------


class TestShowQueueStatus:
    def test_renders_metrics(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st), patch.object(dash_mod, "pd", MagicMock()):
            col_mocks = [MagicMock() for _ in range(4)]
            for c in col_mocks:
                c.__enter__ = MagicMock(return_value=c)
                c.__exit__ = MagicMock(return_value=False)
            mock_st.columns.return_value = col_mocks

            queue = MagicMock()
            queue.get_queue_status.return_value = _make_queue_status(
                items=[_make_item()],
            )

            dash_mod.show_queue_status(queue)
            mock_st.header.assert_called_once()


# ---------------------------------------------------------------------------
# show_analytics
# ---------------------------------------------------------------------------


class TestShowAnalytics:
    def test_renders_router_stats(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st), patch.object(dash_mod, "pd", MagicMock()):
            router = MagicMock()
            router.get_routing_stats.return_value = {
                "total_messages": 100,
                "fast_lane_percentage": 0.7,
                "deliberation_percentage": 0.3,
                "fast_lane_count": 70,
                "deliberation_count": 30,
                "learning_enabled": True,
                "current_threshold": 0.75,
                "history_size": 500,
            }

            col_mocks = [MagicMock() for _ in range(3)]
            for c in col_mocks:
                c.__enter__ = MagicMock(return_value=c)
                c.__exit__ = MagicMock(return_value=False)
            mock_st.columns.return_value = col_mocks

            dash_mod.show_analytics(router, MagicMock())
            mock_st.header.assert_called_once()


# ---------------------------------------------------------------------------
# show_settings
# ---------------------------------------------------------------------------


class TestShowSettings:
    def test_renders_settings(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            router = MagicMock()
            router.impact_threshold = 0.8
            router.enable_learning = True
            mock_st.slider.return_value = 0.8
            mock_st.checkbox.return_value = True

            dash_mod.show_settings(router)
            mock_st.header.assert_called_once()

    def test_threshold_change_shows_button(self):
        mock_st = _fresh_st()
        with patch.object(dash_mod, "st", mock_st):
            router = MagicMock()
            router.impact_threshold = 0.8
            router.enable_learning = False
            mock_st.slider.return_value = 0.5
            mock_st.checkbox.return_value = False
            mock_st.button.return_value = True

            dash_mod.show_settings(router)
            router.set_impact_threshold.assert_called_once_with(0.5)


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_pending_reviews(self):
        mock_st = _fresh_st()
        with (
            patch.object(dash_mod, "st", mock_st),
            patch.object(dash_mod, "get_deliberation_queue") as mock_q_fn,
            patch.object(dash_mod, "get_llm_assistant") as mock_llm_fn,
            patch.object(dash_mod, "get_adaptive_router") as mock_router_fn,
        ):
            mock_st.sidebar.selectbox.return_value = "Pending Reviews"
            queue = MagicMock()
            queue.get_queue_status.return_value = _make_queue_status()
            mock_q_fn.return_value = queue
            mock_llm_fn.return_value = MagicMock()
            mock_router_fn.return_value = MagicMock()

            dash_mod.main()
            mock_st.set_page_config.assert_called_once()
            mock_st.title.assert_called_once()
