"""ConstitutionalTokenVault — the core integration bridge.

Wraps Auth0 Token Vault with MACI constitutional governance, ensuring that:
  1. The requesting agent's MACI role is validated before Token Vault is called.
  2. High-risk scopes trigger CIBA step-up approval.
  3. Every access is recorded in the constitutional audit log.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from acgs_auth0._meta import CONSTITUTIONAL_HASH
from acgs_auth0.audit import TokenAuditLog
from acgs_auth0.exceptions import (
    ConstitutionalScopeViolation,
    MACIRoleNotPermittedError,
    StepUpAuthRequiredError,
)
from acgs_auth0.scope_policy import MACIScopePolicy, PolicyValidationResult

logger = logging.getLogger(__name__)

# Context variable: set by the governed tool decorator, read by get_token_vault_credentials()
_token_vault_credentials_ctx: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("_token_vault_credentials", default=None)
)


def get_token_vault_credentials() -> dict[str, Any]:
    """Retrieve the Token Vault credentials for the current tool execution.

    Must be called from inside a tool wrapped with ``with_constitutional_token_vault``
    or ``ConstitutionalTokenVault.for_connection()``.

    Returns:
        Dict containing at minimum ``access_token`` and ``token_type``.

    Raises:
        RuntimeError: If called outside a governed tool context.

    Usage::

        def my_tool(query: str) -> str:
            creds = get_token_vault_credentials()
            headers = {"Authorization": f"{creds['token_type']} {creds['access_token']}"}
            # call external API ...
    """
    creds = _token_vault_credentials_ctx.get()
    if creds is None:
        raise RuntimeError(
            "get_token_vault_credentials() called outside a governed tool context. "
            "Wrap your tool with with_constitutional_token_vault() first."
        )
    return creds


@dataclass
class TokenVaultRequest:
    """Parameters for a single token retrieval via Token Vault.

    Attributes:
        agent_id: Identifier of the requesting agent.
        role: MACI role of the agent (e.g. "EXECUTIVE").
        connection: Auth0 connection name (e.g. "github", "google-oauth2").
        scopes: OAuth scopes to request.
        refresh_token: The user's Auth0 refresh token used for the exchange.
        user_id: Auth0 user ID (for logging and CIBA user targeting).
        login_hint: Optional hint for multi-account disambiguation.
        tool_name: Name of the LangChain tool making the request.
    """

    agent_id: str
    role: str
    connection: str
    scopes: list[str]
    refresh_token: str
    user_id: str | None = None
    login_hint: str | None = None
    tool_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenVaultResponse:
    """Result of a governed token vault exchange.

    Attributes:
        access_token: The external provider's access token.
        token_type: Token type (typically "Bearer").
        expires_in: Seconds until the access token expires.
        scope: Space-separated granted scopes.
        issued_token_type: Auth0 token type URI.
        validation_result: The constitutional validation that allowed this grant.
    """

    access_token: str
    token_type: str
    expires_in: int
    scope: str
    issued_token_type: str
    validation_result: PolicyValidationResult | None = None

    def as_credentials(self) -> dict[str, Any]:
        """Return a dict compatible with auth0-ai's get_credentials_from_token_vault()."""
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "scope": self.scope,
            "issued_token_type": self.issued_token_type,
        }


