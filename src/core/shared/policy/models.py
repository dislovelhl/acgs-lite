"""
PSV-Verus Shared Models
Constitutional Hash: cdd01ef066bc6cf2
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]

# Centralized Constitutional Hash

from src.core.shared.constants import CONSTITUTIONAL_HASH


class PolicyLanguage(Enum):
    """Supported policy languages."""

    REGO = "rego"  # Open Policy Agent Rego
    DAFNY = "dafny"  # Dafny formal verification
    SMT = "smt"  # SMT-LIB2 format
    NATURAL = "natural"  # Natural language
    Z3 = "z3"  # Z3 SMT solver


class VerificationStatus(Enum):
    """Status of policy verification."""

    UNVERIFIED = "unverified"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"
    PROVEN = "proven"  # Formally proven correct


@dataclass
class PolicySpecification:
    """A policy specification in natural language."""

    spec_id: str
    natural_language: str
    domain: str = "general"
    criticality: str = "medium"  # "low", "medium", "high", "critical"
    context: JSONDict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Serialize this specification to a JSON-compatible dictionary."""
        return {
            "spec_id": self.spec_id,
            "natural_language": self.natural_language,
            "domain": self.domain,
            "criticality": self.criticality,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class VerifiedPolicy:
    """A formally verified policy with multiple representations."""

    policy_id: str
    specification: PolicySpecification
    rego_policy: str  # OPA Rego format
    dafny_spec: str  # Dafny formal specification
    smt_formulation: str  # SMT-LIB2 format
    verification_result: JSONDict
    generation_metadata: JSONDict
    verification_status: VerificationStatus
    confidence_score: float  # 0.0 to 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    verified_at: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Serialize this verified policy to a JSON-compatible dictionary."""
        return {
            "policy_id": self.policy_id,
            "specification": self.specification.to_dict(),
            "rego_policy": self.rego_policy,
            "dafny_spec": self.dafny_spec,
            "smt_formulation": self.smt_formulation,
            "verification_result": self.verification_result,
            "generation_metadata": self.generation_metadata,
            "verification_status": self.verification_status.value,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class PSVIteration:
    """A single Propose-Solve-Verify iteration."""

    iteration_id: str
    specification: PolicySpecification
    proposed_policy: str
    solved_rego: str
    verified_dafny: str
    z3_result: JSONDict
    success: bool
    error_message: str | None
    improvements: list[str]
    execution_time_ms: float
    iteration_number: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Serialize this PSV iteration to a JSON-compatible dictionary."""
        return {
            "iteration_id": self.iteration_id,
            "specification": self.specification.to_dict(),
            "success": self.success,
            "error_message": self.error_message,
            "improvements": self.improvements,
            "execution_time_ms": self.execution_time_ms,
            "iteration_number": self.iteration_number,
            "timestamp": self.timestamp.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }
