# acgs-lite — Structural Closure Strategies

**Premise:** A patch makes one instance of a bug go away. A structural closure makes the entire **class** of bug unrepresentable — the type system, the call graph, or the data shape simply will not let it happen.

For each theme from the gap analysis, two columns:
- **Patch** — what fixes the symptom (already in P0–P5 plan)
- **Closure** — what makes the failure mode impossible to re-introduce

---

## Theme A — Fail-Open Defaults

### Patch
Flip default flags: `enforce_maci=True`, `blocking_severities={CRITICAL}`, change `passed=True` to `passed=False` in exception handlers.

### Closure — Sum-typed `Decision` with no default
```python
class Decision(Protocol):
    def execute(self) -> Outcome: ...

@dataclass(frozen=True)
class Allow:    witness: ProofWitness          # who proved it, how
@dataclass(frozen=True)
class Deny:     rule_id: str; severity: Severity; reason: str
@dataclass(frozen=True)
class Inconclusive: cause: InconclusiveCause   # timeout | unavailable | exception
```
Then `engine.validate(...) -> Decision` — `bool` is not in the public surface anywhere. `Inconclusive` has **no method that returns "allow"** and no implicit truthiness. Every consumer must `match` exhaustively (mypy `--strict` + `assert_never`). The path "exception → fail open" disappears because there is no `bool` to flip the wrong way.

**Eliminates:** E4, F1 (Z3 UNKNOWN), `NullVerificationGate`, the `except Exception: pass` block in governed.py:383-456 (caught exception becomes `Inconclusive`, not silence).

---

## Theme B — Wired-But-Orphaned Subsystems

### Patch
Add the missing call sites (quarantine, stream wrapper, MACI self-check).

### Closure — Builder + exhaustiveness over outcome variants
```python
class EngineBuilder:
    def with_audit(self, b: AuditBackend) -> "EngineBuilder[+Audit]": ...
    def with_quarantine(self, q: Quarantine) -> "EngineBuilder[+Quarantine]": ...
    def with_handlers(self, h: HandlerSet[EscalationKind]) -> "EngineBuilder[+Handlers]": ...

# build() is only available when phantom-typed slots are filled
def build(self: EngineBuilder[+Audit, +Quarantine, +Handlers]) -> Engine: ...
```
And `HandlerSet` is exhaustive over `EscalationKind` (Block, Quarantine, Escalate, RateLimit, …). Adding a new escalation kind → existing builds fail to compile until a handler is registered. **No new orphan can be introduced.**

For the streaming wrapper, the closure is to make adapter streams **return** the engine's `GovernedStream[T]` rather than `Iterable[T]` — the unwrapped variant is not a return type any adapter can produce.

**Eliminates:** E5 (quarantine orphan), I2 (streaming wrapper not wired), the entire class of "implemented-but-uncalled" subsystems going forward.

---

## Theme C — In-Memory Production Defaults

### Patch
Default to JSONL when a path env var is set; emit startup WARN.

### Closure — Make backend non-optional and name ephemeral loudly
```python
class AuditLog:
    def __init__(self, backend: AuditBackend): ...   # required, no default

class EphemeralAuditBackend(AuditBackend):
    """⚠️  IN-MEMORY ONLY — DATA LOST ON RESTART. For tests only."""
    def __repr__(self) -> str: return "<EphemeralAuditBackend ⚠ ephemeral>"
```
And separate the trim concern via type:
```python
class ImmutableAuditLog(AuditLog): ...      # no max_entries, no trim
class CappedAuditLog(AuditLog): ...         # explicit, writes TRIM events to backend
```
The silent chain-genesis rewrite at `audit.py:228-229` becomes structurally impossible because `ImmutableAuditLog` has no `_trim()` method and `CappedAuditLog._trim()` writes a `TrimEvent` to the backend before truncating in-memory state. External verifiers always see a consistent chain.

**Eliminates:** O1, O2, O8 — durability is a deployment-time decision the type system requires you to make.

---

## Theme D — Verification Theater

### Patch
Add ECDSA signing, fix NIST score formula, rename misleading fields.

### Closure — Witness types and unrepresentable contradictions