class ConstitutionalTokenVault:
    """Auth0 Token Vault client with MACI constitutional governance.

    Validates each token request against the configured MACIScopePolicy before
    forwarding to Auth0.  All access attempts are recorded in the audit log.

    Usage::

        from acgs_auth0 import ConstitutionalTokenVault, MACIScopePolicy

        policy = MACIScopePolicy.from_yaml("constitution.yaml")
        vault = ConstitutionalTokenVault(policy=policy)

        # Wrap a LangChain tool
        with_github_read = vault.for_connection(
            connection="github",
            scopes=["read:user", "repo:read"],
        )

        @with_github_read
        def list_issues(repo: str) -> list[dict]:
            creds = get_token_vault_credentials()
            # use creds["access_token"] to call GitHub API
            ...
    """

    def __init__(
        self,
        *,
        policy: MACIScopePolicy,
        audit_log: TokenAuditLog | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        auth0_domain: str | None = None,
        auth0_client_id: str | None = None,
        auth0_client_secret: str | None = None,
    ) -> None:
        self.policy = policy
        self.audit_log = audit_log if audit_log is not None else TokenAuditLog()
        self.constitutional_hash = constitutional_hash

        # Auth0 credentials — fall back to environment variables
        import os

        self._domain = auth0_domain or os.environ.get("AUTH0_DOMAIN", "")
        self._client_id = auth0_client_id or os.environ.get("AUTH0_CLIENT_ID", "")
        self._client_secret = auth0_client_secret or os.environ.get(
            "AUTH0_CLIENT_SECRET", ""
        )

        # Lazy-initialised auth0-ai client
        self._auth0_ai: Any = None
        self._auth0_ai_initialised = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, request: TokenVaultRequest) -> PolicyValidationResult:
        """Run constitutional validation without making any network calls.

        Useful for pre-flight checks in test suites and monitoring.
        """
        return self.policy.validate(
            agent_id=request.agent_id,
            role=request.role,
            connection=request.connection,
            requested_scopes=request.scopes,
        )

    async def exchange(self, request: TokenVaultRequest) -> TokenVaultResponse:
        """Validate the request constitutionally then exchange via Token Vault.

        Flow:
          1. Validate MACI role permissions against the policy.
          2. If validation fails → log denial, raise exception.
          3. If any high-risk scopes present → raise StepUpAuthRequiredError
             (the governed tool decorator catches this and triggers CIBA).
          4. Call Auth0 Token Vault token exchange endpoint.
          5. Log success, return credentials.

        Args:
            request: The token request parameters.

        Returns:
            TokenVaultResponse with the access token from the external provider.

        Raises:
            ConstitutionalScopeViolation: If a scope is denied by the policy.
            MACIRoleNotPermittedError: If the role has no access to the connection.
            StepUpAuthRequiredError: If high-risk scopes require CIBA step-up.
        """
        # Step 1: Constitutional validation
        result = self.policy.validate(
            agent_id=request.agent_id,
            role=request.role,
            connection=request.connection,
            requested_scopes=request.scopes,
        )

        if not result.permitted:
            self._log_denial(request, result)
            assert result.error is not None
            raise result.error

        # Step 2: Check for high-risk scopes requiring step-up
        if result.step_up_required:
            binding_message = self._build_step_up_message(request)
            step_up_error = StepUpAuthRequiredError(
                connection=request.connection,
                high_risk_scopes=result.step_up_required,
                binding_message=binding_message,
            )
            self.audit_log.record_step_up_initiated(
                agent_id=request.agent_id,
                role=request.role,
                connection=request.connection,
                scopes=request.scopes,
                binding_message=binding_message,
                user_id=request.user_id,
                tool_name=request.tool_name,
            )
            raise step_up_error

        # Step 3: Call Token Vault
        response = await self._call_token_vault(request)
        response.validation_result = result

        # Step 4: Audit success
        self.audit_log.record_granted(
            agent_id=request.agent_id,
            role=request.role,
            connection=request.connection,
            scopes=request.scopes,
            user_id=request.user_id,
            tool_name=request.tool_name,
        )

        return response

    def for_connection(
        self,
        *,
        connection: str,
        scopes: list[str],
        get_agent_context: Callable[[], tuple[str, str]] | None = None,
        get_refresh_token: Callable[[], str] | None = None,
        get_user_id: Callable[[], str | None] | None = None,
        ciba_binding_message: str | Callable[..., str] | None = None,
    ) -> "ConnectionTokenVaultWrapper":
        """Create a reusable wrapper for a specific connection and scope set.

        Args:
            connection: External provider name (e.g. ``"github"``).
            scopes: OAuth scopes to request.
            get_agent_context: Callable returning ``(agent_id, role)`` tuple.
                Defaults to reading from LangChain runnable config.
            get_refresh_token: Callable returning the Auth0 refresh token.
                Defaults to reading from LangChain runnable config.
            get_user_id: Callable returning the Auth0 user ID.
            ciba_binding_message: Custom CIBA message for step-up auth.

        Returns:
            A ConnectionTokenVaultWrapper that can wrap LangChain tools.
        """
        return ConnectionTokenVaultWrapper(
            vault=self,
            connection=connection,
            scopes=scopes,
            get_agent_context=get_agent_context,
            get_refresh_token=get_refresh_token,
            get_user_id=get_user_id,
            ciba_binding_message=ciba_binding_message,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_token_vault(self, request: TokenVaultRequest) -> TokenVaultResponse:
        """Exchange the Auth0 refresh token for an external provider access token.

        Performs the Token Vault refresh token exchange as documented at:
        https://auth0.com/docs/secure/tokens/token-vault/refresh-token-exchange-with-token-vault
        """
        import httpx

        if not self._domain or not self._client_id:
            raise RuntimeError(
                "Auth0 domain and client_id must be configured. "
                "Set AUTH0_DOMAIN and AUTH0_CLIENT_ID env vars or pass them to "
                "ConstitutionalTokenVault()."
            )

        payload: dict[str, Any] = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "subject_token": request.refresh_token,
            "grant_type": (
                "urn:auth0:params:oauth:grant-type:"
                "token-exchange:federated-connection-access-token"
            ),
            "subject_token_type": "urn:ietf:params:oauth:token-type:refresh_token",
            "requested_token_type": (
                "http://auth0.com/oauth/token-type/federated-connection-access-token"
            ),
            "connection": request.connection,
        }
        if request.login_hint:
            payload["login_hint"] = request.login_hint

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://{self._domain}/oauth/token",
                json=payload,
                timeout=15.0,
            )

        if resp.status_code != 200:
            error_body = resp.text
            logger.error(
                "Token Vault exchange failed for connection=%s status=%s body=%s",
                request.connection,
                resp.status_code,
                error_body,
            )
            raise RuntimeError(
                f"Token Vault exchange returned HTTP {resp.status_code}: {error_body}"
            )

        data = resp.json()
        return TokenVaultResponse(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in", 3600),
            scope=data.get("scope", " ".join(request.scopes)),
            issued_token_type=data.get(
                "issued_token_type",
                "http://auth0.com/oauth/token-type/federated-connection-access-token",
            ),
        )

    def _build_step_up_message(self, request: TokenVaultRequest) -> str:
        high_risk = self.policy.get_rule(
            connection=request.connection, role=request.role
        )
        step_up = high_risk.step_up_scopes(request.scopes) if high_risk else request.scopes
        return (
            f"Agent '{request.agent_id}' (role={request.role}) requests "
            f"{request.connection} access with elevated scopes: {step_up}. "
            "Please approve or deny."
        )

    def _log_denial(
        self, request: TokenVaultRequest, result: PolicyValidationResult
    ) -> None:
        if isinstance(result.error, MACIRoleNotPermittedError):
            reason = "role_not_permitted"
        else:
            reason = "scope_violation"
        self.audit_log.record_denied(
            agent_id=request.agent_id,
            role=request.role,
            connection=request.connection,
            scopes=request.scopes,
            reason=reason,
            error_message=str(result.error),
            user_id=request.user_id,
            tool_name=request.tool_name,
        )


