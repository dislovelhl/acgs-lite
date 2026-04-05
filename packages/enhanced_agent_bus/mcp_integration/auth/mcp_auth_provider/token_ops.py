"""
MCP Authentication Provider - Token Operations Mixin.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Provides token lifecycle operations for MCPAuthProvider:
- Token acquisition (OAuth2/OIDC)
- Token refresh
- Token revocation
- Token retrieval for tools
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..auth_audit import AuthAuditEventType
from ..oauth2_provider import OAuth2GrantType, OAuth2Token
from ..token_refresh import RefreshResult, RefreshStatus
from .enums import TokenState
from .models import AuthResult, ManagedProviderToken

if TYPE_CHECKING:
    from .provider import MCPAuthProvider

logger = get_logger(__name__)
TOKEN_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class TokenOperationsMixin:
    """
    Mixin providing token operations for MCPAuthProvider.

    This mixin implements token lifecycle methods:
    - acquire_token: Get new OAuth2/OIDC tokens
    - refresh_token: Refresh existing tokens
    - revoke_token: Revoke tokens
    - get_token_for_tool: Get valid token for a specific tool
    - inject_auth_headers: Add auth headers to requests
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

    async def acquire_token(
        self: "MCPAuthProvider",
        provider_name: str | None = None,
        tool_name: str | None = None,
        scopes: list[str] | None = None,
        tenant_id: str | None = None,
        grant_type: OAuth2GrantType = OAuth2GrantType.CLIENT_CREDENTIALS,
        use_oidc: bool = True,
        **kwargs: object,
    ) -> AuthResult:
        """
        Acquire an OAuth2/OIDC token.

        Args:
            provider_name: Provider to use (uses default if not specified)
            tool_name: Tool name for credential binding
            scopes: Requested scopes
            tenant_id: Tenant ID for multi-tenant scenarios
            grant_type: OAuth2 grant type
            use_oidc: Prefer OIDC if available
            **kwargs: Additional arguments for token acquisition

        Returns:
            AuthResult with token information
        """
        start_time = datetime.now(UTC)
        provider_name = provider_name or self.config.default_provider

        if not provider_name:
            return AuthResult(
                success=False,
                error="No provider specified and no default configured",
            )

        # Generate token ID for tracking
        token_id = self._generate_token_id(provider_name, tool_name, tenant_id)

        # Check for existing valid token
        async with self._lock:
            if token_id in self._managed_tokens:
                managed = self._managed_tokens[token_id]
                managed.update_state(
                    self.config.refresh_config.refresh_threshold_seconds
                    if self.config.refresh_config
                    else 300
                )

                if managed.state == TokenState.VALID:
                    managed.last_used = datetime.now(UTC)
                    return AuthResult(
                        success=True,
                        token=managed.token,
                        oidc_tokens=managed.oidc_tokens,
                        provider_name=provider_name,
                        token_id=token_id,
                    )

        # Acquire new token
        result = await self._do_acquire_token(
            provider_name=provider_name,
            token_id=token_id,
            tool_name=tool_name,
            tenant_id=tenant_id,
            scopes=scopes,
            grant_type=grant_type,
            use_oidc=use_oidc,
            **kwargs,
        )

        # Calculate duration
        end_time = datetime.now(UTC)
        result.duration_ms = (end_time - start_time).total_seconds() * 1000

        # Update stats
        if result.success:
            self._stats["auth_successes"] += 1
            self._stats["tokens_acquired"] += 1
        else:
            self._stats["auth_failures"] += 1

        # Audit log
        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=(
                    AuthAuditEventType.TOKEN_ACQUIRED
                    if result.success
                    else AuthAuditEventType.AUTH_FAILURE
                ),
                message=f"Token acquisition: {result.success}",
                success=result.success,
                tool_name=tool_name,
                tenant_id=tenant_id,
                details={
                    "provider": provider_name,
                    "grant_type": grant_type.value,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                },
            )

        return result

    async def _do_acquire_token(
        self: "MCPAuthProvider",
        provider_name: str,
        token_id: str,
        tool_name: str | None,
        tenant_id: str | None,
        scopes: list[str] | None,
        grant_type: OAuth2GrantType,
        use_oidc: bool,
        **kwargs: object,
    ) -> AuthResult:
        """Internal token acquisition logic."""
        # Try OIDC first if preferred and available
        if use_oidc and provider_name in self._oidc_providers:
            oidc_provider = self._oidc_providers[provider_name]

            try:
                oidc_tokens = await oidc_provider.acquire_tokens(
                    grant_type=grant_type,
                    scopes=scopes,
                    cache_key=token_id,
                    **kwargs,
                )

                if oidc_tokens:
                    # Store managed token
                    managed = ManagedProviderToken(
                        token_id=token_id,
                        provider_name=provider_name,
                        tool_name=tool_name,
                        tenant_id=tenant_id,
                        token=oidc_tokens.oauth2_token,
                        oidc_tokens=oidc_tokens,
                    )

                    async with self._lock:
                        self._managed_tokens[token_id] = managed

                    # Register for refresh
                    if oidc_tokens.oauth2_token.refresh_token and oidc_provider._oauth2_provider:
                        await self._token_refresher.register_token(
                            token_id=token_id,
                            token=oidc_tokens.oauth2_token,
                            provider=oidc_provider._oauth2_provider,
                            cache_key=token_id,
                            on_refresh=self._on_token_refresh,
                            on_error=self._on_refresh_error,
                        )

                    return AuthResult(
                        success=True,
                        token=oidc_tokens.oauth2_token,
                        oidc_tokens=oidc_tokens,
                        provider_name=provider_name,
                        token_id=token_id,
                    )

            except TOKEN_OPERATION_ERRORS as e:
                logger.warning(f"OIDC token acquisition failed: {e}")
                # Fall through to OAuth2

        # Try OAuth2
        if provider_name in self._oauth2_providers:
            oauth2_provider = self._oauth2_providers[provider_name]

            try:
                token = await oauth2_provider.acquire_token(
                    grant_type=grant_type,
                    scopes=scopes,
                    cache_key=token_id,
                    **kwargs,
                )

                if token:
                    # Store managed token
                    managed = ManagedProviderToken(
                        token_id=token_id,
                        provider_name=provider_name,
                        tool_name=tool_name,
                        tenant_id=tenant_id,
                        token=token,
                    )

                    async with self._lock:
                        self._managed_tokens[token_id] = managed

                    # Register for refresh
                    if token.refresh_token:
                        await self._token_refresher.register_token(
                            token_id=token_id,
                            token=token,
                            provider=oauth2_provider,
                            cache_key=token_id,
                            on_refresh=self._on_token_refresh,
                            on_error=self._on_refresh_error,
                        )

                    return AuthResult(
                        success=True,
                        token=token,
                        provider_name=provider_name,
                        token_id=token_id,
                    )

            except TOKEN_OPERATION_ERRORS as e:
                return AuthResult(
                    success=False,
                    error=str(e),
                    provider_name=provider_name,
                    token_id=token_id,
                )

        return AuthResult(
            success=False,
            error=f"Provider not found: {provider_name}",
            provider_name=provider_name,
            token_id=token_id,
        )

    async def refresh_token(
        self: "MCPAuthProvider",
        token_id: str,
        force: bool = False,
    ) -> RefreshResult:
        """
        Refresh a managed token.

        Args:
            token_id: Token ID to refresh
            force: Force refresh even if not needed

        Returns:
            RefreshResult
        """
        result = await self._token_refresher.refresh_token(token_id, force=force)

        if result.status == RefreshStatus.SUCCESS:
            self._stats["tokens_refreshed"] += 1

            # Update managed token
            async with self._lock:
                if token_id in self._managed_tokens:
                    managed = self._managed_tokens[token_id]
                    managed.token = result.new_token
                    managed.refresh_count += 1
                    managed.state = TokenState.VALID

        return result

    async def revoke_token(
        self: "MCPAuthProvider",
        token_id: str,
    ) -> bool:
        """
        Revoke a managed token.

        Args:
            token_id: Token ID to revoke

        Returns:
            True if revoked successfully
        """
        async with self._lock:
            if token_id not in self._managed_tokens:
                return False

            managed = self._managed_tokens[token_id]

            # Try to revoke with provider
            if managed.provider_name in self._oauth2_providers:
                provider = self._oauth2_providers[managed.provider_name]
                await provider.revoke_token(managed.token.access_token)

            # Mark as revoked
            managed.state = TokenState.REVOKED

            # Unregister from refresher
            await self._token_refresher.unregister_token(token_id)

            # Remove from managed tokens
            del self._managed_tokens[token_id]

        self._stats["tokens_revoked"] += 1

        # Audit log
        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.TOKEN_REVOKED,
                message=f"Token revoked: {token_id}",
                tool_name=managed.tool_name,
                tenant_id=managed.tenant_id,
            )

        return True

    async def get_token_for_tool(
        self: "MCPAuthProvider",
        tool_name: str,
        tenant_id: str | None = None,
    ) -> OAuth2Token | None:
        """
        Get a valid token for a tool.

        Args:
            tool_name: Tool name
            tenant_id: Optional tenant ID

        Returns:
            Valid OAuth2Token or None
        """
        # Check for mapped provider
        provider_name = self._tool_providers.get(
            tool_name,
            self.config.default_provider,
        )

        if not provider_name:
            return None

        # Try to get existing token
        token_id = self._generate_token_id(provider_name, tool_name, tenant_id)

        async with self._lock:
            if token_id in self._managed_tokens:
                managed = self._managed_tokens[token_id]
                managed.update_state()

                if managed.state in (TokenState.VALID, TokenState.EXPIRING_SOON):
                    managed.last_used = datetime.now(UTC)
                    return managed.token

        # Acquire new token
        result = await self.acquire_token(
            provider_name=provider_name,
            tool_name=tool_name,
            tenant_id=tenant_id,
        )

        return result.token if result.success else None

    def configure_tool_provider(
        self: "MCPAuthProvider",
        tool_name: str,
        provider_name: str,
    ) -> None:
        """
        Configure which provider to use for a tool.

        Args:
            tool_name: Tool name
            provider_name: Provider name
        """
        self._tool_providers[tool_name] = provider_name
        logger.info(f"Configured tool '{tool_name}' to use provider '{provider_name}'")

    async def inject_auth_headers(
        self: "MCPAuthProvider",
        tool_name: str,
        headers: dict[str, str],
        tenant_id: str | None = None,
    ) -> dict[str, str]:
        """
        Inject authentication headers for a tool request.

        Args:
            tool_name: Tool name
            headers: Existing headers
            tenant_id: Optional tenant ID

        Returns:
            Headers with authentication added
        """
        token = await self.get_token_for_tool(tool_name, tenant_id)

        if token:
            headers["Authorization"] = f"{token.token_type} {token.access_token}"

        return headers

    # Callback handlers

    async def _on_token_refresh(
        self: "MCPAuthProvider",
        old_token: OAuth2Token,
        new_token: OAuth2Token,
    ) -> None:
        """Handle token refresh callback."""
        logger.debug("Token refreshed successfully")

        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.TOKEN_REFRESHED,
                message="Token refreshed via background task",
            )

    async def _on_refresh_error(
        self: "MCPAuthProvider",
        token_id: str,
        error: Exception,
    ) -> None:
        """Handle refresh error callback."""
        logger.error(f"Token refresh failed for {token_id}: {error}")

        async with self._lock:
            if token_id in self._managed_tokens:
                self._managed_tokens[token_id].error_count += 1

        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.AUTH_FAILURE,
                message=f"Token refresh failed: {error}",
                success=False,
                details={"token_id": token_id, "error": str(error)},
            )


__all__ = [
    "TokenOperationsMixin",
]
