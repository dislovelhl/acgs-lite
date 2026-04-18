"""Lifecycle quickstart: create_draft → run_evaluation → activate → validate().

Shows the full constitution bundle lifecycle in under 20 lines of application code.
Run with: python examples/lifecycle_quickstart.py
"""

import asyncio

from acgs_lite.constitution.bundle_store import InMemoryBundleStore
from acgs_lite.constitution.evidence import InMemoryLifecycleAuditSink
from acgs_lite.constitution.lifecycle_service import ConstitutionLifecycle
from acgs_lite.engine.bundle_binding import BundleAwareGovernanceEngine
from acgs_lite.evals.schema import EvalScenario


async def main() -> None:
    store = InMemoryBundleStore()
    lc = ConstitutionLifecycle(store=store, sink=InMemoryLifecycleAuditSink())

    # 1. Draft a new constitution bundle
    draft = await lc.create_draft("tenant-acme", "proposer-alice")
    print(f"Draft created: {draft.bundle_id} (status={draft.status.value})")

    # 2. Move through the review/eval/approve/stage states
    await lc.submit_for_review(draft.bundle_id, "proposer-alice")
    await lc.approve_review(draft.bundle_id, "reviewer-bob")  # distinct from proposer
    await lc.run_evaluation(
        draft.bundle_id,
        scenarios=[
            EvalScenario(id="s1", input_action="check system status", expected_valid=True),
        ],
    )
    await lc.approve(draft.bundle_id, "approver-carol", signature="sig-carol-2026")
    await lc.stage(draft.bundle_id, "executor-dave")
    await lc.activate(draft.bundle_id, "executor-dave")
    print(f"Bundle activated: {draft.bundle_id}")

    # 3. Wire the active bundle to a GovernanceEngine
    binding = BundleAwareGovernanceEngine(store)
    engine = binding.for_active_bundle("tenant-acme")
    if engine is None:
        print("No active bundle — cannot validate.")
        return

    result = engine.validate(action="check system status", context={})
    print(f"Validation result: valid={result.valid}, violations={result.violations}")


if __name__ == "__main__":
    asyncio.run(main())
