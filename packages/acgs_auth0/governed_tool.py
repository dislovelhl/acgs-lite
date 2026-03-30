"""High-level decorator for wrapping LangChain tools with constitutional token governance.

This module provides ``with_constitutional_token_vault``, the primary developer-facing
API.  It integrates with ``auth0-ai-langchain``'s ``Auth0AI.with_token_vault`` but adds
MACI role validation and constitutional audit logging around every call.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_auth0 import with_constitutional_token_vault, MACIScopePolicy, get_token_vault_credentials
    from langchain_core.tools import StructuredTool

    policy = MACIScopePolicy.from_yaml("constitution.yaml")

    with_github_read = with_constitutional_token_vault(
        policy=policy,
        connection="github",
        scopes=["read:user", "repo:read"],
    )

    def list_issues(repo: str) -> str:
        creds = get_token_vault_credentials()
        # use creds["access_token"] ...
        return f"Issues for {repo}"

    governed_list_issues = with_github_read(list_issues)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from acgs_auth0.audit import TokenAuditLog
from acgs_auth0.scope_policy import MACIScopePolicy

logger = logging.getLogger(__name__)


def with_constitutional_token_vault(
    policy: MACIScopePolicy,
    *,
    connection: str,
    scopes: list[str],
    audit_log: TokenAuditLog | None = None,
    get_agent_context: Callable[[], tuple[str, str]] | None = None,
    get_refresh_token: Callable[[], str] | None = None,
    get_user_id: Callable[[], str | None] | None = None,
    auth0_domain: str | None = None,
    auth0_client_id: str | None = None,
    auth0_client_secret: str | None = None,
    ciba_binding_message: str | Callable[..., str] | None = None,
) -> Callable[[Callable], Callable]:
    """Create a decorator that wraps a tool with constitutional token governance.

    The decorated tool will only execute if:
      1. The requesting agent's MACI role is permitted to use ``connection``
         under ``policy``.
      2. All requested ``scopes`` are constitutionally allowed for that role.
      3. Any high-risk scopes have received CIBA step-up approval.

    If using ``auth0-ai-langchain``, prefer combining this with
    ``Auth0AI.with_token_vault()`` — see ``ConstitutionalAuth0AI`` below.

    Args:
        policy: Constitutional scope policy.
        connection: Auth0 external provider connection name.
        scopes: OAuth scopes to request from Token Vault.
        audit_log: Optional shared audit log; a new one is created if omitted.
        get_agent_context: Callable returning ``(agent_id, maci_role)`` for the
            current invocation.  Defaults to reading from LangChain config.
        get_refresh_token: Callable returning the user's Auth0 refresh token.
        get_user_id: Callable returning the Auth0 user ID.
        auth0_domain: Auth0 tenant domain.  Falls back to ``AUTH0_DOMAIN`` env var.
        auth0_client_id: Auth0 client ID.  Falls back to ``AUTH0_CLIENT_ID`` env var.
        auth0_client_secret: Auth0 client secret.  Falls back to env var.
        ciba_binding_message: Custom CIBA approval message for high-risk scopes.

    Returns:
        A decorator function.

    Example::

        with_github = with_constitutional_token_vault(policy, connection="github",
                                                      scopes=["repo:read"])
        @with_github
        def list_open_prs(repo: str) -> str:
            creds = get_token_vault_credentials()
            ...
    """
    from acgs_auth0.token_vault import ConstitutionalTokenVault

    vault = ConstitutionalTokenVault(
        policy=policy,
        audit_log=audit_log,
        auth0_domain=auth0_domain,
        auth0_client_id=auth0_client_id,
        auth0_client_secret=auth0_client_secret,
    )
    wrapper = vault.for_connection(
        connection=connection,
        scopes=scopes,
        get_agent_context=get_agent_context,
        get_refresh_token=get_refresh_token,
        get_user_id=get_user_id,
        ciba_binding_message=ciba_binding_message,
    )
    return wrapper


class ConstitutionalAuth0AI:
    """Drop-in constitutional wrapper around ``auth0-ai-langchain``'s ``Auth0AI``.

    Combines Auth0AI's token exchange mechanics with ACGS constitutional
    MACI role validation.  The API mirrors Auth0AI so existing code can
    adopt it with minimal changes.

    Usage::

        from acgs_auth0.governed_tool import ConstitutionalAuth0AI
        from acgs_auth0 import MACIScopePolicy

        policy = MACIScopePolicy.from_yaml("constitution.yaml")
        auth0_ai = ConstitutionalAuth0AI(policy=policy)

        with_github_read = auth0_ai.with_token_vault(
            connection="github",
            scopes=["read:user", "repo:read"],
        )

        @with_github_read
        def list_issues(repo: str) -> str:
            from acgs_auth0 import get_token_vault_credentials
            creds = get_token_vault_credentials()
            ...
    """

    def __init__(
        self,
        *,
        policy: MACIScopePolicy,
        audit_log: TokenAuditLog | None = None,
        auth0_domain: str | None = None,
        auth0_client_id: str | None = None,
        auth0_client_secret: str | None = None,
    ) -> None:
        self.policy = policy
        self.audit_log = audit_log or TokenAuditLog()

        # Lazy-init the upstream Auth0AI instance
        self._auth0_ai: Any = None
        self._auth0_domain = auth0_domain
        self._auth0_client_id = auth0_client_id
        self._auth0_client_secret = auth0_client_secret
        from acgs_auth0.token_vault import ConstitutionalTokenVault

        self._vault = ConstitutionalTokenVault(
            policy=policy,
            audit_log=self.audit_log,
            auth0_domain=auth0_domain,
            auth0_client_id=auth0_client_id,
            auth0_client_secret=auth0_client_secret,
        )

    def _get_auth0_ai(self) -> Any:
        if self._auth0_ai is None:
            try:
                from auth0_ai_langchain.auth0_ai import Auth0AI  # type: ignore[import-untyped]

                kwargs: dict[str, Any] = {}
                if self._auth0_domain:
                    kwargs["domain"] = self._auth0_domain
                if self._auth0_client_id:
                    kwargs["client_id"] = self._auth0_client_id
                if self._auth0_client_secret:
                    kwargs["client_secret"] = self._auth0_client_secret
                self._auth0_ai = Auth0AI(**kwargs)
            except ImportError:
                logger.warning(
                    "auth0-ai-langchain not installed.  "
                    "Install with: pip install auth0-ai-langchain"
                )
                self._auth0_ai = None
        return self._auth0_ai

    def with_token_vault(
        self,
        *,
        connection: str,
        scopes: list[str],
        get_agent_context: Callable[[], tuple[str, str]] | None = None,
        get_refresh_token: Callable[[], str] | None = None,
        get_user_id: Callable[[], str | None] | None = None,
        ciba_binding_message: str | Callable[..., str] | None = None,
        **auth0_ai_kwargs: Any,
    ) -> Callable[[Callable], Callable]:
        """Wrap a tool with constitutional validation + Auth0 Token Vault exchange.

        MACI validation runs first (synchronously).  If permitted, the upstream
        auth0-ai-langchain ``with_token_vault`` handles the actual OAuth exchange.

        Args:
            connection: External provider connection name.
            scopes: OAuth scopes to request.
            get_agent_context: Returns ``(agent_id, maci_role)`` for the caller.
            get_refresh_token: Returns the Auth0 refresh token.
            get_user_id: Returns the Auth0 user ID.
            ciba_binding_message: CIBA approval message for step-up.
            **auth0_ai_kwargs: Extra kwargs forwarded to Auth0AI.with_token_vault().

        Returns:
            A decorator function.
        """
        auth0_ai = self._get_auth0_ai()

        def decorator(tool_fn: Callable) -> Callable:
            from functools import wraps

            # First, apply constitutional gate
            constitutionally_wrapped = self._vault.for_connection(
                connection=connection,
                scopes=scopes,
                get_agent_context=get_agent_context,
                get_refresh_token=get_refresh_token,
                get_user_id=get_user_id,
                ciba_binding_message=ciba_binding_message,
            )(tool_fn)

            # Then, if auth0-ai-langchain is available, also apply its wrapper
            # to handle the actual token exchange plumbing (interrupt / resume flow)
            if auth0_ai is not None:
                try:
                    upstream_wrapped = auth0_ai.with_token_vault(
                        connection=connection,
                        scopes=scopes,
                        **auth0_ai_kwargs,
                    )(tool_fn)

                    @wraps(tool_fn)
                    async def double_wrapped(*args: Any, **kwargs: Any) -> Any:
                        # Constitutional gate first
                        from acgs_auth0.token_vault import _token_vault_credentials_ctx

                        agent_id, role = (get_agent_context or _default_agent_context_fn)()
                        result = self.policy.validate(
                            agent_id=agent_id,
                            role=role,
                            connection=connection,
                            requested_scopes=scopes,
                        )
                        if not result.permitted:
                            self.audit_log.record_denied(
                                agent_id=agent_id,
                                role=role,
                                connection=connection,
                                scopes=scopes,
                                reason="scope_violation"
                                if result.denied_scopes
                                else "role_not_permitted",
                                error_message=str(result.error),
                                tool_name=getattr(tool_fn, "__name__", None),
                            )
                            assert result.error is not None
                            raise result.error

                        # Delegate to auth0-ai-langchain for actual token exchange
                        import inspect

                        if inspect.iscoroutinefunction(upstream_wrapped):
                            return await upstream_wrapped(*args, **kwargs)
                        return upstream_wrapped(*args, **kwargs)

                    return double_wrapped
                except Exception as exc:
                    logger.warning(
                        "Failed to apply auth0-ai-langchain wrapper: %s. "
                        "Falling back to ACGS-only governance.",
                        exc,
                    )

            return constitutionally_wrapped

        return decorator

    def with_async_authorization(
        self,
        *,
        scopes: list[str],
        audience: str,
        binding_message: str | Callable[..., str],
        user_id: Callable[[], str],
        get_agent_context: Callable[[], tuple[str, str]] | None = None,
        **auth0_ai_kwargs: Any,
    ) -> Callable[[Callable], Callable]:
        """Wrap a tool with CIBA step-up + constitutional audit logging.

        Passes through to auth0-ai-langchain's ``with_async_authorization``
        with added constitutional audit events.
        """
        auth0_ai = self._get_auth0_ai()
        if auth0_ai is None:
            raise ImportError(
                "auth0-ai-langchain is required for async authorization. "
                "Install with: pip install auth0-ai-langchain"
            )

        def decorator(tool_fn: Callable) -> Callable:
            from functools import wraps

            upstream_wrapped = auth0_ai.with_async_authorization(
                scopes=scopes,
                audience=audience,
                binding_message=binding_message,
                user_id=user_id,
                **auth0_ai_kwargs,
            )(tool_fn)

            @wraps(tool_fn)
            async def audited_wrapper(*args: Any, **kwargs: Any) -> Any:
                agent_id, role = (get_agent_context or _default_agent_context_fn)()
                uid = user_id()
                bm = binding_message(*args, **kwargs) if callable(binding_message) else binding_message
                try:
                    import inspect

                    if inspect.iscoroutinefunction(upstream_wrapped):
                        result = await upstream_wrapped(*args, **kwargs)
                    else:
                        result = upstream_wrapped(*args, **kwargs)
                    self.audit_log.record_step_up(
                        agent_id=agent_id,
                        role=role,
                        connection="ciba",
                        scopes=scopes,
                        binding_message=bm,
                        approved=True,
                        user_id=uid,
                        tool_name=getattr(tool_fn, "__name__", None),
                    )
                    return result
                except Exception:
                    self.audit_log.record_step_up(
                        agent_id=agent_id,
                        role=role,
                        connection="ciba",
                        scopes=scopes,
                        binding_message=bm,
                        approved=False,
                        user_id=uid,
                        tool_name=getattr(tool_fn, "__name__", None),
                    )
                    raise

            return audited_wrapper

        return decorator


def _default_agent_context_fn() -> tuple[str, str]:
    try:
        from langchain_core.runnables import ensure_config

        cfg = ensure_config().get("configurable", {})
        return (cfg.get("agent_id", "unknown"), cfg.get("maci_role", "UNKNOWN"))
    except Exception:
        return ("unknown", "UNKNOWN")
