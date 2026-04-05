"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- optimization_toolkit/cost.py (CostOptimizer)
- _ext_performance.py (Performance extension exports)
- _ext_context_optimization.py (Context optimization extension exports)
- _ext_circuit_breaker.py (Circuit breaker extension exports)
- agents/chatops_executor.py (ChatOps command executor)
- deliberation_layer/hitl_manager.py (HITL manager)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import enhanced_agent_bus._ext_circuit_breaker as ext_cb
import enhanced_agent_bus._ext_context_optimization as ext_ctx

# ---------------------------------------------------------------------------
# Extension module imports
# ---------------------------------------------------------------------------
import enhanced_agent_bus._ext_performance as ext_perf

# ---------------------------------------------------------------------------
# ChatOps executor imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.agents.chatops_executor import (
    REVIEW_DISPATCH_ERRORS,
    _dispatch_build_fix,
    handle_chatops_command,
)
from enhanced_agent_bus.core_models import AgentMessage, MessageType
from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
    DeliberationQueue,
    DeliberationStatus,
    DeliberationTask,
)

# ---------------------------------------------------------------------------
# HITL manager imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.hitl_manager import (
    HITLManager,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# CostOptimizer imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.optimization_toolkit.cost import (
    CostOptimizer,
    UsageRecord,
)


# ===========================================================================
# Section 1: CostOptimizer tests
# ===========================================================================
class TestUsageRecord:
    """Tests for the UsageRecord dataclass."""

    def test_usage_record_defaults(self):
        record = UsageRecord(model="claude-sonnet-4", tokens=1000, cost=0.003)
        assert record.model == "claude-sonnet-4"
        assert record.tokens == 1000
        assert record.cost == 0.003
        assert isinstance(record.timestamp, datetime)
        assert record.task_complexity is None

    def test_usage_record_with_complexity(self):
        record = UsageRecord(model="claude-opus-4", tokens=5000, cost=0.075, task_complexity=5)
        assert record.task_complexity == 5

    def test_usage_record_timestamp_is_utc(self):
        record = UsageRecord(model="gpt-4o", tokens=100, cost=0.0005)
        assert record.timestamp.tzinfo is not None


class TestCostOptimizerInit:
    """Tests for CostOptimizer initialization."""

    def test_default_init(self):
        opt = CostOptimizer()
        assert opt.monthly_budget == 100.0
        assert opt.daily_budget == pytest.approx(100.0 / 30)
        assert opt.total_cost == 0.0
        assert opt.usage_history == []

    def test_custom_budget(self):
        opt = CostOptimizer(monthly_budget=500.0)
        assert opt.monthly_budget == 500.0
        assert opt.daily_budget == pytest.approx(500.0 / 30)

    def test_custom_daily_budget(self):
        opt = CostOptimizer(monthly_budget=300.0, daily_budget=15.0)
        assert opt.daily_budget == 15.0

    def test_model_costs_are_copied(self):
        opt = CostOptimizer()
        opt.model_costs["custom-model"] = 99.0
        opt2 = CostOptimizer()
        assert "custom-model" not in opt2.model_costs


class TestCostOptimizerEstimate:
    """Tests for estimate_cost."""

    def test_known_model(self):
        opt = CostOptimizer()
        cost = opt.estimate_cost("claude-sonnet-4", 1_000_000)
        assert cost == pytest.approx(3.0)

    def test_unknown_model_defaults_to_3(self):
        opt = CostOptimizer()
        cost = opt.estimate_cost("unknown-model", 1_000_000)
        assert cost == pytest.approx(3.0)

    def test_zero_tokens(self):
        opt = CostOptimizer()
        cost = opt.estimate_cost("claude-opus-4", 0)
        assert cost == 0.0

    def test_haiku_is_cheapest(self):
        opt = CostOptimizer()
        haiku_cost = opt.estimate_cost("claude-haiku-4", 1_000_000)
        sonnet_cost = opt.estimate_cost("claude-sonnet-4", 1_000_000)
        assert haiku_cost < sonnet_cost

    def test_gpt4o_mini_cost(self):
        opt = CostOptimizer()
        cost = opt.estimate_cost("gpt-4o-mini", 1_000_000)
        assert cost == pytest.approx(0.15)


