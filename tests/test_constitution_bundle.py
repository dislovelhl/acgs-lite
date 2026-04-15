"""Tests for Week 1 constitution lifecycle bundle models and store."""

from __future__ import annotations

import pytest

from acgs_lite.constitution import Constitution, Severity
from acgs_lite.constitution.activation import ActivationRecord
from acgs_lite.constitution.bundle import (
    VALID_TRANSITIONS,
    BundleStatus,
    ConstitutionBundle,
)
from acgs_lite.constitution.bundle_store import InMemoryBundleStore
from acgs_lite.constitution.editor import ConstitutionEditor
from acgs_lite.errors import MACIViolationError
from acgs_lite.maci import MACIRole


def _make_constitution() -> Constitution:
    return Constitution.from_rules(
        [
            Constitution.default().rules[0],
            Constitution.default().rules[1],
        ],
        name="bundle-test",
    )


def _make_diff() -> object:
    editor = ConstitutionEditor(_make_constitution())
    editor.add_rule("BUNDLE-001", "New governance guardrail", Severity.HIGH, "safety")
    return editor.diff()


def _make_bundle(
    *,
    tenant_id: str = "tenant-a",
    version: int = 1,
    proposed_by: str = "proposer-1",
) -> ConstitutionBundle:
    return ConstitutionBundle(
        tenant_id=tenant_id,
        version=version,
        constitution=_make_constitution(),
        diff=_make_diff(),
        proposed_by=proposed_by,
    )


class TestBundleStateMachine:
    def test_valid_transition_map_matches_spec(self) -> None:
        assert VALID_TRANSITIONS[BundleStatus.DRAFT] == {
            BundleStatus.REVIEW,
            BundleStatus.WITHDRAWN,
        }
        assert VALID_TRANSITIONS[BundleStatus.ROLLED_BACK] == {
            BundleStatus.DRAFT,
            BundleStatus.SUPERSEDED,
        }
        assert VALID_TRANSITIONS[BundleStatus.SUPERSEDED] == set()

    def test_happy_path_transitions_append_history(self) -> None:
        bundle = _make_bundle()
        bundle.transition_to(BundleStatus.REVIEW, actor_id="proposer-1", actor_role=MACIRole.PROPOSER)
        bundle.transition_to(BundleStatus.EVAL, actor_id="reviewer-1", actor_role=MACIRole.VALIDATOR)
        bundle.transition_to(
            BundleStatus.APPROVE,
            actor_id="approver-1",
            actor_role=MACIRole.VALIDATOR,
        )
        bundle.approval_signature = "sig-1"
        bundle.transition_to(
            BundleStatus.STAGED,
            actor_id="executor-1",
            actor_role=MACIRole.EXECUTOR,
        )
        bundle.transition_to(
            BundleStatus.ACTIVE,
            actor_id="executor-1",
            actor_role=MACIRole.EXECUTOR,
        )
        bundle.transition_to(
            BundleStatus.ROLLED_BACK,
            actor_id="executor-2",
            actor_role=MACIRole.EXECUTOR,
        )

        assert bundle.status == BundleStatus.ROLLED_BACK
        assert [transition.to_status for transition in bundle.status_history] == [
            BundleStatus.REVIEW,
            BundleStatus.EVAL,
            BundleStatus.APPROVE,
            BundleStatus.STAGED,
            BundleStatus.ACTIVE,
            BundleStatus.ROLLED_BACK,
        ]
        assert bundle.reviewed_by == "reviewer-1"
        assert bundle.approved_by == "approver-1"
        assert bundle.staged_by == "executor-1"
        assert bundle.activated_by == "executor-1"
        assert bundle.rolled_back_at is not None

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            (BundleStatus.DRAFT, BundleStatus.ACTIVE),
            (BundleStatus.REVIEW, BundleStatus.STAGED),
            (BundleStatus.EVAL, BundleStatus.ACTIVE),
            (BundleStatus.APPROVE, BundleStatus.ACTIVE),
            (BundleStatus.ACTIVE, BundleStatus.REVIEW),
            (BundleStatus.WITHDRAWN, BundleStatus.DRAFT),
        ],
    )
    def test_invalid_transitions_raise(self, source: BundleStatus, target: BundleStatus) -> None:
        bundle = _make_bundle()
        bundle.status = source

        with pytest.raises(ValueError, match="Cannot transition bundle"):
            bundle.transition_to(
                target,
                actor_id="actor-1",
                actor_role=MACIRole.EXECUTOR,
            )


