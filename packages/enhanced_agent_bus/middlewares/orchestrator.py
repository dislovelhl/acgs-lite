"""
OrchestratorMiddleware — Sprint 6.

Routes HIGH/CRITICAL impact governance decisions through the HierarchicalOrchestrator
so that complex, multi-step deliberation is handled by the supervisor-worker topology
rather than the fast lane.

Design notes:
- fail_closed=False (fail-open): orchestration failures never block the pipeline
- Routing trigger: impact_score >= 0.8 OR ImpactLevel.HIGH/CRITICAL
- Downstream middleware is called first; orchestration runs on the validated context
- orchestration_result and orchestrator_used are set on PipelineContext

Constitutional Hash: 608508a9bd224290
NIST 800-53 SI-7, AU-2 — Integrity checks, Audit events
"""

from __future__ import annotations

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..adaptive_governance.models import ImpactLevel
from ..orchestration.hierarchical import (
    HierarchicalOrchestrator,
    SupervisorNode,
    WorkerNode,
)
from ..pipeline.context import PipelineContext
from ..pipeline.middleware import BaseMiddleware, MiddlewareConfig

logger = get_logger(__name__)
# Matches HITL trigger threshold (CLAUDE.md governance constants)
ORCHESTRATION_THRESHOLD: float = 0.8

_HIGH_IMPACT_LEVELS: frozenset[ImpactLevel] = frozenset({ImpactLevel.HIGH, ImpactLevel.CRITICAL})


def _build_default_orchestrator() -> HierarchicalOrchestrator:
    """Build a two-worker HierarchicalOrchestrator for deliberation routing."""
    supervisor = SupervisorNode(
        supervisor_id="governance-supervisor",
        llm_client=None,
        critique_enabled=True,
        require_handoff_contract=True,
    )
    # Include "generic" so select_worker matches tasks with default task_type="generic"
    supervisor.register_worker(
        "deliberation-worker-1", ["governance", "deliberation", "generic"], capacity=5
    )
    supervisor.register_worker(
        "deliberation-worker-2", ["governance", "review", "generic"], capacity=5
    )

    orchestrator = HierarchicalOrchestrator(supervisor=supervisor)
    orchestrator.register_worker(
        WorkerNode(
            worker_id="deliberation-worker-1",
            capabilities=["governance", "deliberation", "generic"],
            capacity=5,
        )
    )
    orchestrator.register_worker(
        WorkerNode(
            worker_id="deliberation-worker-2",
            capabilities=["governance", "review", "generic"],
            capacity=5,
        )
    )
    return orchestrator


class OrchestratorMiddleware(BaseMiddleware):
    """Route high-impact governance decisions through HierarchicalOrchestrator.

    Fail-open: any exception during orchestration is logged and swallowed;
    the pipeline continues with ``orchestrator_used=False``.

    Args:
        config: Optional middleware configuration (defaults to fail-open, 500 ms timeout).
        orchestrator: Optional pre-built orchestrator (defaults to a two-worker instance).
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        orchestrator: HierarchicalOrchestrator | None = None,
    ) -> None:
        super().__init__(config or MiddlewareConfig(timeout_ms=500, fail_closed=False))
        self._orchestrator = orchestrator or _build_default_orchestrator()

    def _should_orchestrate(self, context: PipelineContext) -> bool:
        """Return True when the message warrants hierarchical deliberation."""
        if context.impact_score >= ORCHESTRATION_THRESHOLD:
            return True
        decision = context.governance_decision
        return bool(decision is not None and decision.impact_level in _HIGH_IMPACT_LEVELS)

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Run downstream middleware, then conditionally route through orchestrator."""
        context.add_middleware("OrchestratorMiddleware")

        if not self._should_orchestrate(context):
            return await self._call_next(context)

        # Always call downstream first to capture full governance context
        context = await self._call_next(context)

        goal = (
            f"Deliberate governance decision for message: "
            f"{getattr(context.message, 'content', str(context.message))[:200]}"
        )
        orchestration_ctx = {
            "impact_score": context.impact_score,
            "middleware_path": list(context.middleware_path),
            "governance_allowed": context.governance_allowed,
            "steps": ["assess_risk", "apply_policy", "produce_decision"],
        }

        try:
            result = await self._orchestrator.execute_goal(
                goal=goal,
                context=orchestration_ctx,
            )
            context.orchestration_result = result
            context.orchestrator_used = True
            logger.info(
                "OrchestratorMiddleware: completed deliberation (completed=%s, failed=%s)",
                result.get("completed_tasks"),
                result.get("failed_tasks"),
            )
        except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
            logger.warning(
                "OrchestratorMiddleware: orchestration failed, continuing: %s",
                exc,
            )

        return context