class TestCostOptimizerTrackUsage:
    """Tests for track_usage and record_usage."""

    def test_track_usage_returns_dict(self):
        opt = CostOptimizer()
        result = opt.track_usage("claude-sonnet-4", 500_000)
        assert result["model"] == "claude-sonnet-4"
        assert result["tokens"] == 500_000
        assert result["cost"] == pytest.approx(1.5)
        assert result["total_cost"] == pytest.approx(1.5)
        assert "budget_remaining" in result
        assert "constitutional_hash" in result

    def test_track_usage_accumulates(self):
        opt = CostOptimizer(monthly_budget=10.0)
        opt.track_usage("claude-haiku-4", 1_000_000)
        opt.track_usage("claude-haiku-4", 1_000_000)
        assert opt.total_cost == pytest.approx(0.5)
        assert len(opt.usage_history) == 2

    def test_record_usage_delegates_to_track(self):
        opt = CostOptimizer()
        opt.record_usage("claude-sonnet-4", 100_000)
        assert opt.total_cost > 0
        assert len(opt.usage_history) == 1

    def test_budget_remaining_decreases(self):
        opt = CostOptimizer(monthly_budget=10.0)
        r1 = opt.track_usage("claude-opus-4", 1_000_000)
        remaining = r1["budget_remaining"]
        assert remaining == pytest.approx(10.0 - 15.0)


class TestCostOptimizerSelectModel:
    """Tests for select_optimal_model and legacy select_model."""

    def test_high_quality_always_opus(self):
        opt = CostOptimizer()
        model = opt.select_optimal_model(task_complexity=1, quality_threshold=0.95)
        assert model == "claude-opus-4"

    def test_expert_complexity_returns_opus(self):
        opt = CostOptimizer()
        model = opt.select_optimal_model(task_complexity=5)
        assert model == "claude-opus-4"

    def test_complex_task_cost_sensitive_low_budget(self):
        opt = CostOptimizer(monthly_budget=100.0)
        # Burn ~60% of budget (budget_ratio ~ 0.4, below 0.5 but above 0.1)
        opt.total_cost = 60.0
        model = opt.select_optimal_model(task_complexity=4, cost_sensitive=True)
        assert model == "claude-sonnet-4"

    def test_complex_task_not_cost_sensitive(self):
        opt = CostOptimizer()
        model = opt.select_optimal_model(task_complexity=4, cost_sensitive=False)
        assert model == "claude-opus-4"

    def test_complex_task_cost_sensitive_high_budget(self):
        opt = CostOptimizer(monthly_budget=1000.0)
        model = opt.select_optimal_model(task_complexity=4, cost_sensitive=True)
        assert model == "claude-opus-4"

    def test_medium_complexity_returns_sonnet(self):
        opt = CostOptimizer()
        model = opt.select_optimal_model(task_complexity=3)
        assert model == "claude-sonnet-4"

    def test_simple_cost_sensitive_returns_haiku(self):
        opt = CostOptimizer()
        model = opt.select_optimal_model(task_complexity=2, cost_sensitive=True)
        assert model == "claude-haiku-4"

    def test_simple_not_cost_sensitive_returns_sonnet(self):
        opt = CostOptimizer()
        model = opt.select_optimal_model(task_complexity=2, cost_sensitive=False)
        assert model == "claude-sonnet-4"

    def test_trivial_returns_haiku(self):
        opt = CostOptimizer()
        model = opt.select_optimal_model(task_complexity=1)
        assert model == "claude-haiku-4"

    def test_emergency_budget_returns_haiku(self):
        opt = CostOptimizer(monthly_budget=10.0)
        # Burn 95% of budget
        opt.total_cost = 9.5
        model = opt.select_optimal_model(task_complexity=5)
        assert model == "claude-haiku-4"

    def test_legacy_select_model_low_complexity(self):
        opt = CostOptimizer()
        model = opt.select_model(task_complexity=0.1)
        assert model == "claude-haiku-4"

    def test_legacy_select_model_high_complexity(self):
        opt = CostOptimizer()
        model = opt.select_model(task_complexity=0.9)
        assert model in ("claude-opus-4", "claude-sonnet-4")

    def test_legacy_select_model_urgent(self):
        opt = CostOptimizer()
        model = opt.select_model(task_complexity=0.5, urgency=True)
        assert model == "claude-opus-4"

    def test_legacy_select_model_zero_complexity(self):
        opt = CostOptimizer()
        model = opt.select_model(task_complexity=0.0)
        assert model == "claude-haiku-4"

    def test_legacy_select_model_max_complexity(self):
        opt = CostOptimizer()
        model = opt.select_model(task_complexity=1.0)
        assert model == "claude-opus-4"


