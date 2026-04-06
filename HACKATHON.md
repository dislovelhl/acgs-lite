# ACGS-Auth0: Constitutional Token Governance for AI Agents

> **Authorized to Act Hackathon** — Auth0 Token Vault + MACI Constitutional Governance
> **Deadline**: April 6, 2026

---

## Devpost Submission

### Project Title
**ACGS-Auth0: Constitutional Token Governance for AI Agents**

### Tagline
_The constitution decides which agents get which tokens — not the agents themselves._

### Description

#### The Problem

Your AI agent can read your GitHub issues. Should it also push code? Who decides — and who gets told when it does?

Today's AI agent authorization is flat: you give an agent a token and it uses it. As agents get more capable, this becomes dangerous:

- A **planner** agent has a GitHub token. Nothing stops it from pushing code — except hope.
- A **validator** agent should never touch external APIs at all. Its entire job is to review, not act.
- Creating a pull request should require the user's explicit approval, not just historical OAuth consent.
- When a token is used, it should be attributable to a specific agent role, not just "the system."

Auth0 Token Vault solves *how* to store and exchange tokens securely. ACGS-Auth0 solves *which agents are constitutionally permitted to ask for them in the first place* — and proves it with an immutable audit trail.

#### What We Built

`acgs-auth0` is an integration package that adds a constitutional governance layer to Auth0 Token Vault. Each agent role in your system has a declared set of scopes it is *constitutionally permitted* to request. Requests outside those bounds are blocked before they reach Token Vault. Write operations require active human approval via CIBA. Everything is logged.

Under the hood it uses MACI (Montesquieu AI Constitutional Infrastructure) — a separation-of-powers framework for AI agents:

```
AI Agent → Constitutional Gate → Auth0 Token Vault → External API
            (MACI validation)     (secure exchange)
```

**Core features:**

**1. Constitutional Scope Policies (YAML)**
```yaml
token_vault:
  connections:
    github:
      EXECUTIVE:   # Proposer role — read only
        permitted_scopes: ["read:user", "repo:read"]
      IMPLEMENTER: # Executor role — write requires step-up
        permitted_scopes: ["repo:read", "repo:write"]
        high_risk_scopes: ["repo:write"]
      # JUDICIAL intentionally absent — validators never call external APIs
      # (MACI Golden Rule: agents never validate their own work)
```

**2. MACI Separation of Powers**

Three core roles — no role can both propose and validate:
- **EXECUTIVE** (Proposer): Can read GitHub, read Calendar. Cannot write.
- **IMPLEMENTER** (Executor): Can write with CIBA step-up approval.
- **JUDICIAL** (Validator): Cannot access any external API. Period.

```
JUDICIAL agent tries to read GitHub:
  → "MACI role 'JUDICIAL' is not permitted to access 'github'"
  ✅ Separation enforced.
```

**3. CIBA Step-Up for High-Stakes Operations**

When a scope is marked `high_risk`, the system triggers Auth0 CIBA — a push notification to the user's mobile device (Auth0 Guardian) — before the token is retrieved:

```
IMPLEMENTER requests repo:write
  ↓
⚠️  CIBA binding message: "AI agent requests GitHub write access to create PR #42"
📱 Push notification sent to user's Auth0 Guardian
⏳ Awaiting approval...
✅ User approved — Token Vault exchange proceeds
```

**4. Constitutional Audit Trail**

Every access attempt — granted, denied, or step-up — is recorded with agent ID, MACI role, connection, scopes, and the constitutional hash:

```json
{
  "agent_id": "planner",
  "role": "EXECUTIVE",
  "connection": "github",
  "requested_scopes": ["repo:read"],
  "outcome": "granted",
  "constitutional_hash": "608508a9bd224290",
  "timestamp": "2026-03-30T14:22:33Z"
}
```

#### How It Works

The `ConstitutionalTokenVault` wraps the Auth0 Token Vault refresh token exchange:

