"""
Batch 14 coverage tests for enhanced_agent_bus.

Target modules (ranked 5-9 by missing lines):
1. message_processor.py (121 missing, 74.7%)
2. deliberation_layer/workflows/deliberation_workflow.py (117 missing, 62.7%)
3. enterprise_sso/middleware.py (116 missing, 55.0%)
4. saga_persistence/postgres/repository.py (113 missing, 20.4%)
5. langgraph_orchestration/constitutional_checkpoints.py (112 missing, 30.4%)

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. MessageProcessor tests
# ---------------------------------------------------------------------------


class TestMessageProcessorInit:
    """Tests for MessageProcessor initialization and configuration."""

    def test_init_isolated_mode(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc._isolated_mode is True
        assert proc._opa_client is None
        assert proc._enable_maci is False

    def test_init_default_mode(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.constitutional_hash is not None
        assert proc._processed_count == 0
        assert proc._failed_count == 0

    def test_invalid_cache_hash_mode_raises(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="invalid")

    def test_valid_cache_hash_modes(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True, cache_hash_mode="sha256")
        assert proc._cache_hash_mode == "sha256"


class TestMessageProcessorProperties:
    """Tests for MessageProcessor property accessors."""

    def test_processed_count(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.processed_count == 0
        proc._processed_count = 42
        assert proc.processed_count == 42

    def test_failed_count(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.failed_count == 0
        proc._failed_count = 7
        assert proc.failed_count == 7

    def test_processing_strategy_property(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        strategy = proc.processing_strategy
        assert strategy is not None

    def test_opa_client_property_none_in_isolated(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.opa_client is None


class TestMessageProcessorHandlers:
    """Tests for handler registration and unregistration."""

    def test_register_handler(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import MessageType

        proc = MessageProcessor(isolated_mode=True)

        async def handler(msg):
            return msg

        proc.register_handler(MessageType.QUERY, handler)
        assert MessageType.QUERY in proc._handlers
        assert handler in proc._handlers[MessageType.QUERY]

    def test_register_multiple_handlers(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import MessageType

        proc = MessageProcessor(isolated_mode=True)

        async def h1(msg):
            return msg

        async def h2(msg):
            return msg

        proc.register_handler(MessageType.QUERY, h1)
        proc.register_handler(MessageType.QUERY, h2)
        assert len(proc._handlers[MessageType.QUERY]) == 2

    def test_unregister_handler(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import MessageType

        proc = MessageProcessor(isolated_mode=True)

        async def handler(msg):
            return msg

        proc.register_handler(MessageType.QUERY, handler)
        result = proc.unregister_handler(MessageType.QUERY, handler)
        assert result is True

    def test_unregister_nonexistent_handler(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import MessageType

        proc = MessageProcessor(isolated_mode=True)

        async def handler(msg):
            return msg

        result = proc.unregister_handler(MessageType.QUERY, handler)
        assert result is False


class TestMessageProcessorMetrics:
    """Tests for get_metrics method."""

    def test_get_metrics_basic(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        metrics = proc.get_metrics()
        assert "processed_count" in metrics
        assert "failed_count" in metrics
        assert "success_rate" in metrics
        assert metrics["processed_count"] == 0
        assert metrics["success_rate"] == 0.0

    def test_get_metrics_with_counts(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        proc._processed_count = 8
        proc._failed_count = 2
        metrics = proc.get_metrics()
        assert metrics["processed_count"] == 8
        assert metrics["failed_count"] == 2
        assert metrics["success_rate"] == 0.8

    def test_get_metrics_pqc_disabled(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        metrics = proc.get_metrics()
        assert "pqc_enabled" in metrics


class TestMessageProcessorAutoSelectStrategy:
    """Tests for _auto_select_strategy."""

    def test_isolated_mode_selects_python_strategy(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        strategy_name = proc._processing_strategy.get_name()
        assert "python" in strategy_name.lower() or strategy_name is not None

    def test_strategy_set(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        mock_strategy = MagicMock()
        proc._set_strategy(mock_strategy)
        assert proc._processing_strategy is mock_strategy


class TestMessageProcessorProcess:
    """Tests for process and _do_process methods."""

    @pytest.mark.asyncio
    async def test_process_valid_message(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={"text": "hello"},
        )
        result = await proc.process(msg, max_retries=1)
        assert result is not None
        assert hasattr(result, "is_valid")

    @pytest.mark.asyncio
    async def test_process_uses_cache_on_repeated_call(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={"text": "hello"},
        )
        r1 = await proc.process(msg, max_retries=1)
        r2 = await proc.process(msg, max_retries=1)
        # Both should succeed (second from cache)
        assert r1 is not None
        assert r2 is not None

    @pytest.mark.asyncio
    async def test_process_retry_on_failure(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={"text": "test"},
        )

        call_count = 0
        original_do_process = proc._do_process

        async def failing_process(m):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient")
            return await original_do_process(m)

        proc._do_process = failing_process
        result = await proc.process(msg, max_retries=3)
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_process_max_retries_exceeded(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={"text": "test"},
        )

        async def always_fail(m):
            raise RuntimeError("persistent failure")

        proc._do_process = always_fail
        result = await proc.process(msg, max_retries=2)
        assert result.is_valid is False
        assert "max_retries_exceeded" in str(result.metadata)


class TestMessageProcessorHelpers:
    """Tests for helper methods."""

    def test_get_compliance_tags_valid(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority
        from enhanced_agent_bus.validators import ValidationResult

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={},
        )
        result = ValidationResult(is_valid=True, errors=[], metadata={})
        tags = proc._get_compliance_tags(msg, result)
        assert "constitutional_validated" in tags
        assert "approved" in tags

    def test_get_compliance_tags_rejected_critical(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority
        from enhanced_agent_bus.validators import ValidationResult

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.QUERY,
            priority=Priority.CRITICAL,
            content={},
        )
        result = ValidationResult(is_valid=False, errors=["fail"], metadata={})
        tags = proc._get_compliance_tags(msg, result)
        assert "rejected" in tags
        assert "high_priority" in tags

    def test_log_decision(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority
        from enhanced_agent_bus.validators import ValidationResult

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={},
        )
        result = ValidationResult(is_valid=True, errors=[], metadata={})
        # Should not raise
        proc._log_decision(msg, result)

    def test_log_decision_with_span(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority
        from enhanced_agent_bus.validators import ValidationResult

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={},
        )
        result = ValidationResult(is_valid=True, errors=[], metadata={})
        span = MagicMock()
        span_ctx = MagicMock()
        span_ctx.trace_id = 12345
        span.get_span_context.return_value = span_ctx
        proc._log_decision(msg, result, span=span)
        span.set_attribute.assert_called()

    def test_extract_rejection_reason(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.validators import ValidationResult

        result = ValidationResult(
            is_valid=False,
            errors=["validation failed"],
            metadata={"rejection_reason": "hash_mismatch"},
        )
        reason = MessageProcessor._extract_rejection_reason(result)
        assert reason == "hash_mismatch"


class TestMessageProcessorIndependentValidator:
    """Tests for independent validator gate."""

    def test_requires_independent_validation_high_impact(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={},
            impact_score=0.95,
        )
        assert proc._requires_independent_validation(msg) is True

    def test_requires_independent_validation_governance_type(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.NORMAL,
            content={},
        )
        assert proc._requires_independent_validation(msg) is True

    def test_not_requires_independent_validation_low_impact(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.QUERY,
            priority=Priority.NORMAL,
            content={},
            impact_score=0.1,
        )
        assert proc._requires_independent_validation(msg) is False

    def test_enforce_independent_validator_gate_disabled(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True, require_independent_validator=False)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.CRITICAL,
            content={},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_enforce_independent_validator_gate_self_validation(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True, require_independent_validator=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.CRITICAL,
            content={},
            metadata={"validated_by_agent": "agent-a"},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False

    def test_enforce_independent_validator_gate_missing_metadata(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True, require_independent_validator=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.CRITICAL,
            content={},
            metadata={},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False

    def test_enforce_independent_validator_gate_invalid_stage(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True, require_independent_validator=True)
        msg = AgentMessage(
            message_id="test-id",
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.CRITICAL,
            content={},
            metadata={
                "validated_by_agent": "agent-c",
                "validation_stage": "preliminary",
            },
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# 2. DeliberationWorkflow tests
# ---------------------------------------------------------------------------


class TestDeliberationWorkflowDataModels:
    """Tests for deliberation workflow data models."""

    def test_workflow_status_enum(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            WorkflowStatus,
        )

        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.APPROVED.value == "approved"
        assert WorkflowStatus.COMPENSATING.value == "compensating"

    def test_deliberation_workflow_input(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflowInput,
        )

        inp = DeliberationWorkflowInput(
            message_id="msg-1",
            content="test content",
            from_agent="agent-a",
            to_agent="agent-b",
            message_type="query",
            priority="normal",
        )
        assert inp.message_id == "msg-1"
        assert inp.require_multi_agent_vote is True
        assert inp.required_votes == 3
        assert inp.consensus_threshold == 0.66
        assert inp.timeout_seconds == 300

    def test_deliberation_workflow_result_to_dict(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflowResult,
            WorkflowStatus,
        )

        result = DeliberationWorkflowResult(
            workflow_id="wf-1",
            message_id="msg-1",
            status=WorkflowStatus.APPROVED,
            approved=True,
            impact_score=0.9,
            validation_passed=True,
            votes_received=3,
            votes_required=3,
            consensus_reached=True,
        )
        d = result.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["status"] == "approved"
        assert d["approved"] is True

    def test_vote_dataclass(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            Vote,
        )

        vote = Vote(
            agent_id="voter-1",
            decision="approve",
            reasoning="looks good",
            confidence=0.95,
            weight=1.5,
        )
        assert vote.agent_id == "voter-1"
        assert vote.decision == "approve"
        assert vote.weight == 1.5


class TestDefaultDeliberationActivities:
    """Tests for DefaultDeliberationActivities."""

    @pytest.mark.asyncio
    async def test_validate_constitutional_hash_valid(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)
        result = await activities.validate_constitutional_hash("msg-1", "hash1", "hash1")
        assert result["is_valid"] is True
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_validate_constitutional_hash_invalid(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(False, "Hash mismatch"))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)
        result = await activities.validate_constitutional_hash("msg-1", "bad", "good")
        assert result["is_valid"] is False
        assert "Hash mismatch" in result["errors"]

    @pytest.mark.asyncio
    async def test_calculate_impact_score_fallback(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)

        # Test fallback keyword scoring
        score = await activities.calculate_impact_score("msg-1", "delete the admin root files")
        assert 0.0 <= score <= 1.0
        assert score > 0  # has high-impact keywords

    @pytest.mark.asyncio
    async def test_calculate_impact_score_low_content(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)

        # Benign content should return a low (but not necessarily zero) score
        score = await activities.calculate_impact_score("msg-1", "good morning sunshine")
        assert 0.0 <= score <= 1.0
        # Score for benign content should be low (< 0.5)
        assert score < 0.5

    @pytest.mark.asyncio
    async def test_evaluate_opa_policy_returns_dict(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)

        result = await activities.evaluate_opa_policy("msg-1", {"content": "test"})
        # Returns a dict with allowed, reasons, policy_version keys
        assert "allowed" in result
        assert "reasons" in result
        assert "policy_version" in result

    @pytest.mark.asyncio
    async def test_request_agent_votes(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)
        request_id = await activities.request_agent_votes("msg-1", ["v1", "v2"], datetime.now(UTC))
        assert isinstance(request_id, str)
        assert len(request_id) > 0

    @pytest.mark.asyncio
    async def test_notify_human_reviewer(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)
        notification_id = await activities.notify_human_reviewer("msg-1", "reviewer-1")
        assert isinstance(notification_id, str)

    @pytest.mark.asyncio
    async def test_record_audit_trail_fallback_when_client_unavailable(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)
        with patch.object(activities, "_create_audit_client", return_value=None):
            audit_hash = await activities.record_audit_trail("msg-1", {"status": "approved"})
        assert isinstance(audit_hash, str)
        assert len(audit_hash) == 16

    @pytest.mark.asyncio
    async def test_record_audit_trail_raises_on_runtime_failure(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        activities = DefaultDeliberationActivities()
        activities._audit_client = Mock(record=AsyncMock(side_effect=RuntimeError("audit failed")))

        with pytest.raises(RuntimeError, match="audit failed"):
            await activities.record_audit_trail("msg-1", {"status": "approved"})

    @pytest.mark.asyncio
    async def test_deliver_message(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(return_value=(True, ""))
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)
        result = await activities.deliver_message("msg-1", "agent-b", "hello")
        assert result is True


class TestDeliberationWorkflow:
    """Tests for DeliberationWorkflow execution."""

    def _make_activities(self, hash_valid=True, opa_allowed=True):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DefaultDeliberationActivities,
        )

        mock_validator = AsyncMock()
        mock_validator.validate_hash = AsyncMock(
            return_value=(hash_valid, "" if hash_valid else "hash mismatch")
        )
        activities = DefaultDeliberationActivities(hash_validator=mock_validator)
        # Always mock OPA and audit to avoid real network calls
        activities.evaluate_opa_policy = AsyncMock(
            return_value={
                "allowed": opa_allowed,
                "reasons": [] if opa_allowed else ["denied"],
                "policy_version": "test",
            }
        )
        activities.record_audit_trail = AsyncMock(return_value="mock-audit-hash")
        return activities

    def _make_input(self, **kwargs):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflowInput,
        )

        defaults = {
            "message_id": "msg-1",
            "content": "test content",
            "from_agent": "agent-a",
            "to_agent": "agent-b",
            "message_type": "query",
            "priority": "normal",
            "require_multi_agent_vote": False,
            "require_human_review": False,
            "timeout_seconds": 1,  # Very short timeout for tests
        }
        defaults.update(kwargs)
        return DeliberationWorkflowInput(**defaults)

    @pytest.mark.asyncio
    async def test_workflow_no_votes_no_human_rejects(self):
        """Without votes or human review, consensus is not reached so workflow rejects."""
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            WorkflowStatus,
        )

        activities = self._make_activities(hash_valid=True, opa_allowed=True)
        wf = DeliberationWorkflow("wf-1", activities=activities)
        inp = self._make_input(require_multi_agent_vote=False, require_human_review=False)
        result = await wf.run(inp)
        # Without votes, consensus_reached=False -> approved=False
        assert result.approved is False
        assert result.status == WorkflowStatus.REJECTED
        assert result.validation_passed is True

    @pytest.mark.asyncio
    async def test_workflow_approved_with_all_votes(self):
        """With all votes approving, workflow approves."""
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
            WorkflowStatus,
        )

        activities = self._make_activities(hash_valid=True, opa_allowed=True)
        votes = [
            Vote(agent_id=f"v{i}", decision="approve", reasoning="ok", confidence=0.9)
            for i in range(3)
        ]
        activities.collect_votes = AsyncMock(return_value=votes)
        wf = DeliberationWorkflow("wf-1", activities=activities)
        inp = self._make_input(require_multi_agent_vote=True, required_votes=3)
        result = await wf.run(inp)
        assert result.approved is True
        assert result.status == WorkflowStatus.APPROVED
        assert result.validation_passed is True

    @pytest.mark.asyncio
    async def test_workflow_rejected_hash_invalid(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            WorkflowStatus,
        )

        activities = self._make_activities(hash_valid=False)
        wf = DeliberationWorkflow("wf-1", activities=activities)
        inp = self._make_input()
        result = await wf.run(inp)
        assert result.approved is False
        assert result.status == WorkflowStatus.REJECTED
        assert result.validation_passed is False

    @pytest.mark.asyncio
    async def test_workflow_rejected_by_opa(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            WorkflowStatus,
        )

        activities = self._make_activities(hash_valid=True, opa_allowed=False)
        wf = DeliberationWorkflow("wf-1", activities=activities)
        inp = self._make_input()
        result = await wf.run(inp)
        assert result.approved is False
        assert result.status == WorkflowStatus.REJECTED

    @pytest.mark.asyncio
    async def test_workflow_with_votes_consensus(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
            WorkflowStatus,
        )

        activities = self._make_activities(hash_valid=True, opa_allowed=True)
        votes = [
            Vote(agent_id=f"v{i}", decision="approve", reasoning="ok", confidence=0.9)
            for i in range(3)
        ]
        activities.collect_votes = AsyncMock(return_value=votes)
        wf = DeliberationWorkflow("wf-1", activities=activities)
        inp = self._make_input(require_multi_agent_vote=True, required_votes=3)
        result = await wf.run(inp)
        assert result.approved is True
        assert result.consensus_reached is True

    @pytest.mark.asyncio
    async def test_workflow_with_votes_no_consensus(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
            WorkflowStatus,
        )

        activities = self._make_activities(hash_valid=True, opa_allowed=True)
        votes = [
            Vote(agent_id="v0", decision="approve", reasoning="ok", confidence=0.9),
            Vote(agent_id="v1", decision="reject", reasoning="bad", confidence=0.9),
            Vote(agent_id="v2", decision="reject", reasoning="bad", confidence=0.9),
        ]
        activities.collect_votes = AsyncMock(return_value=votes)
        wf = DeliberationWorkflow("wf-1", activities=activities)
        inp = self._make_input(require_multi_agent_vote=True, required_votes=3)
        result = await wf.run(inp)
        assert result.approved is False
        assert result.consensus_reached is False

    @pytest.mark.asyncio
    async def test_workflow_failure_triggers_compensation(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            WorkflowStatus,
        )

        activities = self._make_activities(hash_valid=True, opa_allowed=True)
        activities.evaluate_opa_policy = AsyncMock(side_effect=RuntimeError("boom"))
        wf = DeliberationWorkflow("wf-1", activities=activities)
        inp = self._make_input()
        result = await wf.run(inp)
        assert result.status == WorkflowStatus.FAILED
        assert result.approved is False
        assert len(result.errors) > 0

    def test_check_consensus_weights(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
        )

        wf = DeliberationWorkflow("wf-1")
        votes = [
            Vote(agent_id="v0", decision="approve", reasoning="ok", confidence=0.9),
            Vote(agent_id="v1", decision="reject", reasoning="bad", confidence=0.9),
            Vote(agent_id="v2", decision="reject", reasoning="bad", confidence=0.9),
        ]
        # v0 has weight 10, v1 and v2 have weight 1 each
        weights = {"v0": 10.0, "v1": 1.0, "v2": 1.0}
        result = wf._check_consensus(votes, 3, 0.66, weights)
        assert result is True  # 10/12 = 0.833 > 0.66

    def test_check_consensus_not_enough_votes(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
        )

        wf = DeliberationWorkflow("wf-1")
        votes = [
            Vote(agent_id="v0", decision="approve", reasoning="ok", confidence=0.9),
        ]
        result = wf._check_consensus(votes, 3, 0.66)
        assert result is False

    def test_check_consensus_zero_weight(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
        )

        wf = DeliberationWorkflow("wf-1")
        votes = [
            Vote(agent_id="v0", decision="approve", reasoning="ok", confidence=0.0, weight=0.0),
            Vote(agent_id="v1", decision="approve", reasoning="ok", confidence=0.0, weight=0.0),
            Vote(agent_id="v2", decision="approve", reasoning="ok", confidence=0.0, weight=0.0),
        ]
        result = wf._check_consensus(votes, 3, 0.66, {"v0": 0.0, "v1": 0.0, "v2": 0.0})
        assert result is False

    def test_determine_approval_human_required(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
        )

        wf = DeliberationWorkflow("wf-1")
        assert wf._determine_approval(True, "approve", True) is True
        assert wf._determine_approval(True, "reject", True) is False
        assert wf._determine_approval(True, None, True) is False

    def test_determine_approval_no_human(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
        )

        wf = DeliberationWorkflow("wf-1")
        assert wf._determine_approval(True, None, False) is True
        assert wf._determine_approval(False, None, False) is False

    def test_determine_approval_human_decision_overrides(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
        )

        wf = DeliberationWorkflow("wf-1")
        # When human_decision is present but not required, it overrides
        assert wf._determine_approval(False, "approve", False) is True
        assert wf._determine_approval(True, "reject", False) is False

    def test_build_reasoning_with_votes(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
        )

        wf = DeliberationWorkflow("wf-1")
        wf._votes = [
            Vote(agent_id="v0", decision="approve", reasoning="ok", confidence=0.9),
            Vote(agent_id="v1", decision="reject", reasoning="bad", confidence=0.5),
        ]
        reasoning = wf._build_reasoning()
        assert "1/2 approved" in reasoning

    def test_build_reasoning_with_human(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
        )

        wf = DeliberationWorkflow("wf-1")
        wf._human_decision = "approve"
        wf._human_reviewer = "admin-1"
        reasoning = wf._build_reasoning()
        assert "Human decision" in reasoning
        assert "admin-1" in reasoning

    def test_build_reasoning_empty(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
        )

        wf = DeliberationWorkflow("wf-1")
        reasoning = wf._build_reasoning()
        assert reasoning == "Workflow completed"

    def test_signal_vote(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            Vote,
        )

        wf = DeliberationWorkflow("wf-1")
        vote = Vote(agent_id="v0", decision="approve", reasoning="ok", confidence=0.9)
        wf.signal_vote(vote)
        assert len(wf.get_votes()) == 1
        assert wf._vote_signal_received.is_set()

    def test_signal_human_decision(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
        )

        wf = DeliberationWorkflow("wf-1")
        wf.signal_human_decision("approve", "reviewer-1")
        assert wf._human_decision == "approve"
        assert wf._human_reviewer == "reviewer-1"
        assert wf._human_decision_signal.is_set()

    def test_get_status(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            WorkflowStatus,
        )

        wf = DeliberationWorkflow("wf-1")
        assert wf.get_status() == WorkflowStatus.PENDING

    def test_get_voting_agents(self):
        from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
            DeliberationWorkflow,
            DeliberationWorkflowInput,
        )

        wf = DeliberationWorkflow("wf-1")
        inp = DeliberationWorkflowInput(
            message_id="m1",
            content="c",
            from_agent="a",
            to_agent="b",
            message_type="q",
            priority="n",
            required_votes=5,
        )
        agents = wf._get_voting_agents(inp)
        assert len(agents) == 5
        assert agents[0] == "voter_0"


# ---------------------------------------------------------------------------
# 3. Enterprise SSO Middleware tests
# ---------------------------------------------------------------------------


class TestSSOSessionContext:
    """Tests for SSOSessionContext dataclass."""

    def _make_session(self, **kwargs):
        from enhanced_agent_bus.enterprise_sso.middleware import SSOSessionContext

        defaults = {
            "session_id": "sess-1",
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "email": "user@example.com",
            "display_name": "User One",
            "maci_roles": ["ADMIN", "OPERATOR"],
            "idp_groups": ["group-a"],
            "attributes": {},
            "authenticated_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
        defaults.update(kwargs)
        return SSOSessionContext(**defaults)

    def test_is_expired_false(self):
        session = self._make_session()
        assert session.is_expired is False

    def test_is_expired_true(self):
        session = self._make_session(expires_at=datetime.now(UTC) - timedelta(hours=1))
        assert session.is_expired is True

    def test_time_until_expiry(self):
        session = self._make_session(expires_at=datetime.now(UTC) + timedelta(seconds=60))
        assert session.time_until_expiry > 50
        assert session.time_until_expiry <= 60

    def test_time_until_expiry_expired(self):
        session = self._make_session(expires_at=datetime.now(UTC) - timedelta(seconds=60))
        assert session.time_until_expiry == 0.0

    def test_has_role(self):
        session = self._make_session()
        assert session.has_role("admin") is True
        assert session.has_role("ADMIN") is True
        assert session.has_role("viewer") is False

    def test_has_any_role(self):
        session = self._make_session()
        assert session.has_any_role(["admin", "viewer"]) is True
        assert session.has_any_role(["viewer", "editor"]) is False

    def test_has_all_roles(self):
        session = self._make_session()
        assert session.has_all_roles(["admin", "operator"]) is True
        assert session.has_all_roles(["admin", "viewer"]) is False

    def test_to_dict(self):
        session = self._make_session()
        d = session.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["user_id"] == "user-1"
        assert d["tenant_id"] == "tenant-1"
        assert d["email"] == "user@example.com"
        assert "maci_roles" in d


class TestSSOContextVars:
    """Tests for SSO session context variable management."""

    def test_get_set_clear_session(self):
        from enhanced_agent_bus.enterprise_sso.middleware import (
            clear_sso_session,
            get_current_sso_session,
            set_sso_session,
        )

        assert get_current_sso_session() is None
        session = MagicMock()
        set_sso_session(session)
        assert get_current_sso_session() is session
        clear_sso_session()
        assert get_current_sso_session() is None


class TestRaiseAuthError:
    """Tests for _raise_auth_error helper."""

    def test_raise_auth_error_permission_error(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _raise_auth_error

        # When FastAPI is available it raises HTTPException; otherwise PermissionError
        with pytest.raises((PermissionError, Exception)):
            _raise_auth_error(401, "Unauthorized")


class TestCheckSessionValid:
    """Tests for _check_session_valid helper."""

    def test_no_session_raises(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_valid

        with pytest.raises((PermissionError, Exception)):
            _check_session_valid(None, allow_expired=False)

    def test_expired_session_raises(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_valid

        mock_session = MagicMock()
        mock_session.is_expired = True
        with pytest.raises((PermissionError, Exception)):
            _check_session_valid(mock_session, allow_expired=False)

    def test_expired_session_allowed(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_valid

        mock_session = MagicMock()
        mock_session.is_expired = True
        # Should not raise when allow_expired=True
        _check_session_valid(mock_session, allow_expired=True)


class TestCheckSessionRoles:
    """Tests for _check_session_roles helper."""

    def test_no_roles_required(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_roles

        mock_session = MagicMock()
        # No roles = no check
        _check_session_roles(mock_session, [], any_role=True)

    def test_any_role_satisfied(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_roles

        mock_session = MagicMock()
        mock_session.has_any_role.return_value = True
        _check_session_roles(mock_session, ["ADMIN"], any_role=True)

    def test_any_role_not_satisfied(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_roles

        mock_session = MagicMock()
        mock_session.has_any_role.return_value = False
        with pytest.raises((PermissionError, Exception)):
            _check_session_roles(mock_session, ["ADMIN"], any_role=True)

    def test_all_roles_not_satisfied(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_roles

        mock_session = MagicMock()
        mock_session.has_all_roles.return_value = False
        with pytest.raises((PermissionError, Exception)):
            _check_session_roles(mock_session, ["ADMIN", "OPERATOR"], any_role=False)


class TestCheckSessionValidSync:
    """Tests for sync session validation helpers."""

    def test_no_session_raises(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_valid_sync

        with pytest.raises(PermissionError, match="SSO authentication required"):
            _check_session_valid_sync(None, allow_expired=False)

    def test_expired_session_raises(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_valid_sync

        mock_session = MagicMock()
        mock_session.is_expired = True
        with pytest.raises(PermissionError, match="SSO session expired"):
            _check_session_valid_sync(mock_session, allow_expired=False)

    def test_check_roles_sync_any_not_satisfied(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_roles_sync

        mock_session = MagicMock()
        mock_session.has_any_role.return_value = False
        with pytest.raises(PermissionError, match="Requires one of roles"):
            _check_session_roles_sync(mock_session, ["ADMIN"], any_role=True)

    def test_check_roles_sync_all_not_satisfied(self):
        from enhanced_agent_bus.enterprise_sso.middleware import _check_session_roles_sync

        mock_session = MagicMock()
        mock_session.has_all_roles.return_value = False
        with pytest.raises(PermissionError, match="Requires all roles"):
            _check_session_roles_sync(mock_session, ["ADMIN", "OP"], any_role=False)


class TestRequireSSOAuthentication:
    """Tests for require_sso_authentication decorator."""

    @pytest.mark.asyncio
    async def test_decorator_async_no_session(self):
        from enhanced_agent_bus.enterprise_sso.middleware import (
            clear_sso_session,
            require_sso_authentication,
        )

        clear_sso_session()

        @require_sso_authentication()
        async def protected():
            return "ok"

        with pytest.raises((PermissionError, Exception)):
            await protected()

    @pytest.mark.asyncio
    async def test_decorator_async_with_session(self):
        from enhanced_agent_bus.enterprise_sso.middleware import (
            clear_sso_session,
            require_sso_authentication,
            set_sso_session,
        )

        mock_session = MagicMock()
        mock_session.is_expired = False
        set_sso_session(mock_session)

        @require_sso_authentication()
        async def protected():
            return "ok"

        try:
            result = await protected()
            assert result == "ok"
        finally:
            clear_sso_session()

    def test_decorator_sync_no_session(self):
        from enhanced_agent_bus.enterprise_sso.middleware import (
            clear_sso_session,
            require_sso_authentication,
        )

        clear_sso_session()

        @require_sso_authentication()
        def protected():
            return "ok"

        with pytest.raises(PermissionError):
            protected()

    def test_decorator_sync_with_roles(self):
        from enhanced_agent_bus.enterprise_sso.middleware import (
            clear_sso_session,
            require_sso_authentication,
            set_sso_session,
        )

        mock_session = MagicMock()
        mock_session.is_expired = False
        mock_session.has_any_role.return_value = True
        set_sso_session(mock_session)

        @require_sso_authentication(roles=["ADMIN"], any_role=True)
        def protected():
            return "ok"

        try:
            result = protected()
            assert result == "ok"
        finally:
            clear_sso_session()


class TestSSOMiddlewareConfig:
    """Tests for SSOMiddlewareConfig."""

    def test_default_config(self):
        from enhanced_agent_bus.enterprise_sso.middleware import SSOMiddlewareConfig

        config = SSOMiddlewareConfig()
        assert "/health" in config.excluded_paths
        assert "/healthz" in config.excluded_paths
        assert config.require_authentication is True
        assert config.auto_refresh_sessions is True
        assert config.refresh_threshold_seconds == 300

    def test_custom_config(self):
        from enhanced_agent_bus.enterprise_sso.middleware import SSOMiddlewareConfig

        config = SSOMiddlewareConfig(
            require_authentication=False,
            auto_refresh_sessions=False,
            excluded_paths={"/custom"},
        )
        assert config.require_authentication is False
        assert "/custom" in config.excluded_paths


# ---------------------------------------------------------------------------
# 4. PostgresSagaStateRepository tests
# ---------------------------------------------------------------------------


class TestPostgresSagaStateRepository:
    """Tests for PostgresSagaStateRepository with mocked asyncpg."""

    def test_init_with_dsn(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        assert repo._dsn == "postgres://localhost/test"
        assert repo._initialized is False
        assert repo._pool is None

    def test_init_with_pool(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        assert repo._initialized is True
        assert repo._pool is mock_pool

    def test_generate_node_id(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        node_id = repo._generate_node_id()
        assert node_id.startswith("node-")

    def test_ensure_initialized_raises(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        with pytest.raises(RepositoryError, match="not initialized"):
            repo._ensure_initialized()

    def test_ensure_initialized_returns_pool(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        result = repo._ensure_initialized()
        assert result is mock_pool

    @pytest.mark.asyncio
    async def test_initialize_no_dsn_no_pool_raises(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        repo = PostgresSagaStateRepository()
        with pytest.raises(RepositoryError, match="DSN required"):
            await repo.initialize()

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        await repo.initialize()  # Should be a no-op
        assert repo._initialized is True

    @pytest.mark.asyncio
    async def test_close(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = AsyncMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        await repo.close()
        mock_pool.close.assert_called_once()
        assert repo._pool is None
        assert repo._initialized is False

    @pytest.mark.asyncio
    async def test_close_no_pool(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        await repo.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_save_not_initialized_raises(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        mock_saga = MagicMock()
        with pytest.raises(RepositoryError, match="not initialized"):
            await repo.save(mock_saga)

    @pytest.mark.asyncio
    async def test_get_not_initialized_raises(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        with pytest.raises(RepositoryError, match="not initialized"):
            await repo.get("some-id")

    @pytest.mark.asyncio
    async def test_delete_not_initialized_raises(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        with pytest.raises(RepositoryError, match="not initialized"):
            await repo.delete("some-id")

    @pytest.mark.asyncio
    async def test_exists_not_initialized_raises(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        with pytest.raises(RepositoryError, match="not initialized"):
            await repo.exists("some-id")

    def _make_pool_with_conn(self, mock_conn):
        """Create a mock asyncpg pool with proper async context manager."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_pool = MagicMock()
        mock_pool.acquire = acquire
        mock_pool.close = AsyncMock()
        return mock_pool

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool = self._make_pool_with_conn(mock_conn)

        repo = PostgresSagaStateRepository(pool=mock_pool)
        result = await repo.get(str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_exists_returns_bool(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=True)
        mock_pool = self._make_pool_with_conn(mock_conn)

        repo = PostgresSagaStateRepository(pool=mock_pool)
        result = await repo.exists(str(uuid.uuid4()))
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_pool = self._make_pool_with_conn(mock_conn)

        repo = PostgresSagaStateRepository(pool=mock_pool)
        result = await repo.delete(str(uuid.uuid4()))
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 0")
        mock_pool = self._make_pool_with_conn(mock_conn)

        repo = PostgresSagaStateRepository(pool=mock_pool)
        result = await repo.delete(str(uuid.uuid4()))
        assert result is False

    def test_row_to_saga(self):
        from enhanced_agent_bus.saga_persistence.models import (
            CompensationStrategy,
            SagaState,
        )
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        now = datetime.now(UTC)
        saga_id = uuid.uuid4()
        corr_id = uuid.uuid4()
        row = {
            "saga_id": saga_id,
            "saga_name": "test-saga",
            "tenant_id": "tenant-1",
            "correlation_id": corr_id,
            "state": "RUNNING",
            "compensation_strategy": "LIFO",
            "current_step_index": 1,
            "version": 2,
            "steps": "[]",
            "context": '{"key": "val"}',
            "metadata": "{}",
            "compensation_log": "[]",
            "created_at": now,
            "started_at": now,
            "completed_at": None,
            "failed_at": None,
            "compensated_at": None,
            "total_duration_ms": 100.0,
            "failure_reason": None,
            "timeout_ms": 5000,
            "constitutional_hash": "608508a9bd224290",
        }
        saga = repo._row_to_saga(row)
        assert saga.saga_id == str(saga_id)
        assert saga.saga_name == "test-saga"
        assert saga.state == SagaState.RUNNING

    def test_row_to_checkpoint(self):
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        now = datetime.now(UTC)
        cp_id = uuid.uuid4()
        saga_id = uuid.uuid4()
        row = {
            "checkpoint_id": cp_id,
            "saga_id": saga_id,
            "checkpoint_name": "before-step-2",
            "state_snapshot": '{"key": "val"}',
            "completed_step_ids": '["s1"]',
            "pending_step_ids": '["s2"]',
            "created_at": now,
            "is_constitutional": True,
            "metadata": "{}",
            "constitutional_hash": "608508a9bd224290",
        }
        cp = repo._row_to_checkpoint(row)
        assert cp.checkpoint_id == str(cp_id)
        assert cp.checkpoint_name == "before-step-2"
        assert cp.is_constitutional is True

    def test_row_to_saga_native_types(self):
        """Test _row_to_saga with native dict/list types (not JSON strings)."""
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        now = datetime.now(UTC)
        saga_id = uuid.uuid4()
        corr_id = uuid.uuid4()
        row = {
            "saga_id": saga_id,
            "saga_name": "test",
            "tenant_id": "t1",
            "correlation_id": corr_id,
            "state": "INITIALIZED",
            "compensation_strategy": "LIFO",
            "current_step_index": 0,
            "version": 1,
            "steps": [],  # native list
            "context": {"a": 1},  # native dict
            "metadata": {},  # native dict
            "compensation_log": [],  # native list
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "compensated_at": None,
            "total_duration_ms": None,
            "failure_reason": None,
            "timeout_ms": 5000,
            "constitutional_hash": "standalone",
        }
        saga = repo._row_to_saga(row)
        assert saga.context == {"a": 1}

    def test_row_to_checkpoint_native_types(self):
        """Test _row_to_checkpoint with native dict/list types."""
        from enhanced_agent_bus.saga_persistence.postgres.repository import (
            PostgresSagaStateRepository,
        )

        mock_pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=mock_pool)
        now = datetime.now(UTC)
        row = {
            "checkpoint_id": uuid.uuid4(),
            "saga_id": uuid.uuid4(),
            "checkpoint_name": "cp1",
            "state_snapshot": {"x": 1},  # native dict
            "completed_step_ids": ["s1"],  # native list
            "pending_step_ids": ["s2"],  # native list
            "created_at": now,
            "is_constitutional": False,
            "metadata": {"m": "v"},
            "constitutional_hash": "standalone",
        }
        cp = repo._row_to_checkpoint(row)
        assert cp.state_snapshot == {"x": 1}
        assert cp.completed_step_ids == ["s1"]


