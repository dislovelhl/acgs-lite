"""
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .validators import validate_constitutional_hash

logger = get_logger(__name__)

GovernanceCoreMode = Literal["legacy", "shadow", "swarm_enforced"]
VALID_GOVERNANCE_CORE_MODES: tuple[GovernanceCoreMode, ...] = (
    "legacy",
    "shadow",
    "swarm_enforced",
)

SWARM_IMPORT_ERROR: Exception | None = None

try:
    from acgs_lite import Constitution, ConstitutionalViolationError
    from constitutional_swarm import AgentDNA, ConstitutionalMesh

    SWARM_AVAILABLE = True
except ImportError as exc:
    Constitution = None  # type: ignore[assignment, misc]
    ConstitutionalMesh = None  # type: ignore[assignment, misc]
    AgentDNA = None  # type: ignore[assignment, misc]
    ConstitutionalViolationError = RuntimeError  # type: ignore[assignment, misc]
    SWARM_IMPORT_ERROR = exc
    SWARM_AVAILABLE = False


def normalize_governance_core_mode(mode: object) -> GovernanceCoreMode:
    raw_mode = str(mode).strip().lower() if mode is not None else "legacy"
    if raw_mode not in VALID_GOVERNANCE_CORE_MODES:
        raise ValueError(f"Invalid governance_core_mode: {mode}")
    return cast(GovernanceCoreMode, raw_mode)


@dataclass(frozen=True, slots=True)
class GovernanceInput:
    tenant_id: str
    trace_id: str
    message_id: str
    producer_id: str
    producer_role: str | None
    action_type: str
    content: str
    content_hash: str
    constitutional_hash: str
    autonomy_tier: str | None
    requires_independent_validator: bool
    security_scan_result: str | None
    validator_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PeerValidationDecision:
    approved: bool
    reason: str = ""
    votes_for: int = 0
    votes_against: int = 0
    quorum_met: bool = False
    assignment_id: str | None = None
    proof_root: str | None = None
    proof_constitutional_hash: str | None = None
    manifold_summary: JSONDict | None = None
    trust_score: float | None = None

    def to_metadata(self) -> JSONDict:
        metadata: JSONDict = {
            "approved": self.approved,
            "reason": self.reason,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "quorum_met": self.quorum_met,
            "assignment_id": self.assignment_id,
            "proof_root": self.proof_root,
            "proof_constitutional_hash": self.proof_constitutional_hash,
            "trust_score": self.trust_score,
        }
        if self.manifold_summary is not None:
            metadata["manifold_summary"] = self.manifold_summary
        return metadata


@dataclass(frozen=True, slots=True)
class GovernanceDecision:
    allowed: bool
    blocking_stage: str | None
    reasons: tuple[str, ...] = ()
    rule_hits: tuple[str, ...] = ()
    peer_votes: JSONDict = field(default_factory=dict)
    trust_score: float | None = None
    constitutional_hash: str = ""
    swarm_constitutional_hash: str | None = None
    engine_mode: str = "legacy"
    receipt_ref: str | None = None

    def to_metadata(self) -> JSONDict:
        metadata: JSONDict = {
            "allowed": self.allowed,
            "blocking_stage": self.blocking_stage,
            "reasons": list(self.reasons),
            "rule_hits": list(self.rule_hits),
            "peer_votes": dict(self.peer_votes),
            "trust_score": self.trust_score,
            "constitutional_hash": self.constitutional_hash,
            "engine_mode": self.engine_mode,
            "receipt_ref": self.receipt_ref,
        }
        if self.swarm_constitutional_hash is not None:
            metadata["swarm_constitutional_hash"] = self.swarm_constitutional_hash
            metadata["swarm_hash_aligned"] = (
                self.swarm_constitutional_hash == self.constitutional_hash
            )
        return metadata


@dataclass(frozen=True, slots=True)
class GovernanceReceipt:
    receipt_id: str
    engine_mode: str
    message_id: str
    producer_id: str
    content_hash: str
    constitutional_hash: str
    allowed: bool
    blocking_stage: str | None
    reasons: tuple[str, ...] = ()
    rule_hits: tuple[str, ...] = ()
    peer_validation: JSONDict = field(default_factory=dict)
    trust_score: float | None = None
    swarm_constitutional_hash: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_metadata(self) -> JSONDict:
        metadata: JSONDict = {
            "receipt_id": self.receipt_id,
            "engine_mode": self.engine_mode,
            "message_id": self.message_id,
            "producer_id": self.producer_id,
            "content_hash": self.content_hash,
            "constitutional_hash": self.constitutional_hash,
            "allowed": self.allowed,
            "blocking_stage": self.blocking_stage,
            "reasons": list(self.reasons),
            "rule_hits": list(self.rule_hits),
            "peer_validation": dict(self.peer_validation),
            "trust_score": self.trust_score,
            "created_at": self.created_at,
        }
        if self.swarm_constitutional_hash is not None:
            metadata["swarm_constitutional_hash"] = self.swarm_constitutional_hash
            metadata["swarm_hash_aligned"] = (
                self.swarm_constitutional_hash == self.constitutional_hash
            )
        return metadata


class GovernanceCore(Protocol):
    def is_available(self) -> bool: ...

    async def validate_local(self, governance_input: GovernanceInput) -> GovernanceDecision: ...

    async def validate_peer(
        self, governance_input: GovernanceInput
    ) -> PeerValidationDecision | None: ...

    async def score_governance(
        self,
        governance_input: GovernanceInput,
        peer_result: PeerValidationDecision | None,
    ) -> float | None: ...

    def build_receipt(
        self,
        governance_input: GovernanceInput,
        decision: GovernanceDecision,
    ) -> GovernanceReceipt: ...


class LegacyGovernanceCore:
    def __init__(self, expected_constitutional_hash: str) -> None:
        self._expected_constitutional_hash = expected_constitutional_hash

    def is_available(self) -> bool:
        return True

    async def validate_local(self, governance_input: GovernanceInput) -> GovernanceDecision:
        validation_result = validate_constitutional_hash(governance_input.constitutional_hash)
        if not validation_result.is_valid:
            return GovernanceDecision(
                allowed=False,
                blocking_stage="constitutional_hash",
                reasons=tuple(validation_result.errors),
                constitutional_hash=self._expected_constitutional_hash,
                engine_mode="legacy",
            )

        return GovernanceDecision(
            allowed=True,
            blocking_stage=None,
            constitutional_hash=self._expected_constitutional_hash,
            engine_mode="legacy",
        )

    async def validate_peer(
        self, governance_input: GovernanceInput
    ) -> PeerValidationDecision | None:
        _ = governance_input
        return None

    async def score_governance(
        self,
        governance_input: GovernanceInput,
        peer_result: PeerValidationDecision | None,
    ) -> float | None:
        _ = (governance_input, peer_result)
        return None

    def build_receipt(
        self,
        governance_input: GovernanceInput,
        decision: GovernanceDecision,
    ) -> GovernanceReceipt:
        return GovernanceReceipt(
            receipt_id=f"legacy:{governance_input.message_id}",
            engine_mode="legacy",
            message_id=governance_input.message_id,
            producer_id=governance_input.producer_id,
            content_hash=governance_input.content_hash,
            constitutional_hash=governance_input.constitutional_hash,
            allowed=decision.allowed,
            blocking_stage=decision.blocking_stage,
            reasons=decision.reasons,
            rule_hits=decision.rule_hits,
            peer_validation=dict(decision.peer_votes),
            trust_score=decision.trust_score,
        )


class SwarmGovernanceCore:
    def __init__(
        self,
        *,
        expected_constitutional_hash: str,
        enable_peer_validation: bool = True,
        use_manifold: bool = False,
        constitution: Constitution | None = None,
    ) -> None:
        self._expected_constitutional_hash = expected_constitutional_hash
        self._enable_peer_validation = enable_peer_validation
        self._use_manifold = use_manifold
        self._constitution, self._constitution_error = self._resolve_constitution(constitution)
        self._dna = (
            AgentDNA(
                constitution=self._constitution,
                agent_id="enhanced-agent-bus-governance-core",
                strict=False,
                validate_output=False,
            )
            if SWARM_AVAILABLE and self._constitution is not None and AgentDNA is not None
            else None
        )

    def is_available(self) -> bool:
        return self._dna is not None and self._constitution is not None and ConstitutionalMesh is not None

    def _resolve_constitution(
        self,
        constitution: Constitution | None,
    ) -> tuple[Constitution | None, str | None]:
        if not SWARM_AVAILABLE or Constitution is None:
            import_error = str(SWARM_IMPORT_ERROR) if SWARM_IMPORT_ERROR else "swarm unavailable"
            return None, import_error

        if constitution is not None:
            if constitution.hash != self._expected_constitutional_hash:
                raise ValueError(
                    "Swarm governance core requires a constitution whose hash matches "
                    f"{self._expected_constitutional_hash}; got {constitution.hash}"
                )
            return constitution, None

        for candidate in self._iter_constitution_candidates():
            try:
                resolved = Constitution.from_yaml(candidate)
            except (FileNotFoundError, OSError, ValueError):
                continue
            if resolved.hash == self._expected_constitutional_hash:
                return resolved, None

        return (
            None,
            "active constitution not found for hash "
            f"{self._expected_constitutional_hash}; set CONSTITUTION_PATH or inject a "
            "matching Constitution into SwarmGovernanceCore",
        )

    @staticmethod
    def _iter_constitution_candidates() -> tuple[Path, ...]:
        repo_root = Path(__file__).resolve().parents[2]
        env_path = os.environ.get("CONSTITUTION_PATH", "").strip()

        candidates = [
            Path(env_path).expanduser() if env_path else None,
            repo_root / "examples" / "constitution.yaml",
            repo_root / "packages" / "acgs-lite" / "examples" / "constitution.yaml",
            repo_root / "packages" / "acgs-lite" / "hackathon" / "constitution.yaml",
            repo_root / "constitutional-sentinel-demo" / "constitution.yaml",
            repo_root / "autoresearch" / "constitution.yaml",
        ]

        deduped: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            if candidate is None:
                continue
            resolved = candidate.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            deduped.append(resolved)
        return tuple(deduped)

    async def validate_local(self, governance_input: GovernanceInput) -> GovernanceDecision:
        validation_result = validate_constitutional_hash(governance_input.constitutional_hash)
        if not validation_result.is_valid:
            return GovernanceDecision(
                allowed=False,
                blocking_stage="constitutional_hash",
                reasons=tuple(validation_result.errors),
                constitutional_hash=self._expected_constitutional_hash,
                engine_mode="swarm",
                swarm_constitutional_hash=self._swarm_hash,
            )

        if not self.is_available():
            import_error = self._constitution_error or (
                str(SWARM_IMPORT_ERROR) if SWARM_IMPORT_ERROR else "swarm unavailable"
            )
            return GovernanceDecision(
                allowed=False,
                blocking_stage="swarm_unavailable",
                reasons=(import_error,),
                constitutional_hash=self._expected_constitutional_hash,
                engine_mode="swarm",
                swarm_constitutional_hash=self._swarm_hash,
            )

        assert self._dna is not None
        try:
            local_result = self._dna.validate(governance_input.content)
        except ConstitutionalViolationError as exc:
            return GovernanceDecision(
                allowed=False,
                blocking_stage="constitutional_rules",
                reasons=(str(exc),),
                constitutional_hash=self._expected_constitutional_hash,
                engine_mode="swarm",
                swarm_constitutional_hash=self._swarm_hash,
            )

        if not local_result.valid:
            return GovernanceDecision(
                allowed=False,
                blocking_stage="constitutional_rules",
                reasons=local_result.violations,
                rule_hits=_extract_rule_hits(local_result.violations),
                constitutional_hash=self._expected_constitutional_hash,
                engine_mode="swarm",
                swarm_constitutional_hash=self._swarm_hash,
            )

        return GovernanceDecision(
            allowed=True,
            blocking_stage=None,
            constitutional_hash=self._expected_constitutional_hash,
            engine_mode="swarm",
            swarm_constitutional_hash=self._swarm_hash,
        )

    async def validate_peer(
        self, governance_input: GovernanceInput
    ) -> PeerValidationDecision | None:
        validator_ids = tuple(_dedupe_strings(governance_input.validator_ids))
        if not governance_input.requires_independent_validator:
            return None
        if not self._enable_peer_validation or not validator_ids:
            return None
        if not self.is_available():
            import_error = self._constitution_error or (
                str(SWARM_IMPORT_ERROR) if SWARM_IMPORT_ERROR else "swarm unavailable"
            )
            return PeerValidationDecision(
                approved=False,
                reason=import_error,
            )

        assert self._constitution is not None
        assert ConstitutionalMesh is not None

        mesh = ConstitutionalMesh(
            self._constitution,
            peers_per_validation=len(validator_ids),
            quorum=len(validator_ids),
            seed=13,
            use_manifold=self._use_manifold,
        )
        mesh.register_agent(governance_input.producer_id, domain=governance_input.tenant_id)
        for validator_id in validator_ids:
            mesh.register_agent(validator_id, domain=governance_input.tenant_id)

        try:
            result = mesh.full_validation(
                governance_input.producer_id,
                governance_input.content,
                governance_input.message_id,
            )
        except ConstitutionalViolationError as exc:
            return PeerValidationDecision(
                approved=False,
                reason=str(exc),
            )
        trust_score = None
        if validator_ids:
            trust_score = sum(mesh.get_reputation(agent_id) for agent_id in validator_ids) / len(
                validator_ids
            )

        reason = ""
        if not result.quorum_met:
            reason = "peer quorum not met"
        elif not result.accepted:
            reason = "peer validation rejected content"

        return PeerValidationDecision(
            approved=result.accepted and result.quorum_met,
            reason=reason,
            votes_for=result.votes_for,
            votes_against=result.votes_against,
            quorum_met=result.quorum_met,
            assignment_id=result.assignment_id,
            proof_root=result.proof.root_hash if result.proof else None,
            proof_constitutional_hash=result.proof.constitutional_hash if result.proof else None,
            manifold_summary=mesh.manifold_summary(),
            trust_score=trust_score,
        )

    async def score_governance(
        self,
        governance_input: GovernanceInput,
        peer_result: PeerValidationDecision | None,
    ) -> float | None:
        _ = governance_input
        if peer_result is None:
            return None
        return peer_result.trust_score

    def build_receipt(
        self,
        governance_input: GovernanceInput,
        decision: GovernanceDecision,
    ) -> GovernanceReceipt:
        return GovernanceReceipt(
            receipt_id=f"swarm:{governance_input.message_id}",
            engine_mode="swarm",
            message_id=governance_input.message_id,
            producer_id=governance_input.producer_id,
            content_hash=governance_input.content_hash,
            constitutional_hash=governance_input.constitutional_hash,
            allowed=decision.allowed,
            blocking_stage=decision.blocking_stage,
            reasons=decision.reasons,
            rule_hits=decision.rule_hits,
            peer_validation=dict(decision.peer_votes),
            trust_score=decision.trust_score,
            swarm_constitutional_hash=decision.swarm_constitutional_hash,
        )

    @property
    def _swarm_hash(self) -> str | None:
        if self._constitution is None:
            return None
        return self._constitution.hash


def _dedupe_strings(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _extract_rule_hits(violations: Iterable[str]) -> tuple[str, ...]:
    rule_hits: list[str] = []
    for violation in violations:
        rule_id, _, _ = violation.partition(":")
        cleaned = rule_id.strip()
        if cleaned:
            rule_hits.append(cleaned)
    return tuple(rule_hits)


__all__ = [
    "GovernanceCore",
    "GovernanceCoreMode",
    "GovernanceDecision",
    "GovernanceInput",
    "GovernanceReceipt",
    "LegacyGovernanceCore",
    "PeerValidationDecision",
    "SWARM_AVAILABLE",
    "SwarmGovernanceCore",
    "VALID_GOVERNANCE_CORE_MODES",
    "normalize_governance_core_mode",
]
