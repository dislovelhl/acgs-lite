---
id: read-strategy-docs-before-gap-analysis
trigger: "when asked to proceed on a project with associated strategy/roadmap documents"
confidence: 0.87
domain: workflow
source: session-observation
session: 2026-03-29-subnet-gtm-sprint
---

# Read All Strategy Docs Before Gap Analysis

## Action
Before touching any code, read ALL strategy documents — roadmap, Q&A responses,
technical notes, and concept docs — not just the primary concept document.

## Why This Matters
The Q&A and technical notes docs often contain the authoritative implementation spec,
accuracy corrections, and "what does not exist yet" lists that the concept doc elides.
Reading only the concept doc leads to building the wrong thing or missing critical design
constraints.

## Application
- `06-subnet-concept.md` → what to build
- `06-subnet-concept-technical-notes.md` → what claims are accurate vs false
- `07-subnet-concept-qa-responses.md` → the precise implementation design
- `08-subnet-implementation-roadmap.md` → phase order and deliverables

## Evidence
- 2026-03-29: Reading 5 docs (10% of session time) enabled precise gap matrix that
  identified exactly 1 missing Phase 1 file and 2 unstarted phases.
- The Q&A doc §5 contained the zero-retraining architecture for PrecedentStore —
  without it, the design would have added ML model retraining (wrong).
- The technical notes doc flagged "blockchain-anchored" as non-existent in codebase —
  without it, ChainAnchor might have been assumed to already exist.
