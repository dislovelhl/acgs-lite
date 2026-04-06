# acgs-auth0

[![PyPI](https://img.shields.io/pypi/v/acgs-auth0)](https://pypi.org/project/acgs-auth0/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-auth0)](https://pypi.org/project/acgs-auth0/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Constitutional Token Governance for AI Agents — ACGS × Auth0 Token Vault.**

`acgs-auth0` bridges Auth0 Token Vault with ACGS MACI constitutional governance. The constitution — not the agent — decides which OAuth scopes are permitted for each MACI role. Every token request is validated before Auth0 is called; every access attempt (granted or denied) is recorded in an immutable constitutional audit log.

## Installation

```bash
pip install acgs-auth0
```

For LangChain tool integration (requires `auth0-ai-langchain`):

```bash
pip install "acgs-auth0[langchain]"
```

For the full stack (auth0-ai, langchain, langgraph, structlog):

```bash
pip install "acgs-auth0[full]"
```

> `acgs-lite` is **not** automatically installed. If you need it (e.g. for `MACIRole` or `Constitution`), install it separately:
>
> ```bash
> pip install acgs-lite "acgs-auth0[langchain]"
> ```

Requires Python 3.11+.

## Quick Start

### 1. Define a scope policy

Create a `constitution.yaml` with the `token_vault` section:

```yaml
token_vault:
  constitutional_hash: "608508a9bd224290"
  connections:
    github:
      EXECUTIVE:
        permitted_scopes: ["read:user", "repo:read"]
        high_risk_scopes: []
      IMPLEMENTER:
        permitted_scopes: ["read:user", "repo:read", "repo:write"]
        high_risk_scopes: ["repo:write"]
    google-oauth2:
      EXECUTIVE:
        permitted_scopes: ["openid", "https://www.googleapis.com/auth/calendar.freebusy"]
        high_risk_scopes: []
```

### 2. Wrap a tool with constitutional token governance

```python
from acgs_auth0 import (
    with_constitutional_token_vault,
    MACIScopePolicy,
    get_token_vault_credentials,
)

policy = MACIScopePolicy.from_yaml("constitution.yaml")

with_github_read = with_constitutional_token_vault(
    policy=policy,
    connection="github",
    scopes=["read:user", "repo:read"],
)

@with_github_read
def list_open_issues(repo: str) -> list[dict]:
    creds = get_token_vault_credentials()
    # Use creds["access_token"] to call the GitHub API
    ...
```

The decorator validates the agent's MACI role against the policy before the function body executes. High-risk scopes trigger CIBA step-up authentication.

### 3. Use `ConstitutionalTokenVault` directly

```python
from acgs_auth0 import ConstitutionalTokenVault, MACIScopePolicy

policy = MACIScopePolicy.from_yaml("constitution.yaml")
vault = ConstitutionalTokenVault(
    policy=policy,
    auth0_domain="your-tenant.auth0.com",   # or set AUTH0_DOMAIN env var
    auth0_client_id="...",                   # or AUTH0_CLIENT_ID
    auth0_client_secret="...",               # or AUTH0_CLIENT_SECRET
)

# Pre-flight constitutional check (no network call)
from acgs_auth0.token_vault import TokenVaultRequest
req = TokenVaultRequest(
    agent_id="ci-agent",
    role="EXECUTIVE",
    connection="github",
    scopes=["read:user", "repo:read"],
    refresh_token="rt_xxx",
    user_id="user|abc123",
)
validation = vault.validate(req)
print(validation.allowed, validation.denied_scopes)

# Full exchange (validates then calls Auth0 Token Vault)
response = await vault.exchange(req)
access_token = response.credentials["access_token"]
```

### 4. Audit log

```python
from acgs_auth0 import TokenAuditLog, TokenAccessAuditEntry

audit = TokenAuditLog()
# entries are appended automatically by ConstitutionalTokenVault / the decorator
entries = audit.entries  # list[TokenAccessAuditEntry]
for e in entries:
    print(e.outcome, e.agent_id, e.connection, e.requested_scopes)
```

## Key Features

- **Constitutional scope policy** — `MACIScopePolicy` maps MACI roles to permitted OAuth scopes per connection; load from YAML or build programmatically with `ConnectionScopeRule`
- **`with_constitutional_token_vault`** — decorator factory that validates MACI role and scopes before any tool function body executes
- **`ConstitutionalTokenVault`** — full Auth0 Token Vault client with `validate()` (pre-flight) and `exchange()` (live token fetch); CIBA step-up for high-risk scopes
- **`get_token_vault_credentials()`** — retrieves credentials injected by the governed decorator (must be called from inside a governed tool)
- **Scope risk classification** — `ScopeRiskLevel` (LOW / MEDIUM / HIGH / CRITICAL) with built-in heuristics for GitHub, Google, Slack, and other well-known OAuth providers
- **Immutable audit trail** — `TokenAuditLog` / `TokenAccessAuditEntry` records every granted, denied, and step-up event with MACI role, scopes, outcome, and constitutional hash
- **Auth0 environment variables** — `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` used as fallbacks; no credentials hardcoded

## API Reference

| Symbol | Description |
|--------|-------------|
| `ConstitutionalTokenVault` | Main vault; `__init__(policy, audit_log, auth0_domain, auth0_client_id, auth0_client_secret)`; `.validate(request)`, `.exchange(request)`, `.for_connection(connection, scopes)` |
| `get_token_vault_credentials()` | Returns `{"access_token": ..., "token_type": ...}` inside a governed tool |
| `with_constitutional_token_vault` | Decorator factory: `with_constitutional_token_vault(policy, connection=..., scopes=[...])` |
| `MACIScopePolicy` | Scope policy; `.from_yaml(path)`, `.validate(agent_id, role, connection, requested_scopes)` |
| `ConnectionScopeRule` | Dataclass: `connection`, `role`, `permitted_scopes`, `high_risk_scopes` |
| `ScopeRiskLevel` | Enum: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `TokenAuditLog` | Append-only audit log for token access events |
| `TokenAccessAuditEntry` | Immutable record: `agent_id`, `role`, `connection`, `requested_scopes`, `granted_scopes`, `outcome`, `constitutional_hash`, `timestamp` |
| `ConstitutionalScopeViolation` | Raised when requested scopes exceed constitutional policy |
| `MACIRoleNotPermittedError` | Raised when the agent's MACI role cannot use a connection at all |
| `TokenVaultGovernanceError` | Base exception for all `acgs-auth0` errors |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AUTH0_DOMAIN` | Auth0 tenant domain (e.g. `your-tenant.auth0.com`) |
| `AUTH0_CLIENT_ID` | Auth0 machine-to-machine client ID |
| `AUTH0_CLIENT_SECRET` | Auth0 machine-to-machine client secret |

## Runtime dependencies

- `httpx>=0.28.0`
- `pyyaml>=6.0`

LangChain integration requires `auth0-ai-langchain>=1.0.1` and `langchain-core>=0.3.0` (`pip install acgs-auth0[langchain]`).

## License

AGPL-3.0-or-later.

## Links

- [Homepage](https://acgs.ai)
- [PyPI](https://pypi.org/project/acgs-auth0/)
- [Issues](https://github.com/dislovelhl/acgs-auth0/issues)
