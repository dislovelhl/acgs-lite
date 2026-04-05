"""GitHub tools with constitutional Token Vault governance.

These LangChain tools demonstrate ACGS-Auth0 integration:
- list_open_issues: EXECUTIVE role, read-only, no step-up required
- create_pull_request: IMPLEMENTER role, write access, CIBA step-up required

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import httpx
from langchain_core.runnables import ensure_config
from langchain_core.tools import StructuredTool

from acgs_auth0 import (
    MACIScopePolicy,
    get_token_vault_credentials,
    with_constitutional_token_vault,
)
from acgs_auth0.audit import TokenAuditLog


def build_github_tools(
    policy: MACIScopePolicy,
    audit_log: TokenAuditLog,
) -> list[StructuredTool]:
    """Build GitHub tools governed by the constitutional policy.

    Args:
        policy: The constitutional scope policy.
        audit_log: Shared audit log for recording access events.

    Returns:
        List of LangChain tools ready to be used in a graph.
    """

    # -----------------------------------------------------------------------
    # Helper: extract agent context from LangChain runnable config
    # -----------------------------------------------------------------------

    def get_agent_context() -> tuple[str, str]:
        cfg = ensure_config().get("configurable", {})
        return cfg.get("agent_id", "unknown"), cfg.get("maci_role", "UNKNOWN")

    def get_refresh_token() -> str:
        cfg = ensure_config().get("configurable", {})
        return cfg.get("_credentials", {}).get("refresh_token", "")

    def get_user_id() -> str | None:
        return ensure_config().get("configurable", {}).get("user_id")

    # -----------------------------------------------------------------------
    # Tool 1: list_open_issues — EXECUTIVE read (no step-up)
    # -----------------------------------------------------------------------

    with_github_read = with_constitutional_token_vault(
        policy,
        connection="github",
        scopes=["read:user", "repo:read"],
        audit_log=audit_log,
        get_agent_context=get_agent_context,
        get_refresh_token=get_refresh_token,
        get_user_id=get_user_id,
    )

    @with_github_read
    async def _list_open_issues(owner: str, repo: str) -> str:
        """List open GitHub issues for a repository."""
        creds = get_token_vault_credentials()
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues",
                params={"state": "open", "per_page": 10},
                headers=headers,
                timeout=10.0,
            )
        if resp.status_code != 200:
            return f"GitHub API error {resp.status_code}: {resp.text}"
        issues = resp.json()
        if not issues:
            return f"No open issues in {owner}/{repo}"
        lines = [f"Open issues in {owner}/{repo}:"]
        for issue in issues[:10]:
            lines.append(f"  #{issue['number']}: {issue['title']}")
        return "\n".join(lines)

    list_issues_tool = StructuredTool(
        name="list_open_issues",
        description=(
            "List open GitHub issues for a repository. "
            "Requires EXECUTIVE role. Uses Token Vault for GitHub read access."
        ),
        coroutine=_list_open_issues,
        func=_list_open_issues,
    )

    # -----------------------------------------------------------------------
    # Tool 2: create_pull_request — IMPLEMENTER write (CIBA step-up)
    # -----------------------------------------------------------------------

    with_github_write = with_constitutional_token_vault(
        policy,
        connection="github",
        scopes=["read:user", "repo:read", "repo:write", "pull_request:write"],
        audit_log=audit_log,
        get_agent_context=get_agent_context,
        get_refresh_token=get_refresh_token,
        get_user_id=get_user_id,
        ciba_binding_message=(
            lambda owner, repo, title, **_: (  # type: ignore[misc]
                f"AI agent requests permission to create a PR in {owner}/{repo}: '{title}'"
            )
        ),
    )

    @with_github_write
    async def _create_pull_request(
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
    ) -> str:
        """Create a GitHub pull request. Requires CIBA step-up approval."""
        creds = get_token_vault_credentials()
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                json={"title": title, "head": head, "base": base, "body": body},
                headers=headers,
                timeout=10.0,
            )
        if resp.status_code not in (200, 201):
            return f"GitHub API error {resp.status_code}: {resp.text}"
        pr = resp.json()
        return f"Created PR #{pr['number']}: {pr['html_url']}"

    create_pr_tool = StructuredTool(
        name="create_pull_request",
        description=(
            "Create a GitHub pull request. "
            "Requires IMPLEMENTER role AND CIBA step-up user approval. "
            "Uses Token Vault for GitHub write access."
        ),
        coroutine=_create_pull_request,
        func=_create_pull_request,
    )

    return [list_issues_tool, create_pr_tool]
