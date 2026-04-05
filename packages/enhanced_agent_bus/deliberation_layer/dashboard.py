"""Constitutional Hash: 608508a9bd224290
ACGS-2 Deliberation Layer - Human Approval Dashboard
Streamlit-based UI for human-in-the-loop approval of high-risk decisions.
"""

from datetime import UTC, datetime, timezone

import pandas as pd
import streamlit as st

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .adaptive_router import get_adaptive_router

# Import deliberation components
from .deliberation_queue import get_deliberation_queue
from .llm_assistant import get_llm_assistant


def main():
    """Main dashboard function."""
    st.set_page_config(page_title="ACGS-2 Deliberation Dashboard", page_icon="⚖️", layout="wide")

    st.title("⚖️ ACGS-2 Deliberation Dashboard")
    st.markdown("Human-in-the-loop approval for high-risk agent decisions")

    # Initialize components
    deliberation_queue = get_deliberation_queue()
    llm_assistant = get_llm_assistant()
    adaptive_router = get_adaptive_router()

    # Sidebar for navigation
    page = st.sidebar.selectbox(
        "Navigation", ["Pending Reviews", "Queue Status", "Analytics", "Settings"]
    )

    if page == "Pending Reviews":
        show_pending_reviews(deliberation_queue, llm_assistant)
    elif page == "Queue Status":
        show_queue_status(deliberation_queue)
    elif page == "Analytics":
        show_analytics(adaptive_router, deliberation_queue)
    elif page == "Settings":
        show_settings(adaptive_router)


def show_pending_reviews(deliberation_queue, llm_assistant):
    """Show pending items for human review."""
    st.header("Pending Reviews")

    # Get queue status
    queue_status = deliberation_queue.get_queue_status()
    pending_items = [
        item
        for item in queue_status["items"]
        if item["status"] == "pending" or item["status"] == "under_review"
    ]

    if not pending_items:
        st.success("No items pending review! 🎉")
        return

    st.info(f"{len(pending_items)} items awaiting review")

    # Display items
    for item in pending_items:
        with st.expander(
            f"Item {item['item_id']} - {item['status'].replace('_', ' ').title()}", expanded=True
        ):
            col1, col2 = st.columns([2, 1])

            with col1:
                show_item_details(item, llm_assistant, deliberation_queue)

            with col2:
                show_review_actions(item["item_id"], deliberation_queue)


def show_item_details(item: JSONDict, _llm_assistant, deliberation_queue):
    """Show detailed information about a deliberation item."""
    item_details = deliberation_queue.get_item_details(item["item_id"])

    if not item_details:
        st.error("Item details not found")
        return

    # Basic info
    st.subheader("Message Information")
    info_cols = st.columns(3)
    with info_cols[0]:
        st.metric("Message ID", item_details["message_id"][:8] + "...")
    with info_cols[1]:
        st.metric("Status", item_details["status"].replace("_", " ").title())
    with info_cols[2]:
        created = datetime.fromisoformat(item_details["created_at"])
        st.metric("Age", f"{(datetime.now(UTC) - created).seconds}s ago")

    # Message content
    st.subheader("Message Content")
    message_info = item_details.get("message", {})

    content_tabs = st.tabs(["Content", "Technical Details", "Votes", "LLM Analysis"])

    with content_tabs[0]:
        if "content" in message_info:
            st.json(message_info["content"])
        else:
            st.write("No content available")

    with content_tabs[1]:
        tech_info = {
            "message_type": message_info.get("message_type"),
            "from_agent": message_info.get("from_agent"),
            "to_agent": message_info.get("to_agent"),
            "priority": message_info.get("priority"),
            "impact_score": item_details.get("impact_score"),
        }
        st.json(tech_info)

    with content_tabs[2]:
        votes = item_details.get("votes", [])
        if votes:
            votes_df = pd.DataFrame(votes)
            st.dataframe(votes_df)
        else:
            st.write("No votes recorded yet")

    with content_tabs[3]:
        if st.button("Generate LLM Analysis", key=f"llm_{item['item_id']}"):
            with st.spinner("Analyzing with LLM..."):
                # This would need the actual message object
                # For demo, show placeholder
                analysis = {
                    "risk_level": "medium",
                    "reasoning": ["Automated analysis placeholder"],
                    "recommendation": "review",
                }
                st.json(analysis)


