"""ACGS-Auth0: Constitutional Token Governance for AI Agents.

Bridges Auth0 Token Vault with ACGS's MACI constitutional governance,
so the constitution—not the agent—decides which OAuth scopes are permitted.

Constitutional Hash: 608508a9bd224290

Quick start::

    from acgs_auth0 import ConstitutionalTokenVault, MACIScopePolicy, ScopeRiskLevel
    from acgs_auth0 import with_constitutional_token_vault, get_token_vault_credentials

    policy = MACIScopePolicy.from_yaml("constitution.yaml")
    vault = ConstitutionalTokenVault(policy=policy)

    # Wrap a LangChain tool — MACI role is validated before Token Vault is called
    with_github_read = vault.for_connection(
        connection="github",
        scopes=["read:user", "repo:read"],
        risk_level=ScopeRiskLevel.LOW,
    )

    @with_github_read
    def list_open_issues(repo: str) -> list[dict]:
        creds = get_token_vault_credentials()
        # call GitHub API with creds["access_token"]
        ...
"""

from acgs_auth0._meta import CONSTITUTIONAL_HASH, VERSION
from acgs_auth0.audit import TokenAccessAuditEntry, TokenAuditLog
from acgs_auth0.exceptions import (
    ConstitutionalScopeViolation,
    MACIRoleNotPermittedError,
    TokenVaultGovernanceError,
)
from acgs_auth0.governed_tool import with_constitutional_token_vault
from acgs_auth0.scope_policy import (
    ConnectionScopeRule,
    MACIScopePolicy,
    ScopeRiskLevel,
)
from acgs_auth0.token_vault import (
    ConstitutionalTokenVault,
    get_token_vault_credentials,
)

__all__ = [
    # Meta
    "CONSTITUTIONAL_HASH",
    "VERSION",
    # Core
    "ConstitutionalTokenVault",
    "get_token_vault_credentials",
    # Policy
    "MACIScopePolicy",
    "ConnectionScopeRule",
    "ScopeRiskLevel",
    # Tooling
    "with_constitutional_token_vault",
    # Audit
    "TokenAccessAuditEntry",
    "TokenAuditLog",
    # Errors
    "ConstitutionalScopeViolation",
    "MACIRoleNotPermittedError",
    "TokenVaultGovernanceError",
]