class TestCostOptimizerBudget:
    """Tests for budget status methods."""

    def test_is_within_budget_initial(self):
        opt = CostOptimizer()
        assert opt.is_within_budget() is True

    def test_is_within_budget_exhausted(self):
        opt = CostOptimizer(monthly_budget=1.0)
        opt.total_cost = 1.5
        assert opt.is_within_budget() is False

    def test_get_budget_status(self):
        opt = CostOptimizer(monthly_budget=100.0, daily_budget=5.0)
        opt.track_usage("claude-sonnet-4", 1_000_000)
        status = opt.get_budget_status()
        assert status["total_cost"] == pytest.approx(3.0)
        assert status["monthly_budget"] == 100.0
        assert status["daily_budget"] == 5.0
        assert status["remaining"] == pytest.approx(97.0)
        assert status["utilization_percent"] == pytest.approx(3.0)
        assert status["usage_records"] == 1
        assert "constitutional_hash" in status

    def test_budget_remaining_ratio_zero_budget(self):
        opt = CostOptimizer(monthly_budget=0.0)
        assert opt._get_budget_remaining_ratio() == 0.0

    def test_budget_remaining_ratio_negative(self):
        opt = CostOptimizer(monthly_budget=10.0)
        opt.total_cost = 20.0
        assert opt._get_budget_remaining_ratio() == 0.0

    def test_get_cost_report_via_budget_status(self):
        opt = CostOptimizer(monthly_budget=50.0)
        opt.record_usage("claude-haiku-4", 2_000_000)
        opt.record_usage("claude-sonnet-4", 1_000_000)
        status = opt.get_budget_status()
        assert status["usage_records"] == 2
        assert status["total_cost"] == pytest.approx(0.5 + 3.0)


# ===========================================================================
# Section 2: Extension module tests
# ===========================================================================
class TestExtPerformance:
    """Tests for _ext_performance.py module exports."""

    def test_module_has_all_attribute(self):
        assert hasattr(ext_perf, "__all__")
        assert len(ext_perf.__all__) > 0

    def test_ext_all_attribute(self):
        assert hasattr(ext_perf, "_EXT_ALL")
        assert ext_perf._EXT_ALL == ext_perf.__all__

    def test_availability_flag_exists(self):
        assert hasattr(ext_perf, "PERFORMANCE_OPTIMIZATION_AVAILABLE")
        assert isinstance(ext_perf.PERFORMANCE_OPTIMIZATION_AVAILABLE, bool)

    def test_pipeline_stage_exported(self):
        assert hasattr(ext_perf, "PipelineStage")

    def test_pipeline_result_exported(self):
        assert hasattr(ext_perf, "PipelineResult")

    def test_async_pipeline_optimizer_exported(self):
        assert hasattr(ext_perf, "AsyncPipelineOptimizer")

    def test_resource_pool_exported(self):
        assert hasattr(ext_perf, "ResourcePool")

    def test_memory_optimizer_exported(self):
        assert hasattr(ext_perf, "MemoryOptimizer")

    def test_batch_config_exported(self):
        assert hasattr(ext_perf, "BatchConfig")

    def test_latency_reducer_exported(self):
        assert hasattr(ext_perf, "LatencyReducer")

    def test_factory_functions_exported(self):
        for name in [
            "create_async_pipeline",
            "create_resource_pool",
            "create_memory_optimizer",
            "create_latency_reducer",
        ]:
            assert hasattr(ext_perf, name)

    def test_all_names_resolve(self):
        for name in ext_perf.__all__:
            assert hasattr(ext_perf, name), f"Missing export: {name}"