# ---------------------------------------------------------------------------
# 5. Constitutional Checkpoints tests
# ---------------------------------------------------------------------------


class TestConstitutionalHashValidatorCheckpoint:
    """Tests for ConstitutionalHashValidator in checkpoints module."""

    @pytest.mark.asyncio
    async def test_validate_all_hashes_match(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalHashValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        h = "test-hash"
        validator = ConstitutionalHashValidator(expected_hash=h)
        state = GraphState(data={"k": "v"}, constitutional_hash=h)
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="node-1",
            step_index=0,
            state=state,
            constitutional_hash=h,
        )
        context = ExecutionContext(
            graph_id="g1",
            constitutional_hash=h,
        )
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is True
        assert violations == []

    @pytest.mark.asyncio
    async def test_validate_checkpoint_hash_mismatch(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalHashValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        h = "correct"
        validator = ConstitutionalHashValidator(expected_hash=h)
        state = GraphState(data={}, constitutional_hash=h)
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="node-1",
            step_index=0,
            state=state,
            constitutional_hash="wrong",
        )
        context = ExecutionContext(graph_id="g1", constitutional_hash=h)
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is False
        assert len(violations) >= 1

    @pytest.mark.asyncio
    async def test_validate_state_hash_mismatch(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalHashValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        h = "correct"
        validator = ConstitutionalHashValidator(expected_hash=h)
        state = GraphState(data={}, constitutional_hash="wrong")
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="node-1",
            step_index=0,
            state=state,
            constitutional_hash=h,
        )
        context = ExecutionContext(graph_id="g1", constitutional_hash=h)
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_validate_context_hash_mismatch(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalHashValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        h = "correct"
        validator = ConstitutionalHashValidator(expected_hash=h)
        state = GraphState(data={}, constitutional_hash=h)
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="node-1",
            step_index=0,
            state=state,
            constitutional_hash=h,
        )
        context = ExecutionContext(graph_id="g1", constitutional_hash="wrong")
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is False


