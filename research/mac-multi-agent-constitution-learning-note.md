# MAC: Multi-Agent Constitution Learning

*Research note, April 2026*

## Why this paper matters

This is one of the clearest signals yet that **constitutions themselves can become a learnable artifact** rather than a hand-authored static prompt.

That matters directly for ACGS.

If ACGS is the runtime and audit layer for governed agents, work like MAC points toward a future where the constitution is not only enforced, but also:
- proposed automatically,
- refined from labeled examples,
- benchmarked empirically,
- versioned over time,
- and then shipped into a governance runtime with audit trails.

That is a very promising direction for auto-constitution workflows.

## The paper in one sentence

MAC learns an interpretable natural-language constitution using a small multi-agent optimization loop, and beats leading prompt-optimization baselines by more than 50% while staying readable and auditable.

## Core idea

The paper argues that standard prompt optimization is the wrong tool for constitutional learning.

Why:
1. it often needs too many labeled examples,
2. it edits prompts as opaque blobs,
3. prompt quality saturates as the prompt gets longer,
4. and it destroys the explicit rule structure that makes constitutional AI auditable.

MAC’s alternative is to optimize over a **set of rules** instead of a monolithic prompt.

That distinction is crucial.

A constitution is treated as an ordered collection of natural-language rules that can be:
- added,
- edited,
- removed,
- evaluated,
- and retained only if task performance improves.

This is much closer to how a governance system should evolve.

## How MAC works

MAC uses four specialized agents in a loop:

1. **Annotator**
   - applies the current constitution to a batch of examples
   - produces predictions

2. **Decision agent**
   - inspects false positives / false negatives
   - decides whether to add, edit, or remove a rule
   - identifies target rule and rationale

3. **Creator**
   - drafts a new rule when the right move is to add one

4. **Editor**
   - rewrites an existing rule when refinement is better than expansion

Then the system re-runs evaluation. If the updated constitution improves the metric, the change is accepted. If not, it is discarded or retried.

So the optimization target is not "better prompt tokens." It is "better constitutional rules."

## Why that is interesting for ACGS

### 1. It preserves auditability
The output is a human-readable constitution, not an inscrutable optimized string.

That means you can:
- inspect the learned rules,
- edit them manually,
- compare versions,
- review them with domain experts,
- and plausibly anchor runtime decisions to them.

That is exactly the property ACGS needs.

### 2. It fits amendment-based governance
MAC’s add/edit/remove loop looks a lot like constitutional amendment workflow.

That suggests a future ACGS pipeline like:
- collect labeled failures or adjudication logs,
- propose candidate constitutional amendments,
- benchmark them offline,
- approve or reject them,
- assign a new constitutional hash,
- deploy the updated constitution into runtime.

This is much more compelling than manually tweaking prompts.

### 3. It gives a path to domain-specific constitutions
The paper evaluates on PII tagging across finance, legal, and healthcare, where definitions vary by domain and jurisdiction.

That is exactly the sort of environment where one universal hand-written constitution is not enough.

For ACGS, that points toward:
- sector-specific constitutions,
- customer-specific constitutions,
- jurisdiction-specific overlays,
- and learned amendments from observed failures.

### 4. It supports the case for inference-time governance
MAC is competitive with supervised fine-tuning and GRPO while keeping weights fixed.

That is strategically important because ACGS’s value is stronger when governance stays:
- explicit,
- inspectable,
- inference-time,
- and decoupled from model retraining.

### 5. It generalizes beyond classification
The paper explicitly says MAC also generalizes to tool-calling tasks.

That is the bridge from research curiosity to governed agents.

If constitutions can be learned for tool-use behavior, then auto-constitution becomes relevant to real agent systems, not just tagging benchmarks.

## Main empirical takeaways

From the paper’s public materials:
- MAC beats recent prompt optimization baselines by **more than 50%**
- it produces **human-readable, auditable rule sets**
- it reaches performance comparable to **supervised fine-tuning** and **GRPO** without parameter updates
- it works under **limited-label** settings
- it generalizes from PII tagging to **tool calling**

The strongest product-relevant claim is not the absolute benchmark number. It is the combination of:
- sample efficiency,
- readability,
- auditability,
- and transfer beyond one narrow task.

## The most important conceptual move

The paper reframes constitutions as an **optimization space with structure**.

That is the key idea worth carrying forward.

Instead of treating governance prompts as free-form text, MAC treats them as a modular artifact with semantics. That opens the door to:
- version control,
- diffing,
- learned updates,
- approval workflows,
- rollback,
- and runtime attachment to governed decisions.

That lines up unusually well with ACGS’s architecture.

## Where MAC is still limited

This is promising, but it is not the whole governance stack.

### 1. Learned constitutions are not enforced constitutions
MAC learns rules. ACGS still needs to execute and enforce them reliably at runtime.

Learning and runtime governance are different layers.

### 2. Task optimization is not institutional governance
A constitution optimized for F1 on a benchmark is not automatically a legally or operationally acceptable constitution.

You still need:
- human approval,
- review processes,
- evidence trails,
- role separation,
- and fail-closed runtime behavior.

### 3. Benchmark success does not equal safety sufficiency
Good performance on PII tagging or tool calling is encouraging, but insufficient by itself for high-stakes deployment.

A learned constitution can still be incomplete, overfit, underspecified, or vulnerable to distribution shift.

### 4. It needs governance around the constitution learner itself
If constitutions are automatically proposed, then the proposal pipeline also becomes a governed system.

That means future ACGS work should probably govern:
- who can propose amendments,
- what evidence is sufficient,
- what tests must pass,
- who approves deployment,
- and how rollback works.

## What ACGS should take from this now

### Near-term
1. Treat constitutions as modular, versioned artifacts, not just static text.
2. Make `workflow_action` execution first-class so constitutions are operational, not decorative.
3. Build better amendment and diff tooling.
4. Capture runtime failures in a form usable for future constitution learning.

### Medium-term
1. Add offline constitution-eval pipelines.
2. Support proposed-amendment generation from adjudicated failures.
3. Benchmark constitutional revisions against scenario suites before deployment.
4. Make constitutional hashes and amendment lineage central in reporting.

### Longer-term
1. Build an ACGS-native constitution learning loop.
2. Combine learned amendments with formal policy constraints.
3. Let human reviewers approve learned constitutional deltas before runtime activation.
4. Explore auto-constitution for tool access, role boundaries, refusal behavior, and escalation triggers.

## Product / research framing

A useful framing is:

- **MAC** shows how constitutions can be learned.
- **ACGS** can show how constitutions can be enforced, versioned, audited, and governed in production.

That is a strong split.

If Microsoft validates runtime governance as a market category, MAC validates constitution learning as a serious research direction.

Together, they point toward a bigger ACGS story:

> Author constitutions manually when needed, learn them when possible, enforce them at runtime, and preserve full audit lineage throughout.

## Bottom line

MAC is worth taking seriously.

Not because it replaces ACGS, but because it strengthens the long-term thesis behind it.

The paper suggests that constitutional governance does not have to stop at enforcement. The constitution itself can become a living, improvable artifact. If ACGS becomes the runtime, evidence, and amendment system around that artifact, the product gets much more powerful.

## Source
- Thareja, Gupta, Pinto, Lukas, "MAC: Multi-Agent Constitution Learning," arXiv:2603.15968, March 2026