class TestExtContextOptimization:
    """Tests for _ext_context_optimization.py module exports."""

    def test_module_has_all_attribute(self):
        assert hasattr(ext_ctx, "__all__")
        assert len(ext_ctx.__all__) > 0

    def test_ext_all_attribute(self):
        assert hasattr(ext_ctx, "_EXT_ALL")
        assert ext_ctx._EXT_ALL == ext_ctx.__all__

    def test_availability_flag_exists(self):
        assert hasattr(ext_ctx, "CONTEXT_OPTIMIZATION_AVAILABLE")
        assert isinstance(ext_ctx.CONTEXT_OPTIMIZATION_AVAILABLE, bool)

    def test_compression_types_exported(self):
        assert hasattr(ext_ctx, "CompressionStrategy")
        assert hasattr(ext_ctx, "CompressionResult")
        assert hasattr(ext_ctx, "SpecBaseline")
        assert hasattr(ext_ctx, "SpecDeltaCompressor")

    def test_governance_types_exported(self):
        assert hasattr(ext_ctx, "GovernanceDecision")
        assert hasattr(ext_ctx, "ValidationContext")
        assert hasattr(ext_ctx, "GovernanceValidatorProtocol")
        assert hasattr(ext_ctx, "CachedGovernanceValidator")

    def test_optimized_bus_types_exported(self):
        assert hasattr(ext_ctx, "TopicPriority")
        assert hasattr(ext_ctx, "TopicConfig")
        assert hasattr(ext_ctx, "PartitionedMessage")
        assert hasattr(ext_ctx, "PartitionBroker")
        assert hasattr(ext_ctx, "OptimizedAgentBus")

    def test_factory_functions_exported(self):
        for name in [
            "create_spec_compressor",
            "create_cached_validator",
            "create_optimized_bus",
        ]:
            assert hasattr(ext_ctx, name)

    def test_all_names_resolve(self):
        for name in ext_ctx.__all__:
            assert hasattr(ext_ctx, name), f"Missing export: {name}"


class TestExtCircuitBreaker:
    """Tests for _ext_circuit_breaker.py module exports."""

    def test_ext_all_attribute(self):
        assert hasattr(ext_cb, "_EXT_ALL")
        assert len(ext_cb._EXT_ALL) > 0

    def test_availability_flag_exists(self):
        assert hasattr(ext_cb, "SERVICE_CIRCUIT_BREAKER_AVAILABLE")
        assert isinstance(ext_cb.SERVICE_CIRCUIT_BREAKER_AVAILABLE, bool)

    def test_circuit_state_exported(self):
        assert hasattr(ext_cb, "CircuitState")

    def test_circuit_breaker_types_exported(self):
        assert hasattr(ext_cb, "ServiceCircuitBreaker")
        assert hasattr(ext_cb, "ServiceCircuitBreakerRegistry")
        assert hasattr(ext_cb, "ServiceCircuitConfig")
        assert hasattr(ext_cb, "CircuitBreakerMetrics")
        assert hasattr(ext_cb, "CircuitBreakerOpen")

    def test_severity_and_fallback_exported(self):
        assert hasattr(ext_cb, "ServiceSeverity")
        assert hasattr(ext_cb, "FallbackStrategy")
        assert hasattr(ext_cb, "QueuedRequest")

    def test_service_configs_exported(self):
        assert hasattr(ext_cb, "SERVICE_CIRCUIT_CONFIGS")

    def test_functions_exported(self):
        for name in [
            "get_service_config",
            "get_service_circuit_breaker",
            "get_circuit_breaker_registry",
            "reset_circuit_breaker_registry",
            "with_service_circuit_breaker",
            "create_circuit_health_router",
        ]:
            assert hasattr(ext_cb, name)

    def test_all_names_resolve(self):
        for name in ext_cb._EXT_ALL:
            assert hasattr(ext_cb, name), f"Missing export: {name}"


# ===========================================================================
# Section 3: ChatOps executor tests
# ===========================================================================
def _make_chatops_msg(command_body: str, author: str = "testuser") -> AgentMessage:
    """Helper to build a ChatOps command message."""
    return AgentMessage(
        from_agent="github_app_proposer",
        to_agent="chatops_executor",
        message_type=MessageType.COMMAND,
        content={
            "command_body": command_body,
            "author": author,
            "issue_number": 42,
        },
    )


