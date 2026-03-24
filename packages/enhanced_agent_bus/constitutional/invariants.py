"""
ACGS-2 Enhanced Agent Bus - Constitutional Invariant System
Constitutional Hash: cdd01ef066bc6cf2

Defines hard constitutional invariants that cannot be changed through normal
amendment processes. These invariants protect core governance properties like
MACI separation of powers, fail-closed behavior, and tenant isolation.

Invariant scopes:
  HARD  - refoundation only, cannot change via normal amendment
  META  - governs how constitution changes, refoundation only
  SOFT  - strong default, normal amendment with extra review
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "ChangeClassification",
    "EnforcementMode",
    "InvariantCheckResult",
    "InvariantDefinition",
    "InvariantManifest",
    "InvariantScope",
    "check_append_only_audit",
    "check_constitutional_hash_required",
    "check_fail_closed",
    "check_human_approval_for_activation",
    "check_maci_separation",
    "check_tenant_isolation",
    "get_default_manifest",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InvariantScope(StrEnum):
    """Scope determines how an invariant can be changed."""

    HARD = "hard"  # refoundation only — cannot change via normal amendment
    META = "meta"  # governs how constitution changes — refoundation only
    SOFT = "soft"  # strong default — normal amendment with extra review


class EnforcementMode(StrEnum):
    """When the invariant check is enforced."""

    PRE_PROPOSAL = "pre_proposal"
    PRE_ACTIVATION = "pre_activation"
    RUNTIME = "runtime"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class InvariantCheckResult(BaseModel):
    """Result of evaluating a single invariant predicate."""

    passed: bool
    invariant_id: str
    message: str = ""


class InvariantDefinition(BaseModel):
    """Declarative definition of a constitutional invariant."""

    invariant_id: str
    name: str
    scope: InvariantScope
    description: str = ""
    protected_paths: list[str] = Field(default_factory=list)
    enforcement_modes: list[EnforcementMode] = Field(default_factory=list)
    predicate_module: str = ""  # dotted import path to predicate function


class ChangeClassification(BaseModel):
    """Classification of a proposed change against invariant boundaries."""

    touches_invariants: bool
    touched_invariant_ids: list[str] = Field(default_factory=list)
    blocked: bool
    requires_refoundation: bool = False
    reason: str | None = None


class InvariantManifest(BaseModel):
    """
    Versioned manifest of all constitutional invariants.

    The invariant_hash is computed deterministically from the sorted invariant
    definitions, providing tamper detection.
    """

    manifest_version: str = "1.0.0"
    constitutional_hash: str
    invariant_hash: str = ""  # computed from invariants
    invariants: list[InvariantDefinition] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        computed = self._compute_hash()
        if self.invariant_hash and self.invariant_hash != computed:
            raise ValueError(
                f"Invariant hash mismatch: provided={self.invariant_hash}, "
                f"computed={computed}"
            )
        self.invariant_hash = computed

    def _compute_hash(self) -> str:
        content = json.dumps(
            [inv.model_dump() for inv in sorted(self.invariants, key=lambda i: i.invariant_id)],
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Default HARD invariant predicates
# ---------------------------------------------------------------------------


def check_maci_separation(
    state: dict[str, Any],
    change: dict[str, Any],
) -> InvariantCheckResult:
    """INV-001: MACI separation — proposer != validator != executor."""
    proposer = change.get("proposer_id", "")
    validator = change.get("validator_id", "")
    executor = change.get("executor_id", "")

    ids = [proposer, validator, executor]
    non_empty = [i for i in ids if i]

    # Require all three roles to be present for MACI to be verified
    if len(non_empty) < 3:
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-001",
            message=(
                "MACI separation requires all three roles (proposer, validator, "
                "executor) to be present and non-empty"
            ),
        )

    if len(non_empty) != len(set(non_empty)):
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-001",
            message=(
                "MACI separation violated: proposer, validator, and executor "
                "must be distinct agents"
            ),
        )

    return InvariantCheckResult(
        passed=True,
        invariant_id="INV-001",
        message="MACI separation of powers verified",
    )


def check_fail_closed(
    state: dict[str, Any],
    change: dict[str, Any],
) -> InvariantCheckResult:
    """INV-002: Governance must fail-closed on errors."""
    error_action = change.get("on_error")
    if error_action is not None and error_action != "deny":
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-002",
            message=(f"Fail-closed violated: on_error is '{error_action}', must be 'deny'"),
        )

    governance_bypass = change.get("governance_bypass", False)
    if governance_bypass:
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-002",
            message="Fail-closed violated: governance_bypass must not be enabled",
        )

    return InvariantCheckResult(
        passed=True,
        invariant_id="INV-002",
        message="Fail-closed governance verified",
    )


def check_append_only_audit(
    state: dict[str, Any],
    change: dict[str, Any],
) -> InvariantCheckResult:
    """INV-003: Audit trail must be append-only."""
    audit_op = change.get("audit_operation")
    disallowed = {"delete", "update", "truncate", "drop"}

    if audit_op is not None and audit_op in disallowed:
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-003",
            message=(
                f"Append-only audit violated: '{audit_op}' operation is not allowed "
                "on the audit trail"
            ),
        )

    return InvariantCheckResult(
        passed=True,
        invariant_id="INV-003",
        message="Append-only audit trail verified",
    )


def check_constitutional_hash_required(
    state: dict[str, Any],
    change: dict[str, Any],
) -> InvariantCheckResult:
    """INV-004: All governance paths must validate constitutional hash."""
    expected_hash = state.get("constitutional_hash", "")
    provided_hash = change.get("constitutional_hash", "")

    if not provided_hash:
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-004",
            message="Constitutional hash missing from change payload",
        )

    if expected_hash and provided_hash != expected_hash:
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-004",
            message=(
                f"Constitutional hash mismatch: expected '{expected_hash}', got '{provided_hash}'"
            ),
        )

    return InvariantCheckResult(
        passed=True,
        invariant_id="INV-004",
        message="Constitutional hash validated",
    )


def check_tenant_isolation(
    state: dict[str, Any],
    change: dict[str, Any],
) -> InvariantCheckResult:
    """INV-005: Tenant data must never cross boundaries."""
    source_tenant = change.get("source_tenant_id", "")
    target_tenant = change.get("target_tenant_id", "")

    if source_tenant and target_tenant and source_tenant != target_tenant:
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-005",
            message=(
                f"Tenant isolation violated: data from tenant '{source_tenant}' "
                f"cannot cross to tenant '{target_tenant}'"
            ),
        )

    return InvariantCheckResult(
        passed=True,
        invariant_id="INV-005",
        message="Tenant isolation verified",
    )


def check_human_approval_for_activation(
    state: dict[str, Any],
    change: dict[str, Any],
) -> InvariantCheckResult:
    """INV-006: Constitutional activation requires human approval."""
    is_activation = change.get("is_activation", False)
    human_approved = change.get("human_approved", False)

    if is_activation and not human_approved:
        return InvariantCheckResult(
            passed=False,
            invariant_id="INV-006",
            message=(
                "Human approval required: constitutional activation cannot proceed "
                "without explicit human approval"
            ),
        )

    return InvariantCheckResult(
        passed=True,
        invariant_id="INV-006",
        message="Human approval requirement verified",
    )


# ---------------------------------------------------------------------------
# Default manifest factory
# ---------------------------------------------------------------------------

_MODULE_PATH = "enhanced_agent_bus.constitutional.invariants"

_DEFAULT_INVARIANTS: list[InvariantDefinition] = [
    InvariantDefinition(
        invariant_id="INV-001",
        name="MACI Separation of Powers",
        scope=InvariantScope.HARD,
        description=(
            "Proposer, validator, and executor must be distinct agents. "
            "No agent may validate its own output."
        ),
        protected_paths=[
            "middlewares/batch/governance.py",
            "maci/enforcer.py",
        ],
        enforcement_modes=[
            EnforcementMode.PRE_PROPOSAL,
            EnforcementMode.RUNTIME,
        ],
        predicate_module=f"{_MODULE_PATH}.check_maci_separation",
    ),
    InvariantDefinition(
        invariant_id="INV-002",
        name="Fail-Closed Governance",
        scope=InvariantScope.HARD,
        description=(
            "All governance evaluation paths must deny by default on error. "
            "Governance bypass must never be enabled."
        ),
        protected_paths=[
            "bus/governance.py",
            "pipeline/router.py",
        ],
        enforcement_modes=[
            EnforcementMode.PRE_ACTIVATION,
            EnforcementMode.RUNTIME,
        ],
        predicate_module=f"{_MODULE_PATH}.check_fail_closed",
    ),
    InvariantDefinition(
        invariant_id="INV-003",
        name="Append-Only Audit Trail",
        scope=InvariantScope.HARD,
        description=(
            "The audit trail is immutable. Only append operations are permitted. "
            "Delete, update, truncate, and drop are forbidden."
        ),
        protected_paths=[
            "guardrails/audit_log.py",
            "audit_client.py",
        ],
        enforcement_modes=[
            EnforcementMode.PRE_PROPOSAL,
            EnforcementMode.RUNTIME,
        ],
        predicate_module=f"{_MODULE_PATH}.check_append_only_audit",
    ),
    InvariantDefinition(
        invariant_id="INV-004",
        name="Constitutional Hash Validation",
        scope=InvariantScope.META,
        description=(
            "Every governance decision path must validate the constitutional hash "
            "against the canonical value (cdd01ef066bc6cf2)."
        ),
        protected_paths=[
            "constitutional/storage.py",
            "constitutional/activation_saga.py",
        ],
        enforcement_modes=[
            EnforcementMode.PRE_ACTIVATION,
            EnforcementMode.RUNTIME,
        ],
        predicate_module=f"{_MODULE_PATH}.check_constitutional_hash_required",
    ),
    InvariantDefinition(
        invariant_id="INV-005",
        name="Tenant Isolation",
        scope=InvariantScope.HARD,
        description=(
            "Data belonging to one tenant must never be accessible to or "
            "cross boundaries into another tenant's scope."
        ),
        protected_paths=[
            "multi_tenancy/rls.py",
            "multi_tenancy/context.py",
        ],
        enforcement_modes=[
            EnforcementMode.PRE_PROPOSAL,
            EnforcementMode.RUNTIME,
        ],
        predicate_module=f"{_MODULE_PATH}.check_tenant_isolation",
    ),
    InvariantDefinition(
        invariant_id="INV-006",
        name="Human Approval for Activation",
        scope=InvariantScope.META,
        description=(
            "Constitutional amendments must receive explicit human approval "
            "before activation. Fully autonomous activation is forbidden."
        ),
        protected_paths=[
            "constitutional/activation_saga.py",
            "deliberation_layer/hitl_manager.py",
        ],
        enforcement_modes=[
            EnforcementMode.PRE_ACTIVATION,
        ],
        predicate_module=f"{_MODULE_PATH}.check_human_approval_for_activation",
    ),
]


def get_default_manifest() -> InvariantManifest:
    """Return the default invariant manifest with all HARD/META invariants."""
    return InvariantManifest(
        constitutional_hash="cdd01ef066bc6cf2",
        invariants=list(_DEFAULT_INVARIANTS),
    )