**(D1) Replace boolean `verified` with witness ADT:**
```python
class ProofWitness:
    kind: Literal["lean_kernel", "z3_unsat_core", "llm_only", "no_proof"]

@dataclass(frozen=True)
class KernelChecked: lean_term: bytes; lakefile_hash: str
@dataclass(frozen=True)
class SmtUnsatCore: solver: str; core: list[str]; seed: int
@dataclass(frozen=True)
class LLMSuggested: model: str; prompt_hash: str   # explicitly NOT a proof
@dataclass(frozen=True)
class NoProof: reason: str                         # default state
```
A `ProofCertificate` requires a `ProofWitness`. Code that calls `cert.kernel_verified` no longer exists; you must `match witness:` and the `LLMSuggested` arm cannot pretend to be `KernelChecked`. The `kernel_verified=True after codestral fallback` confusion (F4) is unrepresentable.

**(D2) Compliance score that cannot inflate:**
```python
@dataclass(frozen=True)
class Score:
    compliant: int
    pending: int
    not_applicable: int
    @property
    def percentage(self) -> float:
        applicable = self.compliant + self.pending
        return 0.0 if applicable == 0 else self.compliant / applicable
```
NIST and EU AI Act both build a `Score` — the formula lives in one place, N/A items literally have no slot in the numerator. (Eliminates C8.)

**(D3) Signed certificate as a separate type:**
```python
class UnsignedDigest:    bytes_: bytes; sha256: str
class SignedCertificate: digest: UnsignedDigest; signature: bytes; signer: KeyId
```
Only a `Signer` holding a private key can produce `SignedCertificate`. The PDF generator takes `SignedCertificate | UnsignedDigest` and renders different footers. The string "court-attachable" is a property of `SignedCertificate` only. (Eliminates C3, O4.)

**(D4) Z3 verifier takes the `Constitution` as input:**
The current `Z3VerificationGate.check()` builds `Or(*keyword_symbols)` — vacuous because the rule body is not on the input. Closure: change the signature to `check(rule: Rule, action: Action) -> Decision` and translate `Rule` predicates into Z3 constraints structurally. Vacuous SAT becomes impossible because the formula is now a function of the rule, not a function of keyword presence. (Eliminates F2, F6.)

---

## Theme E — Concurrency Safety

### Patch
Add `threading.Lock` to three classes; wrap `engine.validate` in `to_thread`.

### Closure — Single-writer event-sourced log + actor boundary

The structural fix is to remove the shared write surface entirely:

**(E1) AuditLog as actor:**
```python
class AuditLog:
    async def record(self, entry: AuditEntry) -> EntryId:
        await self._inbox.put(entry)
        return await self._completions[entry.cid]
```
There is exactly **one** task that drains the inbox, computes the chain hash, and writes to the backend. Concurrent callers cannot race because they cannot reach `_entries` directly. Locks become unnecessary because there's nothing shared to lock.

**(E2) Engine state as immutable + atomic-replace:**
`GovernanceEngine._fast_records` and `_hot` become `frozen=True` dataclasses; updates produce a new state object swapped in atomically (`threading.Lock` only around the swap, never around access). Readers always see a consistent snapshot — no torn reads.

**(E3) MACI separation via opaque types:**
```python
class ProposerOutput: agent_id: AgentId; payload: bytes
class ValidatorVerdict: agent_id: AgentId; target: ProposerOutput; verdict: Verdict

def settle(p: ProposerOutput, v: ValidatorVerdict) -> Settlement:
    if p.agent_id == v.agent_id:
        raise SelfValidationError  # but the type system can also enforce this
```
Better: make `ValidatorVerdict.__init__` reject `target.agent_id == agent_id` at construction. Self-validation is unconstructable — no runtime check in the hot path needed. (Eliminates E2 root cause.)

**(E4) Async-only public surface:**
Move `engine.validate` to `async def`. Sync callers use `asyncio.run` or `anyio.from_thread`. The "sync call from async loop blocks the event loop" footgun (E1 finding) becomes a type error.

---

## Theme F — Test Theater

### Patch
Add more red-team cases; flip assertions to `assert blocked`.

### Closure — Property-based + differential + tainted-input types

**(F1) Property-based as primary, examples as secondary:**
```python
@given(rule=rule_strategy(), action=action_strategy(), ctx=context_strategy())
def test_validate_is_deterministic(rule, action, ctx):
    e = Engine(constitution=Constitution([rule]))
    assert e.validate(action, ctx) == e.validate(action, ctx)

@given(rules=lists(rule_strategy(), max_size=1000),
       action=mutated_action_strategy())
def test_no_bypass_via_unicode(rules, action):
    # Property: if normalize(action) violates any rule,
    # validate(action) must also violate.
```
Hypothesis explores the space; hand tests pin specific regressions. (Eliminates T2.)