class TestHandleChatopsCommand:
    """Tests for handle_chatops_command dispatch."""

    async def test_wrong_target_returns_none(self):
        msg = AgentMessage(
            from_agent="x",
            to_agent="wrong_target",
            message_type=MessageType.COMMAND,
            content={"command_body": "/acgs-build-fix"},
        )
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_wrong_message_type_returns_none(self):
        msg = AgentMessage(
            from_agent="x",
            to_agent="chatops_executor",
            message_type=MessageType.RESPONSE,
            content={"command_body": "/acgs-build-fix"},
        )
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_non_dict_content_returns_none(self):
        msg = AgentMessage(
            from_agent="x",
            to_agent="chatops_executor",
            message_type=MessageType.COMMAND,
            content="not a dict",
        )
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_build_fix_dispatches(self):
        msg = _make_chatops_msg("/acgs-build-fix --all")
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result.to_agent == "build_fix_swarm"
        assert result.content["action"] == "execute_build_fix"
        assert result.content["issue_number"] == 42
        assert result.content["author"] == "testuser"

    async def test_unrecognized_command_returns_original(self):
        msg = _make_chatops_msg("/unknown-command")
        result = await handle_chatops_command(msg)
        assert result is msg

    async def test_empty_command_body(self):
        msg = _make_chatops_msg("")
        result = await handle_chatops_command(msg)
        assert result is msg

    async def test_review_dispatch_import_error(self):
        """Review dispatch falls back to None on ImportError."""
        msg = _make_chatops_msg("/acgs-review")
        with patch(
            "enhanced_agent_bus.agents.chatops_executor._dispatch_review",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await handle_chatops_command(msg)
        assert result is None

    async def test_review_dispatch_mcp_failure(self):
        """Review command returns None when MCP client fails."""
        msg = _make_chatops_msg("/acgs-review pr-123")
        # _dispatch_review catches all exceptions internally
        with patch(
            "enhanced_agent_bus.agents.chatops_executor._dispatch_review",
            new_callable=AsyncMock,
            side_effect=None,
            return_value=None,
        ):
            result = await handle_chatops_command(msg)
        assert result is None


class TestDispatchBuildFix:
    """Tests for _dispatch_build_fix."""

    def test_returns_agent_message(self):
        result = _dispatch_build_fix(
            issue_number=10, author="dev", command_body="/acgs-build-fix --verbose"
        )
        assert isinstance(result, AgentMessage)
        assert result.from_agent == "chatops_executor"
        assert result.to_agent == "build_fix_swarm"
        assert result.message_type == MessageType.TASK_REQUEST
        assert result.content["issue_number"] == 10
        assert result.content["command_body"] == "/acgs-build-fix --verbose"

    def test_none_issue_number(self):
        result = _dispatch_build_fix(
            issue_number=None, author="dev", command_body="/acgs-build-fix"
        )
        assert result.content["issue_number"] is None


class TestDispatchComplianceIngest:
    """Tests for _dispatch_compliance_ingest."""

    async def test_missing_dependency_returns_none(self):
        with patch(
            "enhanced_agent_bus.agents.chatops_executor.questionnaire_responder",
            None,
        ):
            msg = _make_chatops_msg("/acgs-compliance-ingest file.csv tenant1")
            result = await handle_chatops_command(msg)
        assert result is None

    async def test_invalid_args_returns_none(self):
        mock_responder = MagicMock()
        with patch(
            "enhanced_agent_bus.agents.chatops_executor.questionnaire_responder",
            mock_responder,
        ):
            msg = _make_chatops_msg("/acgs-compliance-ingest")
            result = await handle_chatops_command(msg)
        assert result is None

    async def test_successful_ingest(self):
        mock_responder = MagicMock()
        mock_responder.ingest_questionnaire.return_value = {"job_id": "job-123"}
        with patch(
            "enhanced_agent_bus.agents.chatops_executor.questionnaire_responder",
            mock_responder,
        ):
            msg = _make_chatops_msg("/acgs-compliance-ingest report.csv tenant-abc")
            result = await handle_chatops_command(msg)
        assert result is not None
        assert result.content["job_id"] == "job-123"
        assert result.content["status"] == "success"
        assert result.to_agent == "github_app_proposer"

    async def test_ingest_value_error_returns_none(self):
        mock_responder = MagicMock()
        mock_responder.ingest_questionnaire.side_effect = ValueError("bad input")
        with patch(
            "enhanced_agent_bus.agents.chatops_executor.questionnaire_responder",
            mock_responder,
        ):
            msg = _make_chatops_msg("/acgs-compliance-ingest report.csv tenant-abc")
            result = await handle_chatops_command(msg)
        assert result is None


class TestReviewDispatchErrors:
    """Tests for the REVIEW_DISPATCH_ERRORS tuple."""

    def test_contains_expected_errors(self):
        assert ConnectionError in REVIEW_DISPATCH_ERRORS
        assert ImportError in REVIEW_DISPATCH_ERRORS
        assert RuntimeError in REVIEW_DISPATCH_ERRORS
        assert TimeoutError in REVIEW_DISPATCH_ERRORS
        assert ValueError in REVIEW_DISPATCH_ERRORS
        assert OSError in REVIEW_DISPATCH_ERRORS


# ===========================================================================
# Section 4: HITL Manager tests
# ===========================================================================
class TestHITLManagerInit:
    """Tests for HITLManager initialization."""

    def test_init_with_queue(self):
        queue = DeliberationQueue()
        mgr = HITLManager(deliberation_queue=queue)
        assert mgr.queue is queue
        assert mgr.audit_ledger is not None

    def test_init_with_custom_audit_ledger(self):
        queue = DeliberationQueue()
        ledger = MagicMock()
        mgr = HITLManager(deliberation_queue=queue, audit_ledger=ledger)
        assert mgr.audit_ledger is ledger


class TestHITLRequestApproval:
    """Tests for HITLManager.request_approval."""

    async def test_request_approval_item_not_found(self):
        queue = DeliberationQueue()
        mgr = HITLManager(deliberation_queue=queue)
        # No items in queue, should log error and return
        await mgr.request_approval("nonexistent-id")
        # No exception raised

    async def test_request_approval_sets_under_review(self):
        queue = DeliberationQueue()
        msg = AgentMessage(
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.COMMAND,
            content={"action": "deploy"},
            impact_score=0.9,
        )
        task_id = await queue.enqueue_for_deliberation(msg)
        mgr = HITLManager(deliberation_queue=queue)

        await mgr.request_approval(task_id, channel="slack")

        task = queue.queue[task_id]
        assert task.status == DeliberationStatus.UNDER_REVIEW
        await queue.stop()

    async def test_request_approval_teams_channel(self):
        queue = DeliberationQueue()
        msg = AgentMessage(
            from_agent="agent-x",
            to_agent="agent-y",
            message_type=MessageType.TASK_REQUEST,
            content={"action": "scale"},
            impact_score=0.8,
        )
        task_id = await queue.enqueue_for_deliberation(msg)
        mgr = HITLManager(deliberation_queue=queue)

        await mgr.request_approval(task_id, channel="teams")
        task = queue.queue[task_id]
        assert task.status == DeliberationStatus.UNDER_REVIEW
        await queue.stop()


class TestHITLProcessApproval:
    """Tests for HITLManager.process_approval."""

    async def _setup_under_review(self) -> tuple[DeliberationQueue, str, HITLManager]:
        """Helper: create queue with one item set to UNDER_REVIEW."""
        queue = DeliberationQueue()
        msg = AgentMessage(
            from_agent="agent-a",
            to_agent="agent-b",
            message_type=MessageType.COMMAND,
            content={"action": "deploy"},
            impact_score=0.95,
        )
        task_id = await queue.enqueue_for_deliberation(msg)
        # Set to UNDER_REVIEW so submit_human_decision accepts it
        queue.queue[task_id].status = DeliberationStatus.UNDER_REVIEW

        ledger = AsyncMock()
        ledger.add_validation_result = AsyncMock(return_value="audit-hash-123")
        mgr = HITLManager(deliberation_queue=queue, audit_ledger=ledger)
        return queue, task_id, mgr

    async def test_approve_decision(self):
        queue, task_id, mgr = await self._setup_under_review()
        success = await mgr.process_approval(
            item_id=task_id,
            reviewer_id="reviewer-1",
            decision="approve",
            reasoning="Looks good",
        )
        assert success is True
        assert queue.queue[task_id].status == DeliberationStatus.APPROVED
        await queue.stop()

    async def test_reject_decision(self):
        queue, task_id, mgr = await self._setup_under_review()
        success = await mgr.process_approval(
            item_id=task_id,
            reviewer_id="reviewer-2",
            decision="reject",
            reasoning="Too risky",
        )
        assert success is True
        assert queue.queue[task_id].status == DeliberationStatus.REJECTED
        await queue.stop()

    async def test_approve_records_audit(self):
        queue, task_id, mgr = await self._setup_under_review()
        await mgr.process_approval(
            item_id=task_id,
            reviewer_id="reviewer-1",
            decision="approve",
            reasoning="Approved after review",
        )
        mgr.audit_ledger.add_validation_result.assert_awaited_once()
        call_args = mgr.audit_ledger.add_validation_result.call_args
        audit_res = call_args[0][0]
        assert audit_res.is_valid is True
        assert audit_res.metadata["reviewer"] == "reviewer-1"
        assert audit_res.metadata["decision"] == "approve"
        await queue.stop()

    async def test_reject_records_audit_invalid(self):
        queue, task_id, mgr = await self._setup_under_review()
        await mgr.process_approval(
            item_id=task_id,
            reviewer_id="reviewer-2",
            decision="reject",
            reasoning="Denied",
        )
        call_args = mgr.audit_ledger.add_validation_result.call_args
        audit_res = call_args[0][0]
        assert audit_res.is_valid is False
        await queue.stop()

    async def test_decision_on_nonexistent_item_returns_false(self):
        queue = DeliberationQueue()
        ledger = AsyncMock()
        mgr = HITLManager(deliberation_queue=queue, audit_ledger=ledger)
        success = await mgr.process_approval(
            item_id="missing-id",
            reviewer_id="reviewer",
            decision="approve",
            reasoning="n/a",
        )
        assert success is False

    async def test_decision_on_already_completed_item(self):
        queue, task_id, mgr = await self._setup_under_review()
        # First approval
        await mgr.process_approval(
            item_id=task_id,
            reviewer_id="r1",
            decision="approve",
            reasoning="ok",
        )
        # Second attempt on already-completed item
        success = await mgr.process_approval(
            item_id=task_id,
            reviewer_id="r2",
            decision="reject",
            reasoning="too late",
        )
        assert success is False
        await queue.stop()

    async def test_decision_on_pending_item_returns_false(self):
        """A pending item (not UNDER_REVIEW) should not accept decisions."""
        queue = DeliberationQueue()
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            message_type=MessageType.COMMAND,
            content={},
        )
        task_id = await queue.enqueue_for_deliberation(msg)
        # Item is PENDING, not UNDER_REVIEW
        ledger = AsyncMock()
        mgr = HITLManager(deliberation_queue=queue, audit_ledger=ledger)
        success = await mgr.process_approval(
            item_id=task_id,
            reviewer_id="r1",
            decision="approve",
            reasoning="should fail",
        )
        assert success is False
        await queue.stop()


class TestValidationResultFallback:
    """Tests for the fallback ValidationResult used in HITL."""

    def test_validation_result_defaults(self):
        vr = ValidationResult()
        assert vr.is_valid is True
        assert vr.errors == []
        assert vr.warnings == []

    def test_validation_result_custom(self):
        vr = ValidationResult(
            is_valid=False,
            metadata={"key": "value"},
        )
        assert vr.is_valid is False
        assert vr.metadata["key"] == "value"

    def test_to_dict(self):
        vr = ValidationResult(is_valid=True, metadata={"a": 1})
        d = vr.to_dict()
        assert d["is_valid"] is True
        assert d["metadata"]["a"] == 1
        assert "constitutional_hash" in d

    def test_add_error(self):
        vr = ValidationResult()
        vr.add_error("something went wrong")
        assert vr.is_valid is False
        assert "something went wrong" in vr.errors
