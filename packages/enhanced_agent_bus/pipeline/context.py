from __future__ import annotations

"""
Pipeline context and metrics for ACGS-2 Message Processing.

Constitutional Hash: 608508a9bd224290
"""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import AgentMessage
from enhanced_agent_bus.validators import ValidationResult

from ..ifc.labels import Confidentiality, IFCLabel, IFCViolation, Integrity
from ..prov.labels import ProvLabel, ProvLineage
from ..session_context import SessionContext

if TYPE_CHECKING:
    from ..adaptive_governance.models import GovernanceDecision
    from ..maci_enforcement import MACIValidationResult


@dataclass
class PipelineMetrics:
    """Atomic metrics collection for pipeline execution.

    Uses atomic counters instead of locks for high-concurrency scenarios.
    """

    # Timing metrics (in milliseconds)
    session_resolution_time_ms: float = 0.0
    security_scan_time_ms: float = 0.0
    verification_time_ms: float = 0.0
    strategy_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Counter metrics
    cache_hits: int = 0
    cache_misses: int = 0
    sessions_resolved: int = 0
    sessions_not_found: int = 0
    sessions_errors: int = 0

    def record_session_resolved(self, duration_ms: float) -> None:
        """Record successful session resolution."""
        self.sessions_resolved += 1
        self.session_resolution_time_ms += duration_ms

    def record_session_not_found(self) -> None:
        """Record session not found."""
        self.sessions_not_found += 1

    def record_session_error(self) -> None:
        """Record session resolution error."""
        self.sessions_errors += 1

    def record_cache_hit(self) -> None:
        """Record cache hit."""
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record cache miss."""
        self.cache_misses += 1

    def record_security_scan(self, duration_ms: float) -> None:
        """Record security scan completion."""
        self.security_scan_time_ms += duration_ms

    def record_verification(self, duration_ms: float) -> None:
        """Record verification completion."""
        self.verification_time_ms += duration_ms

    def record_strategy(self, duration_ms: float) -> None:
        """Record strategy execution completion."""
        self.strategy_time_ms += duration_ms

    def finalize(self, start_time: float) -> None:
        """Finalize metrics with total execution time."""
        self.total_time_ms = (time.perf_counter() - start_time) * 1000

    def to_dict(self) -> JSONDict:
        """Convert metrics to dictionary."""
        total_sessions = self.sessions_resolved + self.sessions_not_found + self.sessions_errors
        total_cache = self.cache_hits + self.cache_misses

        return {
            "timing_ms": {
                "session_resolution": round(self.session_resolution_time_ms, 2),
                "security_scan": round(self.security_scan_time_ms, 2),
                "verification": round(self.verification_time_ms, 2),
                "strategy": round(self.strategy_time_ms, 2),
                "total": round(self.total_time_ms, 2),
            },
            "counters": {
                "sessions_resolved": self.sessions_resolved,
                "sessions_not_found": self.sessions_not_found,
                "sessions_errors": self.sessions_errors,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
            },
            "rates": {
                "cache_hit_rate": round(self.cache_hits / total_cache, 4)
                if total_cache > 0
                else 0.0,
                "session_resolution_rate": round(self.sessions_resolved / total_sessions, 4)
                if total_sessions > 0
                else 0.0,
            },
        }


@dataclass
class PipelineContext:
    """Mutable context passed through middleware chain.

    Contains all data necessary for message processing, including:
    - Original message
    - Session context (if resolved)
    - Security scan results
    - Verification results
    - Strategy execution result
    - Metrics collection
    - Tenant validation results
    - Constitutional validation results
    - MACI enforcement results
    - Adaptive governance results
    """

    # Core message
    message: AgentMessage

    # Session context (populated by SessionExtractionMiddleware)
    session: SessionContext | None = None
    session_id: str | None = None

    # Cache (populated by CacheMiddleware)
    cache_key: str | None = None
    cache_hit: bool = False

    # Security (populated by SecurityMiddleware)
    security_passed: bool = False
    security_result: JSONDict | None = None

    # Verification (populated by VerificationMiddleware)
    verification_results: dict[str, ValidationResult] = field(default_factory=dict)

    # Strategy (populated by StrategyMiddleware)
    strategy_result: ValidationResult | None = None

    # Early result (for early exit from pipeline)
    early_result: ValidationResult | None = None

    # Tenant Validation (populated by TenantValidationMiddleware)
    tenant_id: str | None = None
    tenant_validated: bool = False
    tenant_errors: list[str] = field(default_factory=list)

    # Constitutional Validation (populated by ConstitutionalValidationMiddleware)
    constitutional_hash: str = CONSTITUTIONAL_HASH  # pragma: allowlist secret
    message_constitutional_hash: str | None = None
    constitutional_validated: bool = False

    # MACI Enforcement (populated by MACIEnforcementMiddleware)
    maci_role: str | None = None
    maci_action: str | None = None
    maci_enforced: bool = False
    maci_result: MACIValidationResult | None = None

    # Adaptive Governance (populated by AdaptiveGovernanceMiddleware)
    governance_decision: GovernanceDecision | None = None
    governance_allowed: bool = True
    governance_reasoning: str | None = None
    impact_score: float = 0.0

    # Execution tracking
    start_time: float = field(default_factory=time.perf_counter)
    middleware_path: list[str] = field(default_factory=list)

    # Metrics (lock-free)
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)

    # IFC taint tracking (Sprint 4)
    # Populated at pipeline entry from message.ifc_label or defaulted to PUBLIC/MEDIUM.
    ifc_label: IFCLabel = field(
        default_factory=lambda: IFCLabel(
            confidentiality=Confidentiality.PUBLIC,
            integrity=Integrity.MEDIUM,
        )
    )
    ifc_violations: list[IFCViolation] = field(default_factory=list)

    # Temporal ordering: ordered list of completed pipeline stage labels.
    # Populated by TemporalPolicyMiddleware; consumed by evaluate_with_history().
    action_history: list[str] = field(default_factory=list)

    # PROV provenance lineage (Sprint 5)
    # Populated by ProvMiddleware at each governance decision point.
    # Fail-open: missing labels do not block processing.
    prov_lineage: ProvLineage = field(default_factory=ProvLineage)

    # Hierarchical orchestration (Sprint 6)
    # Populated by OrchestratorMiddleware for HIGH/CRITICAL impact messages.
    # Fail-open: None means orchestration was skipped or failed without blocking.
    orchestration_result: JSONDict | None = None
    orchestrator_used: bool = False

    def __post_init__(self) -> None:
        """Adopt ifc_label from the message if it carries one."""
        msg_label = getattr(self.message, "ifc_label", None)
        if msg_label is not None and isinstance(msg_label, IFCLabel):
            self.ifc_label = msg_label

    def record_ifc_violation(self, violation: IFCViolation) -> None:
        """Append an IFC policy violation to the audit trail."""
        self.ifc_violations.append(violation)

    def record_prov_label(self, label: ProvLabel) -> None:
        """Append a provenance label to the pipeline lineage chain."""
        self.prov_lineage.append(label)

    def add_middleware(self, name: str) -> None:
        """Record middleware execution in path."""
        self.middleware_path.append(name)

    def set_early_result(self, result: ValidationResult) -> None:
        """Set early result to exit pipeline early."""
        self.early_result = result

    def finalize(self) -> None:
        """Finalize context and metrics."""
        self.metrics.finalize(self.start_time)

    def to_validation_result(self) -> ValidationResult:
        """Convert context to final validation result."""
        if self.strategy_result:
            # Merge metrics into metadata
            result = self.strategy_result
            result.metadata.update(
                {
                    "pipeline_version": "2.0.0",
                    "middleware_path": self.middleware_path,
                    "metrics": self.metrics.to_dict(),
                    "cache_hit": self.cache_hit,
                    "session_resolved": self.session is not None,
                    "security_scan": "PASSED" if self.security_passed else "BLOCKED",
                    "verification": {
                        name: {"is_valid": vr.is_valid, "errors": vr.errors}
                        for name, vr in self.verification_results.items()
                    },
                    "ifc_label": self.ifc_label.to_dict(),
                    "ifc_violations_count": len(self.ifc_violations),
                    "action_history": list(self.action_history),
                    "prov_lineage": self.prov_lineage.to_dict(),
                    "prov_lineage_length": len(self.prov_lineage),
                    "orchestration_result": self.orchestration_result,
                    "orchestrator_used": self.orchestrator_used,
                }
            )
            return result

        # Fallback if no strategy result
        return ValidationResult(
            is_valid=False,
            errors=["No strategy result produced"],
            metadata={
                "pipeline_version": "2.0.0",
                "middleware_path": self.middleware_path,
                "metrics": self.metrics.to_dict(),
            },
        )