1. **Constitutional validation**: Check MACI role against policy — fail-closed
2. **Step-up detection**: If high-risk scopes → raise `StepUpAuthRequiredError`
3. **CIBA initiation**: `auth0-ai-langchain`'s `with_async_authorization` handles user notification
4. **Token exchange**: Auth0 `/oauth/token` with `grant_type: token-exchange:federated-connection-access-token`
5. **Audit**: Record outcome in immutable constitutional log

#### Integration with `auth0-ai-langchain`

```python
from acgs_auth0 import with_constitutional_token_vault, get_token_vault_credentials

with_github_read = with_constitutional_token_vault(
    policy,
    connection="github",
    scopes=["read:user", "repo:read"],
)

@with_github_read
async def list_open_issues(owner: str, repo: str) -> str:
    creds = get_token_vault_credentials()
    # GitHub API call with creds["access_token"]
    ...
```

If an EXECUTIVE agent calls this: ✅ granted.
If a JUDICIAL agent calls this: 🚫 `MACIRoleNotPermittedError` raised.
If an IMPLEMENTER requests write scope: ⚠️ CIBA step-up triggered.

#### Technical Stack

- **Backend**: Python 3.11+, FastAPI, async/await throughout
- **Auth**: `auth0-ai-langchain` 1.0.1, `auth0-python` 4.13.0
- **Agents**: LangChain / LangGraph tool wrapping pattern
- **Testing**: pytest-asyncio, 45 unit tests, full mock coverage
- **Governance**: ACGS MACI (Constitutional Hash: `608508a9bd224290`)

#### What I Learned

**The key insight**: Token access is a constitutional question, not just a security question.

Auth0 Token Vault is excellent at *securing credential storage and retrieval*. But in a multi-agent system with role separation, you need a governance layer that answers: "Should this specific type of agent be allowed to request these specific scopes at all?" That's not a security question — it's a policy question. It belongs in a constitution, not in individual agent code.

**Pain points and gaps discovered in Auth0's current offering:**

1. **No built-in role-based scope policies**: Token Vault treats all callers equally. There's no native way to say "EXECUTIVE agents may only read, IMPLEMENTER agents may write with approval."

2. **CIBA scoping is manual**: The `with_async_authorization` API requires developers to manually identify which scopes need step-up. A scope risk classification system (LOW/MEDIUM/HIGH/CRITICAL) would help.

3. **No multi-agent audit trail**: When multiple agents share an Auth0 tenant, there's no built-in way to attribute token accesses to specific agent roles.

4. **The `GraphInterrupt` pattern is powerful but opaque**: CIBA's interrupt/resume flow is elegant, but the error surfaces are hard to inspect. Better serializable interrupt state would help orchestration frameworks.

These patterns surfaced directly from building `acgs-auth0` — ACGS's constitutional framework made them visible.

---

## ## Bonus Blog Post

### How Constitutional Governance Changed How I Think About AI Agent Auth

When I started building ACGS-Auth0, I thought the hard part was the Auth0 integration. Connecting to Token Vault, implementing the refresh token exchange, wiring up CIBA — that's all well-documented and `auth0-ai-langchain` makes it remarkably clean.

The hard part was realizing I was solving the wrong problem.

The standard framing is: "How do I stop agents from leaking credentials?" But after building MACI (a constitutional governance layer for AI agents), I started thinking about a different question: "Should this agent be *constitutionally permitted* to even ask for these credentials?"

These sound similar but they're not. Security asks: are the credentials safe? Governance asks: is this agent authorized to act with this capability?

The difference became concrete when I built the JUDICIAL role restriction. In MACI, the JUDICIAL role validates other agents' decisions. It never proposes and it never executes. That's its entire constitutional purpose. So when I wrote the code to prevent JUDICIAL agents from accessing Token Vault at all — not because of a security rule, but because of a separation-of-powers principle — I realized I was encoding something new.

The constitutional policy YAML makes this explicit:

```yaml
# JUDICIAL is intentionally absent
# Validators verify. They never call external APIs.
# This is not a security rule — it's a constitutional principle.
```

That's the insight worth sharing: **the constitution is a better place for authorization policy than the agent itself**. When you encode scope permissions in a YAML constitution with a hash, you get auditability, version control, and amendment processes for free. When you encode it in agent code, you get technical debt and security theater.

