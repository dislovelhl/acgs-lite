# MAC Paper to ACGS Roadmap Brief

*April 2026*

## Executive summary

The MAC paper, *Multi-Agent Constitution Learning*, is one of the strongest recent signals that constitutions can become a **learned, versioned, improvable artifact** rather than a fixed prompt written once by humans.

This is strategically important for ACGS.

MAC does **not** replace runtime governance. It strengthens the case for it. If constitutions can be learned from labeled failures and refined empirically, then ACGS can become the production system that:
- stores them,
- versions them,
- evaluates them,
- enforces them,
- and preserves audit lineage around every amendment.

The right interpretation is:
- **MAC** = constitution learning
- **ACGS** = constitution governance in production

That is a strong complement.

## What MAC contributes conceptually

MAC treats the constitution as a structured set of natural-language rules that can be:
- added,
- edited,
- removed,
- evaluated,
- and retained only if performance improves.

That is the important move.

It shifts constitutions from unstructured prompt text into a modular governance artifact. That maps naturally to ACGS features like:
- amendment tracking,
- constitutional hashing,
- workflow routing,
- review/approval gates,
- rollback,
- and runtime decision evidence.

## Strategic implication for ACGS

ACGS should treat constitution learning as an upstream pipeline and runtime governance as the downstream enforcement layer.

A plausible future flow looks like:
1. collect governed runtime failures, exceptions, overrides, and adjudications,
2. convert them into a constitution-learning dataset,
3. propose candidate constitutional amendments,
4. benchmark those amendments offline,
5. require human approval,
6. assign a new constitutional hash,
7. deploy into production with audit lineage preserved.

This is a much more compelling story than manual prompt tweaking.

## What this means for the roadmap

## Near-term priorities

### 1. Make `workflow_action` real
This remains the highest-leverage product move.

Why:
- it turns constitutions into executable governance law,
- it creates explicit operational semantics for violations,
- and it gives amendment learning something meaningful to optimize toward.

Target outcomes:
- enforceable routing on violation,
- first-class actions like block, audit, escalate, require-human-review,
- visible decision records showing which workflow path was triggered.

### 2. Strengthen constitutional artifact management
If constitutions are going to evolve, artifact quality becomes central.

Needed capabilities:
- constitutional diffs,
- amendment bundles,
- version compare views,
- rollback support,
- better hash visibility in reports and logs.

### 3. Capture runtime evidence in a learnable format
Today’s runtime logs should become tomorrow’s constitution-training corpus.

Needed capabilities:
- structured capture of false positives / false negatives,
- human adjudication labels,
- override rationale,
- escalation outcomes,
- scenario-linked failure examples.

### 4. Build offline constitutional evaluation loops
Before learned amendments can reach production, they need an evaluation harness.

Needed capabilities:
- scenario suites,
- regression baselines,
- diff-aware constitutional scoring,
- pre-deployment approval reports.

## Medium-term priorities

### 5. Amendment proposal pipeline
Build a pipeline that can suggest candidate constitutional updates from evidence.

This does not need to be fully autonomous at first.

A useful first version would:
- cluster similar failures,
- draft amendment text,
- attach supporting examples,
- estimate impact on benchmark suites,
- route to human reviewers.

### 6. Constitution review and approval workflow
If learned constitutions become real, governance over the learner becomes mandatory.

Needed controls:
- who may propose amendments,
- who may approve them,
- what evidence threshold is required,
- what tests must pass,
- what rollback path exists.

### 7. Sector/jurisdiction constitution overlays
MAC’s strongest evidence comes from domain-specific privacy tasks.

That supports a roadmap around:
- finance constitutions,
- healthcare constitutions,
- legal/compliance constitutions,
- EU-specific overlays,
- customer-specific overlays.

## Longer-term priorities

### 8. ACGS-native constitution learning
Longer term, ACGS should not just ingest constitutions. It should help generate and refine them.

That could look like:
- supervised amendment generation from labeled cases,
- role-specialized amendment agents,
- retrieval-augmented constitution updates,
- human-in-the-loop constitutional optimization.

### 9. Formal constraints around learned constitutions
A learned constitution should not be allowed to violate hard governance invariants.

That suggests combining learned amendment generation with:
- hard separation-of-powers constraints,
- formal policy checks,
- bounded rule schemas,
- mandatory oversight triggers.

### 10. Runtime-to-research flywheel
The long-term moat is a governance flywheel:
- production runtime generates evidence,
- evidence improves constitutions,
- improved constitutions strengthen runtime,
- audit records make the whole cycle reviewable.

That is a very strong product and research loop.

## Risks and cautions

### 1. Benchmark optimization is not governance sufficiency
A constitution that improves F1 is not automatically acceptable for production or regulation.

### 2. Learned rules still need institutional approval
Human approval, review trails, and deployment control stay mandatory.

### 3. Distribution shift remains a real problem
A learned constitution may degrade outside the benchmark regime.

### 4. The learning pipeline itself becomes part of the trust boundary
If amendment proposals are machine-generated, their generation and approval path also need governance.

## Recommended framing for external and internal use

### External
"ACGS is the runtime constitutional governance layer for agentic systems. As constitution learning matures, ACGS provides the production enforcement, auditability, and amendment control those learned constitutions require."

### Internal
"Do not treat constitution learning as a separate research curiosity. Treat it as the upstream generator for the next version of the governed artifact."

## Concrete next actions

### Product
1. Implement real `workflow_action` dispatch.
2. Improve constitutional diff and amendment visibility.
3. Add richer decision/evidence capture schemas.
4. Build pre-deployment constitutional evaluation reports.

### Research
1. Build a small constitution-eval corpus from existing governed scenarios.
2. Prototype amendment suggestion from adjudicated failures.
3. Test tool-calling governance scenarios, not just classification-style ones.
4. Explore retrieval-augmented constitution refinement.

### Go-to-market
1. Position ACGS as the place learned constitutions become production-grade.
2. Tie this story to auditability, oversight, and EU AI Act evidence requirements.
3. Use MAC to support the thesis that constitutional governance is becoming a serious technical category.

## Bottom line

The MAC paper strengthens ACGS’s long-term direction.

It suggests that constitutions can become dynamic, learned, and empirically improved. ACGS’s opportunity is to be the system that makes those constitutions governable in the real world: versioned, approved, enforced, and auditable.
