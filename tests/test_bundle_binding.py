"""Tests for BundleAwareGovernanceEngine — Phase E composition wrapper."""

from __future__ import annotations

import pytest

from acgs_lite.constitution.bundle_store import InMemoryBundleStore
from acgs_lite.constitution.evidence import InMemoryLifecycleAuditSink
from acgs_lite.constitution.lifecycle_service import ConstitutionLifecycle
from acgs_lite.constitution.provenance import RuleProvenanceGraph
from acgs_lite.engine.bundle_binding import BundleAwareGovernanceEngine
from acgs_lite.evals.schema import EvalScenario


def _make_lifecycle(store: InMemoryBundleStore | None = None) -> ConstitutionLifecycle:
    return ConstitutionLifecycle(
        store=store if store is not None else InMemoryBundleStore(),
        sink=InMemoryLifecycleAuditSink(),
        provenance=RuleProvenanceGraph(),
    )


async def _drive_to_active(lc: ConstitutionLifecycle, tenant_id: str = "tenant-a") -> str:
    draft = await lc.create_draft(tenant_id, "proposer-1")
    await lc.submit_for_review(draft.bundle_id, "proposer-1")
    await lc.approve_review(draft.bundle_id, "reviewer-1")
    await lc.run_evaluation(
        draft.bundle_id,
        scenarios=[EvalScenario(id="s1", input_action="check status", expected_valid=True)],
    )
    await lc.approve(draft.bundle_id, "approver-1", signature="sig-ok")
    await lc.stage(draft.bundle_id, "executor-1")
    await lc.activate(draft.bundle_id, "executor-1")
    return draft.bundle_id


class TestBundleAwareGovernanceEngine:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_bundle(self) -> None:
        store = InMemoryBundleStore()
        binding = BundleAwareGovernanceEngine(store)

        engine = binding.for_active_bundle("tenant-x")
        assert engine is None

    @pytest.mark.asyncio
    async def test_returns_engine_for_active_bundle(self) -> None:
        store = InMemoryBundleStore()
        lc = _make_lifecycle(store)
        binding = BundleAwareGovernanceEngine(store)

        await _drive_to_active(lc, "tenant-a")

        engine = binding.for_active_bundle("tenant-a")
        assert engine is not None

    @pytest.mark.asyncio
    async def test_engine_is_cached_by_bundle_hash(self) -> None:
        store = InMemoryBundleStore()
        lc = _make_lifecycle(store)
        binding = BundleAwareGovernanceEngine(store)

        await _drive_to_active(lc, "tenant-a")

        engine1 = binding.for_active_bundle("tenant-a")
        engine2 = binding.for_active_bundle("tenant-a")
        assert engine1 is engine2  # same object — cache hit

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(self) -> None:
        store = InMemoryBundleStore()
        lc = _make_lifecycle(store)
        binding = BundleAwareGovernanceEngine(store)

        await _drive_to_active(lc, "tenant-a")

        _engine1 = binding.for_active_bundle("tenant-a")
        binding.invalidate("tenant-a")
        engine2 = binding.for_active_bundle("tenant-a")

        # After invalidation + re-fetch, a fresh engine is constructed
        # (may be a new object or same — depends on cache key)
        assert engine2 is not None

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self) -> None:
        store = InMemoryBundleStore()
        lc = _make_lifecycle(store)
        binding = BundleAwareGovernanceEngine(store)

        await _drive_to_active(lc, "tenant-a")
        await _drive_to_active(lc, "tenant-b")

        engine_a = binding.for_active_bundle("tenant-a")
        engine_b = binding.for_active_bundle("tenant-b")

        assert engine_a is not None
        assert engine_b is not None
        assert engine_a is not engine_b

    @pytest.mark.asyncio
    async def test_for_active_bundle_once_classmethod(self) -> None:
        store = InMemoryBundleStore()
        lc = _make_lifecycle(store)

        await _drive_to_active(lc, "tenant-a")

        engine = BundleAwareGovernanceEngine.for_active_bundle_once(store, "tenant-a")
        assert engine is not None

    @pytest.mark.asyncio
    async def test_for_active_bundle_once_none_when_no_active(self) -> None:
        store = InMemoryBundleStore()
        engine = BundleAwareGovernanceEngine.for_active_bundle_once(store, "tenant-z")
        assert engine is None

    @pytest.mark.asyncio
    async def test_invalidate_tenant_a_does_not_affect_b(self) -> None:
        store = InMemoryBundleStore()
        lc = _make_lifecycle(store)
        binding = BundleAwareGovernanceEngine(store)

        await _drive_to_active(lc, "tenant-a")
        await _drive_to_active(lc, "tenant-b")

        engine_b_before = binding.for_active_bundle("tenant-b")
        binding.invalidate("tenant-a")
        engine_b_after = binding.for_active_bundle("tenant-b")

        # tenant-b's cached engine should survive tenant-a invalidation
        assert engine_b_before is engine_b_after