The CIBA step-up for write access is another example. It's not just "require MFA for sensitive operations" — it's "constitutional write operations require active human endorsement, not just historical consent." The binding message sent to the user's Guardian app tells them exactly what the agent wants to do and why. That's constitutional transparency, not just authentication.

Building `acgs-auth0` for this hackathon taught me that Auth0 Token Vault is the best piece of infrastructure for the *mechanism* of AI agent credential management. The missing layer is the *governance* of which agents should be permitted to invoke that mechanism at all. That's what constitutions are for.

---

## Submission Checklist

- [x] Auth0 Token Vault integration (refresh token exchange)
- [x] CIBA step-up for high-risk scopes  
- [x] MACI role-based scope policies
- [x] Constitutional audit trail (JSONL + structlog)
- [x] `auth0-ai-langchain` integration
- [x] 45 unit tests (pytest-asyncio)
- [x] Working demo (`python main.py`)
- [x] Public code repository
- [x] README with setup instructions
- [x] Bonus Blog Post (see above)

## Links

- **Code**: https://github.com/dislovelhl/acgs
- **Demo video**: [RECORD TODAY — see DEMO_RECORDING.md]
- **Live demo**: `python examples/governed_agents/main.py`

## Team

Solo submission — Martin

---

## /autoplan Review — 2026-03-30

<!-- /autoplan restore point: /home/martin/.gstack/projects/martin668-acgs-clean/main-autoplan-restore-20260330-152718.md -->

### Executive Summary

The core library is production-quality. The submission strategy has critical gaps that could disqualify or significantly underperform. 7 days is enough time to fix all of them.

---

### Phase 1: CEO Review

#### Premises

| # | Premise | Status | Notes |
|---|---------|--------|-------|
| 1 | MACI governance is the differentiated angle | VALID | Unique among 2313 participants |
| 2 | Library can be built in time | VALID | Done |
| 3 | Judges will value constitutional depth | RISK | Judges reward demos, not architecture |
| 4 | Library without web app is acceptable | **CRITICAL RISK** | Rules require "published link to project or application" |
| 5 | New package = new work under submission rules | VALID | acgs_auth0 created after March 2, 2026 |

#### Dream State Delta

```
CURRENT STATE               THIS PLAN (today)           12-MONTH IDEAL
acgs_auth0 library          + CLI demo                  Standard integration
45 tests passing            + Devpost text draft        pattern; cited in
No live web app             Missing: web app,           Auth0 docs; pip
No video                    video, Auth0 tenant,        install acgs-auth0
Auth0 not configured        published URL
7 days to deadline          60% complete
```

#### Implementation Alternatives

```
APPROACH A: Library-only (current)
  Summary: Python package + CLI demo. Frame as "dev tool" to excuse missing URL.
  Effort:  Done
  Risk:    HIGH — may fail eligibility check, loses Design criterion (1/6 score)
  Pros:    Clean architecture, well-tested, distinctive insight value
  Cons:    No published URL, 0 points for Design judging criterion, weak video story

APPROACH B: Add minimal web demo (RECOMMENDED)
  Summary: FastAPI backend + simple Svelte/React one-pager showing governance dashboard.
           Deploy to Vercel/Fly free tier. Same acgs_auth0 logic, visual demo layer on top.
  Effort:  CC ~2h / Human ~2 days
  Risk:    MEDIUM — needs Auth0 tenant setup
  Pros:    Published URL, Design score, visual video story, judges can click it
  Cons:    Auth0 tenant required for live demo
  Reuses:  acgs_auth0 package, existing acgs.ai SvelteKit patterns

APPROACH C: Full acgs.ai integration
  Summary: Add Token Governance page to existing SvelteKit app, wire to enhanced_agent_bus.
  Effort:  CC ~3h / Human ~3 days
  Risk:    MEDIUM-HIGH — more surface area
  Pros:    Richest submission, full platform story
  Cons:    Too much scope, risk of breaking existing app
```

**RECOMMENDATION: Approach B** (P1+P2). The published URL requirement is a potential disqualifier. A 2-hour CC task could be the difference between winning and DQ.

