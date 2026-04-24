# TODOS — acgs-lite

Items deferred from `/autoplan` review of v2.9.0 (`ci/fix-fpdf2-types`).
Generated: 2026-04-22 | Branch: ci/fix-fpdf2-types

---

## 🔴 HIGH PRIORITY (ship these in the next PR)

- [ ] PyPI token renewal: `.pypirc` token expired (403 Forbidden). Regenerate at https://pypi.org/manage/account/token/ then run `python -m twine upload dist/acgs_lite-2.9.0*`
- [ ] Add Star History badge to README (https://star-history.com/#dislovelhl/acgs-lite)
- [ ] Add "Used in production at..." placeholder section to README


### ✅ T-01: Add exception-path test for strict-mode restoration
**Status: COMPLETE** — Committed on `ci/fix-fpdf2-types`.
Two new tests in `TestStrictModeRestoration`: `test_validate_action_restores_strict_mode_on_exception` and `test_check_compliance_restores_strict_mode_on_exception`. Uses `_TrackingEngine` pattern to capture the engine instance and verify `engine.strict is True` after `validate()` raises `RuntimeError`.

### ✅ T-02: Fix FrequencyThresholdRule wrong agent_id index
**Status: COMPLETE** — Committed on `ci/fix-fpdf2-types`.
`grouped` now stores `(timestamp, decision)` tuples. `ordered` is sorted by `p[0]`. `agent_id` comes from `decision.get("agent_id", "")` at the triggering position. Regression test added: `test_frequency_threshold_rule_reports_correct_agent_id_with_mixed_action_types`.

### ✅ T-03: Migrate mcp_server.py to engine.non_strict() context manager
**Status: COMPLETE** — Committed on `ci/fix-fpdf2-types`.
All 3 raw `try/finally` strict-mode blocks replaced with `with engine.non_strict():` in `validate_action`, `check_compliance`, and `explain_violation`.

---

## 🟡 MEDIUM PRIORITY

### T-04: validate(strict=None) — structural fix for engine.strict mutation
**User Challenge from both review phases.**
**Why:** `engine.strict` is a shared mutable attribute. Every place that temporarily overrides it (mcp_server.py, 10+ other integrations) is a mutation site that can race or fail to restore. The fix is a `strict` parameter on `validate()` that the caller passes without touching the shared attribute.
**Estimated effort:** ~3–4 hrs (API change + update all call sites + test update)

### T-05: Fix raw engine.strict mutation in all other integrations
**Files:** `langchain.py:131`, `anthropic.py:273,607,662`, `autogen.py:149`, `google_genai.py:98,148`, `litellm.py:120`, `gitlab.py:413`, `llamaindex.py:109,128,193,212`, `openai.py:82,122`, `workflow.py:133`
**Why:** Same bug pattern as the mcp_server.py fix — no try/finally, no non_strict() usage. Any exception in these paths leaves engine.strict=False permanently.
**Fix:** Either migrate to `engine.non_strict()` or add try/finally. If T-04 lands first, migrate to `validate(strict=False)` instead.
**Estimated effort:** ~2–3 hrs

### T-06: Rust strict=True fast path audit_metadata gap
**File:** `src/acgs_lite/engine/core.py:913, 1076, 1115`
**Why:** The `not audit_metadata` guard fixes the `strict=False` fast path. But the `strict=True` Rust fast path (line 913) may also return early when `_fast_records is not None`, suppressing durable audit writes at lines 1076 and 1115. "bypass fast path = audit written" is not universally true.
**Fix:** Audit the strict=True code path end-to-end. Add test: provide audit_metadata with strict=True and assert the audit entry is written.
**Estimated effort:** ~2 hrs

### T-07: check_trajectory() — make private or add RLock
**File:** `src/acgs_lite/trajectory.py:195`
**Why:** `check_trajectory()` is public but unguarded. Any external caller bypasses the lock on `check_checkpoint()` and races with `self._store.put(session)`. Also: `check_checkpoint()` calls `check_trajectory()` while holding `threading.Lock`. If `check_trajectory()` gains a lock in the future, plain Lock deadlocks — use `threading.RLock`.
**Fix (option A):** Rename to `_check_trajectory()`, deprecate public API. **Fix (option B):** Replace `threading.Lock` with `threading.RLock`.
**Estimated effort:** ~1 hr

### T-08: explain_violation outer except swallows post-validate errors
**File:** `src/acgs_lite/integrations/mcp_server.py:530–587`
**Why:** The outer `except Exception` wraps both the validate call and the post-validate code (result.violations iteration, filter, dict construction). A malformed result raises inside the outer catch and the caller gets a generic error with no violations — governance ran but the decision is orphaned.
**Fix:** Move the outer except to wrap only the post-validate code, not the validate call.
**Estimated effort:** ~30 min

### T-09: Document engine-sharing invariant (MCP + Telegram)
**File:** `src/acgs_lite/integrations/mcp_server.py`, `src/acgs_lite/integrations/telegram_webhook.py`
**Why:** The Telegram handler now runs in the thread pool (def, not async def). If it shares a GovernanceEngine instance with the MCP server, `engine.strict` mutation in the asyncio thread can race with the thread-pool call reading `self.strict`. Today there is no documentation saying these must or must not share an engine.
**Fix:** Add a one-line comment specifying whether sharing is safe, and add an integration test that wires both to the same engine and fires a request through each concurrently.
**Estimated effort:** ~1 hr

---

## 🟢 LOW PRIORITY

### T-10: Lock release before rule evaluation (performance)
**File:** `src/acgs_lite/trajectory.py:212`
**Why:** The threading.Lock is held across all rule evaluation in `check_trajectory()`. `FrequencyThresholdRule.check()` is O(N log N) on session decision count. Under 10x concurrent agents with long sessions, all callers queue while one runs a sort.
**Fix:** Do store mutation under lock, copy decisions snapshot, release lock, run rules outside.
**Estimated effort:** ~1 hr

### T-11: Debug logging for strict-mode recovery and fast-path bypass
**Why:** No log line when the finally block restores strict after exception, and no log when audit_metadata causes fast-path skip. Hard to diagnose in production.
**Fix:** Add `logger.debug("engine.strict restored after exception in %s", func_name)` and `logger.debug("fast-path bypassed: audit_metadata present")`.
**Estimated effort:** ~30 min

### T-12: audit_metadata or None — add comment explaining intentional {} → None
**File:** `src/acgs_lite/integrations/mcp_server.py:401`
**Why:** `audit_metadata or None` silently drops empty-but-technically-valid audit contexts. The behavior is intentional (a zero-hit call produces no audit entry) but will confuse future readers.
**Fix:** Add a one-line comment: `# {} is intentionally falsy — no audit entry written for zero-hit validations`.
**Estimated effort:** ~5 min

---

## Deferred Scope from CEO Review

- **validate(strict=None) API** — see T-04
- **Regression test: strict restored on exception** — see T-01
- **check_trajectory() locking** — see T-07
- **InMemoryTrajectoryStore internal thread-safety** — consider RLock inside InMemoryTrajectoryStore._store operations
- **Concurrency test for check_checkpoint()** — covered by T-01 / T-07
- **Context manager: engine.non_strict()** — see T-03
