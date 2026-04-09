"""OpenShell governance integration for ACGS."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from acgs_lite._meta import VERSION
from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.constitution.quorum import GateState, QuorumManager
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import MACIViolationError
from acgs_lite.maci import MACIEnforcer, MACIRole
from acgs_lite.openshell_state import (
    GovernanceStateBackend,
    GovernanceStateChecksumError,
    GovernanceStateError,
    GovernanceStateMigrationError,
    GovernanceStateObservabilityHook,
    GovernanceStateVersionError,
    InMemoryGovernanceStateBackend,
    JsonFileGovernanceStateBackend,
    PersistentGovernanceState,
    RedisGovernanceStateBackend,
    SQLiteGovernanceStateBackend,
)


def _load_constitutional_hash() -> str:
    try:
        constants_module = import_module("src.core.shared.constants")
    except ImportError:
        return "608508a9bd224290"
    return str(getattr(constants_module, "CONSTITUTIONAL_HASH", "608508a9bd224290"))


CONSTITUTIONAL_HASH = _load_constitutional_hash()

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI


class ActorRole(str, Enum):
    PROPOSER = "proposer"
    VALIDATOR = "validator"
    EXECUTOR = "executor"
    HUMAN = "human"
    SYSTEM = "system"


class OperationType(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    APPROVE = "approve"
    REJECT = "reject"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionType(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"
    REQUIRE_SEPARATE_EXECUTOR = "require_separate_executor"


class OutcomeStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    HTTP_READ = "http.read"
    HTTP_WRITE = "http.write"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    GITHUB_READ = "github.read"
    GITHUB_WRITE = "github.write"
    MEMORY_SHARED_WRITE = "memory.shared_write"
    TOOL_EXECUTION = "tool.execution"
    MODEL_INFERENCE = "model.inference"


class AuditEventType(str, Enum):
    VALIDATION = "validation"
    DECISION = "decision"
    ESCALATION = "escalation"
    APPROVAL = "approval"
    EXECUTION = "execution"
    SYSTEM = "system"


class GovernanceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=True,
    )


_MAX_METADATA_ITEMS = 32
_MAX_METADATA_DEPTH = 2
_MAX_METADATA_STRING_LENGTH = 2000
_MAX_METADATA_SEQUENCE_ITEMS = 20
_RESERVED_VALIDATION_CONTEXT_KEYS = frozenset(
    {
        "request_id",
        "session_id",
        "tenant_id",
        "environment",
        "actor_role",
        "resource_uri",
        "action_type",
        "operation",
        "requires_network",
        "requires_secret",
        "mutates_state",
    }
)
_RESERVED_AUDIT_METADATA_KEYS = frozenset(
    {
        "decision_id",
        "request_id",
        "sandbox_id",
        "provider_id",
        "summary",
        "external_refs",
        "audit_entry_hash",
        "audit_chain_hash",
        "audit_chain_valid",
    }
)


class ResourceRef(GovernanceModel):
    uri: str = Field(..., description="Canonical resource identifier")
    kind: str = Field(..., description="Resource kind, e.g. github_repo, file, api")
    tenant_id: str | None = None
    owner_id: str | None = None


class ActorRef(GovernanceModel):
    actor_id: str
    role: ActorRole
    display_name: str | None = None
    sandbox_id: str | None = None
    provider_id: str | None = None


class ExternalRef(GovernanceModel):
    system: str = Field(..., description="External system name, e.g. github or jira")
    external_id: str
    url: HttpUrl | None = None


class ActionContext(GovernanceModel):
    request_id: str
    session_id: str
    trace_id: str | None = None
    conversation_id: str | None = None
    tenant_id: str | None = None
    environment: Literal["dev", "staging", "prod"] = "dev"
    channel: str | None = None
    model_name: str | None = None
    client_version: str | None = None


class ActionRequirements(GovernanceModel):
    requires_network: bool = False
    requires_secret: bool = False
    requires_human_approval: bool = False
    requires_separate_executor: bool = False
    mutates_state: bool = False


class ActionPayloadSummary(GovernanceModel):
    payload_hash: str = Field(..., description="sha256:...")
    summary: str = Field(..., max_length=1000)
    content_type: str | None = None
    size_bytes: int | None = None


class ActionEnvelope(GovernanceModel):
    action_type: ActionType
    operation: OperationType
    risk_level: RiskLevel
    actor: ActorRef
    resource: ResourceRef
    context: ActionContext
    requirements: ActionRequirements
    payload: ActionPayloadSummary
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceResult(GovernanceModel):
    is_compliant: bool | None = None
    status: ComplianceStatus = ComplianceStatus.UNKNOWN
    reason_codes: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    reasoning: str = ""
    latency_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH


ComplianceVerdict = ComplianceResult


class GovernanceDecision(GovernanceModel):
    decision_id: str
    decision: DecisionType
    action_allowed: bool
    is_final: bool = True
    initiator: ActorRef | None = None
    compliance: ComplianceResult
    reason_codes: list[str] = Field(default_factory=list)
    rationale: str = Field(..., max_length=4000)
    required_role: ActorRole | None = None
    required_approvals: int = 0
    expires_at: datetime | None = None
    policy_hash: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ApprovalSubmission(GovernanceModel):
    decision_id: str
    submitted_by: ActorRef
    note: str | None = Field(default=None, max_length=2000)


class ApprovalReviewRequest(GovernanceModel):
    decision_id: str
    reviewer: ActorRef
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class ApprovalReviewResponse(GovernanceModel):
    decision_id: str
    review_id: str
    reviewer: ActorRef
    approved: bool
    recorded_at: datetime
    updated_decision: GovernanceDecision


class ExecutionOutcome(GovernanceModel):
    decision_id: str
    request_id: str
    executor: ActorRef
    outcome_status: OutcomeStatus
    result_hash: str | None = None
    summary: str = Field(..., max_length=2000)
    latency_ms: int | None = None
    external_refs: list[ExternalRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(GovernanceModel):
    id: str
    event_type: AuditEventType
    timestamp: datetime
    request_id: str
    decision_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    tenant_id: str | None = None
    actor: ActorRef
    action_type: ActionType | None = None
    resource_uri: str | None = None
    compliance_status: ComplianceStatus | None = None
    decision: DecisionType | None = None
    outcome_status: OutcomeStatus | None = None
    reason_codes: list[str] = Field(default_factory=list)
    payload_hash: str | None = None
    result_hash: str | None = None
    external_refs: list[ExternalRef] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    outcome: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


EVALUATE_ACTION_EXAMPLES: dict[str, dict[str, Any]] = {
    "high_risk_github_write": {
        "summary": "High-risk external write from proposer",
        "value": {
            "action_type": "github.write",
            "operation": "write",
            "risk_level": "high",
            "actor": {
                "actor_id": "agent/openclaw-primary",
                "role": "proposer",
                "display_name": "OpenClaw Main Agent",
                "sandbox_id": "sandbox-demo",
            },
            "resource": {
                "uri": "github://repo/org/repo/issues",
                "kind": "github_repo",
                "tenant_id": "tenant-acme",
            },
            "context": {
                "request_id": "req_123",
                "session_id": "sess_456",
                "trace_id": "trace_789",
                "tenant_id": "tenant-acme",
                "environment": "prod",
                "channel": "slack",
                "model_name": "gpt-5.x",
            },
            "requirements": {
                "requires_network": True,
                "requires_secret": True,
                "requires_human_approval": True,
                "requires_separate_executor": True,
                "mutates_state": True,
            },
            "payload": {
                "payload_hash": "sha256:abcd1234",
                "summary": "Create GitHub issue for production incident follow-up",
                "content_type": "application/json",
                "size_bytes": 412,
            },
            "tags": ["incident", "repo-write"],
            "metadata": {"repository": "org/repo"},
        },
    },
    "low_risk_read": {
        "summary": "Low-risk read-only action",
        "value": {
            "action_type": "http.read",
            "operation": "read",
            "risk_level": "low",
            "actor": {
                "actor_id": "agent/openclaw-primary",
                "role": "proposer",
                "sandbox_id": "sandbox-demo",
            },
            "resource": {
                "uri": "https://api.github.com/repos/org/repo",
                "kind": "api",
            },
            "context": {
                "request_id": "req_200",
                "session_id": "sess_200",
                "environment": "prod",
            },
            "requirements": {
                "requires_network": True,
                "mutates_state": False,
            },
            "payload": {
                "payload_hash": "sha256:read123",
                "summary": "Fetch repository metadata.",
            },
        },
    },
}


RECORD_OUTCOME_EXAMPLES: dict[str, dict[str, Any]] = {
    "successful_execution": {
        "summary": "Successful executor outcome",
        "value": {
            "decision_id": "dec_001",
            "request_id": "req_123",
            "executor": {
                "actor_id": "agent/executor-worker",
                "role": "executor",
                "display_name": "Sandbox Executor",
                "sandbox_id": "sandbox-demo",
            },
            "outcome_status": "succeeded",
            "result_hash": "sha256:result123",
            "summary": "GitHub issue created successfully.",
            "latency_ms": 842,
            "external_refs": [
                {
                    "system": "github",
                    "external_id": "issue_456",
                    "url": "https://github.com/org/repo/issues/456",
                }
            ],
            "metadata": {"http_status": 201},
        },
    }
}

_EVALUATE_ACTION_OPENAPI_EXAMPLES = cast(Any, EVALUATE_ACTION_EXAMPLES)
_OPENAPI_RECORD_OUTCOME_EXAMPLES = cast(Any, RECORD_OUTCOME_EXAMPLES)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _map_actor_role(role: ActorRole | str) -> MACIRole:
    normalized_role = _normalize_actor_role(role)
    if normalized_role is None:
        return MACIRole.OBSERVER
    return {
        ActorRole.PROPOSER.value: MACIRole.PROPOSER,
        ActorRole.VALIDATOR.value: MACIRole.VALIDATOR,
        ActorRole.EXECUTOR.value: MACIRole.EXECUTOR,
    }.get(normalized_role.value, MACIRole.OBSERVER)


TrustedActorRoleResolver = Mapping[str, ActorRole | str] | Callable[[str], ActorRole | str | None]


def _normalize_actor_role(role: ActorRole | str) -> ActorRole | None:
    if isinstance(role, ActorRole):
        return role
    try:
        return ActorRole(str(role))
    except ValueError:
        return None


def _resolve_trusted_actor_role(
    actor_id: str,
    actor_role_resolver: TrustedActorRoleResolver | None,
) -> ActorRole | None:
    if actor_role_resolver is None:
        return None
    raw_role: ActorRole | str | None
    if callable(actor_role_resolver):
        raw_role = actor_role_resolver(actor_id)
    else:
        raw_role = actor_role_resolver.get(actor_id)
    if raw_role is None:
        return None
    if isinstance(raw_role, ActorRole):
        return raw_role
    try:
        return ActorRole(str(raw_role))
    except ValueError:
        return None


def _trusted_role_error(
    actor: ActorRef,
    *,
    trusted_role: ActorRole | None,
) -> tuple[str, str]:
    claimed_role = _normalize_actor_role(actor.role)
    claimed_role_value = claimed_role.value if claimed_role is not None else str(actor.role)
    if trusted_role is None:
        return (
            "TRUSTED_ACTOR_ROLE_REQUIRED",
            f"Actor {actor.actor_id!r} is not bound to a trusted server-side role.",
        )
    return (
        "ACTOR_ROLE_MISMATCH",
        (
            f"Actor {actor.actor_id!r} claimed role {claimed_role_value!r}, "
            f"but the trusted role binding is {trusted_role.value!r}."
        ),
    )


def _validate_actor_binding(
    actor: ActorRef,
    actor_role_resolver: TrustedActorRoleResolver | None,
) -> tuple[ActorRole | None, tuple[str, str] | None]:
    claimed_role = _normalize_actor_role(actor.role)
    if claimed_role is None:
        return (
            None,
            (
                "INVALID_ACTOR_ROLE",
                f"Actor {actor.actor_id!r} supplied an invalid role value {actor.role!r}.",
            ),
        )
    trusted_role = _resolve_trusted_actor_role(actor.actor_id, actor_role_resolver)
    if trusted_role is None or trusted_role != claimed_role:
        return None, _trusted_role_error(actor, trusted_role=trusted_role)
    return trusted_role, None


def _map_maci_action(payload: ActionEnvelope) -> str:
    normalized_role = _normalize_actor_role(payload.actor.role)
    role = normalized_role.value if normalized_role is not None else str(payload.actor.role)
    operation = str(payload.operation)
    if role == ActorRole.VALIDATOR.value or operation in {
        OperationType.APPROVE.value,
        OperationType.REJECT.value,
    }:
        return "validate"
    if role == ActorRole.EXECUTOR.value or operation in {
        OperationType.EXECUTE.value,
        OperationType.DELETE.value,
    }:
        return "execute"
    if operation == OperationType.READ.value:
        return "read"
    return "propose"


def _build_action_text(payload: ActionEnvelope) -> str:
    return (
        f"action_type={payload.action_type}; "
        f"operation={payload.operation}; "
        f"resource={payload.resource.uri}; "
        f"summary={payload.payload.summary}"
    )


def _truncate_string(value: str) -> str:
    if len(value) <= _MAX_METADATA_STRING_LENGTH:
        return value
    return value[: _MAX_METADATA_STRING_LENGTH - 12] + "...[truncated]"


def _sanitize_metadata_value(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _truncate_string(value)
    if depth >= _MAX_METADATA_DEPTH:
        return _truncate_string(repr(value))
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for index, (key, nested_value) in enumerate(value.items()):
            if index >= _MAX_METADATA_ITEMS:
                break
            sanitized[str(key)] = _sanitize_metadata_value(nested_value, depth=depth + 1)
        return sanitized
    if isinstance(value, list | tuple | set | frozenset):
        return [
            _sanitize_metadata_value(item, depth=depth + 1)
            for item in list(value)[:_MAX_METADATA_SEQUENCE_ITEMS]
        ]
    return _truncate_string(repr(value))


def _sanitize_metadata(
    metadata: Mapping[str, Any],
    *,
    reserved_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for index, (key, value) in enumerate(metadata.items()):
        if index >= _MAX_METADATA_ITEMS:
            break
        normalized_key = str(key)
        if normalized_key in reserved_keys:
            continue
        sanitized[normalized_key] = _sanitize_metadata_value(value)
    return sanitized


def _decision_is_expired(decision: GovernanceDecision) -> bool:
    return decision.expires_at is not None and decision.expires_at < _utcnow()


def _build_decision(
    payload: ActionEnvelope,
    *,
    engine: GovernanceEngine,
    maci: MACIEnforcer,
    actor_role_resolver: TrustedActorRoleResolver | None = None,
) -> GovernanceDecision:
    decision_id = f"dec_{uuid4().hex}"
    sanitized_metadata = _sanitize_metadata(
        payload.metadata,
        reserved_keys=_RESERVED_VALIDATION_CONTEXT_KEYS,
    )
    trusted_role, binding_error = _validate_actor_binding(payload.actor, actor_role_resolver)
    if binding_error is not None:
        reason_code, reason_text = binding_error
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.DENY,
            action_allowed=False,
            initiator=payload.actor,
            compliance=ComplianceResult(
                is_compliant=False,
                status=ComplianceStatus.NON_COMPLIANT,
                reason_codes=[reason_code],
                findings=[reason_text],
                reasoning=reason_text,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            reason_codes=[reason_code],
            rationale=reason_text,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    assert trusted_role is not None
    actor_role = _map_actor_role(trusted_role)
    maci_action = _map_maci_action(payload)
    maci.assign_role(payload.actor.actor_id, actor_role)
    try:
        maci.check(payload.actor.actor_id, maci_action)
    except MACIViolationError as exc:
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.DENY,
            action_allowed=False,
            initiator=payload.actor,
            compliance=ComplianceResult(
                is_compliant=False,
                status=ComplianceStatus.NON_COMPLIANT,
                reason_codes=["MACI_VIOLATION"],
                findings=[str(exc)],
                reasoning=str(exc),
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            reason_codes=["MACI_VIOLATION"],
            rationale=str(exc),
            required_role=ActorRole.VALIDATOR,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    action_text = _build_action_text(payload)
    validation = engine.validate(
        action_text,
        agent_id=payload.actor.actor_id,
        context={
            "request_id": payload.context.request_id,
            "session_id": payload.context.session_id,
            "tenant_id": payload.context.tenant_id,
            "environment": payload.context.environment,
            "actor_role": payload.actor.role,
            "resource_uri": payload.resource.uri,
            "action_type": payload.action_type,
            "operation": payload.operation,
            "requires_network": payload.requirements.requires_network,
            "requires_secret": payload.requirements.requires_secret,
            "mutates_state": payload.requirements.mutates_state,
            **sanitized_metadata,
        },
    )
    risk = maci.classify_action_risk(action_text)
    validation_errors = [f"{v.rule_id}: {v.rule_text}" for v in validation.violations]
    risk_reason_codes = [
        f"RISK_{str(payload.risk_level).upper()}",
        f"MACI_ACTION_{maci_action.upper()}",
        f"ESCALATION_{risk['escalation_path'].upper()}",
    ]

    if not validation.valid:
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.DENY,
            action_allowed=False,
            initiator=payload.actor,
            compliance=ComplianceResult(
                is_compliant=False,
                status=ComplianceStatus.NON_COMPLIANT,
                reason_codes=["CONSTITUTIONAL_VIOLATION", *risk_reason_codes],
                findings=validation_errors,
                reasoning="Constitutional validation found blocking violations.",
                latency_ms=validation.latency_ms,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            reason_codes=["CONSTITUTIONAL_VIOLATION", *risk_reason_codes],
            rationale="The action violates one or more constitutional rules.",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    if (
        str(payload.risk_level) in {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}
        or payload.requirements.requires_human_approval
        or risk["risk_tier"] in {"high", "critical"}
    ):
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.ESCALATE,
            action_allowed=False,
            is_final=False,
            initiator=payload.actor,
            compliance=ComplianceResult(
                is_compliant=None,
                status=ComplianceStatus.UNKNOWN,
                reason_codes=["VALIDATION_PASSED", "VALIDATOR_REVIEW_REQUIRED", *risk_reason_codes],
                findings=[
                    "Constitutional validation passed, but the action requires higher-risk review."
                ],
                reasoning=risk["matched_signal"] or "High-risk action requires validator review.",
                latency_ms=validation.latency_ms,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            reason_codes=["VALIDATION_PASSED", "VALIDATOR_REVIEW_REQUIRED", *risk_reason_codes],
            rationale="The action passed constitutional validation but requires validator review.",
            required_role=ActorRole.VALIDATOR,
            required_approvals=1,
            expires_at=_utcnow() + timedelta(minutes=30),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    if payload.requirements.requires_separate_executor and actor_role != MACIRole.EXECUTOR:
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.REQUIRE_SEPARATE_EXECUTOR,
            action_allowed=False,
            initiator=payload.actor,
            compliance=ComplianceResult(
                is_compliant=True,
                status=ComplianceStatus.COMPLIANT,
                reason_codes=[
                    "VALIDATION_PASSED",
                    "SEPARATE_EXECUTOR_REQUIRED",
                    *risk_reason_codes,
                ],
                findings=["The action is valid but must be executed by a distinct executor."],
                reasoning="MACI requires a separate executor for this governed action.",
                latency_ms=validation.latency_ms,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            reason_codes=["VALIDATION_PASSED", "SEPARATE_EXECUTOR_REQUIRED", *risk_reason_codes],
            rationale="The action is allowed only through a separate executor identity.",
            required_role=ActorRole.EXECUTOR,
            expires_at=_utcnow() + timedelta(minutes=30),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    return GovernanceDecision(
        decision_id=decision_id,
        decision=DecisionType.ALLOW,
        action_allowed=True,
        initiator=payload.actor,
        compliance=ComplianceResult(
            is_compliant=True,
            status=ComplianceStatus.COMPLIANT,
            reason_codes=["VALIDATION_PASSED", *risk_reason_codes],
            findings=["The action passed constitutional validation and MACI checks."],
            reasoning="The action is within policy and the actor role is permitted.",
            latency_ms=validation.latency_ms,
            constitutional_hash=CONSTITUTIONAL_HASH,
        ),
        reason_codes=["VALIDATION_PASSED", *risk_reason_codes],
        rationale="The action passed constitutional validation and MACI enforcement.",
        expires_at=_utcnow() + timedelta(minutes=30),
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


def _decision_from_gate_status(
    *,
    decision_id: str,
    status: str,
    constitutional_hash: str,
    note: str,
) -> GovernanceDecision:
    if status == GateState.APPROVED.value:
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.REQUIRE_SEPARATE_EXECUTOR,
            action_allowed=False,
            compliance=ComplianceResult(
                is_compliant=True,
                status=ComplianceStatus.COMPLIANT,
                reason_codes=["VALIDATOR_APPROVED", "SEPARATE_EXECUTOR_REQUIRED"],
                findings=["The approval gate reached the required quorum."],
                reasoning=note or "Validator approval quorum satisfied.",
                constitutional_hash=constitutional_hash,
            ),
            reason_codes=["VALIDATOR_APPROVED", "SEPARATE_EXECUTOR_REQUIRED"],
            rationale="The approval gate passed and execution must use a separate executor.",
            required_role=ActorRole.EXECUTOR,
            expires_at=_utcnow() + timedelta(minutes=30),
            constitutional_hash=constitutional_hash,
        )

    if status == GateState.REJECTED.value:
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.DENY,
            action_allowed=False,
            compliance=ComplianceResult(
                is_compliant=False,
                status=ComplianceStatus.NON_COMPLIANT,
                reason_codes=["VALIDATOR_REJECTED"],
                findings=["The approval gate was vetoed by a validator."],
                reasoning=note or "Validator rejected the governed action.",
                constitutional_hash=constitutional_hash,
            ),
            reason_codes=["VALIDATOR_REJECTED"],
            rationale="The approval gate was rejected.",
            constitutional_hash=constitutional_hash,
        )

    if status == GateState.TIMED_OUT.value:
        return GovernanceDecision(
            decision_id=decision_id,
            decision=DecisionType.DENY,
            action_allowed=False,
            compliance=ComplianceResult(
                is_compliant=False,
                status=ComplianceStatus.NON_COMPLIANT,
                reason_codes=["APPROVAL_TIMED_OUT"],
                findings=["The approval gate timed out before sufficient review."],
                reasoning=note or "Approval timed out.",
                constitutional_hash=constitutional_hash,
            ),
            reason_codes=["APPROVAL_TIMED_OUT"],
            rationale="The approval window expired before approval quorum was reached.",
            constitutional_hash=constitutional_hash,
        )

    return GovernanceDecision(
        decision_id=decision_id,
        decision=DecisionType.ESCALATE,
        action_allowed=False,
        is_final=False,
        compliance=ComplianceResult(
            is_compliant=None,
            status=ComplianceStatus.UNKNOWN,
            reason_codes=["APPROVAL_PENDING"],
            findings=["The approval gate is still open."],
            reasoning=note or "Waiting for additional validator approvals.",
            constitutional_hash=constitutional_hash,
        ),
        reason_codes=["APPROVAL_PENDING"],
        rationale="The approval gate remains open.",
        required_role=ActorRole.VALIDATOR,
        required_approvals=1,
        expires_at=_utcnow() + timedelta(minutes=30),
        constitutional_hash=constitutional_hash,
    )


def create_openshell_governance_router(
    audit_log: AuditLog | None = None,
    *,
    observability_hook: GovernanceStateObservabilityHook | None = None,
    state_backend: GovernanceStateBackend | None = None,
    state_path: str | Path | None = None,
    actor_role_resolver: TrustedActorRoleResolver | None = None,
) -> APIRouter:
    """Create a FastAPI router exposing the OpenShell governance contract."""
    try:
        from fastapi import APIRouter, Body, status
        from fastapi.responses import HTMLResponse
    except ImportError as e:
        raise ImportError(
            "fastapi is required for OpenShell governance endpoints. "
            "Install with: pip install fastapi uvicorn"
        ) from e

    router = APIRouter(prefix="/governance", tags=["governance"])
    router_audit_log = audit_log if audit_log is not None else AuditLog()
    engine = GovernanceEngine(
        Constitution.default(), audit_log=router_audit_log, strict=False, audit_mode="full"
    )
    maci = MACIEnforcer(audit_log=router_audit_log)
    quorum = QuorumManager()
    backend = state_backend
    if backend is None and state_path is not None:
        backend = JsonFileGovernanceStateBackend(state_path)
    state_store = PersistentGovernanceState(backend, observability_hook=observability_hook)
    decision_store: dict[str, GovernanceDecision] = state_store.load_decisions(GovernanceDecision)
    state_store.load_quorum(quorum)

    @router.post(
        "/evaluate-action",
        response_model=GovernanceDecision,
        status_code=status.HTTP_200_OK,
    )
    async def evaluate_action(
        payload: ActionEnvelope = Body(  # noqa: B008
            ..., openapi_examples=_EVALUATE_ACTION_OPENAPI_EXAMPLES
        ),
    ) -> GovernanceDecision:
        decision = _build_decision(
            payload,
            engine=engine,
            maci=maci,
            actor_role_resolver=actor_role_resolver,
        )
        decision_store[decision.decision_id] = decision
        state_store.save(decision_store=decision_store, quorum=quorum)
        return decision

    @router.post(
        "/submit-for-approval",
        response_model=GovernanceDecision,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def submit_for_approval(payload: ApprovalSubmission) -> GovernanceDecision:
        base_decision = decision_store.get(payload.decision_id)
        if base_decision is None:
            return GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=["UNKNOWN_DECISION_ID"],
                    findings=["The decision must be evaluated before approval submission."],
                    reasoning="Unknown decision identifier.",
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=["UNKNOWN_DECISION_ID"],
                rationale="The decision ID was not found in the governance decision registry.",
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        trusted_role, binding_error = _validate_actor_binding(
            payload.submitted_by, actor_role_resolver
        )
        if binding_error is not None:
            reason_code, reason_text = binding_error
            return GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                initiator=base_decision.initiator,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=[reason_code],
                    findings=[reason_text],
                    reasoning=reason_text,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=[reason_code],
                rationale=reason_text,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        if (
            base_decision.initiator is not None
            and payload.submitted_by.actor_id != base_decision.initiator.actor_id
        ):
            reason_text = (
                "Only the actor that initiated the governance decision may submit it for approval."
            )
            return GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                initiator=base_decision.initiator,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=["SUBMITTER_MISMATCH"],
                    findings=[reason_text],
                    reasoning=reason_text,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=["SUBMITTER_MISMATCH"],
                rationale=reason_text,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        assert trusted_role is not None
        maci.assign_role(payload.submitted_by.actor_id, _map_actor_role(trusted_role))
        try:
            maci.check(payload.submitted_by.actor_id, "propose")
        except MACIViolationError as exc:
            return GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=["MACI_VIOLATION"],
                    findings=[str(exc)],
                    reasoning=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=["MACI_VIOLATION"],
                rationale=str(exc),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        if payload.decision_id not in quorum.list_gates():
            quorum.open(
                action=base_decision.rationale,
                required_approvals=max(1, base_decision.required_approvals or 1),
                gate_id=payload.decision_id,
                metadata={
                    "submitted_by": payload.submitted_by.actor_id,
                    "submitted_role": str(payload.submitted_by.role),
                    "constitutional_hash": base_decision.constitutional_hash,
                },
            )

        decision = _decision_from_gate_status(
            decision_id=payload.decision_id,
            status=quorum.status(payload.decision_id).state,
            constitutional_hash=base_decision.constitutional_hash,
            note=payload.note or "The action has been submitted for validator review.",
        )
        decision_store[payload.decision_id] = decision
        state_store.save(decision_store=decision_store, quorum=quorum)
        return decision

    @router.post(
        "/review-approval",
        response_model=ApprovalReviewResponse,
        status_code=status.HTTP_200_OK,
    )
    async def review_approval(payload: ApprovalReviewRequest) -> ApprovalReviewResponse:
        base_decision = decision_store.get(payload.decision_id)
        if base_decision is None:
            updated_decision = GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=["UNKNOWN_DECISION_ID"],
                    findings=["The decision must be submitted before review."],
                    reasoning="Unknown decision identifier.",
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=["UNKNOWN_DECISION_ID"],
                rationale="The decision ID was not found in the approval state machine.",
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return ApprovalReviewResponse(
                decision_id=payload.decision_id,
                review_id=f"rev_{uuid4().hex}",
                reviewer=payload.reviewer,
                approved=False,
                recorded_at=_utcnow(),
                updated_decision=updated_decision,
            )

        trusted_role, binding_error = _validate_actor_binding(payload.reviewer, actor_role_resolver)
        if binding_error is not None:
            reason_code, reason_text = binding_error
            updated_decision = GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                initiator=base_decision.initiator,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=[reason_code],
                    findings=[reason_text],
                    reasoning=reason_text,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=[reason_code],
                rationale=reason_text,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            decision_store[payload.decision_id] = updated_decision
            state_store.save(decision_store=decision_store, quorum=quorum)
            return ApprovalReviewResponse(
                decision_id=payload.decision_id,
                review_id=f"rev_{uuid4().hex}",
                reviewer=payload.reviewer,
                approved=False,
                recorded_at=_utcnow(),
                updated_decision=updated_decision,
            )

        assert trusted_role is not None
        maci.assign_role(payload.reviewer.actor_id, _map_actor_role(trusted_role))
        try:
            maci.check(payload.reviewer.actor_id, "validate")
        except MACIViolationError as exc:
            updated_decision = GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=["MACI_VIOLATION"],
                    findings=[str(exc)],
                    reasoning=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=["MACI_VIOLATION"],
                rationale=str(exc),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            decision_store[payload.decision_id] = updated_decision
            state_store.save(decision_store=decision_store, quorum=quorum)
            return ApprovalReviewResponse(
                decision_id=payload.decision_id,
                review_id=f"rev_{uuid4().hex}",
                reviewer=payload.reviewer,
                approved=False,
                recorded_at=_utcnow(),
                updated_decision=updated_decision,
            )

        if payload.decision_id not in set(quorum.list_gates()):
            quorum.open(
                action=base_decision.rationale,
                required_approvals=max(1, base_decision.required_approvals or 1),
                gate_id=payload.decision_id,
                metadata={
                    "submitted_by": "system",
                    "submitted_role": "system",
                    "constitutional_hash": base_decision.constitutional_hash,
                },
            )

        gate = quorum._gates[payload.decision_id]
        submitted_by = str(gate.metadata.get("submitted_by", ""))
        if submitted_by:
            try:
                maci.check_no_self_validation(submitted_by, payload.reviewer.actor_id)
            except MACIViolationError as exc:
                updated_decision = GovernanceDecision(
                    decision_id=payload.decision_id,
                    decision=DecisionType.DENY,
                    action_allowed=False,
                    compliance=ComplianceResult(
                        is_compliant=False,
                        status=ComplianceStatus.NON_COMPLIANT,
                        reason_codes=["MACI_SELF_VALIDATION_FORBIDDEN"],
                        findings=[str(exc)],
                        reasoning=str(exc),
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    ),
                    reason_codes=["MACI_SELF_VALIDATION_FORBIDDEN"],
                    rationale=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                decision_store[payload.decision_id] = updated_decision
                state_store.save(decision_store=decision_store, quorum=quorum)
                return ApprovalReviewResponse(
                    decision_id=payload.decision_id,
                    review_id=f"rev_{uuid4().hex}",
                    reviewer=payload.reviewer,
                    approved=False,
                    recorded_at=_utcnow(),
                    updated_decision=updated_decision,
                )

        try:
            gate_status = quorum.vote(
                payload.decision_id,
                voter_id=payload.reviewer.actor_id,
                approve=payload.approve,
                note=payload.note or "",
            )
            updated_decision = _decision_from_gate_status(
                decision_id=payload.decision_id,
                status=gate_status.state,
                constitutional_hash=base_decision.constitutional_hash,
                note=payload.note or "",
            )
        except (KeyError, ValueError) as exc:
            updated_decision = GovernanceDecision(
                decision_id=payload.decision_id,
                decision=DecisionType.DENY,
                action_allowed=False,
                compliance=ComplianceResult(
                    is_compliant=False,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason_codes=["APPROVAL_STATE_ERROR"],
                    findings=[str(exc)],
                    reasoning=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                ),
                reason_codes=["APPROVAL_STATE_ERROR"],
                rationale=str(exc),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        decision_store[payload.decision_id] = updated_decision
        state_store.save(decision_store=decision_store, quorum=quorum)
        return ApprovalReviewResponse(
            decision_id=payload.decision_id,
            review_id=f"rev_{uuid4().hex}",
            reviewer=payload.reviewer,
            approved=payload.approve,
            recorded_at=_utcnow(),
            updated_decision=updated_decision,
        )

    @router.post(
        "/record-outcome",
        response_model=AuditEvent,
        status_code=status.HTTP_201_CREATED,
    )
    async def record_outcome(
        payload: ExecutionOutcome = Body(  # noqa: B008
            ..., openapi_examples=_OPENAPI_RECORD_OUTCOME_EXAMPLES
        ),
    ) -> AuditEvent:
        try:
            from fastapi import HTTPException
        except ImportError as e:
            raise ImportError(
                "fastapi is required for OpenShell governance endpoints. "
                "Install with: pip install fastapi uvicorn"
            ) from e

        trusted_role, binding_error = _validate_actor_binding(payload.executor, actor_role_resolver)
        if binding_error is not None:
            reason_code, reason_text = binding_error
            raise HTTPException(
                status_code=403,
                detail={"reason_code": reason_code, "message": reason_text},
            )

        if trusted_role is not ActorRole.EXECUTOR:
            raise HTTPException(
                status_code=403,
                detail={
                    "reason_code": "EXECUTOR_ROLE_REQUIRED",
                    "message": "Only trusted executor identities may record execution outcomes.",
                },
            )

        decision = decision_store.get(payload.decision_id)
        if decision is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "reason_code": "UNKNOWN_DECISION_ID",
                    "message": "Execution outcomes require a known governance decision.",
                },
            )
        if _decision_is_expired(decision):
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_code": "DECISION_EXPIRED",
                    "message": "The governance decision has expired and can no longer be executed.",
                },
            )
        if decision.decision not in {
            DecisionType.ALLOW.value,
            DecisionType.REQUIRE_SEPARATE_EXECUTOR.value,
        }:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_code": "DECISION_NOT_EXECUTABLE",
                    "message": "Only executable governance decisions may record outcomes.",
                },
            )
        if (
            decision.decision == DecisionType.REQUIRE_SEPARATE_EXECUTOR.value
            and decision.initiator is not None
            and decision.initiator.actor_id == payload.executor.actor_id
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "reason_code": "SEPARATE_EXECUTOR_REQUIRED",
                    "message": "The initiating actor cannot record outcomes for separately executed actions.",
                },
            )

        sanitized_metadata = _sanitize_metadata(
            payload.metadata,
            reserved_keys=_RESERVED_AUDIT_METADATA_KEYS,
        )

        event_type = (
            AuditEventType.EXECUTION
            if payload.outcome_status == OutcomeStatus.SUCCEEDED
            else AuditEventType.DECISION
        )
        audit_entry = AuditEntry(
            id=f"evt_{uuid4().hex}",
            type=event_type.value,
            agent_id=payload.executor.actor_id,
            action="record_outcome",
            valid=payload.outcome_status == OutcomeStatus.SUCCEEDED,
            violations=[]
            if payload.outcome_status == OutcomeStatus.SUCCEEDED
            else [payload.summary],
            constitutional_hash=CONSTITUTIONAL_HASH,
            latency_ms=float(payload.latency_ms or 0.0),
            metadata={
                "decision_id": payload.decision_id,
                "request_id": payload.request_id,
                "sandbox_id": payload.executor.sandbox_id,
                "provider_id": payload.executor.provider_id,
                "summary": payload.summary,
                "external_refs": [ref.model_dump(mode="json") for ref in payload.external_refs],
                **sanitized_metadata,
            },
        )
        chain_hash = router_audit_log.record(audit_entry)
        return AuditEvent(
            id=audit_entry.id,
            event_type=event_type,
            timestamp=_utcnow(),
            request_id=payload.request_id,
            decision_id=payload.decision_id,
            actor=payload.executor,
            outcome_status=payload.outcome_status,
            result_hash=payload.result_hash,
            external_refs=payload.external_refs,
            details={
                **audit_entry.metadata,
                "audit_entry_hash": audit_entry.entry_hash,
                "audit_chain_hash": chain_hash,
                "audit_chain_valid": router_audit_log.verify_chain(),
            },
            outcome=str(payload.outcome_status),
        )

    @router.get("/audit-log", status_code=status.HTTP_200_OK)
    async def get_audit_log(limit: int = 50) -> dict[str, Any]:
        entries = router_audit_log.export_dicts()[-min(max(limit, 0), 200) :]
        return {
            "entries": entries,
            "entry_count": len(router_audit_log),
            "chain_valid": router_audit_log.verify_chain(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    @router.get("/examples", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
    async def governance_examples() -> str:
        eval_json = json.dumps(
            EVALUATE_ACTION_EXAMPLES["high_risk_github_write"]["value"], indent=2
        )
        outcome_json = json.dumps(
            RECORD_OUTCOME_EXAMPLES["successful_execution"]["value"],
            indent=2,
        )
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>ACGS OpenShell Governance Examples</title>
    <style>
      body {{ font-family: sans-serif; margin: 2rem; line-height: 1.5; }}
      pre {{ background: #f6f8fa; padding: 1rem; overflow-x: auto; }}
      code {{ font-family: monospace; }}
    </style>
  </head>
  <body>
    <h1>ACGS OpenShell Governance Examples</h1>
    <p>Interactive OpenAPI docs are available at <code>/docs</code>. These examples are also
    embedded into the request schemas for the governance endpoints.</p>
    <h2>POST /governance/evaluate-action</h2>
    <pre>{eval_json}</pre>
    <h2>POST /governance/record-outcome</h2>
    <pre>{outcome_json}</pre>
  </body>
</html>"""

    return router


