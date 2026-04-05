---
id: roadmap-gap-matrix-before-build
trigger: "when given an implementation roadmap and an existing codebase"
confidence: 0.90
domain: workflow
source: session-observation
session: 2026-03-29-subnet-gtm-sprint
---

# Build an Explicit Gap Matrix Before Writing Code

## Action
Create a 3-column matrix: `roadmap deliverable | file | status`
Status values: ✅ exists + tested | ⚠️ exists but incomplete | ❌ not started

Sort by phase. Only build what's ❌ or ⚠️.

## Template
```
Phase 1 — Protocol Bridge:
  ✅ synapses.py                    — DeliberationSynapse, JudgmentSynapse, ValidationSynapse
  ✅ miner.py                       — ConstitutionalMiner + MinerStats
  ✅ validator.py                    — ConstitutionalValidator + ValidatorStats
  ✅ subnet_owner.py                 — SubnetOwner + PrecedentRecord + EscalatedCase
  ✅ protocol.py                     — EscalationType, MinerTier, SubnetMetrics, configs
  ❌ constitution_sync.py            — MISSING: ConstitutionDistributor/Receiver
  ⚠️ bittensor/__init__.py          — Only exports 6/30 public symbols
```

## Why
- Prevents rebuilding things that already exist
- Makes the sprint scope unambiguous before starting
- Reveals the exact dependency order (Phase 1 must be complete before Phase 2)
- Surfaces "nearly done" (⚠️) vs "completely absent" (❌)

## Evidence
- 2026-03-29: Gap matrix revealed exactly 1 missing Phase 1 file and 2 unstarted phases.
  Sprint was precisely scoped: constitution_sync.py, chain_anchor.py, precedent_store.py.
  Nothing was rebuilt that already existed. Nothing needed was skipped.