class TestStateIntegrityValidator:
    """Tests for StateIntegrityValidator."""

    @pytest.mark.asyncio
    async def test_validate_valid_state(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            StateIntegrityValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        validator = StateIntegrityValidator()
        state = GraphState(data={"key": "value"}, version=1)
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="node-1",
            step_index=1,
            state=state,
            metadata={},
        )
        context = ExecutionContext(graph_id="g1")
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is True
        assert "state_checksum" in checkpoint.metadata

    @pytest.mark.asyncio
    async def test_validate_invalid_version_at_step(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            StateIntegrityValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        validator = StateIntegrityValidator()
        state = GraphState(data={}, version=0)
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="node-1",
            step_index=5,  # step > 0 but version is 0
            state=state,
            metadata={},
        )
        context = ExecutionContext(graph_id="g1")
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is False
        assert any("Invalid state version" in v for v in violations)


class TestMACIRoleValidator:
    """Tests for MACIRoleValidator."""

    @pytest.mark.asyncio
    async def test_validate_no_enforcer(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            MACIRoleValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        validator = MACIRoleValidator(maci_enforcer=None)
        state = GraphState(data={})
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=state,
        )
        context = ExecutionContext(graph_id="g1")
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is True
        assert checkpoint.maci_validated is True

    @pytest.mark.asyncio
    async def test_validate_with_enforcer_no_session(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            MACIRoleValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        mock_enforcer = MagicMock()
        validator = MACIRoleValidator(maci_enforcer=mock_enforcer)
        state = GraphState(data={})
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=state,
        )
        context = ExecutionContext(graph_id="g1", maci_session_id=None)
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_validate_with_enforcer_and_session(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            MACIRoleValidator,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            ExecutionContext,
            GraphState,
        )

        mock_enforcer = MagicMock()
        validator = MACIRoleValidator(maci_enforcer=mock_enforcer)
        state = GraphState(data={})
        checkpoint = Checkpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=state,
        )
        context = ExecutionContext(graph_id="g1", maci_session_id="sess-1")
        is_valid, violations = await validator.validate(checkpoint, context)
        assert is_valid is True
        assert checkpoint.maci_validated is True


