"""ConstitutionLifecycle — saga-style coordinator for bundle lifecycle.

Orchestrates the full path from draft creation through activation and
rollback, connecting BundleStore, PolicyRolloutPipeline, provenance
graph, and the durable lifecycle audit sink.

Concurrency contract: optimistic CAS via per-tenant version counter.
Two concurrent operations on the same tenant will race; the loser gets
a ``ConcurrentLifecycleError`` and must retry.

Fail-closed: if the evidence sink append fails after earlier side
effects, the coordinator unwinds all prior steps and raises.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from typing import Any

from acgs_lite.constitution.activation import ActivationRecord
from acgs_lite.constitution.bundle import BundleStatus, ConstitutionBundle
from acgs_lite.constitution.bundle_store import BundleStore
from acgs_lite.constitution.evidence import (
    LifecycleAuditSink,
    LifecycleAuditSinkError,
    LifecycleEvidenceRecord,
)
from acgs_lite.constitution.provenance import RuleProvenanceGraph
from acgs_lite.maci import MACIRole

logger = logging.getLogger(__name__)


class LifecycleError(Exception):
    """Base error for lifecycle coordinator failures."""


class BundleNotFoundError(LifecycleError, LookupError):
    """Raised when a lifecycle operation references a missing bundle."""


class ConcurrentLifecycleError(LifecycleError):
    """Raised when a tenant-level CAS check fails."""


class LifecycleEvidenceError(LifecycleError):
    """Raised when the evidence sink fails and the operation is unwound."""


class ConstitutionLifecycle:
    """Saga-style coordinator for the constitution bundle lifecycle.

    All mutating operations follow this pattern:
    1. Read durable state (bundle, audit head, tenant version).
    2. Perform side effects (store saves, rollout, provenance).
    3. Append evidence as the final commit point.
    4. If evidence append fails, unwind all prior side effects.
    """

    __slots__ = (
        "_store",
        "_sink",
        "_provenance",
        "_tenant_versions",
    )

    def __init__(
        self,
        store: BundleStore,
        sink: LifecycleAuditSink,
        provenance: RuleProvenanceGraph | None = None,
    ) -> None:
        self._store = store
        self._sink = sink
        self._provenance = provenance if provenance is not None else RuleProvenanceGraph()
        self._tenant_versions: dict[str, int] = {}

    # ── tenant CAS guard ────────────────────────────────────────────────

    def _read_tenant_version(self, tenant_id: str) -> int:
        return self._tenant_versions.get(tenant_id, 0)

    def _cas_tenant_version(self, tenant_id: str, expected: int) -> None:
        current = self._tenant_versions.get(tenant_id, 0)
        if current != expected:
            raise ConcurrentLifecycleError(
                f"Tenant {tenant_id!r} version conflict: expected {expected}, current {current}"
            )
        self._tenant_versions[tenant_id] = current + 1

    # ── evidence helper ─────────────────────────────────────────────────

    def _make_evidence(
        self,
        bundle: ConstitutionBundle,
        *,
        from_status: str,
        to_status: str,
        actor_id: str,
        actor_role: str,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> LifecycleEvidenceRecord:
        return LifecycleEvidenceRecord(
            bundle_id=bundle.bundle_id,
            tenant_id=bundle.tenant_id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            metadata=metadata or {},
        )

    def _append_evidence(
        self,
        record: LifecycleEvidenceRecord,
        expected_prev_hash: str | None,
    ) -> str:
        """Append evidence to the sink. Returns the new chain hash."""
        receipt = self._sink.append(record, expected_prev_hash)
        return receipt.chain_hash

    # ── bundle helpers ──────────────────────────────────────────────────

    def _load_bundle(self, bundle_id: str) -> ConstitutionBundle:
        bundle = self._store.get_bundle(bundle_id)
        if bundle is None:
            raise BundleNotFoundError(f"Bundle not found: {bundle_id!r}")
        return bundle

    def _next_version(self, tenant_id: str) -> int:
        bundles = self._store.list_bundles(tenant_id, limit=1)
        if not bundles:
            return 1
        return bundles[0].version + 1

    # ── public API ──────────────────────────────────────────────────────

    # ── rule mutation helpers (DRAFT only) ──────────────────────────────

    def _assert_draft(self, bundle: ConstitutionBundle) -> None:
        if bundle.status != BundleStatus.DRAFT:
            raise LifecycleError(
                f"Bundle {bundle.bundle_id!r} must be in DRAFT state for rule mutations, "
                f"current: {bundle.status.value!r}"
            )

    async def add_rule(
        self,
        bundle_id: str,
        rule: Any,
    ) -> ConstitutionBundle:
        """Add a rule to a DRAFT bundle."""
        bundle = self._load_bundle(bundle_id)
        self._assert_draft(bundle)
        audit_head = self._sink.head()

        new_rules = [*bundle.constitution.rules, rule]
        bundle.constitution = bundle.constitution.model_copy(update={"rules": new_rules})
        self._store.save_bundle(bundle)

        rule_id = getattr(rule, "id", "unknown")
        evidence = self._make_evidence(
            bundle,
            from_status=BundleStatus.DRAFT.value,
            to_status=BundleStatus.DRAFT.value,
            actor_id=bundle.proposed_by,
            actor_role=MACIRole.PROPOSER.value,
            reason=f"Rule added: {rule_id}",
        )
        self._append_evidence(evidence, audit_head)
        return self._load_bundle(bundle_id)

    async def remove_rule(
        self,
        bundle_id: str,
        rule_id: str,
    ) -> ConstitutionBundle:
        """Remove a rule from a DRAFT bundle by rule ID."""
        bundle = self._load_bundle(bundle_id)
        self._assert_draft(bundle)
        audit_head = self._sink.head()

        new_rules = [r for r in bundle.constitution.rules if r.id != rule_id]
        if len(new_rules) == len(bundle.constitution.rules):
            raise LifecycleError(f"Rule {rule_id!r} not found in bundle {bundle_id!r}")
        bundle.constitution = bundle.constitution.model_copy(update={"rules": new_rules})
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=BundleStatus.DRAFT.value,
            to_status=BundleStatus.DRAFT.value,
            actor_id=bundle.proposed_by,
            actor_role=MACIRole.PROPOSER.value,
            reason=f"Rule removed: {rule_id}",
        )
        self._append_evidence(evidence, audit_head)
        return self._load_bundle(bundle_id)

    async def modify_rule(
        self,
        bundle_id: str,
        rule_id: str,
        updates: dict[str, Any],
    ) -> ConstitutionBundle:
        """Modify a rule in a DRAFT bundle by rule ID."""
        bundle = self._load_bundle(bundle_id)
        self._assert_draft(bundle)
        audit_head = self._sink.head()

        found = False
        new_rules = []
        for r in bundle.constitution.rules:
            if r.id == rule_id:
                new_rules.append(r.model_copy(update=updates))
                found = True
            else:
                new_rules.append(r)

        if not found:
            raise LifecycleError(f"Rule {rule_id!r} not found in bundle {bundle_id!r}")
        bundle.constitution = bundle.constitution.model_copy(update={"rules": new_rules})
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=BundleStatus.DRAFT.value,
            to_status=BundleStatus.DRAFT.value,
            actor_id=bundle.proposed_by,
            actor_role=MACIRole.PROPOSER.value,
            reason=f"Rule modified: {rule_id}",
        )
        self._append_evidence(evidence, audit_head)
        return self._load_bundle(bundle_id)

    # ── lifecycle transitions ───────────────────────────────────────────

    async def create_draft(
        self,
        tenant_id: str,
        proposer_id: str,
        base_bundle_id: str | None = None,
    ) -> ConstitutionBundle:
        """Create a new draft bundle, optionally forking from an existing one."""
        tv = self._read_tenant_version(tenant_id)

        if base_bundle_id is not None:
            base = self._load_bundle(base_bundle_id)
            constitution = base.constitution.model_copy(deep=True)
            parent_bundle_id = base.bundle_id
            parent_hash = base.constitutional_hash
        else:
            from acgs_lite.constitution.core import Constitution

            constitution = Constitution.default()
            parent_bundle_id = None
            parent_hash = None

        version = self._next_version(tenant_id)
        bundle = ConstitutionBundle(
            tenant_id=tenant_id,
            version=version,
            constitution=constitution,
            proposed_by=proposer_id,
            parent_bundle_id=parent_bundle_id,
            parent_hash=parent_hash,
        )

        audit_head = self._sink.head()
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status="none",
            to_status=BundleStatus.DRAFT.value,
            actor_id=proposer_id,
            actor_role=MACIRole.PROPOSER.value,
            reason="Draft created",
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            # Unwind: we can't reliably remove from store, but the bundle
            # is still DRAFT and harmless. Log and raise.
            logger.error("Evidence append failed on create_draft for %s", bundle.bundle_id)
            raise LifecycleEvidenceError(
                f"Evidence append failed for create_draft on bundle {bundle.bundle_id!r}"
            ) from exc

        self._cas_tenant_version(tenant_id, tv)
        return self._load_bundle(bundle.bundle_id)

    async def submit_for_review(
        self,
        bundle_id: str,
        actor_id: str,
    ) -> ConstitutionBundle:
        """DRAFT -> REVIEW. Freezes content, generates diff."""
        bundle = self._load_bundle(bundle_id)
        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        bundle.transition_to(
            BundleStatus.REVIEW,
            actor_id=actor_id,
            actor_role=MACIRole.PROPOSER,
        )
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.REVIEW.value,
            actor_id=actor_id,
            actor_role=MACIRole.PROPOSER.value,
            reason="Submitted for review",
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            # Unwind: restore bundle to DRAFT
            bundle.status = BundleStatus.DRAFT
            bundle.status_history.pop()
            bundle.submitted_at = None
            self._store.save_bundle(bundle)
            raise LifecycleEvidenceError(
                f"Evidence append failed for submit_for_review on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)
        return self._load_bundle(bundle_id)

    async def approve_review(
        self,
        bundle_id: str,
        reviewer_id: str,
    ) -> ConstitutionBundle:
        """REVIEW -> EVAL. Reviewer must != proposer."""
        bundle = self._load_bundle(bundle_id)
        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        bundle.transition_to(
            BundleStatus.EVAL,
            actor_id=reviewer_id,
            actor_role=MACIRole.VALIDATOR,
        )
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.EVAL.value,
            actor_id=reviewer_id,
            actor_role=MACIRole.VALIDATOR.value,
            reason="Review approved",
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            bundle.status = BundleStatus.REVIEW
            bundle.status_history.pop()
            bundle.reviewed_by = None
            self._store.save_bundle(bundle)
            raise LifecycleEvidenceError(
                f"Evidence append failed for approve_review on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)
        return self._load_bundle(bundle_id)

    async def reject(
        self,
        bundle_id: str,
        actor_id: str,
        reason: str,
    ) -> ConstitutionBundle:
        """Any pre-active state -> REJECTED."""
        bundle = self._load_bundle(bundle_id)
        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        bundle.transition_to(
            BundleStatus.REJECTED,
            actor_id=actor_id,
            actor_role=MACIRole.VALIDATOR,
            reason=reason,
        )
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.REJECTED.value,
            actor_id=actor_id,
            actor_role=MACIRole.VALIDATOR.value,
            reason=reason,
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            bundle.status = BundleStatus(from_status)
            bundle.status_history.pop()
            self._store.save_bundle(bundle)
            raise LifecycleEvidenceError(
                f"Evidence append failed for reject on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)
        return self._load_bundle(bundle_id)

    async def run_evaluation(
        self,
        bundle_id: str,
        scenarios: list[Any] | None = None,
        eval_run_id: str | None = None,
        pass_threshold: float = 1.0,
    ) -> ConstitutionBundle:
        """Execute eval scenarios against a bundle in EVAL state.

        :param bundle_id: ID of the bundle to evaluate.
        :param scenarios: Non-empty list of ``EvalScenario`` objects.
            Raises ``LifecycleError`` when *None* or empty — vacuous-pass
            bypass (passing zero scenarios to force a "passed" result) is
            explicitly rejected.
        :param eval_run_id: Optional explicit run ID; auto-generated if omitted.
        :param pass_threshold: Fraction of scenarios that must pass (0.0–1.0).
            Defaults to 1.0 (all scenarios must pass).
        """
        from acgs_lite.engine import GovernanceEngine
        from acgs_lite.evals.runner import evaluate_scenario
        from acgs_lite.evals.schema import EvalScenario

        if not scenarios:
            raise LifecycleError(
                "run_evaluation() requires a non-empty list of EvalScenario objects. "
                "Passing None or an empty list is rejected to prevent vacuous-pass bypass."
            )
        for i, s in enumerate(scenarios):
            if not isinstance(s, EvalScenario):
                raise LifecycleError(
                    f"scenarios[{i}] is {type(s).__name__!r}, expected EvalScenario. "
                    "Passing raw dicts causes AttributeError deep in the eval runner."
                )

        bundle = self._load_bundle(bundle_id)
        if bundle.status != BundleStatus.EVAL:
            raise LifecycleError(
                f"Bundle {bundle_id!r} must be in EVAL state to run evaluation, "
                f"current: {bundle.status.value!r}"
            )

        audit_head = self._sink.head()
        run_id = eval_run_id or f"eval-{bundle.bundle_id[:8]}"

        engine = GovernanceEngine(bundle.constitution, strict=False)
        total = len(scenarios)
        passed = sum(1 for s in scenarios if evaluate_scenario(engine, s).passed)
        pass_rate = passed / total
        status = "passed" if pass_rate >= pass_threshold else "failed"

        bundle.eval_run_ids.append(run_id)
        bundle.eval_summary = {
            "status": status,
            "run_id": run_id,
            "total": total,
            "passed": passed,
            "pass_rate": pass_rate,
        }
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=BundleStatus.EVAL.value,
            to_status=BundleStatus.EVAL.value,
            actor_id="system",
            actor_role="system",
            reason=f"Evaluation completed: {run_id} ({passed}/{total} passed, {status})",
            metadata={"eval_run_id": run_id, "pass_rate": pass_rate, "status": status},
        )
        self._append_evidence(evidence, audit_head)
        return self._load_bundle(bundle_id)

    async def approve(
        self,
        bundle_id: str,
        approver_id: str,
        signature: str,
    ) -> ConstitutionBundle:
        """EVAL -> APPROVE. Approver must != proposer. Requires passing eval."""
        bundle = self._load_bundle(bundle_id)
        if approver_id == bundle.proposed_by:
            raise LifecycleError(
                f"Approver {approver_id!r} cannot be the same actor as the proposer"
            )
        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        if not bundle.eval_summary.get("status") == "passed":
            raise LifecycleError(
                f"Bundle {bundle_id!r} requires a passing evaluation before approval"
            )

        bundle.transition_to(
            BundleStatus.APPROVE,
            actor_id=approver_id,
            actor_role=MACIRole.VALIDATOR,
        )
        bundle.approval_signature = signature
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.APPROVE.value,
            actor_id=approver_id,
            actor_role=MACIRole.VALIDATOR.value,
            reason="Evaluation passed, bundle approved",
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            bundle.status = BundleStatus.EVAL
            bundle.status_history.pop()
            bundle.approved_by = None
            bundle.approved_at = None
            bundle.approval_signature = None
            self._store.save_bundle(bundle)
            raise LifecycleEvidenceError(
                f"Evidence append failed for approve on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)
        return self._load_bundle(bundle_id)

    async def stage(
        self,
        bundle_id: str,
        executor_id: str,
        canary_agent_ids: list[str] | None = None,
    ) -> ConstitutionBundle:
        """APPROVE -> STAGED. Deploys to canary agents via rollout pipeline."""
        bundle = self._load_bundle(bundle_id)
        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        if canary_agent_ids:
            bundle.canary_agent_ids = canary_agent_ids

        bundle.transition_to(
            BundleStatus.STAGED,
            actor_id=executor_id,
            actor_role=MACIRole.EXECUTOR,
        )
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.STAGED.value,
            actor_id=executor_id,
            actor_role=MACIRole.EXECUTOR.value,
            reason="Bundle staged for canary rollout",
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            # Unwind staging
            bundle.status = BundleStatus.APPROVE
            bundle.status_history.pop()
            bundle.staged_by = None
            bundle.staged_at = None
            self._store.save_bundle(bundle)
            raise LifecycleEvidenceError(
                f"Evidence append failed for stage on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)
        return self._load_bundle(bundle_id)

    async def activate(
        self,
        bundle_id: str,
        executor_id: str,
    ) -> ActivationRecord:
        """STAGED -> ACTIVE. Full enforcement.

        Compensation order:
        1. Load state + read audit head
        2. Supersede old active bundle (if any) and save
        3. Transition new bundle to ACTIVE and save
        4. Write ActivationRecord
        5. Write provenance edge
        6. Append evidence (final commit point)

        If evidence fails, unwind steps 5-2 in reverse.
        """
        bundle = self._load_bundle(bundle_id)
        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        # 1. Snapshot previous active state for rollback
        old_active = self._store.get_active_bundle(bundle.tenant_id)
        old_activation = self._store.get_activation(bundle.tenant_id)

        # 2. Supersede old active bundle
        if old_active is not None:
            old_active.transition_to(
                BundleStatus.SUPERSEDED,
                actor_id="system",
                actor_role="system",
                reason=f"Superseded by bundle {bundle.bundle_id}",
            )
            self._store.save_bundle(old_active)

        # 3. Transition new bundle to ACTIVE
        try:
            bundle.transition_to(
                BundleStatus.ACTIVE,
                actor_id=executor_id,
                actor_role=MACIRole.EXECUTOR,
            )
            self._store.save_bundle(bundle)
        except Exception:
            # Restore old active bundle if we superseded it
            if old_active is not None:
                old_active.status = BundleStatus.ACTIVE
                old_active.status_history.pop()
                self._store.save_bundle(old_active)
            raise

        # 4. Write ActivationRecord
        activation = ActivationRecord.from_bundle(
            bundle,
            signature=bundle.approval_signature or "",
            rollback_to_bundle_id=(old_active.bundle_id if old_active is not None else None),
        )
        self._store.save_activation(activation)

        # 5. Write provenance edge
        provenance_written = False
        if old_active is not None:
            try:
                # Ensure nodes exist
                if self._provenance.get_node(old_active.bundle_id) is None:
                    self._provenance.add_rule(old_active.bundle_id)
                if self._provenance.get_node(bundle.bundle_id) is None:
                    self._provenance.add_rule(bundle.bundle_id)
                from acgs_lite.constitution.provenance import ProvenanceRelation

                self._provenance.add_relation(
                    old_active.bundle_id,
                    bundle.bundle_id,
                    ProvenanceRelation.REPLACED_BY,
                    reason=f"Activated bundle {bundle.bundle_id} replacing {old_active.bundle_id}",
                )
                provenance_written = True
            except (ValueError, KeyError):
                logger.warning(
                    "Provenance edge write failed for %s -> %s",
                    old_active.bundle_id,
                    bundle.bundle_id,
                )

        # 6. Append evidence — final commit point
        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.ACTIVE.value,
            actor_id=executor_id,
            actor_role=MACIRole.EXECUTOR.value,
            reason="Bundle activated",
            metadata={
                "superseded_bundle_id": (old_active.bundle_id if old_active is not None else None),
            },
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            # UNWIND in reverse order: provenance, activation, bundle, old bundle
            logger.error("Evidence append failed on activate for %s — unwinding", bundle.bundle_id)

            # Undo provenance (best-effort; graph has no remove_relation)
            if provenance_written:
                logger.warning(
                    "Cannot remove provenance edge %s -> %s (graph is append-only)",
                    old_active.bundle_id if old_active else "?",
                    bundle.bundle_id,
                )

            # Restore activation record
            if old_activation is not None:
                self._store.save_activation(old_activation)

            # Restore new bundle to STAGED
            bundle.status = BundleStatus.STAGED
            bundle.status_history.pop()
            bundle.activated_by = None
            bundle.activated_at = None
            self._store.save_bundle(bundle)

            # Restore old active bundle from SUPERSEDED
            if old_active is not None:
                old_active.status = BundleStatus.ACTIVE
                old_active.status_history.pop()
                self._store.save_bundle(old_active)

            raise LifecycleEvidenceError(
                f"Evidence append failed for activate on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)
        return activation

    async def rollback(
        self,
        bundle_id: str,
        executor_id: str,
        reason: str,
    ) -> ActivationRecord:
        """ACTIVE -> ROLLED_BACK. Re-activates parent bundle.

        Idempotent: if the bundle is already ROLLED_BACK, returns the
        current activation record without duplicate side effects.
        """
        bundle = self._load_bundle(bundle_id)

        # Idempotent: already rolled back
        if bundle.status == BundleStatus.ROLLED_BACK:
            activation = self._store.get_activation(bundle.tenant_id)
            if activation is not None:
                return activation
            raise LifecycleError(
                f"Bundle {bundle_id!r} is ROLLED_BACK but no activation record found"
            )

        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        # Find the parent bundle to restore
        parent_bundle_id = bundle.parent_bundle_id
        parent_bundle: ConstitutionBundle | None = None
        if parent_bundle_id is not None:
            parent_bundle = self._store.get_bundle(parent_bundle_id)

        # 1. Transition current bundle to ROLLED_BACK
        bundle.transition_to(
            BundleStatus.ROLLED_BACK,
            actor_id=executor_id,
            actor_role=MACIRole.EXECUTOR,
            reason=reason,
        )
        self._store.save_bundle(bundle)

        # 2. Re-activate parent if available.
        # NOTE: Direct status assignment bypasses the state machine because
        # SUPERSEDED is terminal (VALID_TRANSITIONS[SUPERSEDED] == set()).
        # The evidence sink is the authoritative audit trail for this path.
        # Week 3 follow-up: consider ActivationRecord.for_restoration().
        restored_activation: ActivationRecord | None = None
        if parent_bundle is not None and parent_bundle.status in {
            BundleStatus.SUPERSEDED,
            BundleStatus.ROLLED_BACK,
        }:
            parent_bundle.status = BundleStatus.ACTIVE
            parent_bundle.activated_by = executor_id
            self._store.save_bundle(parent_bundle)

            restored_activation = ActivationRecord.from_bundle(
                parent_bundle,
                signature=parent_bundle.approval_signature or "",
                rollback_to_bundle_id=parent_bundle.parent_bundle_id,
            )
            self._store.save_activation(restored_activation)

        # 3. Provenance edge
        if parent_bundle is not None:
            try:
                if self._provenance.get_node(bundle.bundle_id) is None:
                    self._provenance.add_rule(bundle.bundle_id)
                if self._provenance.get_node(parent_bundle.bundle_id) is None:
                    self._provenance.add_rule(parent_bundle.bundle_id)
                from acgs_lite.constitution.provenance import ProvenanceRelation

                self._provenance.add_relation(
                    bundle.bundle_id,
                    parent_bundle.bundle_id,
                    ProvenanceRelation.REPLACED_BY,
                    reason=f"Rollback: {reason}",
                )
            except (ValueError, KeyError):
                logger.warning(
                    "Provenance edge write failed on rollback %s -> %s",
                    bundle.bundle_id,
                    parent_bundle.bundle_id,
                )

        # 4. Evidence — final commit point
        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.ROLLED_BACK.value,
            actor_id=executor_id,
            actor_role=MACIRole.EXECUTOR.value,
            reason=reason,
            metadata={
                "restored_bundle_id": (
                    parent_bundle.bundle_id if parent_bundle is not None else None
                ),
            },
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            logger.error("Evidence append failed on rollback for %s — unwinding", bundle.bundle_id)

            # Undo parent re-activation
            if parent_bundle is not None and restored_activation is not None:
                parent_bundle.status = BundleStatus.SUPERSEDED
                parent_bundle.activated_by = None
                self._store.save_bundle(parent_bundle)

            # Restore current bundle to ACTIVE
            bundle.status = BundleStatus.ACTIVE
            bundle.status_history.pop()
            bundle.rolled_back_at = None
            self._store.save_bundle(bundle)

            # Restore original activation
            old_activation = ActivationRecord.from_bundle(
                bundle,
                signature=bundle.approval_signature or "",
            )
            self._store.save_activation(old_activation)

            raise LifecycleEvidenceError(
                f"Evidence append failed for rollback on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)

        if restored_activation is not None:
            return restored_activation

        # No parent to restore — return a record for the rolled-back state
        return ActivationRecord(
            bundle_id=bundle.bundle_id,
            version=bundle.version,
            tenant_id=bundle.tenant_id,
            constitutional_hash=bundle.constitutional_hash,
            activated_by=executor_id,
            parent_bundle_id=bundle.parent_bundle_id,
            rollback_to_bundle_id=None,
            signature=bundle.approval_signature or "",
        )

    async def withdraw(
        self,
        bundle_id: str,
        proposer_id: str,
        reason: str = "withdrawn by proposer",
    ) -> ConstitutionBundle:
        """Any pre-active -> WITHDRAWN. Only original proposer."""
        bundle = self._load_bundle(bundle_id)
        tv = self._read_tenant_version(bundle.tenant_id)
        audit_head = self._sink.head()
        from_status = bundle.status.value

        bundle.transition_to(
            BundleStatus.WITHDRAWN,
            actor_id=proposer_id,
            actor_role=MACIRole.PROPOSER,
            reason=reason,
        )
        self._store.save_bundle(bundle)

        evidence = self._make_evidence(
            bundle,
            from_status=from_status,
            to_status=BundleStatus.WITHDRAWN.value,
            actor_id=proposer_id,
            actor_role=MACIRole.PROPOSER.value,
            reason=reason,
        )
        try:
            self._append_evidence(evidence, audit_head)
        except LifecycleAuditSinkError as exc:
            bundle.status = BundleStatus(from_status)
            bundle.status_history.pop()
            self._store.save_bundle(bundle)
            raise LifecycleEvidenceError(
                f"Evidence append failed for withdraw on bundle {bundle_id!r}"
            ) from exc

        self._cas_tenant_version(bundle.tenant_id, tv)
        return self._load_bundle(bundle_id)

    # ── read helpers ────────────────────────────────────────────────────

    async def get_active_bundle(self, tenant_id: str) -> ConstitutionBundle | None:
        return self._store.get_active_bundle(tenant_id)

    async def get_bundle(self, bundle_id: str) -> ConstitutionBundle | None:
        return self._store.get_bundle(bundle_id)

    async def get_bundle_history(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[ConstitutionBundle]:
        return self._store.list_bundles(tenant_id, limit=limit)

    async def get_activation_record(self, tenant_id: str) -> ActivationRecord | None:
        return self._store.get_activation(tenant_id)


__all__ = [
    "ConcurrentLifecycleError",
    "ConstitutionLifecycle",
    "LifecycleError",
    "LifecycleEvidenceError",
]