#### Error & Rescue Registry

| Error | Trigger | Caught by | Tested? |
|-------|---------|-----------|--------|
| ConstitutionalScopeViolation | Agent requests denied scope | governed_tool | ✅ |
| MACIRoleNotPermittedError | Role not in policy | validate() | ✅ |
| StepUpAuthRequiredError | High-risk scope | exchange() | ✅ |
| RuntimeError: outside context | get_token_vault_credentials() misuse | — | ✅ |
| HTTP error from Token Vault | Auth0 non-200 | _call_token_vault | ✅ mock only |
| Auth0 domain not configured | Empty domain/client_id | _call_token_vault | ❌ MISSING |
| YAML missing token_vault key | Bad constitution.yaml | from_yaml() | ❌ MISSING |

#### Failure Modes Registry (CEO)

| Mode | Severity | Description |
|------|----------|-------------|
| No published URL | CRITICAL | Rules require it; library-only may be flagged |
| No demo video | CRITICAL | Required by submission rules |
| Auth0 tenant not configured | CRITICAL | Can't show live Token Vault exchange |
| Design criterion ignored | HIGH | ~1/6 of judging score with 0 frontend |
| MACI terminology opaque | MEDIUM | Judges may not connect to Token Vault value |
| ConstitutionalAuth0AI bug | HIGH | Context var mismatch breaks integration path |

---

### Phase 2: Design Review — SKIPPED (no UI scope detected)

*(Note: Design judging criterion IS a gap — addressed via Approach B recommendation)*

---

### Phase 3: Eng Review

#### Architecture ASCII Diagram

```
packages/acgs_auth0/
  __init__.py ─────────────────── re-exports public API
  scope_policy.py ─────────────── MACIScopePolicy ←── constitution.yaml
                                  ConnectionScopeRule
                                  PolicyValidationResult
  token_vault.py ─────────────── ConstitutionalTokenVault
                                ┌──→ scope_policy.validate()   (step 1)
                                ├──→ audit_log._append()       (step 2 — BUG: should be public)
                                ├──→ audit_log.record_*()      (steps 4)
                                └──→ _call_token_vault()        (step 3)
                                        └──→ httpx.POST /oauth/token
  governed_tool.py ──────────── with_constitutional_token_vault()
                                ConnectionTokenVaultWrapper
                                  └──→ ConstitutionalTokenVault.exchange()
                                ConstitutionalAuth0AI  ← BUG: double_wrapped ctx mismatch
  audit.py ────────────────────── TokenAuditLog → JSONL / structlog
  exceptions.py ───────────────── Error hierarchy

examples/governed_agents/
  main.py ──────────────────── CLI demo (validate() only, no exchange)
  constitutions/default.yaml ←─ policy
  tools/github_tools.py ──────── LangChain tools (github read+write)

MISSING:
  web_app/ ────────────────────── NOT EXISTS (needed for published URL)
  Auth0 tenant ────────────────── NOT CONFIGURED
  demo video ──────────────────── NOT RECORDED
```

#### Section 2: Code Quality Issues

| Severity | Location | Issue |
|----------|----------|-------|
| HIGH | `governed_tool.py:243` | `ConstitutionalAuth0AI.double_wrapped`: imports `_token_vault_credentials_ctx` but NEVER calls `.set()` — context var mismatch. Tools using `get_token_vault_credentials()` will raise RuntimeError when auth0-ai-langchain is installed. |
| HIGH | `token_vault.py:234` | `self.audit_log._append()` called directly instead of a named public method like `record_step_up_initiated()` — breaks encapsulation. |
| MEDIUM | `token_vault.py:435` | `asyncio.get_event_loop().run_until_complete()` deprecated in Python 3.10+, fails if called from async context. |
| LOW | `scope_policy.py:196` | `data.get("token_vault", data)` silently uses whole dict if key missing — should warn. |

#### Section 3: Test Coverage

**Test diagram — codepaths → coverage:**

