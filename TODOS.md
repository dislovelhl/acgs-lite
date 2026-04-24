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

### ✅ T-08: explain_violation outer except swallows post-validate errors
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `src/acgs_lite/integrations/mcp_server.py:530–587`
**Why:** The outer `except Exception` wraps both the validate call and the post-validate code (result.violations iteration, filter, dict construction). A malformed result raises inside the outer catch and the caller gets a generic error with no violations — governance ran but the decision is orphaned.
**Fix:** Move the outer except to wrap only the post-validate code, not the validate call.
**Estimated effort:** ~30 min

### ✅ T-09: Document engine-sharing invariant (MCP + Telegram)
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
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

---

## New Items from /autoplan v2.10.0 Review (2026-04-23)

### 🔴 HIGH PRIORITY — P1 correctness/governance holes

### ✅ T-13: Fix `list_bundles(limit=None)` PostgreSQL LIMIT NULL bug
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `src/acgs_lite/constitution/postgres_bundle_store.py:242,248`
**Why:** Passing `None` as a LIMIT bind value causes a PostgreSQL syntax error. Any caller using `list_bundles()` without a limit hits this.
**Fix:** Omit the `LIMIT` clause entirely when `limit is None`.
**Estimated effort:** ~5 min CC

### ✅ T-14: Fix `_ensure_schema` INSERT race on concurrent cold-starts
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `src/acgs_lite/constitution/postgres_bundle_store.py:145-161`
**Why:** Two replicas starting simultaneously both run `CREATE TABLE IF NOT EXISTS` then `INSERT INTO schema_migrations`. The INSERT has no `ON CONFLICT DO NOTHING`, so the second instance raises `UniqueViolation` → `LifecycleError` at startup.
**Fix:** Add `ON CONFLICT (version) DO NOTHING` to schema_migrations INSERT.
**Estimated effort:** ~5 min CC

### ✅ T-15: Fix CAS race on new tenants in PostgresBundleStore
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `src/acgs_lite/constitution/postgres_bundle_store.py:370-387`
**Why:** `SELECT ... FOR UPDATE` locks no row when absent. Two concurrent callers with `expected=0` both pass the lock, both `ON CONFLICT ... DO UPDATE SET version=1`, and both "succeed" — defeating the optimistic concurrency guarantee for multi-replica lifecycle.
**Fix:** Add `INSERT INTO tenant_versions ... ON CONFLICT DO NOTHING` before the FOR UPDATE select to force row creation, or use a Postgres advisory lock.
**Estimated effort:** ~1-2 hr CC

### ✅ T-16: Fix `import acgs_lite` crash when optional deps absent
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `src/acgs_lite/__init__.py:131` (and lean_verify, z3_verify, formal.smt_gate)
**Why:** `from acgs_lite.openshell import ... RedisGovernanceStateBackend ...` runs at import time. If `redis` is not installed, `import acgs_lite` raises `ImportError` and makes the entire package unimportable for users who never use Redis. Same risk for Z3/Lean.
**Fix:** Add `__getattr__` lazy loading for experimental symbols (`RedisGovernanceStateBackend`, `Z3VerificationGate`, `LeanstralVerifier`, OpenShell symbols).
**Estimated effort:** ~30 min CC

### ✅ T-17: Fix docs examples lying after require_auth=True flip
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**Files:** `docs/api/lifecycle.md:16-19`, `docs/telegram-webhook.md:20-25`
**Why:** Examples call `create_governance_app()` without `api_key` — these now raise `ValueError` at startup after the v2.10.0 default flip. Callers copying these examples will hit an opaque startup failure.
**Fix:** Update all `create_governance_app()` examples to include `api_key` or `require_auth=False` with explanation.
**Estimated effort:** ~10 min CC

---

### 🟡 MEDIUM PRIORITY — P2 quality/correctness

### T-18: Add `__enter__`/`__exit__` to PostgresBundleStore
**Why:** Standard Python context-manager protocol expected for connection-holding objects. `with PostgresBundleStore(...) as store:` currently raises `AttributeError`.
**Fix:** Add `__enter__` returning `self`, `__exit__` calling `self.close()`.
**Estimated effort:** ~5 min CC

### T-19: Unify `_utcnow()` return type between stores
**Files:** `postgres_bundle_store.py:77` (returns `datetime`), `sqlite_bundle_store.py:54` (returns `str`)
**Why:** Type divergence will bite anyone extracting a shared BundleStore base or helper.
**Fix:** Unify to `datetime` in both; let each layer serialize as needed.
**Estimated effort:** ~10 min CC

