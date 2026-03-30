# acgs-auth0 — Constitutional Token Governance for AI Agents

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Constitutional Hash](https://img.shields.io/badge/constitutional%20hash-608508a9bd224290-green)](/)
[![Tests](https://img.shields.io/badge/tests-45%20passed-brightgreen)](/)

> **Auth0 "Authorized to Act" Hackathon 2026**
> _Build an agentic AI application using Auth0 for AI Agents Token Vault_

`acgs-auth0` bridges [Auth0 Token Vault](https://auth0.com/docs/secure/tokens/token-vault) with [ACGS](https://github.com/acgs-ai/acgs-clean)'s MACI constitutional governance, so **the constitution—not the agent—decides which OAuth scopes are permitted.**

## The Problem

Current AI agent authorization is flat: you give an agent a token and it uses it. But as agents become more capable and autonomous, this creates real risks:

- A "planner" agent shouldn't be able to push code to GitHub just because it has a token
- A "validator" agent should never access external APIs at all (MACI Golden Rule: no self-validation)
- Write access to Google Calendar should require explicit human approval (CIBA step-up)
- Every token access should be recorded in an immutable constitutional audit trail

## The Solution

`acgs-auth0` adds a constitutional governance layer between your AI agents and Auth0 Token Vault:

```
AI Agent requests token
        ↓
MACI Role validated against Constitution  ← NEW
  • Is this role permitted for this connection?
  • Are all requested scopes allowed?
  • Do any scopes require CIBA step-up?
        ↓ (if permitted)
Auth0 Token Vault exchange               ← unchanged
        ↓
Agent calls external API
        ↓
Constitutional audit log                 ← NEW
```

## Key Features

### 1. Constitutional Scope Control

Define exactly which MACI roles can request which OAuth scopes in a YAML constitution:

```yaml
token_vault:
  constitutional_hash: "608508a9bd224290"
  connections:
    github:
      EXECUTIVE:          # Proposer — read only
        permitted_scopes: ["read:user", "repo:read"]
        high_risk_scopes: []
      IMPLEMENTER:        # Executor — read + write (write requires CIBA)
        permitted_scopes: ["read:user", "repo:read", "repo:write"]
        high_risk_scopes: ["repo:write"]
      # JUDICIAL is intentionally absent — validators never access external APIs
```

### 2. MACI Separation of Powers

```
JUDICIAL role → cannot access GitHub
  "MACI role 'JUDICIAL' is not permitted to access connection 'github'"
  ✅ MACI separation enforced correctly.

EXECUTIVE role → cannot write to GitHub  
  "Constitutional scope violation: requested denied scopes: ['repo:write'].
   Permitted: ['read:user', 'repo:read']"
```

### 3. CIBA Step-Up for High-Risk Scopes

When an IMPLEMENTER agent requests write access, the constitution triggers CIBA:

```
⚠️  Step-up required for: ['repo:write']

📱 CIBA binding message:
   "executor (IMPLEMENTER) requests GitHub write access to create a pull request.
    Approve or deny?"

⏳ Awaiting user approval on Auth0 Guardian mobile app...
✅ User approved via Guardian push notification
📋 Step-up approval recorded in constitutional audit log.
```

### 4. Constitutional Audit Trail

Every token access — granted, denied, or step-up — is recorded with full context:

```
✅ [granted                 ] agent=planner   role=EXECUTIVE   conn=github
🚫 [denied_scope_violation  ] agent=planner   role=EXECUTIVE   conn=github
✅ [step_up_approved        ] agent=executor  role=IMPLEMENTER conn=github
```

## Installation

```bash
pip install acgs-auth0

# With LangChain integration:
pip install "acgs-auth0[langchain]"

# Full stack (LangGraph + structlog + auth0-ai):
pip install "acgs-auth0[full]"
```

## Quick Start

```python
from acgs_auth0 import (
    MACIScopePolicy,
    ConstitutionalTokenVault,
    get_token_vault_credentials,
)

# Load constitutional policy from YAML
policy = MACIScopePolicy.from_yaml("constitution.yaml")
vault = ConstitutionalTokenVault(policy=policy)

# Pre-flight validation (no network call)
result = vault.validate(TokenVaultRequest(
    agent_id="planner",
    role="EXECUTIVE",
    connection="github",
    scopes=["repo:read"],
    refresh_token="...",
))
# result.permitted → True
# result.step_up_required → []

# Exchange (validates constitutionally, then calls Token Vault)
response = await vault.exchange(request)
# response.access_token → GitHub access token
```

## LangChain Integration

```python
from acgs_auth0 import with_constitutional_token_vault, get_token_vault_credentials
from langchain_core.tools import StructuredTool

with_github_read = with_constitutional_token_vault(
    policy,
    connection="github",
    scopes=["read:user", "repo:read"],
)

@with_github_read
async def list_issues(owner: str, repo: str) -> str:
    creds = get_token_vault_credentials()
    # use creds["access_token"] to call GitHub API
    ...

# EXECUTIVE agents can call this tool
# JUDICIAL agents cannot — constitutional violation raised automatically
```

## Run the Demo

```bash
git clone https://github.com/your-org/acgs-auth0
cd acgs-auth0/examples/governed_agents

# Run all demos (no Auth0 credentials needed for validation demos)
python main.py

# Specific scenarios:
python main.py --demo deny      # Show scope violation enforcement
python main.py --demo step-up   # Show CIBA step-up flow
python main.py --demo audit     # Show constitutional audit trail

# Live Token Vault exchange (requires Auth0 tenant):
export AUTH0_DOMAIN=your-tenant.auth0.com
export AUTH0_CLIENT_ID=your-client-id
export AUTH0_CLIENT_SECRET=your-client-secret
python main.py --demo grant
```

## Running Tests

```bash
pip install pytest pytest-asyncio pyyaml
pytest packages/acgs_auth0/tests/ -v
# 45 passed
```

## Architecture

```
acgs_auth0/
├── scope_policy.py      # MACIScopePolicy — YAML-driven role→scope mapping
├── token_vault.py       # ConstitutionalTokenVault — validation + exchange
├── governed_tool.py     # with_constitutional_token_vault() decorator
├── audit.py             # TokenAuditLog — immutable constitutional audit trail
└── exceptions.py        # ConstitutionalScopeViolation, MACIRoleNotPermittedError
```

## Judging Criteria Alignment

| Criterion | How ACGS-Auth0 addresses it |
|-----------|----------------------------|
| **Security Model** | MACI separation: JUDICIAL never accesses external APIs. Constitutional rules define exact scope boundaries. CIBA step-up for high-risk operations. Fail-closed by default. |
| **User Control** | Constitutional YAML defines agent permissions transparently. Users approve high-risk operations via CIBA Guardian push. Immutable audit trail. |
| **Technical Execution** | Production-ready: async/await, context vars, thread-safe audit log, httpx for Token Vault exchange, auth0-ai-langchain integration, 45 passing tests. |
| **Design** | Decorator pattern matches auth0-ai-langchain API. YAML constitution is human-readable. Clear error messages with allowed/denied scopes. |
| **Potential Impact** | Any multi-agent system (LangGraph, AutoGen, CrewAI) can adopt MACI scope policies without changing agent code. |
| **Insight Value** | Token access is a constitutional question, not just a security question. Surfaces: Auth0 needs first-class role-based scope policies for multi-agent systems. |

## Constitutional Hash

`608508a9bd224290` — This hash is embedded in every audit entry and validated on load to ensure the governance policy hasn't been tampered with.

## License

AGPL-3.0-or-later. Commercial license available for proprietary use.
