"""
Swarm Intelligence - Swarm Coordinator

Central swarm coordination engine for agent lifecycle and task management.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .capabilities import CapabilityMatcher
from .consensus import ConsensusMechanism
from .enums import AgentState, ConsensusType, TaskPriority
from .message_bus import MessageBus
from .models import AgentCapability, ConsensusProposal, SwarmAgent, SwarmTask
from .task_decomposer import TaskDecomposer

logger = get_logger(__name__)
# Configuration constants
MAX_TASK_DESCRIPTION_LENGTH = 10000
MAX_ASSIGN_ITERATIONS = 1000
MIN_AGENT_NAME_LENGTH = 1
MAX_AGENT_NAME_LENGTH = 255


class SwarmCoordinator:
    """
    Central swarm coordination engine.

    Manages agent lifecycle, task distribution, and swarm health.
    """

    def __init__(
        self,
        max_agents: int = 8,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.max_agents = max_agents
        self._constitutional_hash = constitutional_hash

        # Thread safety lock for shared state mutations
        self._lock = asyncio.Lock()

        # Core components (protected by _lock)
        self._agents: dict[str, SwarmAgent] = {}
        self._tasks: dict[str, SwarmTask] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()

        # Utilities
        self._decomposer = TaskDecomposer()
        self._matcher = CapabilityMatcher()
        self._consensus = ConsensusMechanism()
        self._message_bus = MessageBus()

        # Metrics (protected by _lock)
        self._metrics = {
            "agents_spawned": 0,
            "agents_terminated": 0,
            "tasks_submitted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "consensus_proposals": 0,
            "messages_sent": 0,
        }

    async def spawn_agent(
        self,
        name: str,
        capabilities: list[AgentCapability],
    ) -> SwarmAgent | None:
        """
        Spawn a new agent in the swarm.

        Args:
            name: Agent name (1-255 characters).
            capabilities: List of agent capabilities.

        Returns:
            The spawned agent, or None if max agents reached.

        Raises:
            ValueError: If name or capabilities are invalid.
        """
        # Input validation
        if not name or len(name) < MIN_AGENT_NAME_LENGTH:
            raise ACGSValidationError(
                f"Agent name must be at least {MIN_AGENT_NAME_LENGTH} character",
                error_code="SWARM_AGENT_NAME_TOO_SHORT",
            )
        if len(name) > MAX_AGENT_NAME_LENGTH:
            raise ACGSValidationError(
                f"Agent name must not exceed {MAX_AGENT_NAME_LENGTH} characters",
                error_code="SWARM_AGENT_NAME_TOO_LONG",
            )
        if not capabilities:
            raise ACGSValidationError(
                "At least one capability is required",
                error_code="SWARM_NO_CAPABILITIES",
            )

        async with self._lock:
            if len(self._agents) >= self.max_agents:
                logger.warning(f"Max agents ({self.max_agents}) reached, cannot spawn")
                return None

            agent = SwarmAgent(
                id=str(uuid4()),
                name=name,
                capabilities=capabilities,
                state=AgentState.READY,
            )

            self._agents[agent.id] = agent
            self._metrics["agents_spawned"] += 1

        logger.info(f"Spawned agent: {name} ({agent.id}) with {len(capabilities)} capabilities")
        return agent

    async def terminate_agent(self, agent_id: str) -> bool:
        """
        Terminate an agent.

        Args:
            agent_id: The ID of the agent to terminate.

        Returns:
            True if the agent was terminated, False if not found.
        """
        async with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False

            agent.state = AgentState.TERMINATED
            del self._agents[agent_id]
            self._metrics["agents_terminated"] += 1

        logger.info(f"Terminated agent: {agent.name} ({agent_id})")
        return True

    async def submit_task(
        self,
        description: str,
        required_capabilities: list[str],
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: list[str] | None = None,
        decompose: bool = True,
    ) -> str:
        """
        Submit a task to the swarm.

        Args:
            description: Task description (1-10000 characters).
            required_capabilities: List of required capability names.
            priority: Task priority level.
            dependencies: Optional list of task IDs this task depends on.
            decompose: Whether to decompose into subtasks.

        Returns:
            The task ID.

        Raises:
            ValueError: If description or capabilities are invalid.
        """
        # Input validation
        if not description or len(description) < 1:
            raise ACGSValidationError(
                "Task description is required",
                error_code="SWARM_TASK_EMPTY",
            )
        if len(description) > MAX_TASK_DESCRIPTION_LENGTH:
            raise ACGSValidationError(
                f"Task description must not exceed {MAX_TASK_DESCRIPTION_LENGTH} characters",
                error_code="SWARM_TASK_TOO_LONG",
            )
        if not required_capabilities:
            raise ACGSValidationError(
                "At least one required capability must be specified",
                error_code="SWARM_TASK_NO_CAPABILITIES",
            )

        task = SwarmTask(
            id=str(uuid4()),
            description=description,
            required_capabilities=required_capabilities,
            priority=priority,
            dependencies=dependencies or [],
        )

        if decompose:
            subtasks = self._decomposer.decompose(task)
            if len(subtasks) > 1:
                # Store subtasks with lock
                async with self._lock:
                    for subtask in subtasks:
                        self._tasks[subtask.id] = subtask
                        await self._task_queue.put(subtask)
                    self._metrics["tasks_submitted"] += len(subtasks)
                return task.id

        async with self._lock:
            self._tasks[task.id] = task
            await self._task_queue.put(task)
            self._metrics["tasks_submitted"] += 1

        return task.id

    async def assign_tasks(self) -> int:
        """
        Assign pending tasks to available agents.

        Uses iteration limiting to prevent infinite loops when all tasks
        have unsatisfied dependencies.

        Returns:
            Number of tasks assigned.
        """
        assigned = 0
        seen_tasks: set = set()
        iterations = 0

        while not self._task_queue.empty() and iterations < MAX_ASSIGN_ITERATIONS:
            iterations += 1
            task = await self._task_queue.get()

            # Prevent infinite loop: if we've seen this task before
            # and it still can't be assigned, stop processing
            if task.id in seen_tasks:
                await self._task_queue.put(task)
                logger.debug("All remaining tasks have unmet dependencies, stopping assignment")
                break

            # Check dependencies
            if not self._dependencies_satisfied(task):
                seen_tasks.add(task.id)
                await self._task_queue.put(task)
                continue

            # Find best agent (with lock for reading agents)
            async with self._lock:
                available_agents = list(self._agents.values())
                agent = self._matcher.find_best_agent(task, available_agents)

                if agent:
                    task.assigned_agent = agent.id
                    task.started_at = datetime.now(UTC)
                    agent.state = AgentState.BUSY
                    agent.current_task = task.id
                    assigned += 1
                    logger.debug(f"Assigned task {task.id} to agent {agent.name}")
                else:
                    # No suitable agent, requeue
                    await self._task_queue.put(task)
                    break

        if iterations >= MAX_ASSIGN_ITERATIONS:
            logger.warning(f"Task assignment reached iteration limit ({MAX_ASSIGN_ITERATIONS})")

        return assigned

    def _dependencies_satisfied(self, task: SwarmTask) -> bool:
        """Check if all task dependencies are completed."""
        for dep_id in task.dependencies:
            dep_task = self._tasks.get(dep_id)
            if not dep_task or dep_task.completed_at is None:
                return False
        return True

    async def complete_task(
        self,
        task_id: str,
        result: object,
        error: str | None = None,
    ) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: The ID of the task to complete.
            result: The task result.
            error: Optional error message if task failed.

        Returns:
            True if the task was completed, False if not found.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            task.completed_at = datetime.now(UTC)
            task.result = result
            task.error = error

            # Update agent state
            if task.assigned_agent:
                agent = self._agents.get(task.assigned_agent)
                if agent:
                    agent.state = AgentState.READY
                    agent.current_task = None
                    if error:
                        agent.tasks_failed += 1
                        self._metrics["tasks_failed"] += 1
                    else:
                        agent.tasks_completed += 1
                        self._metrics["tasks_completed"] += 1

                    # Update execution time
                    if task.started_at:
                        exec_time = (task.completed_at - task.started_at).total_seconds()
                        agent.total_execution_time += exec_time

        return True

    async def request_consensus(
        self,
        proposer_id: str,
        action: str,
        context: JSONDict,
        consensus_type: ConsensusType = ConsensusType.MAJORITY,
    ) -> ConsensusProposal:
        """
        Request consensus from the swarm.

        Args:
            proposer_id: The ID of the proposing agent.
            action: The action being proposed.
            context: Context data for the proposal.
            consensus_type: Type of consensus required.

        Returns:
            The created consensus proposal.
        """
        proposal = await self._consensus.create_proposal(
            proposer_id=proposer_id,
            action=action,
            context=context,
            consensus_type=consensus_type,
        )

        async with self._lock:
            self._metrics["consensus_proposals"] += 1
            agent_ids = list(self._agents.keys())

        # Broadcast to all agents
        await self._message_bus.broadcast(
            sender_id=proposer_id,
            message_type="consensus_request",
            payload={
                "proposal_id": proposal.id,
                "action": action,
                "context": context,
            },
            recipients=agent_ids,
        )

        return proposal

    async def vote_on_consensus(
        self,
        proposal_id: str,
        voter_id: str,
        approve: bool,
    ) -> tuple[bool, bool | None]:
        """Vote on a consensus proposal and check result."""
        await self._consensus.vote(proposal_id, voter_id, approve)
        return self._consensus.check_consensus(proposal_id, len(self._agents))

    async def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        message_type: str,
        payload: JSONDict,
    ) -> str:
        """
        Send a message between agents.

        Args:
            sender_id: The sender agent ID.
            recipient_id: The recipient agent ID.
            message_type: Type of message.
            payload: Message payload.

        Returns:
            The message ID.
        """
        msg_id = await self._message_bus.send(
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            payload=payload,
        )
        async with self._lock:
            self._metrics["messages_sent"] += 1
        return msg_id

    async def broadcast_message(
        self,
        sender_id: str,
        message_type: str,
        payload: JSONDict,
    ) -> str:
        """
        Broadcast a message to all agents.

        Args:
            sender_id: The sender agent ID.
            message_type: Type of message.
            payload: Message payload.

        Returns:
            The message ID.
        """
        async with self._lock:
            agent_ids = list(self._agents.keys())
            agent_count = len(self._agents)

        msg_id = await self._message_bus.broadcast(
            sender_id=sender_id,
            message_type=message_type,
            payload=payload,
            recipients=agent_ids,
        )

        async with self._lock:
            self._metrics["messages_sent"] += agent_count

        return msg_id

    def get_agent(self, agent_id: str) -> SwarmAgent | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def get_task(self, task_id: str) -> SwarmTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_active_agents(self) -> list[SwarmAgent]:
        """Get all active agents."""
        return [a for a in self._agents.values() if a.state != AgentState.TERMINATED]

    def get_available_agents(self) -> list[SwarmAgent]:
        """Get all available (ready) agents."""
        return [a for a in self._agents.values() if a.state == AgentState.READY]

    # Health Monitoring v3.1
    async def check_agent_health(
        self,
        agent_id: str,
        max_task_duration_seconds: int = 600,
        max_heartbeat_age_seconds: int = 120,
    ) -> JSONDict:
        """
        Check health of an agent with self-healing detection.

        Returns health status and recommended action.
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return {"healthy": False, "status": "not_found", "action": "none"}

        health_issues = []
        action = "none"

        # Check if agent is in ERROR state
        if agent.state == AgentState.ERROR:
            health_issues.append("Agent in ERROR state")
            action = "terminate"

        # Check for stuck tasks (busy too long)
        if agent.state == AgentState.BUSY and agent.current_task:
            task = self._tasks.get(agent.current_task)
            if task and task.started_at:
                duration = (datetime.now(UTC) - task.started_at).total_seconds()
                if duration > max_task_duration_seconds:
                    health_issues.append(f"Task stuck for {duration:.0f}s")
                    action = "restart_task"

        # Check last activity (heartbeat)
        last_activity_age = (datetime.now(UTC) - agent.last_active).total_seconds()
        if last_activity_age > max_heartbeat_age_seconds:
            health_issues.append(f"No activity for {last_activity_age:.0f}s")
            action = "restart"

        # Check failure rate
        total_tasks = agent.tasks_completed + agent.tasks_failed
        if total_tasks > 5:
            failure_rate = agent.tasks_failed / total_tasks
            if failure_rate > 0.5:  # More than 50% failures
                health_issues.append(f"High failure rate: {failure_rate:.1%}")
                action = "terminate"

        healthy = len(health_issues) == 0

        return {
            "healthy": healthy,
            "status": "healthy" if healthy else "unhealthy",
            "issues": health_issues,
            "action": action,
            "agent_id": agent_id,
            "agent_name": agent.name,
            "state": agent.state.name if hasattr(agent.state, "name") else str(agent.state),
        }

    async def perform_self_healing(
        self,
        agent_id: str,
        health_result: JSONDict,
    ) -> bool:
        """
        Perform self-healing action based on health check.

        Args:
            agent_id: The ID of the agent to heal.
            health_result: The health check result containing the action.

        Returns:
            True if healing action was taken.
        """
        action = health_result.get("action")

        if action == "none":
            return False

        async with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False

            agent_name = agent.name
            logger.warning(f"Self-healing: {action} for agent {agent_name} ({agent_id})")

            if action == "terminate":
                # Mark agent as terminated (release lock first, terminate_agent acquires it)
                pass  # Will call terminate_agent outside lock

            elif action == "restart":
                # Mark as ready to accept new tasks (restart capability)
                agent.state = AgentState.READY
                agent.current_task = None
                return True

            elif action == "restart_task":
                # Requeue the stuck task
                if agent.current_task:
                    task = self._tasks.get(agent.current_task)
                    if task:
                        task.assigned_agent = None
                        task.started_at = None
                        task.retry_count += 1
                        await self._task_queue.put(task)

                agent.state = AgentState.READY
                agent.current_task = None
                return True

            else:
                return False

        # Handle terminate outside lock since terminate_agent acquires lock
        if action == "terminate":
            await self.terminate_agent(agent_id)
            return True

        return False

    async def run_health_checks(
        self,
        auto_heal: bool = True,
    ) -> list[JSONDict]:
        """
        Run health checks on all agents with optional auto-healing.

        Args:
            auto_heal: Whether to automatically perform healing actions.

        Returns:
            List of health check results.
        """
        results = []

        # Get snapshot of agent IDs to avoid modification during iteration
        async with self._lock:
            agent_ids = list(self._agents.keys())

        for agent_id in agent_ids:
            health = await self.check_agent_health(agent_id)
            results.append(health)

            if auto_heal and not health["healthy"]:
                await self.perform_self_healing(agent_id, health)

        return results

    async def update_agent_heartbeat(self, agent_id: str) -> bool:
        """
        Update heartbeat timestamp for an agent.

        Args:
            agent_id: The ID of the agent to update.

        Returns:
            True if updated, False if agent not found.
        """
        async with self._lock:
            agent = self._agents.get(agent_id)
            if agent:
                agent.last_active = datetime.now(UTC)
                return True
        return False

    def get_health_stats(self) -> JSONDict:
        """Get comprehensive health statistics for the swarm."""
        healthy_count = 0
        unhealthy_count = 0
        issues_summary: dict[str, int] = defaultdict(int)

        for _agent_id, agent in self._agents.items():
            # Simple health check without async
            is_healthy = agent.state not in [AgentState.ERROR, AgentState.TERMINATED]
            if is_healthy:
                healthy_count += 1
            else:
                unhealthy_count += 1
                issues_summary[f"state_{agent.state}"] += 1

        return {
            "healthy_agents": healthy_count,
            "unhealthy_agents": unhealthy_count,
            "total_agents": len(self._agents),
            "health_ratio": healthy_count / len(self._agents) if self._agents else 0.0,
            "issues_summary": dict(issues_summary),
        }

    def get_stats(self) -> JSONDict:
        """Get swarm statistics."""
        return {
            "total_agents": len(self._agents),
            "active_agents": len(self.get_active_agents()),
            "available_agents": len(self.get_available_agents()),
            "pending_tasks": self._task_queue.qsize(),
            "total_tasks": len(self._tasks),
            "metrics": self._metrics.copy(),
            "constitutional_hash": self._constitutional_hash,
        }

    async def get_dashboard_metrics(self) -> JSONDict:
        """
        Get comprehensive dashboard metrics for swarm health monitoring.

        Aggregates all swarm statistics into a unified dashboard view.
        """
        # Basic stats
        basic_stats = self.get_stats()
        health_stats = self.get_health_stats()

        # Calculate success rates
        total_completed = self._metrics["tasks_completed"] + self._metrics["tasks_failed"]
        task_success_rate = (
            self._metrics["tasks_completed"] / total_completed if total_completed > 0 else 0.0
        )

        # Get consensus stats
        consensus_stats = self._consensus.get_proposal_stats()

        # Get message bus stats
        message_stats = await self._message_bus.get_message_stats()

        # Calculate agent utilization
        busy_agents = len([a for a in self._agents.values() if a.state == AgentState.BUSY])
        utilization_rate = busy_agents / len(self._agents) if self._agents else 0.0

        # Task breakdown by status
        completed_tasks = [t for t in self._tasks.values() if t.completed_at is not None]
        failed_tasks = [t for t in self._tasks.values() if t.error is not None]
        pending_task_count = self._task_queue.qsize()

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": self._constitutional_hash,
            "version": "3.1",
            "agents": {
                "total": basic_stats["total_agents"],
                "active": basic_stats["active_agents"],
                "available": basic_stats["available_agents"],
                "busy": busy_agents,
                "healthy": health_stats["healthy_agents"],
                "unhealthy": health_stats["unhealthy_agents"],
                "health_ratio": health_stats["health_ratio"],
                "utilization_rate": utilization_rate,
            },
            "tasks": {
                "pending": pending_task_count,
                "total": len(self._tasks),
                "completed": len(completed_tasks),
                "failed": len(failed_tasks),
                "success_rate": task_success_rate,
            },
            "consensus": consensus_stats,
            "messaging": message_stats,
            "lifecycle": {
                "spawned": self._metrics["agents_spawned"],
                "terminated": self._metrics["agents_terminated"],
                "tasks_submitted": self._metrics["tasks_submitted"],
                "tasks_completed": self._metrics["tasks_completed"],
                "tasks_failed": self._metrics["tasks_failed"],
            },
            "health": health_stats,
        }

    async def shutdown(self) -> None:
        """Gracefully shutdown the swarm."""
        logger.info("Shutting down swarm coordinator")

        # Terminate all agents
        for agent_id in list(self._agents.keys()):
            await self.terminate_agent(agent_id)

        logger.info("Swarm coordinator shutdown complete")


# Factory function
def create_swarm_coordinator(
    max_agents: int = 8,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
) -> SwarmCoordinator:
    """Create a configured swarm coordinator."""
    return SwarmCoordinator(
        max_agents=max_agents,
        constitutional_hash=constitutional_hash,
    )


__all__ = [
    "SwarmCoordinator",
    "create_swarm_coordinator",
]