### T-20: Wire `save_bundle_transactional()` into `activate()` or document as extension
**File:** `src/acgs_lite/constitution/postgres_bundle_store.py:289-346`; `lifecycle_service.py:617-648`
**Why:** `activate()` still does separate writes (supersede + save + activation record) with no savepoint. A DB failure between writes leaves half-applied state. `save_bundle_transactional()` exists but is not in the `BundleStore` protocol and has no caller.
**Fix:** Either add `save_bundle_transactional` to `BundleStore` protocol and wire `activate()` through it, or document explicitly that multi-step activation is not atomic.
**Estimated effort:** ~2 hr CC

---

### 🟢 LOW PRIORITY — adoption story (accepted from CEO review)

### ✅ T-21: Write `docs/stability.md`
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**Why:** `acgs_lite.stability()` and `API_STABILITY` exist in code but no user-facing documentation references them. Users see "4 - Beta" on PyPI and can't know what's safe to depend on.
**Content:** What stable/beta/experimental means, SemVer commitment for each tier, how to check at runtime.
**Estimated effort:** ~15 min CC

### ✅ T-22: Export `PostgresBundleStore` + `SQLiteBundleStore` from `acgs_lite.__init__`
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**Why:** Users who `pip install 'acgs-lite[postgres]'` have no discoverable import path. Neither store appears in `__all__`.
**Fix:** Add both to `__init__.py` imports and `__all__`, classify as `beta` in `_STABILITY_BETA`.
**Estimated effort:** ~5 min CC

### ✅ T-23: Add Rust fallback CI job
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**Why:** CLAUDE.md requires Python fallback testing when optional Rust acceleration exists. No CI matrix entry tests `import acgs_lite` without `acgs-lite-rust`.
**Fix:** Add matrix entry to CI that installs only `acgs-lite` (no Rust companion), runs the test suite, confirms Python fallback is used.
**Estimated effort:** ~15 min CC

### ✅ T-24: Write v2.10.0 upgrade guide in `docs/`
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**Why:** `require_auth=True` breaking change is documented in CHANGELOG only. Many users won't read it before upgrading.
**Content:** Clear migration steps, `require_auth=False` escape hatch, env var setup.
**Estimated effort:** ~15 min CC

### T-25: Push `rust-v*` tag to trigger Rust wheel build
**Why:** `wheels.yml` workflow triggers on `rust-v*` tag pushes but no such tag has been pushed. `acgs-lite-rust` package doesn't exist on PyPI yet.
**Action:** Push `rust-v0.1.0` tag after confirming `wheels.yml` is correct.
**Estimated effort:** ~5 min

---

### Priority Updates from this review

- **T-08** (explain_violation outer except): upgraded from MEDIUM → **HIGH** (P1 governance hole, both CEO and Eng voices flagged)
- **T-09** (engine-sharing invariant): upgraded from MEDIUM → **HIGH** (P1, non_strict() still mutates shared state, concurrent overlap untested)
- **T-11, T-12**: remain LOW


---

### DX Fixes from Phase 3.5 (2026-04-23)

### ✅ T-26: Fix README quickstart import name (P1 — cold install breaks immediately)
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `README.md` — first code block
**Why:** `from acgs import Constitution, GovernedAgent` → `ModuleNotFoundError`. Package is `acgs_lite`. This is the first line a developer copies.
**Fix:** Replace `from acgs import ...` with `from acgs_lite import ...` throughout README hero quickstart.
**Estimated effort:** ~5 min CC

### ✅ T-27: Replace hero demo with pip-install-friendly inline code block (P1)
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `README.md:38-40`
**Why:** `python examples/basic_governance/main.py` requires cloned repo. Fails after cold `pip install acgs-lite`. "20-second proof" takes ~8 minutes for first-time user.
**Fix:** Add inline runnable block: `python -c "from acgs_lite import ..."` that works immediately after pip install.
**Estimated effort:** ~10 min CC

### ✅ T-28: Update README version badge + add v2.10 callout (P1)
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**File:** `README.md:20`
**Why:** "Stable core (v2.9.0)" is stale after today's v2.10.0 release. Developers see mismatched version and lose confidence.
**Fix:** Update to v2.10.0. Add Installation section note about the require_auth default change.
**Estimated effort:** ~5 min CC

### ✅ T-29: Add `Upgrading from v2.9.x?` callout in README Installation section (P1)
**Status: COMPLETE** — Fixed in autopilot sprint 2026-04-24.
**Why:** `pip install --upgrade acgs-lite` gives no signal that a breaking default changed. Only discoverable via CHANGELOG.
**Fix:** Add `> **Upgrading from v2.9.x?** ...` callout pointing to CHANGELOG breaking change entry.
**Estimated effort:** ~5 min CC

### T-30: Move GovernedAgent.decorate example before MACI/audit sections (P2)
**Why:** Primary use case for AI agent developers is buried after MACI theory. Developers bouncing to find "how do I wrap my agent" hit MACI before the answer.
**Fix:** Promote the `GovernedAgent.decorate` example to immediately follow the 5-line quickstart.
**Estimated effort:** ~10 min CC

