"""
MCP Authentication Provider.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Main authentication provider for MCP integration.
Provides unified OAuth2/OIDC authentication with support for
multiple providers (Azure AD, Okta, generic OAuth2, etc.).

Features:
- Multi-provider support with automatic discovery
- Token lifecycle management with automatic refresh
- Per-tool credential binding
- Comprehensive audit logging
- Constitutional governance compliance
"""

import asyncio
import hashlib
from datetime import UTC, datetime

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..auth_audit import (
    AuditLoggerConfig,
    AuthAuditEventType,
    AuthAuditLogger,
)
from ..credential_manager import (
    CredentialManager,
    CredentialManagerConfig,
)
from ..oauth2_provider import OAuth2Provider
from ..oidc_provider import OIDCConfig, OIDCProvider, OIDCProviderMetadata
from ..token_refresh import RefreshConfig, TokenRefresher
from .enums import ProviderType, TokenState
from .models import (
    ManagedProviderToken,
    MCPAuthProviderConfig,
    ProviderConfig,
)
from .token_ops import TokenOperationsMixin

logger = get_logger(__name__)
OIDC_PROVIDER_REGISTRATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class MCPAuthProvider(TokenOperationsMixin):
    """
    Main authentication provider for MCP integration.

    Provides unified OAuth2/OIDC authentication with support for
    multiple providers (Azure AD, Okta, generic OAuth2, etc.).

    Features:
    - Multi-provider support with automatic discovery
    - Token lifecycle management with automatic refresh
    - Per-tool credential binding
    - Comprehensive audit logging
    - Constitutional governance compliance

    Constitutional Hash: 608508a9bd224290
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

    def __init__(self, config: MCPAuthProviderConfig | None = None):
        """
        Initialize the MCP Auth Provider.

        Args:
            config: Provider configuration
        """
        self.config = config or MCPAuthProviderConfig()

        # Initialize OAuth2 providers
        self._oauth2_providers: dict[str, OAuth2Provider] = {}

        # Initialize OIDC providers
        self._oidc_providers: dict[str, OIDCProvider] = {}

        # Managed tokens
        self._managed_tokens: dict[str, ManagedProviderToken] = {}

        # Tool-to-provider mappings
        self._tool_providers: dict[str, str] = {}

        # Initialize credential manager
        self._credential_manager = CredentialManager(
            self.config.credential_config or CredentialManagerConfig()
        )

        # Initialize token refresher
        self._token_refresher = TokenRefresher(self.config.refresh_config or RefreshConfig())

        # Initialize audit logger
        self._audit_logger: AuthAuditLogger | None = None
        if self.config.enable_audit:
            self._audit_logger = AuthAuditLogger(self.config.audit_config or AuditLoggerConfig())

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Discovery cache
        self._discovery_cache: dict[str, OIDCProviderMetadata] = {}

        # Statistics
        self._stats = {
            "tokens_acquired": 0,
            "tokens_refreshed": 0,
            "tokens_revoked": 0,
            "auth_successes": 0,
            "auth_failures": 0,
            "discovery_calls": 0,
        }

    async def initialize(self) -> None:
        """
        Initialize the auth provider.

        Performs OIDC discovery for configured providers and
        starts the token refresh background task.
        """
        # Initialize providers from config
        for name, provider_config in self.config.providers.items():
            await self.add_provider(name, provider_config)

        # Start token refresher
        if self.config.auto_refresh_enabled:
            await self._token_refresher.start()

        # Load persisted credentials
        await self._credential_manager.load_credentials()

        logger.info(
            f"MCPAuthProvider initialized with {len(self._oauth2_providers)} OAuth2 "
            f"and {len(self._oidc_providers)} OIDC providers"
        )

        # Audit log
        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.SYSTEM_START,
                message="MCP Auth Provider initialized",
                details={
                    "oauth2_providers": list(self._oauth2_providers.keys()),
                    "oidc_providers": list(self._oidc_providers.keys()),
                },
            )

    async def shutdown(self) -> None:
        """Shutdown the auth provider."""
        # Stop token refresher
        await self._token_refresher.stop()

        # Audit log
        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.SYSTEM_STOP,
                message="MCP Auth Provider shutdown",
                details={
                    "stats": self._stats,
                    "managed_tokens": len(self._managed_tokens),
                },
            )

        logger.info("MCPAuthProvider shutdown complete")

    async def add_provider(
        self,
        name: str,
        config: ProviderConfig,
    ) -> bool:
        """
        Add an OAuth2/OIDC provider.

        Args:
            name: Provider name
            config: Provider configuration

        Returns:
            True if provider was added successfully
        """
        async with self._lock:
            # Determine if OIDC or pure OAuth2
            is_oidc = config.discovery_enabled and config.issuer_url

            if is_oidc or config.provider_type in (
                ProviderType.AZURE_AD,
                ProviderType.OKTA,
                ProviderType.KEYCLOAK,
                ProviderType.AUTH0,
                ProviderType.GOOGLE,
            ):
                # OIDC provider with discovery
                oidc_config = config.to_oidc_config()
                oidc_provider = OIDCProvider(oidc_config)

                # Perform discovery
                try:
                    metadata = await oidc_provider.discover()
                    if metadata:
                        self._discovery_cache[name] = metadata
                        self._oidc_providers[name] = oidc_provider
                        self._stats["discovery_calls"] += 1
                        logger.info(f"Added OIDC provider '{name}' ({config.provider_type.value})")
                    else:
                        logger.warning(
                            f"OIDC discovery failed for '{name}', falling back to OAuth2"
                        )
                        # Fall back to OAuth2
                        oauth2_config = config.to_oauth2_config()
                        self._oauth2_providers[name] = OAuth2Provider(oauth2_config)
                except OIDC_PROVIDER_REGISTRATION_ERRORS as e:
                    logger.error(f"Error adding OIDC provider '{name}': {e}")
                    return False
            else:
                # Pure OAuth2 provider
                oauth2_config = config.to_oauth2_config()
                self._oauth2_providers[name] = OAuth2Provider(oauth2_config)
                logger.info(f"Added OAuth2 provider '{name}' ({config.provider_type.value})")

            return True

    async def remove_provider(self, name: str) -> bool:
        """
        Remove a provider.

        Args:
            name: Provider name

        Returns:
            True if provider was removed
        """
        async with self._lock:
            removed = False

            if name in self._oauth2_providers:
                del self._oauth2_providers[name]
                removed = True

            if name in self._oidc_providers:
                del self._oidc_providers[name]
                removed = True

            if name in self._discovery_cache:
                del self._discovery_cache[name]

            # Revoke associated tokens
            tokens_to_remove = [
                tid for tid, t in self._managed_tokens.items() if t.provider_name == name
            ]
            for token_id in tokens_to_remove:
                del self._managed_tokens[token_id]
                await self._token_refresher.unregister_token(token_id)

            if removed:
                logger.info(f"Removed provider '{name}'")

            return removed

    async def discover_provider(
        self,
        issuer_url: str,
        name: str | None = None,
        force_refresh: bool = False,
    ) -> OIDCProviderMetadata | None:
        """
        Discover OIDC provider metadata from issuer URL.

        Args:
            issuer_url: OIDC issuer URL
            name: Optional provider name (uses issuer URL hash if not provided)
            force_refresh: Force refresh of cached metadata

        Returns:
            OIDCProviderMetadata or None
        """
        provider_name = name or hashlib.sha256(issuer_url.encode()).hexdigest()[:16]

        # Check cache
        if not force_refresh and provider_name in self._discovery_cache:
            metadata = self._discovery_cache[provider_name]
            cache_age = datetime.now(UTC) - metadata.discovered_at
            if cache_age.total_seconds() < 3600:  # 1 hour cache
                return metadata

        # Create temporary OIDC provider for discovery
        temp_config = OIDCConfig(
            issuer_url=issuer_url,
            cache_discovery=True,
        )
        temp_provider = OIDCProvider(temp_config)

        metadata = await temp_provider.discover(force_refresh=force_refresh)
        if metadata:
            self._discovery_cache[provider_name] = metadata
            self._stats["discovery_calls"] += 1

        return metadata

    # Helper methods

    def _generate_token_id(
        self,
        provider_name: str,
        tool_name: str | None,
        tenant_id: str | None,
    ) -> str:
        """Generate unique token ID."""
        components = [
            provider_name,
            tool_name or "global",
            tenant_id or "default",
        ]
        return ":".join(components)

    # Status and stats

    def get_stats(self) -> JSONDict:
        """Get provider statistics."""
        return {
            **self._stats,
            "oauth2_providers": list(self._oauth2_providers.keys()),
            "oidc_providers": list(self._oidc_providers.keys()),
            "managed_tokens": len(self._managed_tokens),
            "tool_mappings": len(self._tool_providers),
            "refresher_stats": self._token_refresher.get_stats(),
            "credential_stats": self._credential_manager.get_stats(),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }

    def list_managed_tokens(self) -> list[JSONDict]:
        """List all managed tokens."""
        result = []
        for managed in self._managed_tokens.values():
            managed.update_state()
            result.append(managed.to_dict())
        return result

    def get_provider_info(self, name: str) -> JSONDict | None:
        """Get information about a provider."""
        if name in self._oidc_providers:
            oidc_provider = self._oidc_providers[name]
            return {
                "type": "oidc",
                "discovered": oidc_provider.get_metadata() is not None,
                "metadata": oidc_provider.get_metadata().to_dict()
                if oidc_provider.get_metadata()
                else None,
                "stats": oidc_provider.get_stats(),
            }

        if name in self._oauth2_providers:
            oauth2_provider = self._oauth2_providers[name]
            return {
                "type": "oauth2",
                "stats": oauth2_provider.get_stats(),
            }

        return None

    async def get_health(self) -> JSONDict:
        """Get health status."""
        providers_health = {}

        for name in self._oauth2_providers:
            providers_health[name] = {"type": "oauth2", "healthy": True}

        for name, provider in self._oidc_providers.items():
            metadata = provider.get_metadata()
            providers_health[name] = {
                "type": "oidc",
                "healthy": metadata is not None,
                "discovered": metadata is not None,
            }

        # Check for expiring tokens
        expiring_tokens = 0
        expired_tokens = 0
        for managed in self._managed_tokens.values():
            state = managed.update_state()
            if state == TokenState.EXPIRING_SOON:
                expiring_tokens += 1
            elif state == TokenState.EXPIRED:
                expired_tokens += 1

        return {
            "healthy": True,
            "providers": providers_health,
            "total_providers": len(self._oauth2_providers) + len(self._oidc_providers),
            "managed_tokens": len(self._managed_tokens),
            "expiring_tokens": expiring_tokens,
            "expired_tokens": expired_tokens,
            "refresher_running": self._token_refresher._running,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }


__all__ = [
    "MCPAuthProvider",
]
