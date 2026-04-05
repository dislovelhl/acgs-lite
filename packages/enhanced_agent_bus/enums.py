"""
ACGS-2 Enhanced Agent Bus - Enumerations
Constitutional Hash: 608508a9bd224290

Centralized enumeration definitions for the agent bus.
Split from models.py for improved maintainability.
"""

import sys
from enum import Enum

_module = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.enums", _module)
sys.modules.setdefault("packages.enhanced_agent_bus.enums", _module)


class MessageType(Enum):
    """Types of messages in the agent bus."""

    COMMAND = "command"
    QUERY = "query"
    RESPONSE = "response"
    EVENT = "event"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    GOVERNANCE_REQUEST = "governance_request"
    GOVERNANCE_RESPONSE = "governance_response"
    CONSTITUTIONAL_VALIDATION = "constitutional_validation"
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    BOUNTY_SUBMISSION = "bounty_submission"
    PAYMENT_REQUEST = "payment_request"
    AUDIT_LOG = "audit_log"


class Priority(Enum):
    """Priority levels for messages.

    Higher value = Higher priority.
    Constitutional Hash: 608508a9bd224290

    Note: NORMAL is an alias for MEDIUM for backward compatibility
    with code that used MessagePriority.NORMAL.
    """

    LOW = 0
    NORMAL = 1  # Alias for MEDIUM (backward compatibility)
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class ValidationStatus(Enum):
    """Status of message validation."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


# RiskLevel is canonically defined in src.core.shared.enums.
# Re-exported here for backward compatibility.
from enhanced_agent_bus._compat.enums import RiskLevel


class AutonomyTier(Enum):
    """Safe Autonomy Tiers for agent governance (ACGS-AI-007).

    Defines the level of autonomy an agent has for executing actions.
    Higher tiers require less oversight; lower tiers require more.

    Constitutional Hash: 608508a9bd224290
    """

    ADVISORY = "advisory"  # Can only query/observe, cannot execute commands
    HUMAN_APPROVED = "human_approved"  # Commands require independent validation evidence
    BOUNDED = "bounded"  # Can execute within defined policy boundaries
    UNRESTRICTED = "unrestricted"  # Full autonomy (reserved for system-level agents)


class MessageStatus(Enum):
    """Message processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"
    PENDING_DELIBERATION = "pending_deliberation"
    VALIDATED = "validated"


class BatchItemStatus(Enum):
    """Status of individual batch items during processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskComplexity(Enum):
    """Task complexity levels for routing decisions."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VISIONARY = "visionary"


class TaskType(Enum):
    """Task type classification for agent selection.

    Constitutional Hash: 608508a9bd224290
    """

    # Original general categories
    CODING = "coding"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    INTEGRATION = "integration"
    GOVERNANCE = "governance"
    UNKNOWN = "unknown"

    # Specific task types for routing engine
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DEBUGGING = "debugging"
    ARCHITECTURE = "architecture"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    OPTIMIZATION = "optimization"
    SECURITY_AUDIT = "security_audit"
    CONSTITUTIONAL_VALIDATION = "constitutional_validation"
    WORKFLOW_AUTOMATION = "workflow_automation"


class AgentCapability(Enum):
    """Agent capabilities for routing and selection.

    Constitutional Hash: 608508a9bd224290
    """

    # Core capabilities
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    INTEGRATION = "integration"
    GOVERNANCE = "governance"
    ORCHESTRATION = "orchestration"
    VERIFICATION = "verification"

    # Language-specific experts
    PYTHON_EXPERT = "python_expert"
    TYPESCRIPT_EXPERT = "typescript_expert"
    RUST_EXPERT = "rust_expert"

    # Specialized capabilities for routing engine
    SECURITY_SPECIALIST = "security_specialist"
    CONSTITUTIONAL_VALIDATOR = "constitutional_validator"
    RESEARCH_SPECIALIST = "research_specialist"
    ARCHITECTURE_DESIGNER = "architecture_designer"
    TEST_AUTOMATION = "test_automation"
    PERFORMANCE_OPTIMIZER = "performance_optimizer"


# Re-export all enums
__all__ = [
    "AgentCapability",
    "AutonomyTier",
    "BatchItemStatus",
    "MessageStatus",
    "MessageType",
    "Priority",
    "RiskLevel",
    "TaskComplexity",
    "TaskType",
    "ValidationStatus",
]
