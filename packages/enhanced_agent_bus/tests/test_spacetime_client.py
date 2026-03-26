"""
Tests for SpacetimeDB Real-Time Governance Client.

All tests mock the spacetimedb_sdk dependency.
Validates client logic, event dispatch, MACI role handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def mock_sdk():
    """Mock spacetimedb_sdk module."""
    mock_client_cls = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.connect = AsyncMock()
    mock_client_instance.disconnect = AsyncMock()
    mock_client_instance.call_reducer = AsyncMock()
    mock_client_instance.on_connect = MagicMock()
    mock_client_instance.on_disconnect = MagicMock()
    mock_client_instance.on_error = MagicMock()
    mock_client_instance.on_row_update = MagicMock()
    mock_client_instance.subscribe = MagicMock()
    mock_client_cls.return_value = mock_client_instance

    mock_identity = MagicMock()

    return mock_client_cls, mock_client_instance, mock_identity


@pytest.fixture()
def _patch_sdk(mock_sdk):
    """Patch spacetimedb_sdk in the spacetime_client module."""
    mock_cls, mock_inst, mock_id = mock_sdk
    with (
        patch(
            "enhanced_agent_bus.persistence.spacetime_client.HAS_SPACETIMEDB",
            True,
        ),
        patch(
            "enhanced_agent_bus.persistence.spacetime_client.SpacetimeDBClient",
            mock_cls,
        ),
        patch(
            "enhanced_agent_bus.persistence.spacetime_client.Identity",
            mock_id,
        ),
    ):
        yield mock_cls, mock_inst, mock_id


class TestGovernanceStateClient:
    """Tests for the SpacetimeDB governance client."""

    @pytest.mark.usefixtures("_patch_sdk")
    def test_construction(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceStateClient,
            SpacetimeConfig,
        )

        config = SpacetimeConfig(host="http://localhost:3000")
        client = GovernanceStateClient(config=config)

        assert not client.is_connected
        assert client.identity is None
        assert client.stats["events_received"] == 0

    def test_construction_without_sdk_raises(self):
        with patch(
            "enhanced_agent_bus.persistence.spacetime_client.HAS_SPACETIMEDB",
            False,
        ):
            from enhanced_agent_bus.persistence.spacetime_client import (
                GovernanceStateClient,
            )

            with pytest.raises(RuntimeError, match="spacetimedb-sdk is not installed"):
                GovernanceStateClient()

    @pytest.mark.usefixtures("_patch_sdk")
    @pytest.mark.asyncio()
    async def test_connect(self, mock_sdk):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceStateClient,
        )

        _, mock_inst, _ = mock_sdk
        client = GovernanceStateClient()
        await client.connect()

        mock_inst.on_connect.assert_called_once()
        mock_inst.on_disconnect.assert_called_once()
        mock_inst.on_error.assert_called_once()
        assert mock_inst.on_row_update.call_count == 3  # 3 tables
        mock_inst.connect.assert_awaited_once()

    @pytest.mark.usefixtures("_patch_sdk")
    @pytest.mark.asyncio()
    async def test_propose_action_when_not_connected_raises(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceStateClient,
        )

        client = GovernanceStateClient()

        with pytest.raises(RuntimeError, match="Not connected"):
            await client.propose_action("t1", "hash", "reason", [1])

    @pytest.mark.usefixtures("_patch_sdk")
    def test_event_callback_registration(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceEventType,
            GovernanceStateClient,
        )

        client = GovernanceStateClient()
        callback = MagicMock()

        client.on(GovernanceEventType.DECISION_VALIDATED, callback)
        client.off(GovernanceEventType.DECISION_VALIDATED, callback)

        # After removing, callbacks list should be empty
        assert callback not in client._callbacks.get(GovernanceEventType.DECISION_VALIDATED, [])

    @pytest.mark.usefixtures("_patch_sdk")
    def test_decision_event_dispatch(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceEventType,
            GovernanceStateClient,
        )

        client = GovernanceStateClient()
        callback = MagicMock()
        client.on(GovernanceEventType.DECISION_CREATED, callback)

        # Simulate a new decision row
        client._on_decision_update(None, MagicMock(verdict="pending"))

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.event_type == GovernanceEventType.DECISION_CREATED
        assert event.table_name == "governance_decision"
        assert client.stats["events_received"] == 1

    @pytest.mark.usefixtures("_patch_sdk")
    def test_principle_amendment_event(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceEventType,
            GovernanceStateClient,
        )

        client = GovernanceStateClient()
        callback = MagicMock()
        client.on(GovernanceEventType.PRINCIPLE_AMENDED, callback)

        # Simulate amendment (old exists, new exists)
        client._on_principle_update(
            MagicMock(active=True),
            MagicMock(active=False),
        )

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.event_type == GovernanceEventType.PRINCIPLE_AMENDED

    @pytest.mark.usefixtures("_patch_sdk")
    def test_callback_error_does_not_propagate(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceEventType,
            GovernanceStateClient,
        )

        client = GovernanceStateClient()

        def bad_callback(_event):
            raise ValueError("boom")

        client.on(GovernanceEventType.ROLE_BINDING_CHANGED, bad_callback)

        # Should not raise
        client._on_role_update(None, MagicMock())
        assert client.stats["events_received"] == 1

    @pytest.mark.usefixtures("_patch_sdk")
    def test_row_to_dict(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceStateClient,
        )

        assert GovernanceStateClient._row_to_dict(None) is None

        row = MagicMock()
        row.__dict__ = {"id": 1, "name": "test", "_private": "hidden"}
        result = GovernanceStateClient._row_to_dict(row)
        assert result == {"id": 1, "name": "test"}


class TestGovernanceEventType:
    """Test the event type enum."""

    def test_event_types_exist(self):
        from enhanced_agent_bus.persistence.spacetime_client import (
            GovernanceEventType,
        )

        assert GovernanceEventType.DECISION_CREATED.value == "decision_created"
        assert GovernanceEventType.DECISION_VALIDATED.value == "decision_validated"
        assert GovernanceEventType.PRINCIPLE_AMENDED.value == "principle_amended"
        assert GovernanceEventType.PRINCIPLE_CREATED.value == "principle_created"
        assert GovernanceEventType.ROLE_BINDING_CHANGED.value == "role_binding_changed"
