# Constitutional Hash: 608508a9bd224290
# Sprint 61 — mcp_server/adapters/policy_client.py coverage
"""
Comprehensive tests for mcp_server/adapters/policy_client.py.
Targets >=95% coverage of all classes, methods, and branches.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.mcp_server.adapters.policy_client import (
    POLICY_CLIENT_OPERATION_ERRORS,
    PolicyClientAdapter,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

pytestmark = [pytest.mark.unit, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_policy_client_operation_errors_is_tuple(self):
        assert isinstance(POLICY_CLIENT_OPERATION_ERRORS, tuple)

    def test_policy_client_operation_errors_contains_expected_exceptions(self):
        expected = {AttributeError, OSError, RuntimeError, TimeoutError, TypeError, ValueError}
        assert set(POLICY_CLIENT_OPERATION_ERRORS) == expected


# ---------------------------------------------------------------------------
# PolicyClientAdapter.__init__
# ---------------------------------------------------------------------------


class TestPolicyClientAdapterInit:
    def test_default_init_no_client(self):
        adapter = PolicyClientAdapter()
        assert adapter.policy_client is None
        assert adapter._request_count == 0

    def test_init_with_policy_client(self):
        mock_client = MagicMock()
        adapter = PolicyClientAdapter(policy_client=mock_client)
        assert adapter.policy_client is mock_client
        assert adapter._request_count == 0

    def test_init_with_explicit_none(self):
        adapter = PolicyClientAdapter(policy_client=None)
        assert adapter.policy_client is None

    def test_constitutional_hash_class_attribute(self):
        adapter = PolicyClientAdapter()
        assert adapter.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# PolicyClientAdapter.get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_metrics_no_client(self):
        adapter = PolicyClientAdapter()
        metrics = adapter.get_metrics()
        assert metrics["request_count"] == 0
        assert metrics["connected"] is False
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_metrics_with_client(self):
        adapter = PolicyClientAdapter(policy_client=MagicMock())
        metrics = adapter.get_metrics()
        assert metrics["connected"] is True

    def test_metrics_request_count_increments(self):
        adapter = PolicyClientAdapter()
        # Manually bump the internal counter without going async
        adapter._request_count = 5
        assert adapter.get_metrics()["request_count"] == 5


# ---------------------------------------------------------------------------
# PolicyClientAdapter._get_default_principles  (sync helper)
# ---------------------------------------------------------------------------


class TestGetDefaultPrinciples:
    def setup_method(self):
        self.adapter = PolicyClientAdapter()

    def test_returns_all_principles_no_filter(self):
        principles = self.adapter._get_default_principles(None, None, False, None)
        assert len(principles) == 8

    def test_filter_by_category_core(self):
        principles = self.adapter._get_default_principles("core", None, False, None)
        assert all(p["category"] == "core" for p in principles)
        assert len(principles) == 2  # beneficence, autonomy

    def test_filter_by_category_safety(self):
        principles = self.adapter._get_default_principles("safety", None, False, None)
        assert all(p["category"] == "safety" for p in principles)
        assert len(principles) == 2  # non_maleficence, safety

    def test_filter_by_category_privacy(self):
        principles = self.adapter._get_default_principles("privacy", None, False, None)
        assert len(principles) == 1
        assert principles[0]["name"] == "privacy"

    def test_filter_by_category_fairness(self):
        principles = self.adapter._get_default_principles("fairness", None, False, None)
        assert len(principles) == 1
        assert principles[0]["name"] == "justice"

    def test_filter_by_category_transparency(self):
        principles = self.adapter._get_default_principles("transparency", None, False, None)
        assert len(principles) == 1
        assert principles[0]["name"] == "transparency"

    def test_filter_by_category_governance(self):
        principles = self.adapter._get_default_principles("governance", None, False, None)
        assert len(principles) == 1
        assert principles[0]["name"] == "accountability"

    def test_filter_by_category_nonexistent(self):
        principles = self.adapter._get_default_principles("nonexistent_cat", None, False, None)
        assert principles == []

    def test_filter_by_enforcement_level_strict(self):
        principles = self.adapter._get_default_principles(None, "strict", False, None)
        assert all(p["enforcement_level"] == "strict" for p in principles)

    def test_filter_by_enforcement_level_moderate(self):
        principles = self.adapter._get_default_principles(None, "moderate", False, None)
        assert all(p["enforcement_level"] == "moderate" for p in principles)
        assert len(principles) == 1
        assert principles[0]["name"] == "transparency"

    def test_filter_by_enforcement_level_nonexistent(self):
        principles = self.adapter._get_default_principles(None, "nonexistent", False, None)
        assert principles == []

    def test_include_inactive_false_keeps_active(self):
        # All defaults are active=True, so result should be same as full list
        principles = self.adapter._get_default_principles(None, None, False, None)
        assert all(p.get("active", True) for p in principles)
        assert len(principles) == 8

    def test_include_inactive_true_returns_all(self):
        # All default principles are active; with include_inactive=True the same 8 are returned
        principles = self.adapter._get_default_principles(None, None, True, None)
        assert len(principles) == 8

    def test_filter_by_principle_ids(self):
        principles = self.adapter._get_default_principles(None, None, False, ["P001", "P003"])
        ids = [p["id"] for p in principles]
        assert set(ids) == {"P001", "P003"}

    def test_filter_by_principle_ids_nonexistent(self):
        principles = self.adapter._get_default_principles(None, None, False, ["PXXX"])
        assert principles == []

    def test_combined_filters_category_and_enforcement(self):
        principles = self.adapter._get_default_principles("safety", "strict", False, None)
        assert all(
            p["category"] == "safety" and p["enforcement_level"] == "strict" for p in principles
        )

    def test_combined_filters_category_and_ids(self):
        principles = self.adapter._get_default_principles("core", None, False, ["P001"])
        assert len(principles) == 1
        assert principles[0]["id"] == "P001"

    def test_all_filters_combined(self):
        principles = self.adapter._get_default_principles("core", "strict", False, ["P001"])
        assert len(principles) == 1

    def test_principle_structure(self):
        principles = self.adapter._get_default_principles(None, None, False, None)
        required_keys = {
            "id",
            "name",
            "category",
            "description",
            "enforcement_level",
            "version",
            "active",
            "precedence",
        }
        for p in principles:
            assert required_keys.issubset(p.keys())


# ---------------------------------------------------------------------------
# PolicyClientAdapter.get_active_principles  (async, no client)
# ---------------------------------------------------------------------------


class TestGetActivePrinciplesNoClient:
    async def test_increments_request_count(self):
        adapter = PolicyClientAdapter()
        await adapter.get_active_principles()
        assert adapter._request_count == 1

    async def test_multiple_calls_increment_count(self):
        adapter = PolicyClientAdapter()
        await adapter.get_active_principles()
        await adapter.get_active_principles()
        assert adapter._request_count == 2

    async def test_returns_default_principles_when_no_client(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_active_principles()
        assert len(result) == 8

    async def test_category_filter_passed_through(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_active_principles(category="core")
        assert all(p["category"] == "core" for p in result)

    async def test_enforcement_level_filter_passed_through(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_active_principles(enforcement_level="moderate")
        assert len(result) == 1

    async def test_include_inactive_passed_through(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_active_principles(include_inactive=True)
        assert len(result) == 8

    async def test_principle_ids_filter_passed_through(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_active_principles(principle_ids=["P001"])
        assert len(result) == 1
        assert result[0]["id"] == "P001"

    async def test_principle_ids_empty_list_returns_all(self):
        # The source checks `if principle_ids:` — an empty list is falsy,
        # so no filtering is applied and all defaults are returned.
        adapter = PolicyClientAdapter()
        result = await adapter.get_active_principles(principle_ids=[])
        assert len(result) == 8


# ---------------------------------------------------------------------------
# PolicyClientAdapter.get_active_principles  (async, with client)
# ---------------------------------------------------------------------------


class TestGetActivePrinciplesWithClient:
    async def test_calls_policy_client_get_principles(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(
            return_value=[
                {"id": "P001", "name": "beneficence"},
            ]
        )
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_active_principles()

        mock_client.get_principles.assert_awaited_once_with(
            category=None,
            enforcement_level=None,
            include_inactive=False,
        )
        assert result == [{"id": "P001", "name": "beneficence"}]

    async def test_passes_filters_to_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(return_value=[])
        adapter = PolicyClientAdapter(policy_client=mock_client)

        await adapter.get_active_principles(
            category="core",
            enforcement_level="strict",
            include_inactive=True,
        )

        mock_client.get_principles.assert_awaited_once_with(
            category="core",
            enforcement_level="strict",
            include_inactive=True,
        )

    async def test_principle_ids_filter_applied_after_client_call(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(
            return_value=[
                {"id": "P001", "name": "beneficence"},
                {"id": "P002", "name": "non_maleficence"},
            ]
        )
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_active_principles(principle_ids=["P001"])
        assert len(result) == 1
        assert result[0]["id"] == "P001"

    async def test_principle_ids_none_returns_all_from_client(self):
        mock_client = MagicMock()
        principles = [{"id": f"P{i:03d}", "name": f"p{i}"} for i in range(3)]
        mock_client.get_principles = AsyncMock(return_value=principles)
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_active_principles(principle_ids=None)
        assert result == principles

    async def test_increments_request_count_with_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(return_value=[])
        adapter = PolicyClientAdapter(policy_client=mock_client)

        await adapter.get_active_principles()
        assert adapter._request_count == 1

    async def test_raises_attribute_error_from_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(side_effect=AttributeError("attr error"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with pytest.raises(AttributeError):
            await adapter.get_active_principles()

    async def test_raises_runtime_error_from_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(side_effect=RuntimeError("runtime"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with pytest.raises(RuntimeError):
            await adapter.get_active_principles()

    async def test_raises_timeout_error_from_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(side_effect=TimeoutError("timeout"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with pytest.raises(TimeoutError):
            await adapter.get_active_principles()

    async def test_raises_value_error_from_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(side_effect=ValueError("bad value"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with pytest.raises(ValueError):
            await adapter.get_active_principles()

    async def test_raises_type_error_from_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(side_effect=TypeError("type err"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with pytest.raises(TypeError):
            await adapter.get_active_principles()

    async def test_raises_os_error_from_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(side_effect=OSError("os err"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with pytest.raises(OSError):
            await adapter.get_active_principles()

    async def test_error_is_logged_on_exception(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(side_effect=RuntimeError("boom"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with patch("enhanced_agent_bus.mcp_server.adapters.policy_client.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await adapter.get_active_principles()
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            assert "Policy client error" in call_args


# ---------------------------------------------------------------------------
# PolicyClientAdapter.get_policy_by_name  (async, no client)
# ---------------------------------------------------------------------------


class TestGetPolicyByNameNoClient:
    async def test_returns_none_for_unknown_name(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("nonexistent_policy")
        assert result is None

    async def test_returns_principle_for_known_name(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("beneficence")
        assert result is not None
        assert result["name"] == "beneficence"

    async def test_returns_non_maleficence(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("non_maleficence")
        assert result is not None
        assert result["id"] == "P002"

    async def test_returns_autonomy(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("autonomy")
        assert result is not None

    async def test_returns_justice(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("justice")
        assert result is not None

    async def test_returns_transparency(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("transparency")
        assert result is not None

    async def test_returns_accountability(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("accountability")
        assert result is not None

    async def test_returns_privacy(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("privacy")
        assert result is not None

    async def test_returns_safety(self):
        adapter = PolicyClientAdapter()
        result = await adapter.get_policy_by_name("safety")
        assert result is not None

    async def test_increments_request_count(self):
        adapter = PolicyClientAdapter()
        await adapter.get_policy_by_name("beneficence")
        assert adapter._request_count == 1


# ---------------------------------------------------------------------------
# PolicyClientAdapter.get_policy_by_name  (async, with client)
# ---------------------------------------------------------------------------


class TestGetPolicyByNameWithClient:
    async def test_calls_policy_client_get_policy(self):
        mock_client = MagicMock()
        expected = {"id": "P001", "name": "beneficence"}
        mock_client.get_policy = AsyncMock(return_value=expected)
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("beneficence")

        mock_client.get_policy.assert_awaited_once_with("beneficence")
        assert result == expected

    async def test_increments_request_count_with_client(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(return_value={})
        adapter = PolicyClientAdapter(policy_client=mock_client)

        await adapter.get_policy_by_name("some_policy")
        assert adapter._request_count == 1

    async def test_returns_none_on_attribute_error(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(side_effect=AttributeError("no attr"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("test")
        assert result is None

    async def test_returns_none_on_runtime_error(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(side_effect=RuntimeError("fail"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("test")
        assert result is None

    async def test_returns_none_on_timeout_error(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(side_effect=TimeoutError("timeout"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("test")
        assert result is None

    async def test_returns_none_on_value_error(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(side_effect=ValueError("bad"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("test")
        assert result is None

    async def test_returns_none_on_type_error(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(side_effect=TypeError("type"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("test")
        assert result is None

    async def test_returns_none_on_os_error(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(side_effect=OSError("os"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("test")
        assert result is None

    async def test_error_is_logged_on_exception(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(side_effect=RuntimeError("boom"))
        adapter = PolicyClientAdapter(policy_client=mock_client)

        with patch("enhanced_agent_bus.mcp_server.adapters.policy_client.logger") as mock_logger:
            result = await adapter.get_policy_by_name("my_policy")
            assert result is None
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            assert "my_policy" in call_args

    async def test_returns_none_on_client_returning_none(self):
        mock_client = MagicMock()
        mock_client.get_policy = AsyncMock(return_value=None)
        adapter = PolicyClientAdapter(policy_client=mock_client)

        result = await adapter.get_policy_by_name("unknown")
        assert result is None


# ---------------------------------------------------------------------------
# Integration-style: combined operations
# ---------------------------------------------------------------------------


class TestCombinedOperations:
    async def test_request_count_across_mixed_calls(self):
        adapter = PolicyClientAdapter()
        await adapter.get_active_principles()
        await adapter.get_policy_by_name("beneficence")
        await adapter.get_active_principles(category="core")
        assert adapter._request_count == 3
        assert adapter.get_metrics()["request_count"] == 3

    async def test_metrics_reflect_connected_false_initially(self):
        adapter = PolicyClientAdapter()
        metrics = adapter.get_metrics()
        assert not metrics["connected"]

    async def test_metrics_reflect_connected_true_with_client(self):
        mock_client = MagicMock()
        mock_client.get_principles = AsyncMock(return_value=[])
        adapter = PolicyClientAdapter(policy_client=mock_client)
        await adapter.get_active_principles()
        assert adapter.get_metrics()["connected"] is True
