# acgs-lite Gap Analysis — 2026-04-16

**Goal:** Find capability gaps and improvements to fully close `acgs-lite` so it can "always handle the work."
**Method:** 6 parallel scientist agents across engine/MACI, compliance, formal verification, integrations, observability, and test coverage.
**Status:** RESEARCH_COMPLETE

---

## Executive Summary

`acgs-lite` (v2.8.0) is a mature governance library with 19 compliance frameworks, multiple LLM/agent adapters, formal verification (Z3 + Lean), and a streaming engine. The architecture is sound, but there is a recurring pattern of **fail-open defaults**, **wired-but-orphaned subsystems**, and **in-memory production defaults** that prevent it from being trustworthy under real load. The test suite is broad (124 files) but shallow on adversarial, chaos, and concurrency surfaces.

Six cross-cutting themes emerge — fixing them closes ~80% of the production-readiness gap.

---

## Cross-Cutting Themes

### Theme A — Fail-Open Defaults (CRITICAL)
The system silently allows actions when components fail. A constitutional safety library that defaults to "allow on error" is the wrong shape.

| Component | Symptom | Source |
|---|---|---|
| Z3 UNKNOWN/timeout | `satisfiable=True, verified=False` — callers checking `satisfiable` allow it | F1, smt_gate.py:89 |
| Streaming validator on engine exception | sets `passed=True, should_halt=False` and logs a warning | E4, streaming.py:210-227 |
| `_validate_nonstrict()` | unconditionally enters `non_strict()` — CRITICAL violations don't halt | E4 |
| `blocking_severities` | defaults to empty `frozenset()` — no severity halts streaming | E4 |
| CDP emission block in `governed.py` | blanket `except Exception: pass` on entire compliance + intervention chain | E5, governed.py:383-456 |
| MACI enforcement | `enforce_maci=False` default → role separation is advisory | E2 |
| `NullVerificationGate` | always returns `satisfiable=True, contradiction=False` | F1, smt_gate.py:89 |

**Fix shape:** Adopt a tri-state `SAFE / VIOLATION / INCONCLUSIVE` and require callers to handle `INCONCLUSIVE` explicitly. Replace `except Exception: pass` with `except Exception as exc: log + fail_closed`.

---

### Theme B — Wired-But-Orphaned Subsystems (HIGH)
Capabilities are fully implemented and tested in isolation, then not called from any pipeline.

| Capability | What's built | What's missing |
|---|---|---|
| `GovernanceQuarantine` | full lifecycle (submit/approve/deny/timeout) | never invoked from `InterventionEngine._handle_escalate()` (E5) |
| `GovernedStreamWrapper` / `StreamingValidator` | engine-level chunk validator | no adapter (LangChain/Anthropic/Google/AutoGen/LlamaIndex) wraps its stream with it (I2) |
| SQLite audit backend (`acgs.audit_sqlite`) | exists in `acgs-core` | dynamic-import probe in server.py is invisible to `acgs-lite` standalone; no docs (O1) |
| `JSONLAuditBackend` | fsync-based durability | never auto-selected; no rotation, TTL, or size cap (O1, O8) |
| `pqc_signature` field on `AuditEntry` | typed and tested | `InMemoryPQCSigner` is a test stub (no real PQC); CDPRecordV1 has no signing field (O4) |
| `MACIEnforcer.check_no_self_validation()` | exists, lines 101-125 | grep of `governed.py` for it returns 0 — proposer can self-validate (E2) |
| `proof_hash` on ProofCertificate | computed | never used as cache key (F5) |

**Fix shape:** A two-day sprint of wiring calls — no new architecture needed.

---

### Theme C — In-Memory Production Defaults (HIGH)
Every governance decision is lost on restart unless the operator knows to wire a backend.

- `AuditLog` defaults to `InMemoryAuditBackend` in 14+ integration paths (O1)
- `InMemoryCDPBackend` is the sole CDP implementation; `server.py` instantiates it as module global (O2)
- `max_entries=10_000` trim silently rebases the chain genesis hash → external verifiers misled (O8)
- `ObservationLogger` appends without rotation to `~/.acgs/observations.jsonl` (O8)

**Fix shape:** Default to JSONL when a path env var is set; emit a startup WARN when neither backend is configured. Ship `RotatingJSONLAuditBackend` and `SQLiteCDPBackend` (~100 LOC each).

---

### Theme D — Verification Theater (HIGH)
Marketed verification primitives don't prove what their names imply.

