# acgs-auth0

[![PyPI](https://img.shields.io/pypi/v/acgs-auth0)](https://pypi.org/project/acgs-auth0/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-auth0)](https://pypi.org/project/acgs-auth0/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Constitutional token governance for AI agents.**

`acgs-auth0` bridges Auth0 Token Vault with ACGS MACI governance so the
constitution, not the agent, decides which OAuth scopes can be requested. It supports
offline pre-flight checks, step-up approval for elevated scopes, and audit logging
around every exchange.

## Installation

`acgs-auth0` supports Python 3.11+.

```bash
pip install acgs-auth0
pip install acgs-auth0[langchain]
```

## Quick Start

### Define a Scope Policy

```yaml
# constitution.yaml
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
```

### Validate and Exchange Tokens

```python
from acgs_auth0 import ConstitutionalTokenVault, MACIScopePolicy
from acgs_auth0.token_vault import TokenVaultRequest

policy = MACIScopePolicy.from_yaml("constitution.yaml")
vault = ConstitutionalTokenVault(policy=policy)

request = TokenVaultRequest(
    agent_id="planner",
    role="EXECUTIVE",
    connection="github",
    scopes=["repo:read"],
    refresh_token="rt_example",
    tool_name="list_issues",
)

validation = vault.validate(request)
assert validation.permitted is True

response = await vault.exchange(request)
print(response.access_token, response.scope)
```

### Step-Up for High-Risk Scopes

```python
request = TokenVaultRequest(
    agent_id="builder",
    role="IMPLEMENTER",
    connection="github",
    scopes=["repo:write"],
    refresh_token="rt_example",
)

validation = vault.validate(request)
print(validation.step_up_required)
```

### Tool Decorator

```python
from acgs_auth0 import get_token_vault_credentials, with_constitutional_token_vault

with_github = with_constitutional_token_vault(
    policy,
    connection="github",
    scopes=["read:user", "repo:read"],
)

@with_github
async def list_issues(repo: str) -> str:
    creds = get_token_vault_credentials()
    return f"using {creds['token_type']} for {repo}"
```

## Configuration

Set these environment variables for live Token Vault exchanges:

| Variable | Purpose |
| --- | --- |
| `AUTH0_DOMAIN` | Auth0 tenant domain |
| `AUTH0_CLIENT_ID` | Auth0 client ID |
| `AUTH0_CLIENT_SECRET` | Auth0 client secret |

## Key Features

- YAML-driven MACI role-to-scope governance.
- Offline validation through `MACIScopePolicy` and `ConstitutionalTokenVault.validate()`.
- Auth0 Token Vault exchange flow with optional step-up handling for elevated scopes.
- Audit primitives including `TokenAuditLog` and `TokenAccessAuditEntry`.
- Decorator-based integration for LangChain or plain Python callables.

## License

AGPL-3.0-or-later. Commercial licensing is available; contact `hello@acgs.ai`.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://github.com/dislovelhl/acgs/tree/main/packages/acgs_auth0)
- [PyPI](https://pypi.org/project/acgs-auth0/)
- [Repository](https://github.com/dislovelhl/acgs)
- [Issues](https://github.com/dislovelhl/acgs/issues)
- [Changelog](https://github.com/dislovelhl/acgs/releases)

Constitutional Hash: `608508a9bd224290`
