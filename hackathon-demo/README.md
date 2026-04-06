# Governed Agent Vault

**Constitutional AI Governance for Auth0 Token Vault**

> Auth is necessary but not sufficient. You also need *policy governance*.

## What It Does

Governed Agent Vault adds a **constitutional governance layer** on top of Auth0 Token Vault. Before any OAuth token is issued to an AI agent, the request is validated against a constitution that defines:

- **Which MACI roles** (Executive, Judicial, Implementer) can access which connections
- **Which OAuth scopes** each role is permitted to request
- **Which scopes are high-risk** and require CIBA step-up approval
- **Every decision is audited** in an immutable trail

If the constitution says no, **the token is never issued**. The agent never sees the credential.

## Architecture

```
Agent Request  -->  ACGS Constitution  -->  Validate MACI Role + Scopes
                          |                              |
                  PASS: Token Vault              FAIL: Deny + Audit
                  Exchange token                 No token issued
                          |
                  Call External API
                  (GitHub / Google / Slack)
```

## How It Works

### 1. Define a constitutional policy (`constitution.yaml`)

```yaml
token_vault:
  constitutional_hash: "608508a9bd224290"
  connections:
    github:
      EXECUTIVE:
        permitted_scopes: ["read:user", "repo"]
        high_risk_scopes: []
      IMPLEMENTER:
        permitted_scopes: ["read:user", "repo", "delete_repo"]
        high_risk_scopes: ["delete_repo"]  # Requires step-up approval
```

### 2. The governance engine validates every request

```python
from acgs_auth0 import ConstitutionalTokenVault, MACIScopePolicy

policy = MACIScopePolicy.from_yaml("constitution.yaml")
vault = ConstitutionalTokenVault(policy=policy)

# Executive tries to delete a repo -> DENIED (not in their permitted scopes)
result = vault.validate(request)
# result.permitted = False
# result.denied_scopes = ["delete_repo"]
```

### 3. Tokens are ONLY issued after governance passes

In production, `vault.exchange(request)` calls Auth0 Token Vault's RFC 8693 token exchange endpoint. The token is never fetched unless the constitution permits it.

## Demo Scenarios

| Scenario | Role | Connection | Scopes | Result |
|----------|------|------------|--------|--------|
| Read GitHub repos | EXECUTIVE | github | `read:user`, `repo` | ALLOWED |
| Delete GitHub repo | EXECUTIVE | github | `delete_repo` | DENIED |
| Delete GitHub repo | IMPLEMENTER | github | `delete_repo` | STEP-UP REQUIRED |
| Read Gmail | EXECUTIVE | google-oauth2 | `gmail.readonly` | ALLOWED |
| Send Gmail | JUDICIAL | google-oauth2 | `gmail.send` | DENIED |
| Post to Slack | EXECUTIVE | slack | `chat:write` | STEP-UP REQUIRED |

## Quick Start

### Prerequisites

- Python 3.11+
- Auth0 account with Token Vault enabled

### Install

```bash
pip install acgs-auth0 fastapi uvicorn
```

### Run

```bash
# Set Auth0 credentials (optional for demo mode)
export AUTH0_DOMAIN=your-tenant.auth0.com
export AUTH0_CLIENT_ID=your-client-id
export AUTH0_CLIENT_SECRET=your-client-secret

# Start the demo
cd hackathon-demo
PYTHONPATH=../packages uvicorn app:app --reload --port 8000
```

Open http://localhost:8000 to see the interactive demo.

### Run with Docker

```bash
docker build -t governed-agent-vault .
docker run -p 8000:8000 governed-agent-vault
```

## Key Insight: Why This Matters

OAuth scopes define what an API *can* do. But AI agents need a higher-level policy layer that defines what the agent *should* do — based on its role, the context, and organizational rules.

**Token Vault handles the "how" of credential management.
ACGS handles the "whether" of agent authorization.**

Together, they create a system where:
1. Users define constitutional rules (not just OAuth scopes)
2. MACI separation of powers prevents any single agent from having unchecked access
3. High-risk operations require human step-up approval (CIBA)
4. Every decision is audited with cryptographic integrity

This is the missing layer between "the agent has credentials" and "the agent should use them."

## Technology

- **[acgs-lite](https://pypi.org/project/acgs-lite/)** — Constitutional AI governance engine (10 packages, 50K+ tests)
- **[acgs-auth0](https://pypi.org/project/acgs-auth0/)** — Auth0 Token Vault constitutional bridge
- **Auth0 Token Vault** — Secure OAuth credential management for AI agents
- **FastAPI** — Demo application server
- **MACI Framework** — Separation of powers for AI agents (proposer/validator/executor)

## Links

- [acgs-auth0 on PyPI](https://pypi.org/project/acgs-auth0/)
- [acgs-lite on PyPI](https://pypi.org/project/acgs-lite/)
- [ACGS Project](https://acgs.ai)
- [Auth0 Token Vault Docs](https://auth0.com/ai/docs/intro/token-vault)

## License

AGPL-3.0-or-later