**(F2) Differential testing against a reference engine:**
Ship a tiny pure-Python reference governance engine (no Rust, no caching, no fast path). Every property test runs both implementations and asserts equivalence. Optimization bugs in the production engine become visible immediately, with no need to predict the failure mode.

**(F3) Tainted-input types:**
```python
class Tainted(Generic[T]):
    """Input from outside the trust boundary."""
    _inner: T

class Sanitized(Generic[T]):
    """Input that has been normalized + redacted."""
    _inner: T

def normalize(t: Tainted[str]) -> Sanitized[str]: ...
```
`Engine.validate` takes `Sanitized[Action]`. There is no path from `Tainted[str]` to the engine that doesn't pass through `normalize` — homoglyph/zero-width/BIDI bypass becomes a type error in the integration layer. (Eliminates T6 root cause.)

**(F4) Chaos tests as fixtures:**
Provide `pytest` fixtures `with_z3_timeout`, `with_disk_full`, `with_malformed_llm` that any test can opt into. Then add a CI gate: every public engine method must have at least one test that runs under each fixture. Coverage becomes "every method × every chaos mode," not "every line." (Eliminates T5.)

---

## Bigger Architectural Moves (eliminate multiple themes at once)

### Move 1 — Capability tokens for governed actions
Replace ambient authority with explicit tokens. An agent that wants to take a governed action receives a `GovernedActionToken` from the engine; the token is non-forgeable (private constructor, sealed module). Without a token, the action API simply cannot be called. **Eliminates Themes A + E** (no fail-open path because there is no path; no MACI self-validation because tokens encode the proposer identity).

### Move 2 — Event-sourced governance state
Engine state is the fold of an append-only event log. `validate()` emits an event; queries derive state by replay. Restart restores from the log; tampering visible because events form a hash chain. **Eliminates Themes B + C** (audit log IS the source of truth — orphaned subsystems are visible as missing event consumers; in-memory state is just a cache that can always be rebuilt).

### Move 3 — Constitution as compiled program
Parse YAML/Markdown constitution into a typed AST. The verifier walks the AST and emits SMT-LIB structurally — every AST node has a `to_smt()` method, total over the variant. Adding a new predicate kind without `to_smt()` → compile error. The compiler also emits framework-mapping evidence: a single source generates the engine rules, the Z3 formulas, the Lean theorems, AND the compliance checklist mapping. **Eliminates Themes D + F1** (verification cannot be vacuous; framework count and code cannot drift).

### Move 4 — Single source-of-truth for framework definitions
Today the "18 frameworks" claim is in three places (README, `__init__.py` docstring, `MultiFrameworkAssessor` registry) and they've already drifted (iGaming = unlisted 19th). Closure: a single `frameworks/registry.toml` with required fields per framework (`name`, `controls: list[Control]`, `evidence_collectors: list[CollectorRef]`, `report_format: list[str]`). Marketing copy, `__init__.py` exports, and the registry are all generated from it. README and code cannot disagree because one is generated from the other. (Eliminates C1; reduces C6/C7 to filling required slots.)

---

## Recommended Sequencing

The structural moves are larger but pay back permanently. Sequencing:

1. **Now (1–2 weeks)** — Theme A closure (Decision sum type) + Theme C closure (no default backend). Both are localised changes with high blast radius for safety. Forces every caller to think about failure modes.
2. **Sprint 2 (2–3 weeks)** — Theme B closure (Builder + exhaustive HandlerSet) + Move 4 (framework registry). Eliminates the orphan + drift problem classes.
3. **Sprint 3 (3–4 weeks)** — Theme D closure (witness types + Z3 takes Rule). Closes the verification-theater complaint with type-level guarantees.
4. **Quarter 2** — Theme E (actor model for AuditLog) + Move 2 (event sourcing). Concurrency disappears as a hand-written concern.
5. **Quarter 2** — Theme F closure (property + differential + tainted types). Adversarial coverage becomes generative, not enumerated.
6. **Optional Q3+** — Move 1 (capability tokens) + Move 3 (constitution-as-program) for the next major (v3.0).

Each closure is breaking — version bump and migration guide. The patch path stays available for teams that can't move yet, but the structural path is what makes "always handle the work" a true property of the system, not an aspiration.
