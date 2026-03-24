"""
MACI Agent Registry with session-scoped support.

Maintains a mapping of agent IDs to their MACI roles and outputs.
Supports both global and session-scoped agent registration for multi-tenant scenarios.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..maci_imports import CONSTITUTIONAL_HASH
from ..observability.structured_logging import get_logger
from .models import (
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    VALIDATION_CONSTRAINTS,
    MACIAction,
    MACIRole,
)

logger = get_logger(__name__)


@dataclass
class MACIAgentRecord:
    """Record of a registered agent with its role and outputs.

    Tracks an agent's role assignment, outputs produced, and metadata.
    Supports session-scoped registration for multi-tenant scenarios.

    Attributes:
        agent_id: Unique agent identifier
        role: MACI role assigned to the agent
        outputs: list of output IDs produced by this agent
        registered_at: Timestamp when agent was registered
        metadata: Additional agent metadata
        constitutional_hash: Constitutional hash for validation
        session_id: Optional session identifier for session-scoped registration
    """

    agent_id: str
    role: MACIRole
    outputs: list[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    session_id: str | None = None  # Session identifier for session-aware MACI

    def can_perform(self, action: MACIAction) -> bool:
        """Check if agent can perform a specific action.

        Args:
            action: Action to check

        Returns:
            True if action is permitted for agent's role, False otherwise
        """
        return action in ROLE_PERMISSIONS.get(self.role, set())

    def can_validate_role(self, target_role: MACIRole) -> bool:
        """Check if agent can validate a target role.

        Args:
            target_role: Role to validate

        Returns:
            True if agent can validate the target role, False otherwise
        """
        return target_role in VALIDATION_CONSTRAINTS.get(self.role, set())

    def add_output(self, output_id: str) -> None:
        """Record an output produced by this agent.

        Args:
            output_id: Identifier of the output to record
        """
        if output_id not in self.outputs:
            self.outputs.append(output_id)

    def owns_output(self, output_id: str) -> bool:
        """Check if agent owns (produced) a specific output.

        Args:
            output_id: Output identifier to check

        Returns:
            True if agent produced this output, False otherwise
        """
        return output_id in self.outputs

    def validate_role(self, role: MACIRole) -> bool:
        """Check if agent's role matches a specific role.

        Args:
            role: Role to compare against

        Returns:
            True if agent's role matches, False otherwise
        """
        return self.role == role

    def has_sufficient_privilege(self, required_role: MACIRole) -> bool:
        """Check if agent has sufficient privilege compared to required role.

        Args:
            required_role: Required role for the operation

        Returns:
            True if agent's privilege level >= required role's level
        """
        return ROLE_HIERARCHY.get(self.role, 0) >= ROLE_HIERARCHY.get(required_role, 0)

    def to_audit_dict(self) -> JSONDict:
        """Convert to dictionary for audit logging with session context.

        Returns:
            Dictionary representation suitable for audit logs
        """
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "session_id": self.session_id,
            "registered_at": self.registered_at.isoformat(),
            "output_count": len(self.outputs),
            "constitutional_hash": self.constitutional_hash,
        }


class MACIRoleRegistry:
    """Registry for MACI agent roles with session-scoped support.

    Maintains a mapping of agent IDs to their MACI roles and outputs.
    Supports both global and session-scoped agent registration for multi-tenant
    scenarios. Thread-safe with asyncio.Lock.

    Attributes:
        constitutional_hash: Constitutional hash for validation
    """

    def __init__(self):
        """Initialize the MACI role registry."""
        self._agents: dict[str, MACIAgentRecord] = {}
        self._out_to_ag: dict[str, str] = {}
        self._session_out_to_ag: dict[str, dict[str, str]] = {}
        self._session_agents: dict[
            str, dict[str, MACIAgentRecord]
        ] = {}  # session_id -> {agent_id -> record}
        self._lock = asyncio.Lock()
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def _get_agent_locked(
        self,
        agent_id: str,
        session_id: str | None = None,
    ) -> MACIAgentRecord | None:
        if session_id is not None:
            return self._session_agents.get(session_id, {}).get(agent_id)
        return self._agents.get(agent_id)

    async def register_agent(
        self,
        agent_id: str,
        role: MACIRole,
        metadata: JSONDict | None = None,
        session_id: str | None = None,
    ) -> MACIAgentRecord:
        """Register an agent with optional session context.

        Args:
            agent_id: Unique agent identifier
            role: MACI role to assign
            metadata: Optional agent metadata (defaults to empty dict)
            session_id: Optional session identifier for session-scoped registration

        Returns:
            MACIAgentRecord for the registered agent
        """
        async with self._lock:
            # Ensure metadata is a valid dict
            safe_metadata: JSONDict = metadata if metadata is not None else {}
            rec = MACIAgentRecord(agent_id, role, metadata=safe_metadata, session_id=session_id)
            if session_id:
                if session_id not in self._session_agents:
                    self._session_agents[session_id] = {}
                if session_id not in self._session_out_to_ag:
                    self._session_out_to_ag[session_id] = {}
                self._session_agents[session_id][agent_id] = rec
                logger.debug(f"Registered agent {agent_id} with session {session_id}")
            else:
                self._agents[agent_id] = rec
            return rec

    async def unregister_agent(
        self,
        agent_id: str,
        session_id: str | None = None,
    ) -> MACIAgentRecord | None:
        """Unregister an agent from the registry.

        Args:
            agent_id: Agent identifier to unregister
            session_id: Optional session scope for session-registered agents

        Returns:
            MACIAgentRecord if agent was registered, None otherwise
        """
        async with self._lock:
            if session_id is not None:
                session_agents = self._session_agents.get(session_id)
                if not session_agents or agent_id not in session_agents:
                    return None
                rec = session_agents.pop(agent_id)
                session_outputs = self._session_out_to_ag.get(session_id, {})
                for output_id in list(session_outputs):
                    if session_outputs[output_id] == agent_id:
                        del session_outputs[output_id]
                if not session_agents:
                    self._session_agents.pop(session_id, None)
                if not session_outputs:
                    self._session_out_to_ag.pop(session_id, None)
                return rec

            rec = self._agents.pop(agent_id, None)
            if rec is None:
                return None
            for output_id in list(self._out_to_ag):
                if self._out_to_ag[output_id] == agent_id:
                    del self._out_to_ag[output_id]
            return rec

    async def get_agent(
        self, agent_id: str, session_id: str | None = None
    ) -> MACIAgentRecord | None:
        """Get agent by ID, optionally scoped to a session.

        Args:
            agent_id: Agent identifier
            session_id: Optional session ID to restrict lookup

        Returns:
            MACIAgentRecord if found, None otherwise
        """
        async with self._lock:
            return self._get_agent_locked(agent_id, session_id=session_id)

    async def get_agents_by_role(
        self, role: MACIRole, session_id: str | None = None
    ) -> list[MACIAgentRecord]:
        """Get all agents with a specific role.

        Args:
            role: MACI role to filter by
            session_id: Optional session ID to restrict lookup

        Returns:
            list of agents with the specified role
        """
        async with self._lock:
            if session_id is not None:
                return [
                    agent
                    for agent in self._session_agents.get(session_id, {}).values()
                    if agent.role == role
                ]
            return [a for a in self._agents.values() if a.role == role]

    async def get_session_agents(self, session_id: str) -> dict[str, MACIAgentRecord]:
        """Get all agents registered for a session.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary of agent_id to MACIAgentRecord for the session
        """
        async with self._lock:
            return dict(self._session_agents.get(session_id, {}))

    async def clear_session(self, session_id: str) -> int:
        """Clear all agents registered for a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of agents removed
        """
        async with self._lock:
            if session_id not in self._session_agents:
                return 0

            session_agents = self._session_agents.pop(session_id)
            self._session_out_to_ag.pop(session_id, None)
            count = len(session_agents)

            logger.info(f"Cleared {count} agents from session {session_id}")
            return count

    async def record_output(
        self,
        agent_id: str,
        output_id: str,
        session_id: str | None = None,
    ) -> None:
        """Record an output produced by an agent.

        Args:
            agent_id: Agent identifier
            output_id: Output identifier to record
            session_id: Optional session scope for session-registered agents
        """
        async with self._lock:
            agent_record = self._get_agent_locked(agent_id, session_id=session_id)
            if agent_record is None:
                return
            agent_record.add_output(output_id)
            if session_id is not None:
                if session_id not in self._session_out_to_ag:
                    self._session_out_to_ag[session_id] = {}
                self._session_out_to_ag[session_id][output_id] = agent_id
            else:
                self._out_to_ag[output_id] = agent_id

    async def get_output_producer(
        self,
        output_id: str,
        session_id: str | None = None,
    ) -> str | None:
        """Get the agent ID that produced a specific output.

        Args:
            output_id: Output identifier
            session_id: Optional session scope for session-registered agents

        Returns:
            Agent ID if output was produced, None otherwise
        """
        if session_id is not None:
            return self._session_out_to_ag.get(session_id, {}).get(output_id)
        return self._out_to_ag.get(output_id)

    async def is_self_output(
        self,
        agent_id: str,
        output_id: str,
        session_id: str | None = None,
    ) -> bool:
        """Check if an output was produced by a specific agent.

        Args:
            agent_id: Agent identifier
            output_id: Output identifier
            session_id: Optional session scope for session-registered agents

        Returns:
            True if agent produced this output, False otherwise
        """
        rec = self._get_agent_locked(agent_id, session_id=session_id)
        return rec.owns_output(output_id) if rec else False

    async def batch_record_outputs(
        self,
        agent_id: str,
        output_ids: list[str],
        session_id: str | None = None,
    ) -> None:
        """Optimized batch recording of outputs.

        Args:
            agent_id: Agent identifier
            output_ids: list of output identifiers to record
            session_id: Optional session scope for session-registered agents
        """
        async with self._lock:
            agent_rec = self._get_agent_locked(agent_id, session_id=session_id)
            if agent_rec is None:
                return
            if session_id is not None:
                if session_id not in self._session_out_to_ag:
                    self._session_out_to_ag[session_id] = {}
                output_map = self._session_out_to_ag[session_id]
            else:
                output_map = self._out_to_ag
            for oid in output_ids:
                if oid not in agent_rec.outputs:
                    agent_rec.outputs.append(oid)
                output_map[oid] = agent_id
