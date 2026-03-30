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

Today's AI agent authorization is flat. You give an agent a token and it uses it. But as agents grow more capable, this becomes dangerous:

- A **planner** agent shouldn't push code to GitHub just because it has a token
- A **validator** agent should never access external APIs at all (it validates — it never acts)
- Creating a pull request should require explicit human approval, not just implicit credential access
- Every token retrieval should be auditable and attributable to a specific role and decision

Auth0 Token Vault solves *how* to store and retrieve external API tokens. ACGS-Auth0 solves *who is constitutionally allowed to ask for them*.

#### What We Built

`acgs-auth0` is an integration package that wraps Auth0 Token Vault with MACI (Montesquieu AI Constitutional Infrastructure) role-based governance:

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

- **Code**: https://github.com/[your-github]/acgs-clean
- **Demo video**: [to be recorded]
- **Live demo**: `python examples/governed_agents/main.py`

## Team

Solo submission — Martin