class TestMACISeparation:
    def test_proposer_cannot_approve_bundle(self) -> None:
        bundle = _make_bundle(proposed_by="same-actor")
        bundle.transition_to(BundleStatus.REVIEW, actor_id="same-actor", actor_role=MACIRole.PROPOSER)
        bundle.transition_to(BundleStatus.EVAL, actor_id="reviewer-1", actor_role=MACIRole.VALIDATOR)

        with pytest.raises(MACIViolationError, match="approver must differ from proposer"):
            bundle.transition_to(
                BundleStatus.APPROVE,
                actor_id="same-actor",
                actor_role=MACIRole.VALIDATOR,
            )

    def test_only_staging_executor_can_activate(self) -> None:
        bundle = _make_bundle()
        bundle.transition_to(BundleStatus.REVIEW, actor_id="proposer-1", actor_role=MACIRole.PROPOSER)
        bundle.transition_to(BundleStatus.EVAL, actor_id="reviewer-1", actor_role=MACIRole.VALIDATOR)
        bundle.transition_to(
            BundleStatus.APPROVE,
            actor_id="approver-1",
            actor_role=MACIRole.VALIDATOR,
        )
        bundle.approval_signature = "sig-1"
        bundle.transition_to(
            BundleStatus.STAGED,
            actor_id="executor-1",
            actor_role=MACIRole.EXECUTOR,
        )

        with pytest.raises(MACIViolationError, match="staged the bundle may activate"):
            bundle.transition_to(
                BundleStatus.ACTIVE,
                actor_id="executor-2",
                actor_role=MACIRole.EXECUTOR,
            )


class TestSerialization:
    def test_bundle_json_round_trip(self) -> None:
        bundle = _make_bundle()
        payload = bundle.model_dump_json()
        restored = ConstitutionBundle.model_validate_json(payload)

        assert restored.bundle_id == bundle.bundle_id
        assert restored.constitutional_hash == bundle.constitution.hash
        assert restored.rules_added == 1
        assert restored.constitution.hash == bundle.constitution.hash

    def test_activation_record_from_active_bundle(self) -> None:
        bundle = _make_bundle()
        bundle.transition_to(BundleStatus.REVIEW, actor_id="proposer-1", actor_role=MACIRole.PROPOSER)
        bundle.transition_to(BundleStatus.EVAL, actor_id="reviewer-1", actor_role=MACIRole.VALIDATOR)
        bundle.transition_to(
            BundleStatus.APPROVE,
            actor_id="approver-1",
            actor_role=MACIRole.VALIDATOR,
        )
        bundle.approval_signature = "sig-1"
        bundle.transition_to(
            BundleStatus.STAGED,
            actor_id="executor-1",
            actor_role=MACIRole.EXECUTOR,
        )
        bundle.transition_to(
            BundleStatus.ACTIVE,
            actor_id="executor-1",
            actor_role=MACIRole.EXECUTOR,
        )

        activation = ActivationRecord.from_bundle(bundle, signature="signed")
        restored = ActivationRecord.model_validate_json(activation.model_dump_json())

        assert restored.bundle_id == bundle.bundle_id
        assert restored.rollback_to_bundle_id == bundle.parent_bundle_id
        assert restored.signature == "signed"


class TestInMemoryBundleStore:
    def test_store_crud_active_and_listing(self) -> None:
        store = InMemoryBundleStore()
        draft = _make_bundle(version=1)
        active = _make_bundle(version=2, proposed_by="proposer-2")
        active.status = BundleStatus.ACTIVE
        active.activated_by = "executor-1"

        store.save_bundle(draft)
        store.save_bundle(active)

        fetched = store.get_bundle(draft.bundle_id)
        assert fetched is not None
        assert fetched.bundle_id == draft.bundle_id

        active_bundle = store.get_active_bundle("tenant-a")
        assert active_bundle is not None
        assert active_bundle.bundle_id == active.bundle_id

        listed = store.list_bundles("tenant-a")
        assert [bundle.version for bundle in listed] == [2, 1]

    def test_store_saves_and_retrieves_current_activation(self) -> None:
        store = InMemoryBundleStore()
        bundle = _make_bundle(version=3)
        bundle.status = BundleStatus.ACTIVE
        bundle.activated_by = "executor-1"
        store.save_bundle(bundle)

        activation = ActivationRecord.from_bundle(bundle, signature="sig-activation")
        store.save_activation(activation)

        current = store.get_activation("tenant-a")
        assert current is not None
        assert current.bundle_id == bundle.bundle_id
        assert current.signature == "sig-activation"

    def test_store_rejects_second_active_bundle_for_same_tenant(self) -> None:
        store = InMemoryBundleStore()
        bundle_a = _make_bundle(version=1)
        bundle_a.status = BundleStatus.ACTIVE
        bundle_a.activated_by = "executor-a"
        bundle_b = _make_bundle(version=2, proposed_by="proposer-2")
        bundle_b.status = BundleStatus.ACTIVE
        bundle_b.activated_by = "executor-b"

        store.save_bundle(bundle_a)
        with pytest.raises(ValueError, match="already has an ACTIVE bundle"):
            store.save_bundle(bundle_b)
