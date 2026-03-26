"""Tests for opa_client/health.py — OPAClientHealthMixin."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.opa_client.health import OPAClientHealthMixin

# ---------------------------------------------------------------------------
# Concrete test host that provides the attrs the mixin expects
# ---------------------------------------------------------------------------


class _FakeOPAClient(OPAClientHealthMixin):
    """Minimal host satisfying the mixin's self.* assumptions."""

    def __init__(self, mode: str = "http", opa_url: str = "http://localhost:8181") -> None:
        self.mode = mode
        self.opa_url = opa_url
        self._http_client: MagicMock | None = MagicMock()
        self._multipath_evaluation_count = 0
        self._multipath_last_path_count = 0
        self._multipath_last_diversity_ratio = 0.0
        self._multipath_last_support_family_count = 0

    async def evaluate_policy(self, input_data: dict, policy_path: str = "") -> dict:
        return {"allowed": True, "reason": "ok", "result": True, "metadata": {}}

    def _handle_evaluation_error(self, error: Exception, policy_path: str) -> dict:
        return {"allowed": False, "reason": str(error), "metadata": {}}


# ---------------------------------------------------------------------------
# _extract_support_set_candidates
# ---------------------------------------------------------------------------


class TestExtractSupportSetCandidates:
    def test_returns_empty_for_missing_key(self) -> None:
        client = _FakeOPAClient()
        assert client._extract_support_set_candidates({}, max_paths=5) == []

    def test_returns_empty_for_non_list(self) -> None:
        client = _FakeOPAClient()
        assert client._extract_support_set_candidates({"support_set_candidates": "bad"}, 5) == []

    def test_extracts_dicts_only(self) -> None:
        client = _FakeOPAClient()
        raw = [{"a": 1}, "skip", {"b": 2}, 42]
        result = client._extract_support_set_candidates({"support_set_candidates": raw}, 10)
        assert result == [{"a": 1}, {"b": 2}]

    def test_respects_max_paths(self) -> None:
        client = _FakeOPAClient()
        raw = [{"a": i} for i in range(20)]
        result = client._extract_support_set_candidates({"support_set_candidates": raw}, 3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# _build_temporal_support_set_candidates
# ---------------------------------------------------------------------------


class TestBuildTemporalCandidates:
    def test_empty_history(self) -> None:
        client = _FakeOPAClient()
        assert client._build_temporal_support_set_candidates([]) == []

    def test_single_item_history(self) -> None:
        client = _FakeOPAClient()
        assert client._build_temporal_support_set_candidates(["a"]) == []

    def test_two_item_history(self) -> None:
        client = _FakeOPAClient()
        result = client._build_temporal_support_set_candidates(["a", "b"])
        assert len(result) >= 1
        assert all("action_history" in c for c in result)

    def test_respects_max_paths(self) -> None:
        client = _FakeOPAClient()
        result = client._build_temporal_support_set_candidates(
            ["a", "b", "c", "d", "e", "f"], max_paths=2
        )
        assert len(result) <= 2


# ---------------------------------------------------------------------------
# Feature flag helpers
# ---------------------------------------------------------------------------


class TestFeatureFlags:
    def test_temporal_multi_path_disabled_by_default(self) -> None:
        client = _FakeOPAClient()
        assert client._is_temporal_multi_path_enabled() is False

    def test_temporal_multi_path_enabled(self) -> None:
        client = _FakeOPAClient()
        with patch.dict(os.environ, {"ACGS_ENABLE_TEMPORAL_MULTI_PATH": "true"}):
            assert client._is_temporal_multi_path_enabled() is True

    def test_multi_path_generation_disabled_by_default(self) -> None:
        client = _FakeOPAClient()
        assert client._is_multi_path_candidate_generation_enabled() is False

    def test_multi_path_generation_enabled(self) -> None:
        client = _FakeOPAClient()
        with patch.dict(os.environ, {"ACGS_ENABLE_OPA_MULTI_PATH_GENERATION": "1"}):
            assert client._is_multi_path_candidate_generation_enabled() is True


# ---------------------------------------------------------------------------
# _minimal_support_sets
# ---------------------------------------------------------------------------


class TestMinimalSupportSets:
    def test_empty_paths(self) -> None:
        client = _FakeOPAClient()
        assert client._minimal_support_sets([]) == []

    def test_drops_strict_supersets(self) -> None:
        client = _FakeOPAClient()
        paths = [
            {"support_set": {"a": 1}},
            {"support_set": {"a": 1, "b": 2}},
        ]
        result = client._minimal_support_sets(paths)
        assert len(result) == 1
        assert result[0] == {"a": 1}

    def test_keeps_incomparable_sets(self) -> None:
        client = _FakeOPAClient()
        paths = [
            {"support_set": {"a": 1}},
            {"support_set": {"b": 2}},
        ]
        result = client._minimal_support_sets(paths)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _compute_diversity_metrics
# ---------------------------------------------------------------------------


class TestComputeDiversityMetrics:
    def test_no_allowed_paths(self) -> None:
        client = _FakeOPAClient()
        result = client._compute_diversity_metrics([], [], [])
        assert result["path_diversity_ratio"] == 0.0
        assert result["support_family_count"] == 0

    def test_with_allowed_and_minimal(self) -> None:
        client = _FakeOPAClient()
        paths = [
            {"support_set": {"a": 1}},
            {"support_set": {"b": 2}},
        ]
        allowed = paths
        minimal = [{"a": 1}]
        result = client._compute_diversity_metrics(paths, allowed, minimal)
        assert result["path_diversity_ratio"] == 0.5
        assert result["support_family_count"] == 2


# ---------------------------------------------------------------------------
# evaluate_policy_multi_path (async)
# ---------------------------------------------------------------------------


class TestEvaluatePolicyMultiPath:
    @pytest.mark.asyncio
    async def test_baseline_only(self) -> None:
        client = _FakeOPAClient()
        result = await client.evaluate_policy_multi_path({"action": "read"})
        assert result["allowed"] is True
        assert result["metadata"]["path_count"] == 1
        assert result["metadata"]["allowed_path_count"] == 1

    @pytest.mark.asyncio
    async def test_with_candidates(self) -> None:
        client = _FakeOPAClient()
        input_data = {
            "action": "read",
            "support_set_candidates": [{"extra": True}, {"extra2": True}],
        }
        result = await client.evaluate_policy_multi_path(input_data)
        assert result["metadata"]["path_count"] == 3
        assert len(result["paths"]) == 3

    @pytest.mark.asyncio
    async def test_candidate_evaluation_error(self) -> None:
        client = _FakeOPAClient()
        client.evaluate_policy = AsyncMock(
            side_effect=[
                {"allowed": True, "reason": "ok", "result": True, "metadata": {}},
                ValueError("boom"),
            ]
        )
        input_data = {
            "action": "read",
            "support_set_candidates": [{"x": 1}],
        }
        result = await client.evaluate_policy_multi_path(input_data)
        assert result["metadata"]["path_count"] == 2

    @pytest.mark.asyncio
    async def test_updates_multipath_counters(self) -> None:
        client = _FakeOPAClient()
        assert client._multipath_evaluation_count == 0
        await client.evaluate_policy_multi_path({"a": 1})
        assert client._multipath_evaluation_count == 1


# ---------------------------------------------------------------------------
# _build_constitutional_support_set_candidates
# ---------------------------------------------------------------------------


class TestBuildConstitutionalCandidates:
    def test_no_metadata(self) -> None:
        client = _FakeOPAClient()
        assert client._build_constitutional_support_set_candidates({}) == []

    def test_non_dict_metadata(self) -> None:
        client = _FakeOPAClient()
        assert client._build_constitutional_support_set_candidates({"metadata": "bad"}) == []

    def test_removes_true_flags(self) -> None:
        client = _FakeOPAClient()
        msg = {"metadata": {"flag_a": True, "flag_b": False, "flag_c": True}}
        result = client._build_constitutional_support_set_candidates(msg)
        assert len(result) == 2
        for c in result:
            assert "message" in c


# ---------------------------------------------------------------------------
# _build_authorization_support_set_candidates
# ---------------------------------------------------------------------------


class TestBuildAuthorizationCandidates:
    def test_removes_true_flags(self) -> None:
        client = _FakeOPAClient()
        context = {"admin": True, "viewer": False}
        result = client._build_authorization_support_set_candidates(context)
        assert len(result) == 1

    def test_role_removal(self) -> None:
        client = _FakeOPAClient()
        context = {"roles": ["admin", "viewer", "editor"]}
        result = client._build_authorization_support_set_candidates(context)
        assert len(result) == 3
        for c in result:
            assert len(c["context"]["roles"]) == 2

    def test_respects_max_paths(self) -> None:
        client = _FakeOPAClient()
        context = {f"f{i}": True for i in range(20)}
        result = client._build_authorization_support_set_candidates(context, max_paths=3)
        assert len(result) <= 3


# ---------------------------------------------------------------------------
# _build_policy_lifecycle_support_set_candidates
# ---------------------------------------------------------------------------


class TestBuildPolicyLifecycleCandidates:
    def test_non_lifecycle_action(self) -> None:
        client = _FakeOPAClient()
        assert client._build_policy_lifecycle_support_set_candidates({"action": "read"}) == []

    def test_invalid_action_type(self) -> None:
        client = _FakeOPAClient()
        assert client._build_policy_lifecycle_support_set_candidates({"action": 123}) == []

    def test_lifecycle_action_with_flags(self) -> None:
        client = _FakeOPAClient()
        input_data = {
            "action": "modify_policy",
            "requires_human_approval": True,
            "has_security_review": True,
        }
        result = client._build_policy_lifecycle_support_set_candidates(input_data)
        assert len(result) == 2

    def test_lifecycle_action_with_context_flags(self) -> None:
        client = _FakeOPAClient()
        input_data = {
            "action": "update_policy",
            "context": {"requires_human_approval": True},
        }
        result = client._build_policy_lifecycle_support_set_candidates(input_data)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# health_check (async)
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_http_healthy(self) -> None:
        client = _FakeOPAClient(mode="http")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        client._http_client.get = AsyncMock(return_value=mock_response)

        result = await client.health_check()
        assert result["status"] == "healthy"
        assert result["mode"] == "http"

    @pytest.mark.asyncio
    async def test_non_http_mode(self) -> None:
        client = _FakeOPAClient(mode="wasm")
        client._http_client = None
        result = await client.health_check()
        assert result["status"] == "healthy"
        assert result["mode"] == "wasm"

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        from httpx import ConnectError

        client = _FakeOPAClient(mode="http")
        client._http_client.get = AsyncMock(side_effect=ConnectError("refused"))

        result = await client.health_check()
        assert result["status"] == "unhealthy"
        assert "Connection failed" in result["error"]