| Claim | Reality |
|---|---|
| "court-attachable" PDF certificate | SHA-256 integrity hash only — no signature, no PKI, no timestamp anchor (C3, O4) |
| "Z3 verified" | `Z3VerificationGate` SAT-checks `Or(*keyword_symbols)` — trivially SAT (F2) |
| "Lean kernel proven" | `kernel_verified=False` is the production default when Lean toolchain absent (F3) |
| "Constitutional rules verified" | Z3 verifier hardcodes 6 boolean predicates; user `Rule` objects never reach it (F6) |
| "Leanstral fallback" | mutates `self._model` in-place (not thread-safe); `LeanVerifyResult` has no `fallback_used` field (F4) |
| Lean theorem strength | `_build_theorem_statement` silently drops fields not in runtime context — provable for trivial instantiations (F7) |
| 18-framework compliance | 19 frameworks actually present (iGaming undocumented); NIST RMF MEASURE 1.1/1.2/1.4 have no evidence collectors; HIPAA PHI redaction is a label only (C1, C6, C7) |
| NIST RMF compliance score | counts NOT_APPLICABLE as COMPLIANT — inflated and incomparable to EU AI Act score (C8) |

**Fix shape:** Either deliver the substance or trim the marketing. Add ECDSA signing for certificates; encode actual `Rule` semantics into Z3; add `fallback_used` and `kernel_verified` to public surface; align `_build_assessment` across frameworks.

---

### Theme E — No Concurrency Safety (HIGH)
The package is shipped as a multi-agent governance layer but has no synchronization on shared state.

- `AuditLog._entries` — list append + chain hash recompute, lock-free (E3)
- `GovernanceEngine._fast_records` and `_hot` cache — mutated unlocked (E3)
- `InterventionEngine._throttle_state` / `_cooloff_state` — docstring says "single-process only" (E3)
- Module-level `_request_counter = itertools.count(1)` in `audit_runtime.py` — increment-then-use is not atomic (E3)
- `LeanstralVerifier._model` mutation — not safe for concurrent verify() calls (F4)
- `GovernanceEngine.validate()` is sync; called inside `GovernedAgent.arun()` without `to_thread` — blocks event loop (E1)
- `arun()` skips the circuit breaker pre-check that `run()` performs at step 0 — async kill-switch bypass (E1 bonus)

**Test gap:** 0 dedicated thread-safety/race test files; 1 file with 2 cancellation assertions; no `asyncio.gather` of 50 concurrent validates (T3).

**Fix shape:** Add `threading.Lock` to the three shared-state classes; replace counter with `threading.local()` or locked counter; wrap `engine.validate` in `asyncio.to_thread` inside `arun()`; mirror the `run()` step-0 circuit breaker check.

---

### Theme F — Adversarial & Chaos Test Gaps (MEDIUM)
124 test files, but the failure modes that matter in production are untested.

- Red-team tests assert `isinstance(result.valid, bool)` (no-crash), not `result.valid is False` (T1)
- 0 property-based / Hypothesis tests across the suite (T2)
- 0 chaos tests for: Z3 hang, audit log disk full, malformed LLM JSON (T5)
- Unicode evasion tests cover only benign inputs — no BIDI override (U+202E), no overlong UTF-8, no null bytes (T6)
- 0 tool-call hijack tests — payload inside `tool_calls` arg dict bypasses text-only governance (T7)
- All ~30 integration test files mock-only — no VCR cassettes; SDK contract drift invisible (T8)
- 5 CLI test files; 0 use `CliRunner` or `subprocess` for full-stack invocation (T9)
- 0 mutation testing config; package-level `[tool.coverage]` absent → inherits repo-root 70% threshold (T10)

---

## Adapter Coverage Matrix (selected)

| Provider | Extra | Adapter | Streaming Output Gov. | Tool-Call Gov. | Async | Status |
|---|---|---|---|---|---|---|
| OpenAI | `openai` | yes | input-only | NO | yes | partial |
| Anthropic | `anthropic` | yes | input-only | YES (only one) | NO `acreate` | partial |
| Google GenAI | `google` | yes | input-only | NO | yes | partial |
| LiteLLM | `litellm` | yes | input-only | NO | yes | partial |
| LangChain | `langchain` | yes | input-only | NO | yes | partial |
| AutoGen | `autogen` | yes | input-only | NO | yes | partial |
| LlamaIndex | `llamaindex` | yes | input-only | NO | yes | partial |
| **Mistral** | `mistral` | **MISSING** | — | — | — | **broken promise** |
| MCP | `mcp` | server-only | n/a | yes (server) | yes | client adapter missing (I8) |
| DSPy / Pydantic AI / Haystack / xAI | none | yes | — | NO | mixed | extras not declared (I7) |
| Semantic Kernel / smolagents / LlamaStack | — | MISSING | — | — | — | not present (I10) |