def create_openshell_governance_app(
    audit_log: AuditLog | None = None,
    *,
    observability_hook: GovernanceStateObservabilityHook | None = None,
    state_backend: GovernanceStateBackend | None = None,
    state_path: str | Path | None = None,
    actor_role_resolver: TrustedActorRoleResolver | None = None,
) -> FastAPI:
    """Create a standalone FastAPI app for the OpenShell governance API."""
    try:
        from fastapi import FastAPI
    except ImportError as e:
        raise ImportError(
            "fastapi is required for OpenShell governance app creation. "
            "Install with: pip install fastapi uvicorn"
        ) from e

    app = FastAPI(title="acgs-openshell-governance", version=VERSION)
    app.include_router(
        create_openshell_governance_router(
            audit_log=audit_log,
            observability_hook=observability_hook,
            state_backend=state_backend,
            state_path=state_path,
            actor_role_resolver=actor_role_resolver,
        )
    )
    return app


__all__ = [
    "ActionContext",
    "ActionEnvelope",
    "ActionPayloadSummary",
    "ActionRequirements",
    "ActionType",
    "ActorRef",
    "ActorRole",
    "ApprovalReviewRequest",
    "ApprovalReviewResponse",
    "ApprovalSubmission",
    "AuditEvent",
    "AuditEventType",
    "ComplianceResult",
    "ComplianceStatus",
    "ComplianceVerdict",
    "DecisionType",
    "ExecutionOutcome",
    "ExternalRef",
    "GovernanceStateChecksumError",
    "GovernanceDecision",
    "GovernanceStateBackend",
    "GovernanceStateError",
    "GovernanceStateMigrationError",
    "GovernanceStateObservabilityHook",
    "GovernanceStateVersionError",
    "InMemoryGovernanceStateBackend",
    "JsonFileGovernanceStateBackend",
    "OperationType",
    "OutcomeStatus",
    "RedisGovernanceStateBackend",
    "ResourceRef",
    "RiskLevel",
    "SQLiteGovernanceStateBackend",
    "create_openshell_governance_app",
    "create_openshell_governance_router",
]
