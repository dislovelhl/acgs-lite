# Devpost Submission: Governed Agent Vault

## Project Name
Governed Agent Vault — Constitutional AI Governance for Auth0 Token Vault

## Tagline
The constitution decides whether an agent gets a token — not the agent itself.

---

## Description

### Inspiration

OAuth scopes tell you what an API *can* do. But when AI agents act on behalf of users, you need a higher-level policy layer that answers: *should* this agent use these credentials right now?

We built Governed Agent Vault to answer that question with a constitutional governance framework.

### What it does

Governed Agent Vault adds a **constitutional policy layer** between AI agents and Auth0 Token Vault. Before any OAuth token is issued:

1. The agent's request is validated against a YAML-defined constitution
2. MACI role separation (Executive/Judicial/Implementer) determines which scopes each agent type can access
3. High-risk scopes automatically trigger CIBA step-up approval
4. Every decision (granted, denied, step-up) is recorded in an immutable audit trail
5. If the constitution says no, **the token is never issued** — the agent never sees the credential

### How we built it

- **acgs-auth0** (Python package, published on PyPI) bridges Auth0 Token Vault with ACGS constitutional governance
- **MACIScopePolicy** defines per-connection, per-role scope permissions in YAML
- **ConstitutionalTokenVault** wraps Token Vault's RFC 8693 token exchange with pre-flight constitutional validation
- **FastAPI demo app** with interactive UI showing 6 governance scenarios across GitHub, Google, and Slack
- Built on top of **acgs-lite**, our constitutional AI governance engine (50K+ tests, 10 packages)

### Key architectural decisions

- **Fail-closed**: If the constitution can't be loaded or validation fails, no token is issued
- **MACI separation of powers**: No single agent role has unchecked access — Executives can read but not delete, Implementers can delete but need step-up approval
- **Scope risk classification**: Built-in heuristics classify OAuth scopes (LOW/MEDIUM/HIGH/CRITICAL) to automatically flag dangerous operations
- **Zero credential exposure**: The governance layer validates *before* any token exchange — agents never see credentials for denied requests

### Challenges we ran into

The hardest part was mapping the MACI constitutional governance model to OAuth scope hierarchies. OAuth scopes are flat strings, but governance needs to understand risk levels, role permissions, and escalation paths. We solved this with a declarative YAML policy format that's human-readable but machine-enforceable.

### What we learned

Auth is necessary but not sufficient for AI agent safety. OAuth scopes control what APIs expose, but you also need a policy layer that controls what agents are *allowed* to do — based on their role, the operation's risk level, and organizational rules. Token Vault + constitutional governance is the right combination.

### What's next

- Production deployment with real Auth0 Token Vault token exchange
- Integration with LangGraph and Vercel AI SDK via the `with_constitutional_token_vault` decorator
- EU AI Act Article 14 human oversight integration (step-up approval linked to CIBA)
- Multi-tenant constitutions for different organizational units

---

## Built With

- python
- fastapi
- auth0
- token-vault
- acgs-lite
- oauth2
- maci-governance

## Try It Out

- [GitHub Repository](https://github.com/dislovelhl/acgs-clean/tree/main/hackathon-demo)
- [acgs-auth0 on PyPI](https://pypi.org/project/acgs-auth0/)

---

## Blog Post (Bonus Prize)

### Auth Is Necessary But Not Sufficient: Why AI Agents Need Constitutional Governance

When you give an AI agent access to your GitHub repos, Gmail, or Slack, you're trusting it with your digital identity. Auth0 Token Vault solves the credential management problem beautifully — secure storage, automatic refresh, scoped access. But there's a gap between "the agent has credentials" and "the agent should use them."

**That gap is policy governance.**

Consider a team of AI agents working together. The planning agent needs to read your GitHub repos to understand the codebase. The implementation agent needs to create branches and push code. The review agent needs read-only access. And nobody should be deleting repos without explicit human approval.

OAuth scopes alone can't express this. You need:
- **Role-based access**: Different agent types get different permissions
- **Risk-aware escalation**: Destructive operations require human step-up
- **Immutable audit trails**: Every access attempt is recorded, whether granted or denied
- **Fail-closed defaults**: If policy can't be evaluated, deny access

This is exactly what MACI (Multi-Agent Constitutional Infrastructure) provides. MACI separates agent responsibilities into Executive (orchestration), Judicial (validation), and Implementer (execution) roles — inspired by constitutional separation of powers.

**Governed Agent Vault** combines Auth0 Token Vault with MACI constitutional governance:

```yaml
token_vault:
  connections:
    github:
      EXECUTIVE:
        permitted_scopes: ["read:user", "repo"]
      IMPLEMENTER:
        permitted_scopes: ["read:user", "repo", "delete_repo"]
        high_risk_scopes: ["delete_repo"]  # Requires CIBA step-up
```

When an Executive agent requests `delete_repo`, the constitution denies it — the token is never fetched. When an Implementer requests it, the constitution permits it but flags it as high-risk, triggering CIBA step-up approval. The user gets a push notification to approve or deny.

The key insight: **the governance layer sits between the agent and Token Vault**. It validates *before* any credential is exchanged. This means:
- Denied requests never touch the token — zero credential exposure for unauthorized actions
- The audit trail captures intent, not just access — you know what the agent *tried* to do
- Policy changes take effect immediately without redeploying agents

Token Vault handles the *how* of credential management. Constitutional governance handles the *whether*. Together, they make AI agents safe to deploy at scale.

The EU AI Act takes effect August 2, 2026. Article 14 mandates human oversight for high-risk AI systems. CIBA step-up approval, triggered by constitutional policy, is how you implement Article 14 compliance for agentic systems.

Auth is the foundation. Governance is the guardrail. You need both.

---

*Built with [acgs-lite](https://pypi.org/project/acgs-lite/) and [acgs-auth0](https://pypi.org/project/acgs-auth0/). Constitutional Hash: 608508a9bd224290.*