---

## Prioritized Action Plan (top 15)

### P0 — Fail-Closed & Safety
1. **MACI self-validation enforcement** — wire `check_no_self_validation()` into `_check_maci()`; flip `enforce_maci` default to `True` with deprecation path. (E2)
2. **Streaming fail-closed** — change `_validate_window()` exception handler to `passed=False, should_halt=True`; default `blocking_severities = {CRITICAL}`. (E4)
3. **Z3 tri-state result** — replace `(satisfiable, verified)` with `SAFE | VIOLATION | INCONCLUSIVE`; require explicit handling. Apply to `NullVerificationGate` too. (F1)
4. **Async kill-switch** — mirror `run()` step-0 circuit breaker check inside `arun()`. (E1)

### P1 — Wire Orphaned Subsystems
5. **Wire `GovernanceQuarantine`** — call `quarantine.submit(cdp_record)` from `InterventionEngine._handle_escalate()`. (E5)
6. **Wire `GovernedStreamWrapper` into adapter streams** — wrap LangChain/Google/AutoGen/LlamaIndex streaming methods with the existing engine wrapper. (I2)
7. **Default to durable backends** — JSONL when env var set, WARN at startup otherwise; ship `SQLiteCDPBackend`. (O1, O2)

### P2 — Concurrency Safety
8. **Add `threading.Lock`** to `AuditLog._entries` (with chain hash), `GovernanceEngine._fast_records`/`_hot`, `InterventionEngine` rate state; replace `itertools.count` request counter. (E3)
9. **Async-wrap engine.validate()** — `await asyncio.to_thread(self.engine.validate, ...)` in `GovernedAgent.arun()`. (E1)
10. **Concurrent validate() race test** — `asyncio.gather` 50 mixed allow/deny calls and assert all correct. (T3)

### P3 — Verification & Compliance Substance
11. **Wire `Rule`/`Constitution` into `Z3ConstraintVerifier`** — translate user rules into Z3 constraints; remove vacuous `Or(*keywords)` gate. (F2, F6)
12. **Add CDP signing** — optional ECDSA via `cryptography` extra; embed signature + key fingerprint in PDF; remove "court-attachable" until shipped. (C3, O4)
13. **Compliance fixes** — add GDPR Art. 17 erasure, EU AI Act Art. 61/72, fix NIST RMF NOT_APPLICABLE inflation, document iGaming as 19th framework. (C4, C5, C8, C1)

### P4 — Adapter & Integration Fill
14. **Mistral adapter** + tool-call governance for OpenAI/LiteLLM/AutoGen/LangChain; declare extras for DSPy/Pydantic AI/Haystack/xAI. (I1, I3, I7)

### P5 — Adversarial Test Coverage
15. **Red-team substance** — `xfail` or assert-blocked for homoglyph/zero-width; add chaos tests (Z3 hang, audit disk full, malformed JSON); add tool-call hijack tests; add `[tool.coverage] fail_under=80, branch=true`. (T1, T5, T7, T10)

---

## Limitations

- All findings are static (source read + grep). No dynamic execution; `.coverage` not parsed.
- Some `acgs.*` modules (e.g., `acgs.audit_sqlite`) live in `acgs-core` and may partially mitigate `acgs-lite` defaults when both are installed — undocumented for standalone users.
- Lean theorem-strength gap (F7) requires actual Lean kernel runs to confirm exploitation.
- "Marketed but undelivered" judgments are based on README/docstring text vs. code — some may have been intentional caveats.

---

## Appendix — Stage-to-Finding Index

- E1–E5: engine, MACI, async, concurrency, quarantine
- C1–C8: compliance frameworks, certificate signing, GDPR/EU AI Act/NIST/HIPAA gaps
- F1–F7: Z3/Lean/Leanstral verification soundness
- I1–I10: adapter coverage, streaming, tool calls, federation, OTel, missing frameworks
- O1–O9: audit durability, CDP backend, PII redaction, certificate verifiability, eval, metrics, replay, rotation, dashboards
- T1–T10: red-team depth, property tests, concurrency, benchmarks, chaos, unicode, tool hijack, cassettes, CLI, mutation
