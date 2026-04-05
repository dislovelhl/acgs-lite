"""Tests for deliberation_layer.loco_operator_client module.

Covers GovernanceScoringResult, PolicyEvaluationResult, HealthCheckResult dataclasses,
LocoOperatorGovernanceClient methods, and utility helpers.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.deliberation_layer.loco_operator_client import (
    GovernanceScoringResult,
    HealthCheckResult,
    LocoOperatorGovernanceClient,
    PolicyEvaluationResult,
    _parse_json_response,
    _truncate_json,
)
from enhanced_agent_bus.exceptions.operations import GovernanceError

# ---------------------------------------------------------------------------
# GovernanceScoringResult
# ---------------------------------------------------------------------------


class TestGovernanceScoringResult:
    """Tests for GovernanceScoringResult dataclass validation."""

    def _hash(self) -> str:
        """Return the module-level constitutional hash."""
        from enhanced_agent_bus.deliberation_layer.loco_operator_client import (
            CONSTITUTIONAL_HASH,
        )

        return CONSTITUTIONAL_HASH

    def test_valid_result(self):
        h = self._hash()
        r = GovernanceScoringResult(
            score=0.5,
            rationale="ok",
            maci_role="proposer",
            constitutional_hash=h,
            model_id="test-model",
            latency_ms=10.0,
        )
        assert r.score == 0.5
        assert r.maci_role == "proposer"

    def test_score_below_zero_raises(self):
        with pytest.raises(ACGSValidationError):
            GovernanceScoringResult(
                score=-0.1,
                rationale="bad",
                maci_role="proposer",
                constitutional_hash=self._hash(),
                model_id="m",
                latency_ms=1.0,
            )

    def test_score_above_one_raises(self):
        with pytest.raises(ACGSValidationError):
            GovernanceScoringResult(
                score=1.1,
                rationale="bad",
                maci_role="proposer",
                constitutional_hash=self._hash(),
                model_id="m",
                latency_ms=1.0,
            )

    def test_invalid_maci_role_raises(self):
        with pytest.raises(ACGSValidationError):
            GovernanceScoringResult(
                score=0.5,
                rationale="ok",
                maci_role="validator",
                constitutional_hash=self._hash(),
                model_id="m",
                latency_ms=1.0,
            )

    def test_wrong_hash_raises(self):
        with pytest.raises(ACGSValidationError):
            GovernanceScoringResult(
                score=0.5,
                rationale="ok",
                maci_role="proposer",
                constitutional_hash="wrong",
                model_id="m",
                latency_ms=1.0,
            )


# ---------------------------------------------------------------------------
# PolicyEvaluationResult
# ---------------------------------------------------------------------------


class TestPolicyEvaluationResult:
    def _hash(self) -> str:
        from enhanced_agent_bus.deliberation_layer.loco_operator_client import (
            CONSTITUTIONAL_HASH,
        )

        return CONSTITUTIONAL_HASH

    def test_valid_result(self):
        r = PolicyEvaluationResult(
            is_compliant=True,
            confidence=0.9,
            explanation="ok",
            maci_role="proposer",
            constitutional_hash=self._hash(),
        )
        assert r.is_compliant is True
        assert r.confidence == 0.9

    def test_none_compliant_allowed(self):
        r = PolicyEvaluationResult(
            is_compliant=None,
            confidence=0.5,
            explanation="uncertain",
            maci_role="proposer",
            constitutional_hash=self._hash(),
        )
        assert r.is_compliant is None

    def test_confidence_out_of_range(self):
        with pytest.raises(ACGSValidationError):
            PolicyEvaluationResult(
                is_compliant=True,
                confidence=1.5,
                explanation="x",
                maci_role="proposer",
                constitutional_hash=self._hash(),
            )

    def test_bad_maci_role(self):
        with pytest.raises(ACGSValidationError):
            PolicyEvaluationResult(
                is_compliant=True,
                confidence=0.5,
                explanation="x",
                maci_role="executor",
                constitutional_hash=self._hash(),
            )


# ---------------------------------------------------------------------------
# HealthCheckResult
# ---------------------------------------------------------------------------


class TestHealthCheckResult:
    def test_healthy(self):
        r = HealthCheckResult(is_healthy=True, model_id="m", latency_ms=5.0)
        assert r.is_healthy is True
        assert r.error is None

    def test_unhealthy_with_error(self):
        r = HealthCheckResult(is_healthy=False, model_id="m", latency_ms=0, error="down")
        assert r.is_healthy is False
        assert r.error == "down"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestTruncateJson:
    def test_basic_truncation(self):
        result = _truncate_json({"key": "value"})
        assert "key" in result

    def test_respects_max_chars(self):
        big = {"k": "x" * 2000}
        result = _truncate_json(big, max_chars=50)
        assert len(result) <= 50

    def test_non_serializable_fallback(self):
        result = _truncate_json({"s": set()})  # type: ignore[dict-item]
        assert isinstance(result, str)


class TestParseJsonResponse:
    def test_plain_json(self):
        raw = '{"score": 0.7, "rationale": "ok"}'
        parsed = _parse_json_response(raw)
        assert parsed["score"] == 0.7

    def test_markdown_fenced(self):
        raw = '```json\n{"score": 0.5}\n```'
        parsed = _parse_json_response(raw)
        assert parsed["score"] == 0.5

    def test_json_with_surrounding_text(self):
        raw = 'Here is the result: {"score": 0.3} end'
        parsed = _parse_json_response(raw)
        assert parsed["score"] == 0.3

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not json at all")


# ---------------------------------------------------------------------------
# LocoOperatorGovernanceClient
# ---------------------------------------------------------------------------


class TestLocoOperatorGovernanceClient:
    """Tests for the governance client — adapter is always mocked."""

    def test_unavailable_when_adapter_missing(self):
        with patch(
            "enhanced_agent_bus.deliberation_layer.loco_operator_client._HUGGINGFACE_ADAPTER_AVAILABLE",
            False,
        ):
            client = LocoOperatorGovernanceClient()
            assert client.is_available is False

    def test_model_id_property(self):
        client = LocoOperatorGovernanceClient()
        assert isinstance(client.model_id, str)

    @pytest.mark.asyncio
    async def test_score_governance_action_unavailable_returns_none(self):
        client = LocoOperatorGovernanceClient()
        # Force unavailable state regardless of whether HuggingFace is installed
        client._available = False
        client._adapter = None
        result = await client.score_governance_action("deploy", {"env": "prod"})
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_policy_fragment_unavailable_returns_none(self):
        client = LocoOperatorGovernanceClient()
        client._available = False
        client._adapter = None
        result = await client.evaluate_policy_fragment("All agents must log")
        assert result is None

    @pytest.mark.asyncio
    async def test_health_check_unavailable(self):
        client = LocoOperatorGovernanceClient()
        client._available = False
        client._adapter = None
        result = await client.health_check()
        assert result.is_healthy is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_score_governance_action_available(self):
        client = LocoOperatorGovernanceClient()
        # Force available
        client._available = True
        mock_adapter = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"score": 0.6, "rationale": "moderate risk"}'
        mock_adapter.acomplete = AsyncMock(return_value=mock_resp)
        client._adapter = mock_adapter

        # Patch LLMMessage to avoid None guard
        with patch(
            "enhanced_agent_bus.deliberation_layer.loco_operator_client.LLMMessage",
            MagicMock(),
        ):
            result = await client.score_governance_action("deploy", {"x": 1})

        assert result is not None
        assert result.score == 0.6
        assert result.maci_role == "proposer"

    @pytest.mark.asyncio
    async def test_score_governance_action_transport_error(self):
        client = LocoOperatorGovernanceClient()
        client._available = True
        mock_adapter = AsyncMock()
        mock_adapter.acomplete = AsyncMock(side_effect=RuntimeError("timeout"))
        client._adapter = mock_adapter

        with patch(
            "enhanced_agent_bus.deliberation_layer.loco_operator_client.LLMMessage",
            MagicMock(),
        ):
            with pytest.raises(GovernanceError, match="transport failure"):
                await client.score_governance_action("deploy", {})

    @pytest.mark.asyncio
    async def test_score_governance_action_parse_error(self):
        client = LocoOperatorGovernanceClient()
        client._available = True
        mock_adapter = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.content = "not json"
        mock_adapter.acomplete = AsyncMock(return_value=mock_resp)
        client._adapter = mock_adapter

        with patch(
            "enhanced_agent_bus.deliberation_layer.loco_operator_client.LLMMessage",
            MagicMock(),
        ):
            with pytest.raises(GovernanceError, match="parse failure"):
                await client.score_governance_action("deploy", {})

    @pytest.mark.asyncio
    async def test_evaluate_policy_fragment_available(self):
        client = LocoOperatorGovernanceClient()
        client._available = True
        mock_adapter = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"is_compliant": true, "confidence": 0.8, "explanation": "ok"}'
        mock_adapter.acomplete = AsyncMock(return_value=mock_resp)
        client._adapter = mock_adapter

        with patch(
            "enhanced_agent_bus.deliberation_layer.loco_operator_client.LLMMessage",
            MagicMock(),
        ):
            result = await client.evaluate_policy_fragment("All agents must log")

        assert result is not None
        assert result.is_compliant is True
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_evaluate_policy_fragment_transport_error(self):
        client = LocoOperatorGovernanceClient()
        client._available = True
        mock_adapter = AsyncMock()
        mock_adapter.acomplete = AsyncMock(side_effect=ConnectionError("down"))
        client._adapter = mock_adapter

        with patch(
            "enhanced_agent_bus.deliberation_layer.loco_operator_client.LLMMessage",
            MagicMock(),
        ):
            with pytest.raises(GovernanceError, match="transport failure"):
                await client.evaluate_policy_fragment("test")

    @pytest.mark.asyncio
    async def test_health_check_available_healthy(self):
        client = LocoOperatorGovernanceClient()
        client._available = True
        mock_adapter = AsyncMock()
        mock_adapter.health_check = AsyncMock()
        client._adapter = mock_adapter

        result = await client.health_check()
        assert result.is_healthy is True
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_health_check_available_failure(self):
        client = LocoOperatorGovernanceClient()
        client._available = True
        mock_adapter = AsyncMock()
        mock_adapter.health_check = AsyncMock(side_effect=RuntimeError("gpu error"))
        client._adapter = mock_adapter

        result = await client.health_check()
        assert result.is_healthy is False
        assert "gpu error" in (result.error or "")

    @pytest.mark.asyncio
    async def test_call_adapter_no_adapter_raises(self):
        client = LocoOperatorGovernanceClient()
        client._adapter = None
        with pytest.raises(GovernanceError, match="not initialised"):
            await client._call_adapter("sys", "user")