| Codepath | Test type | Exists? |
|----------|-----------|--------|
| MACIScopePolicy.validate() — all outcomes | Unit | ✅ 8 tests |
| ConnectionScopeRule all methods | Unit | ✅ 5 tests |
| YAML load / permissive / error | Unit | ✅ 3 tests |
| ScopeRiskLevel classification | Unit | ✅ 5 tests |
| TokenAuditLog all record methods | Unit | ✅ 7 tests |
| TokenAuditLog thread safety | Unit | ✅ 1 test |
| TokenAuditLog file-backed | Unit | ✅ 1 test |
| ConstitutionalTokenVault.validate() | Unit | ✅ 3 tests |
| ConstitutionalTokenVault.exchange() — happy path | Unit (mocked) | ✅ 1 test |
| ConstitutionalTokenVault.exchange() — denied | Unit | ✅ 2 tests |
| ConstitutionalTokenVault.exchange() — step-up | Unit | ✅ 1 test |
| get_token_vault_credentials() context var | Unit | ✅ 2 tests |
| **ConstitutionalAuth0AI.with_token_vault()** | **MISSING** | ❌ 0 tests |
| **ConstitutionalAuth0AI.with_async_authorization()** | **MISSING** | ❌ 0 tests |
| **Auth0 domain not configured** | **MISSING** | ❌ 0 tests |
| **YAML missing token_vault key** | **MISSING** | ❌ 0 tests |
| **ConnectionTokenVaultWrapper sync path** | **MISSING** | ❌ 0 tests |
| _call_token_vault live HTTP | Integration | ❌ (by design — needs tenant) |

**Critical gap:** `ConstitutionalAuth0AI` has 0 test coverage. The `double_wrapped` bug is live and undetected.

#### Failure Modes Registry (Eng)

| Mode | Severity | File | Line |
|------|----------|------|------|
| Context var never set in double_wrapped | HIGH | governed_tool.py | 243 |
| asyncio.get_event_loop() in async context | MEDIUM | token_vault.py | 435 |
| Auth0 unconfigured fails late, not at construction | MEDIUM | token_vault.py | 312 |
| YAML missing token_vault key silently passes | LOW | scope_policy.py | 196 |

---

### Decision Audit Trail

<!-- AUTONOMOUS DECISION LOG -->

| # | Phase | Decision | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|
| 1 | CEO | Fix double_wrapped context var bug | P5 (explicit > clever) | Bug breaks integration when auth0-ai-langchain is installed; ~20 line fix | Leave as-is |
| 2 | CEO | Add `record_step_up_initiated()` to TokenAuditLog | P5 (explicit) | Bypassing `_append` directly is a design smell | Keep private call |
| 3 | Eng | Add test for Auth0 domain not configured | P1 (completeness) | Error path is real, test costs ~10 lines | Defer |
| 4 | Eng | Add test for YAML missing `token_vault` key | P1 (completeness) | Silent behavior should be tested | Defer |
| 5 | CEO/Eng | Fix asyncio.get_event_loop() → asyncio.run() pattern | P5 | Deprecated; fails in async contexts | Defer to post-submission |
| 6 | CEO | TASTE: Add web demo app (Approach B) | P1+P2 | May be required for eligibility; Design scoring gap | Submit library-only |
| 7 | CEO | TASTE: Lead with user benefit, not MACI terminology | P5 | Codex explicit: "constitutional governance" is opaque | Keep current framing |
| 8 | Eng | TASTE: Add ConstitutionalAuth0AI tests now vs defer | P1 | Bug is live; tests expose it | Defer |

---

### Cross-Phase Themes

**Theme: Missing runnable product** — flagged in Phase 1 (CEO: "no live web app", Codex: "no visible product") and Phase 3 (Eng: "MISSING: web_app/"). High-confidence signal. This is the single biggest risk.

**Theme: ConstitutionalAuth0AI is untested and broken** — flagged in Phase 1 (architectural risk) and Phase 3 (test coverage gap, context var bug). The advertised integration path doesn't work when auth0-ai-langchain is installed.

**Theme: Framing vs. Substance** — Codex flagged "optimizing for architectural novelty, not judge comprehension." Phase 1 premise challenge flagged MACI terminology as opaque. The idea is strong; the presentation needs reordering.
