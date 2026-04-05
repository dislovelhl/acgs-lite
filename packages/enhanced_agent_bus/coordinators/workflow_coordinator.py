"""
Workflow Coordinator - Manages LangGraph workflow execution and evolution.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_WORKFLOW_COORDINATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class WorkflowCoordinator:
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(self, enable_evolution: bool = True, saga_enabled: bool = True):
        self._enable_evolution = enable_evolution
        self._saga_enabled = saga_enabled
        self._workflow_engine: object | None = None
        self._evolution_engine: object | None = None
        self._initialized = False
        self._active_workflows: dict[str, JSONDict] = {}

        self._initialize_engines()

    def _initialize_engines(self) -> None:
        try:
            from ..langgraph_orchestrator import create_governance_workflow

            self._workflow_engine = create_governance_workflow()
            self._initialized = True
            logger.info("WorkflowCoordinator: LangGraph initialized")
        except ImportError:
            logger.info("LangGraph not available, using basic workflow execution")
        except _WORKFLOW_COORDINATOR_OPERATION_ERRORS as e:
            logger.warning(f"LangGraph init failed: {e}")

        if self._enable_evolution:
            try:
                from ..workflow_evolution import create_workflow_engine

                self._evolution_engine = create_workflow_engine(
                    constitutional_hash=self.constitutional_hash,
                )
                logger.info("WorkflowCoordinator: Evolution engine initialized")
            except ImportError:
                logger.info("Workflow evolution not available")
            except _WORKFLOW_COORDINATOR_OPERATION_ERRORS as e:
                logger.warning(f"Evolution engine init failed: {e}")

    @property
    def is_langgraph_available(self) -> bool:
        return self._workflow_engine is not None

    @property
    def is_evolution_available(self) -> bool:
        return self._evolution_engine is not None

    async def execute_workflow(
        self,
        workflow_id: str,
        input_data: JSONDict,
        timeout_seconds: int = 300,
    ) -> JSONDict:
        execution_id = f"{workflow_id}-{len(self._active_workflows)}"

        self._active_workflows[execution_id] = {
            "workflow_id": workflow_id,
            "state": "running",
            "input": input_data,
        }

        try:
            if self._workflow_engine:
                result = await self._workflow_engine.execute(
                    workflow_id=workflow_id,
                    input_data=input_data,
                    timeout=timeout_seconds,
                )
                self._active_workflows[execution_id]["state"] = "completed"
                return {
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "state": "completed",
                    "result": result,
                    "constitutional_hash": self.constitutional_hash,
                }

            result = await self._execute_basic_workflow(workflow_id, input_data)
            self._active_workflows[execution_id]["state"] = "completed"
            return {
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "state": "completed",
                "result": result,
                "constitutional_hash": self.constitutional_hash,
            }

        except _WORKFLOW_COORDINATOR_OPERATION_ERRORS as e:
            self._active_workflows[execution_id]["state"] = "failed"
            self._active_workflows[execution_id]["error"] = str(e)

            if self._saga_enabled:
                await self._rollback_workflow(execution_id)

            return {
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "state": "failed",
                "error": str(e),
                "rolled_back": self._saga_enabled,
                "constitutional_hash": self.constitutional_hash,
            }

    async def _execute_basic_workflow(
        self,
        workflow_id: str,
        input_data: JSONDict,
    ) -> JSONDict:
        return {
            "workflow_id": workflow_id,
            "steps_completed": 1,
            "output": input_data,
        }

    async def _rollback_workflow(self, execution_id: str) -> None:
        logger.info(f"Rolling back workflow execution: {execution_id}")
        if execution_id in self._active_workflows:
            self._active_workflows[execution_id]["state"] = "rolled_back"

    async def evolve_workflow(
        self,
        workflow_id: str,
        feedback: JSONDict,
        strategy: str = "moderate",
    ) -> JSONDict:
        if not self._evolution_engine:
            return {
                "success": False,
                "reason": "Evolution engine not available",
                "constitutional_hash": self.constitutional_hash,
            }

        try:
            from ..workflow_evolution import OptimizationType

            proposal = await self._evolution_engine.propose_evolution(
                workflow_id=workflow_id,
                optimization_type=OptimizationType.LATENCY,
            )

            return {
                "success": True,
                "proposal_id": proposal.id if hasattr(proposal, "id") else "prop-1",
                "changes": proposal.changes if hasattr(proposal, "changes") else [],
                "risk_level": proposal.risk_level if hasattr(proposal, "risk_level") else "low",
                "constitutional_hash": self.constitutional_hash,
            }

        except _WORKFLOW_COORDINATOR_OPERATION_ERRORS as e:
            logger.error(f"Workflow evolution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "constitutional_hash": self.constitutional_hash,
            }

    def get_workflow_stats(self) -> JSONDict:
        states: dict[str, int] = {}
        for wf in self._active_workflows.values():
            state = wf.get("state", "unknown")
            states[state] = states.get(state, 0) + 1

        return {
            "constitutional_hash": self.constitutional_hash,
            "langgraph_available": self.is_langgraph_available,
            "evolution_available": self.is_evolution_available,
            "saga_enabled": self._saga_enabled,
            "active_workflows": len(self._active_workflows),
            "state_distribution": states,
        }