def show_review_actions(item_id: str, deliberation_queue):
    """Show action buttons for reviewing an item."""
    st.subheader("Review Actions")

    # Decision buttons
    decision = st.radio("Decision", ["Approve", "Reject", "Escalate"], key=f"decision_{item_id}")

    # Reasoning input
    reasoning = st.text_area(
        "Reasoning (required)",
        height=100,
        key=f"reasoning_{item_id}",
        placeholder="Explain your decision...",
    )

    # Reviewer info
    reviewer = st.text_input(
        "Your Name/ID", key=f"reviewer_{item_id}", placeholder="Enter your identifier"
    )

    # Submit button
    if st.button("Submit Decision", key=f"submit_{item_id}", type="primary"):
        if not reasoning.strip():
            st.error("Please provide reasoning for your decision")
            return

        if not reviewer.strip():
            st.error("Please enter your name/ID")
            return

        # Submit decision
        decision_map = {"Approve": "approved", "Reject": "rejected", "Escalate": "escalate"}

        success = deliberation_queue.submit_human_decision(
            item_id=item_id, reviewer=reviewer, decision=decision_map[decision], reasoning=reasoning
        )

        if success:
            st.success(f"Decision submitted: {decision}")
            st.rerun()  # Refresh the page
        else:
            st.error("Failed to submit decision")


def show_queue_status(deliberation_queue):
    """Show overall queue status and statistics."""
    st.header("Queue Status")

    status = deliberation_queue.get_queue_status()
    stats = status["stats"]

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Queue Size", status["queue_size"])

    with col2:
        st.metric("Processing", status["processing_count"])

    with col3:
        approval_rate = stats["deliberation_approved"] / max(stats["deliberation_count"], 1)
        st.metric("Approval Rate", f"{approval_rate:.1%}")

    with col4:
        avg_time = stats.get("avg_processing_time", 0)
        st.metric("Avg Processing Time", f"{avg_time:.1f}s")

    # Detailed stats
    st.subheader("Detailed Statistics")
    stats_df = pd.DataFrame([stats])
    st.dataframe(stats_df.T, use_container_width=True)

    # Current items
    st.subheader("Current Queue Items")
    if status["items"]:
        items_df = pd.DataFrame(status["items"])
        st.dataframe(items_df, use_container_width=True)
    else:
        st.info("Queue is empty")


def show_analytics(adaptive_router, _deliberation_queue):
    """Show analytics and performance metrics."""
    st.header("Analytics & Performance")

    # Router stats
    router_stats = adaptive_router.get_routing_stats()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Messages", router_stats.get("total_messages", 0))

    with col2:
        fast_lane_pct = router_stats.get("fast_lane_percentage", 0)
        st.metric("Fast Lane %", f"{fast_lane_pct:.1%}")

    with col3:
        deliberation_pct = router_stats.get("deliberation_percentage", 0)
        st.metric("Deliberation %", f"{deliberation_pct:.1%}")

    # Performance chart
    st.subheader("Routing Distribution")
    routing_data = pd.DataFrame(
        {
            "type": ["Fast Lane", "Deliberation"],
            "Count": [
                router_stats.get("fast_lane_count", 0),
                router_stats.get("deliberation_count", 0),
            ],
        }
    )

    st.bar_chart(routing_data.set_index("type"))

    # Learning status
    st.subheader("Adaptive Learning")
    learning_enabled = router_stats.get("learning_enabled", False)
    st.info(f"Learning: {'Enabled' if learning_enabled else 'Disabled'}")

    if learning_enabled:
        threshold = router_stats.get("current_threshold", 0.8)
        st.metric("Current Threshold", f"{threshold:.3f}")

        history_size = router_stats.get("history_size", 0)
        st.metric("History Size", history_size)


def show_settings(adaptive_router):
    """Show settings and configuration options."""
    st.header("Settings")

    st.subheader("Impact Threshold")
    current_threshold = adaptive_router.impact_threshold

    new_threshold = st.slider(
        "Impact Threshold",
        min_value=0.0,
        max_value=1.0,
        value=current_threshold,
        step=0.05,
        help="Messages with impact score above this threshold go to deliberation",
    )

    if new_threshold != current_threshold:
        if st.button("Update Threshold"):
            adaptive_router.set_impact_threshold(new_threshold)
            st.success(f"Threshold updated to {new_threshold:.3f}")
            st.rerun()

    st.subheader("Learning Configuration")
    learning_enabled = st.checkbox(
        "Enable Adaptive Learning", value=adaptive_router.enable_learning
    )

    if learning_enabled != adaptive_router.enable_learning:
        st.info("Learning setting will be applied on next restart")

    # System info
    st.subheader("System Information")
    st.json(
        {
            "version": "ACGS-2 Deliberation Layer v1.0",
            "components": [
                "Impact Scorer",
                "Adaptive Router",
                "Deliberation Queue",
                "LLM Assistant",
            ],
            "status": "operational",
        }
    )


if __name__ == "__main__":
    main()