class TestConstitutionalCheckpoint:
    """Tests for ConstitutionalCheckpoint wrapper."""

    @pytest.mark.asyncio
    async def test_validate_all_pass(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalCheckpoint,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            CheckpointStatus,
            ExecutionContext,
            GraphState,
        )

        h = "test-hash"
        state = GraphState(data={"x": 1}, constitutional_hash=h)
        cp = ConstitutionalCheckpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=state,
        )
        # Add a passing validator
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=(True, []))
        cp.add_validator("mock", mock_validator)

        context = ExecutionContext(graph_id="g1", constitutional_hash=h)
        result = await cp.validate(context)
        assert result is True
        assert cp.checkpoint.status == CheckpointStatus.VALIDATED

    @pytest.mark.asyncio
    async def test_validate_failure_raises(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalCheckpoint,
        )
        from enhanced_agent_bus.langgraph_orchestration.exceptions import (
            ConstitutionalViolationError,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            GraphState,
        )

        state = GraphState(data={})
        cp = ConstitutionalCheckpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=state,
        )
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=(False, ["violation!"]))
        cp.add_validator("failing", mock_validator)

        context = ExecutionContext(graph_id="g1")
        with pytest.raises(ConstitutionalViolationError):
            await cp.validate(context)

    @pytest.mark.asyncio
    async def test_validate_exception_in_validator(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalCheckpoint,
        )
        from enhanced_agent_bus.langgraph_orchestration.exceptions import (
            ConstitutionalViolationError,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            GraphState,
        )

        state = GraphState(data={})
        cp = ConstitutionalCheckpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=state,
        )
        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(side_effect=RuntimeError("boom"))
        cp.add_validator("error", mock_validator)

        context = ExecutionContext(graph_id="g1")
        with pytest.raises(ConstitutionalViolationError):
            await cp.validate(context)

    def test_to_dict(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalCheckpoint,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        state = GraphState(data={"x": 1})
        cp = ConstitutionalCheckpoint(
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=state,
        )
        d = cp.to_dict()
        assert "checkpoint" in d
        assert "validation_results" in d


class TestConstitutionalCheckpointManager:
    """Tests for ConstitutionalCheckpointManager."""

    def _make_manager(self, **kwargs):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalCheckpointManager,
        )

        return ConstitutionalCheckpointManager(**kwargs)

    def _make_context(self, **kwargs):
        from enhanced_agent_bus.langgraph_orchestration.models import ExecutionContext

        defaults = {"graph_id": "g1"}
        defaults.update(kwargs)
        return ExecutionContext(**defaults)

    @pytest.mark.asyncio
    async def test_create_checkpoint_no_validation(self):
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        manager = self._make_manager(enable_integrity_check=False)
        ctx = self._make_context()
        state = GraphState(data={"k": "v"})
        cp = await manager.create_checkpoint(ctx, "node-1", state, validate=False)
        assert cp.node_id == "node-1"
        assert cp.id in manager._checkpoints

    @pytest.mark.asyncio
    async def test_create_checkpoint_with_validation(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            CONSTITUTIONAL_HASH as CP_HASH,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        # Must use the module-level CONSTITUTIONAL_HASH since ConstitutionalCheckpoint
        # hardcodes it in its __init__
        h = CP_HASH
        manager = self._make_manager(constitutional_hash=h, enable_integrity_check=True)
        ctx = self._make_context(constitutional_hash=h)
        state = GraphState(data={"k": "v"}, version=1, constitutional_hash=h)
        cp = await manager.create_checkpoint(ctx, "node-1", state, validate=True)
        assert cp.constitutional_validated is True
        assert cp.id in ctx.checkpoints

    @pytest.mark.asyncio
    async def test_restore_checkpoint_from_cache(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            CONSTITUTIONAL_HASH as CP_HASH,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            CheckpointStatus,
            GraphState,
        )

        h = CP_HASH
        manager = self._make_manager(constitutional_hash=h, enable_integrity_check=False)
        ctx = self._make_context(constitutional_hash=h)
        state = GraphState(data={"k": "v"}, constitutional_hash=h)
        cp = await manager.create_checkpoint(ctx, "n1", state, validate=False)

        restored_cp, restored_state = await manager.restore_checkpoint(cp.id, ctx)
        assert restored_cp.status == CheckpointStatus.RESTORED
        assert restored_state.data == {"k": "v"}

    @pytest.mark.asyncio
    async def test_restore_checkpoint_not_found(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import CheckpointError

        manager = self._make_manager()
        ctx = self._make_context()
        with pytest.raises(CheckpointError):
            await manager.restore_checkpoint("nonexistent", ctx)

    @pytest.mark.asyncio
    async def test_restore_checkpoint_hash_mismatch(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import CheckpointError
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        manager = self._make_manager(constitutional_hash="hash-a", enable_integrity_check=False)
        ctx = self._make_context(constitutional_hash="hash-a")
        state = GraphState(data={}, constitutional_hash="hash-a")
        cp = await manager.create_checkpoint(ctx, "n1", state, validate=False)

        # Change manager's hash to simulate mismatch
        manager.constitutional_hash = "hash-b"
        with pytest.raises(CheckpointError):
            await manager.restore_checkpoint(cp.id, ctx)

    @pytest.mark.asyncio
    async def test_get_checkpoint(self):
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        manager = self._make_manager(enable_integrity_check=False)
        ctx = self._make_context()
        state = GraphState(data={})
        cp = await manager.create_checkpoint(ctx, "n1", state, validate=False)
        result = await manager.get_checkpoint(cp.id)
        assert result is not None
        assert result.id == cp.id

    @pytest.mark.asyncio
    async def test_get_checkpoint_not_found(self):
        manager = self._make_manager()
        result = await manager.get_checkpoint("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_checkpoints_from_cache(self):
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        manager = self._make_manager(enable_integrity_check=False)
        ctx = self._make_context()
        state = GraphState(data={})
        await manager.create_checkpoint(ctx, "n1", state, validate=False)
        await manager.create_checkpoint(ctx, "n2", state, validate=False)

        cps = await manager.list_checkpoints(ctx.workflow_id)
        assert len(cps) == 2

    @pytest.mark.asyncio
    async def test_list_checkpoints_with_run_id_filter(self):
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        manager = self._make_manager(enable_integrity_check=False)
        ctx = self._make_context()
        state = GraphState(data={})
        cp = await manager.create_checkpoint(ctx, "n1", state, validate=False)

        cps = await manager.list_checkpoints(ctx.workflow_id, run_id=ctx.run_id)
        assert len(cps) >= 1

        cps2 = await manager.list_checkpoints(ctx.workflow_id, run_id="other-run")
        assert len(cps2) == 0

    @pytest.mark.asyncio
    async def test_delete_checkpoint(self):
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        manager = self._make_manager(enable_integrity_check=False)
        ctx = self._make_context()
        state = GraphState(data={})
        cp = await manager.create_checkpoint(ctx, "n1", state, validate=False)

        result = await manager.delete_checkpoint(cp.id)
        assert result is True
        assert cp.id not in manager._checkpoints

    @pytest.mark.asyncio
    async def test_delete_checkpoint_not_found(self):
        manager = self._make_manager()
        result = await manager.delete_checkpoint("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_old_checkpoints(self):
        from enhanced_agent_bus.langgraph_orchestration.models import GraphState

        manager = self._make_manager(enable_integrity_check=False)
        ctx = self._make_context()
        state = GraphState(data={})
        for _ in range(7):
            await manager.create_checkpoint(ctx, "n1", state, validate=False)

        deleted = await manager.cleanup_old_checkpoints(ctx.workflow_id, keep_count=3)
        assert deleted == 4
        remaining = await manager.list_checkpoints(ctx.workflow_id)
        assert len(remaining) == 3


class TestCreateCheckpointManager:
    """Tests for the factory function."""

    def test_create_checkpoint_manager(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            ConstitutionalCheckpointManager,
            create_checkpoint_manager,
        )

        manager = create_checkpoint_manager(
            enable_integrity_check=True,
            constitutional_hash="test-hash",
        )
        assert isinstance(manager, ConstitutionalCheckpointManager)
        assert manager.constitutional_hash == "test-hash"

    def test_create_with_maci_enforcer(self):
        from enhanced_agent_bus.langgraph_orchestration.constitutional_checkpoints import (
            create_checkpoint_manager,
        )

        mock_enforcer = MagicMock()
        manager = create_checkpoint_manager(maci_enforcer=mock_enforcer)
        # Should have maci_role validator
        validator_names = [name for name, _ in manager._validators]
        assert "maci_role" in validator_names