class ConnectionTokenVaultWrapper:
    """Reusable wrapper returned by ConstitutionalTokenVault.for_connection().

    Can be used as a decorator on plain functions or LangChain StructuredTools.
    """

    def __init__(
        self,
        vault: ConstitutionalTokenVault,
        connection: str,
        scopes: list[str],
        get_agent_context: Callable[[], tuple[str, str]] | None = None,
        get_refresh_token: Callable[[], str] | None = None,
        get_user_id: Callable[[], str | None] | None = None,
        ciba_binding_message: str | Callable[..., str] | None = None,
    ) -> None:
        self.vault = vault
        self.connection = connection
        self.scopes = scopes
        self._get_agent_context = get_agent_context or _default_agent_context
        self._get_refresh_token = get_refresh_token or _default_refresh_token
        self._get_user_id = get_user_id or _default_user_id
        self._ciba_binding_message = ciba_binding_message

    def __call__(self, tool_fn: Callable) -> Callable:
        """Decorate a tool function with constitutional token governance."""
        from functools import wraps

        wrapper_self = self

        @wraps(tool_fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await wrapper_self._execute(tool_fn, args, kwargs)

        @wraps(tool_fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            import asyncio

            return asyncio.get_event_loop().run_until_complete(
                wrapper_self._execute(tool_fn, args, kwargs)
            )

        import inspect

        if inspect.iscoroutinefunction(tool_fn):
            return async_wrapper
        return sync_wrapper

    async def _execute(
        self, tool_fn: Callable, args: tuple, kwargs: dict
    ) -> Any:
        """Run the full governed token retrieval + tool execution pipeline."""
        agent_id, role = self._get_agent_context()
        refresh_token = self._get_refresh_token()
        user_id = self._get_user_id()

        request = TokenVaultRequest(
            agent_id=agent_id,
            role=role,
            connection=self.connection,
            scopes=self.scopes,
            refresh_token=refresh_token,
            user_id=user_id,
            tool_name=getattr(tool_fn, "__name__", None),
        )

        response = await self.vault.exchange(request)
        token = _token_vault_credentials_ctx.set(response.as_credentials())
        try:
            import inspect

            if inspect.iscoroutinefunction(tool_fn):
                return await tool_fn(*args, **kwargs)
            return tool_fn(*args, **kwargs)
        finally:
            _token_vault_credentials_ctx.reset(token)


# ------------------------------------------------------------------
# Default context resolvers (read from LangChain runnable config)
# ------------------------------------------------------------------

def _default_agent_context() -> tuple[str, str]:
    """Read agent_id and role from LangChain runnable config."""
    try:
        from langchain_core.runnables import ensure_config

        cfg = ensure_config().get("configurable", {})
        return (
            cfg.get("agent_id", "unknown"),
            cfg.get("maci_role", "UNKNOWN"),
        )
    except Exception:
        return ("unknown", "UNKNOWN")


def _default_refresh_token() -> str:
    """Read refresh_token from LangChain runnable config."""
    try:
        from langchain_core.runnables import ensure_config

        cfg = ensure_config().get("configurable", {})
        creds = cfg.get("_credentials", {})
        return creds.get("refresh_token", "")
    except Exception:
        return ""


def _default_user_id() -> str | None:
    """Read user_id from LangChain runnable config."""
    try:
        from langchain_core.runnables import ensure_config

        return ensure_config().get("configurable", {}).get("user_id")
    except Exception:
        return None
