"""
MACI Data Models and Enums for Constitutional AI Governance.

Contains the core data types used across the MACI enforcement system:
role and action enumerations, configuration dataclasses, validation results,
and the role-permission matrix.

Constitutional Hash: cdd01ef066bc6cf2
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from src.core.shared.constants import MACIRole

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..maci_imports import CONSTITUTIONAL_HASH


class MACIAction(Enum):
    """MACI action enumeration for role-based access control.

    Defines all possible actions that agents can perform. Each action is restricted
    to specific roles via ROLE_PERMISSIONS matrix.

    Attributes:
        PROPOSE: Propose new governance actions (EXECUTIVE only)
        VALIDATE: Validate decisions and outputs (JUDICIAL/AUDITOR only)
        EXTRACT_RULES: Extract governance rules (LEGISLATIVE only)
        SYNTHESIZE: Synthesize policies and implementations (EXECUTIVE/LEGISLATIVE/IMPLEMENTER)
        AUDIT: Audit decisions and compliance (AUDITOR only)
        QUERY: Query system state (all roles)
        MANAGE_POLICY: Manage policy definitions (CONTROLLER only)
        EMERGENCY_COOLDOWN: Trigger emergency cooldown (JUDICIAL only)
        MONITOR_ACTIVITY: Monitor system activity (MONITOR only)
        ENFORCE_CONTROL: Enforce control policies (CONTROLLER only)
    """

    PROPOSE = "propose"
    VALIDATE = "validate"
    EXTRACT_RULES = "extract_rules"
    SYNTHESIZE = "synthesize"
    AUDIT = "audit"
    QUERY = "query"
    MANAGE_POLICY = "manage_policy"
    EMERGENCY_COOLDOWN = "emergency_cooldown"
    MONITOR_ACTIVITY = "monitor_activity"
    ENFORCE_CONTROL = "enforce_control"


ROLE_PERMISSIONS = {
    MACIRole.EXECUTIVE: {MACIAction.PROPOSE, MACIAction.SYNTHESIZE, MACIAction.QUERY},
    MACIRole.LEGISLATIVE: {MACIAction.EXTRACT_RULES, MACIAction.SYNTHESIZE, MACIAction.QUERY},
    MACIRole.JUDICIAL: {
        MACIAction.VALIDATE,
        MACIAction.AUDIT,
        MACIAction.QUERY,
        MACIAction.EMERGENCY_COOLDOWN,
    },
    MACIRole.MONITOR: {MACIAction.MONITOR_ACTIVITY, MACIAction.QUERY},
    MACIRole.AUDITOR: {MACIAction.AUDIT, MACIAction.QUERY},
    MACIRole.CONTROLLER: {MACIAction.ENFORCE_CONTROL, MACIAction.QUERY},
    MACIRole.IMPLEMENTER: {MACIAction.SYNTHESIZE, MACIAction.QUERY},
}

VALIDATION_CONSTRAINTS = {
    MACIRole.JUDICIAL: {MACIRole.EXECUTIVE, MACIRole.LEGISLATIVE, MACIRole.IMPLEMENTER},
    MACIRole.AUDITOR: {MACIRole.MONITOR, MACIRole.CONTROLLER, MACIRole.IMPLEMENTER},
}

ROLE_HIERARCHY = {
    MACIRole.JUDICIAL: 100,
    MACIRole.AUDITOR: 90,
    MACIRole.LEGISLATIVE: 80,
    MACIRole.EXECUTIVE: 70,
    MACIRole.CONTROLLER: 60,
    MACIRole.MONITOR: 50,
    MACIRole.IMPLEMENTER: 40,
}


@dataclass
class MACIAgentRoleConfig:
    """Configuration for an agent's MACI role and capabilities.

    Stores the role assignment and metadata for an agent, used during initialization
    and configuration loading.

    Attributes:
        agent_id: Unique identifier for the agent
        role: MACI role assigned to the agent
        capabilities: list of capability names the agent possesses
        metadata: Additional metadata dictionary for the agent
    """

    agent_id: str
    role: MACIRole
    capabilities: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize role string to MACIRole enum if needed."""
        if isinstance(self.role, str):
            try:  # noqa: SIM105
                self.role = MACIRole.parse(self.role)
            except ValueError:
                pass


@dataclass
class MACIConfig:
    """MACI configuration container.

    Holds the complete MACI configuration including strict mode, agent definitions,
    and default role. Used to initialize MACIRoleRegistry and MACIEnforcer.

    Attributes:
        strict_mode: If True, reject unauthorized actions (fail-closed)
        agents: list of agent role configurations
        default_role: Default role for agents without explicit assignment
        constitutional_hash: Constitutional hash for validation
    """

    strict_mode: bool = True
    agents: list[MACIAgentRoleConfig] = field(default_factory=list)
    default_role: MACIRole | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def get_role_for_agent(self, agent_id: str) -> MACIRole | None:
        """Get the MACI role assigned to an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            MACIRole if agent is configured, default_role otherwise, or None
        """
        for a in self.agents:
            if a.agent_id == agent_id:
                return a.role
        return self.default_role

    def get_agent_config(self, agent_id: str) -> MACIAgentRoleConfig | None:
        """Get the configuration for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            MACIAgentRoleConfig if found, None otherwise
        """
        for a in self.agents:
            if a.agent_id == agent_id:
                return a
        return None


@dataclass
class MACIValidationResult:
    """Result of a MACI validation check.

    Captures the outcome of a MACI validation including success/failure status,
    violation type, error message, and detailed context for audit logging.

    Attributes:
        is_valid: Whether the validation passed
        violation_type: type of violation if validation failed
        error_message: Human-readable error message
        details: Additional context dictionary
        constitutional_hash: Constitutional hash for validation
        session_id: Optional session context for audit trail
        validated_at: Timestamp of validation
    """

    is_valid: bool = True
    violation_type: str | None = None
    error_message: str | None = None
    details: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    session_id: str | None = None  # Session context for audit trail
    validated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __init__(self, is_valid: bool = True, **kwargs):
        """Initialize validation result with flexible kwargs.

        Args:
            is_valid: Whether validation passed
            **kwargs: Additional attributes to set
        """
        self.is_valid = is_valid
        self.__dict__.update(kwargs)
        if "constitutional_hash" not in self.__dict__:
            self.constitutional_hash = CONSTITUTIONAL_HASH
        if "error_message" not in self.__dict__:
            self.error_message = None
        if "session_id" not in self.__dict__:
            self.session_id = None
        if "violation_type" not in self.__dict__:
            self.violation_type = None
        if "details" not in self.__dict__:
            self.details = {}
        if "validated_at" not in self.__dict__:
            self.validated_at = datetime.now(UTC)

    def to_audit_dict(self) -> JSONDict:
        """Convert to dictionary for audit logging with session context.

        Returns:
            Dictionary representation suitable for audit logs
        """
        return {
            "is_valid": self.is_valid,
            "violation_type": self.violation_type,
            "error_message": self.error_message,
            "session_id": self.session_id,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "constitutional_hash": self.constitutional_hash,
            "details": self.details,
        }


class MACIValidationContext:
    """Context container for MACI validation with constitutional hash.

    Flexible container for passing validation context through the system.

    Attributes:
        constitutional_hash: Constitutional hash for validation
    """

    def __init__(self, **kwargs):
        """Initialize validation context with flexible kwargs.

        Args:
            **kwargs: Arbitrary context attributes
        """
        self.__dict__.update(kwargs)
        if "constitutional_hash" not in self.__dict__:
            self.constitutional_hash = CONSTITUTIONAL_HASH
