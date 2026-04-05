"""
Auth Injector for MCP Tool Requests.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Main entry point for MCP authentication injection:
- Coordinates OAuth2, OIDC, and credential management
- Automatic credential injection into tool requests
- Token lifecycle management
- Comprehensive audit logging
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

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

from .auth_audit import AuditLoggerConfig, AuditSeverity, AuthAuditEventType, AuthAuditLogger
from .credential_manager import (
    Credential,
    CredentialManager,
    CredentialManagerConfig,
    CredentialType,
)
from .oauth2_provider import OAuth2Config, OAuth2GrantType, OAuth2Provider, OAuth2Token
from .oidc_provider import OIDCConfig, OIDCProvider, OIDCTokens
from .token_refresh import RefreshConfig, TokenRefresher

logger = get_logger(__name__)
AUTH_INJECTOR_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class AuthMethod(str, Enum):
    """Authentication method."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    CUSTOM = "custom"


class InjectionStatus(str, Enum):
    """Status of credential injection."""

    SUCCESS = "success"
    FAILED = "failed"
    NO_CREDENTIALS = "no_credentials"
    SKIPPED = "skipped"
    EXPIRED = "expired"


@dataclass
class AuthInjectorConfig:
    """Configuration for auth injector."""

    # Credential manager
    credential_config: CredentialManagerConfig | None = None

    # OAuth2 providers
    oauth2_providers: dict[str, OAuth2Config] = field(default_factory=dict)

    # OIDC providers
    oidc_providers: dict[str, OIDCConfig] = field(default_factory=dict)

    # Token refresh
    refresh_config: RefreshConfig | None = None

    # Audit
    audit_config: AuditLoggerConfig | None = None
    enable_audit: bool = True

    # Behavior
    fail_on_auth_error: bool = True
    retry_on_401: bool = True
    auto_refresh_enabled: bool = True

    # Default provider
    default_oauth2_provider: str | None = None
    default_oidc_provider: str | None = None


@dataclass
class AuthContext:
    """Authentication context for a tool request."""

    # Tool identification - support both 'tool_name' and 'tool_id' for flexibility
    tool_name: str | None = None
    tool_id: str | None = None  # Alias for tool_name

    agent_id: str | None = None
    tenant_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None

    # Auth requirements - support both 'required_scopes' and 'scopes'
    required_scopes: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)  # Alias

    auth_method: AuthMethod = AuthMethod.NONE
    provider_name: str | None = None

    # Request details
    source_ip: str | None = None
    user_agent: str | None = None

    # Additional metadata
    metadata: JSONDict = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def get_tool_name(self) -> str:
        """Get tool name (supports both field names)."""
        return self.tool_name or self.tool_id or "unknown"

    def get_scopes(self) -> list[str]:
        """Get scopes (supports both field names)."""
        return self.required_scopes or self.scopes or []


@dataclass
class InjectionResult:
    """Result of credential injection."""

    status: InjectionStatus
    auth_method: AuthMethod
    modified_headers: dict[str, str] = field(default_factory=dict)
    modified_params: JSONDict = field(default_factory=dict)
    modified_body: JSONDict = field(default_factory=dict)
    credentials_used: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    # Aliases for compatibility with server.py
    @property
    def success(self) -> bool:
        """Check if injection was successful."""
        return self.status == InjectionStatus.SUCCESS

    @property
    def injected_headers(self) -> dict[str, str]:
        """Alias for modified_headers."""
        return self.modified_headers

    @property
    def injected_params(self) -> JSONDict:
        """Alias for modified_params."""
        return self.modified_params

    @property
    def injected_body(self) -> JSONDict:
        """Alias for modified_body."""
        return self.modified_body

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "success": self.success,
            "auth_method": self.auth_method.value,
            "has_modified_headers": bool(self.modified_headers),
            "has_modified_params": bool(self.modified_params),
            "has_modified_body": bool(self.modified_body),
            "credentials_used": self.credentials_used,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "constitutional_hash": self.constitutional_hash,
        }


class AuthInjector:
    """
    Main authentication injector for MCP tools.

    Coordinates:
    - OAuth2 token acquisition and refresh
    - OIDC authentication flows
    - Credential management and injection
    - Audit logging

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: AuthInjectorConfig | None = None):
        self.config = config or AuthInjectorConfig()

        # Initialize components
        self._credential_manager = CredentialManager(
            self.config.credential_config or CredentialManagerConfig()
        )

        self._token_refresher = TokenRefresher(self.config.refresh_config or RefreshConfig())

        self._audit_logger = (
            AuthAuditLogger(self.config.audit_config or AuditLoggerConfig())
            if self.config.enable_audit
            else None
        )

        # OAuth2 providers
        self._oauth2_providers: dict[str, OAuth2Provider] = {}
        for name, oauth_config in self.config.oauth2_providers.items():
            self._oauth2_providers[name] = OAuth2Provider(oauth_config)

        # OIDC providers
        self._oidc_providers: dict[str, OIDCProvider] = {}
        for name, oidc_config in self.config.oidc_providers.items():
            self._oidc_providers[name] = OIDCProvider(oidc_config)

        # Tool auth configurations
        self._tool_auth_configs: dict[str, JSONDict] = {}

        # Lock
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "injections_attempted": 0,
            "injections_successful": 0,
            "injections_failed": 0,
            "oauth2_tokens_acquired": 0,
            "oidc_tokens_acquired": 0,
        }

    async def start(self) -> None:
        """Start the auth injector."""
        # Start token refresher
        await self._token_refresher.start()

        # Load credentials
        await self._credential_manager.load_credentials()

        # Discover OIDC providers
        for name, provider in self._oidc_providers.items():
            try:
                await provider.discover()
                logger.info(f"OIDC provider '{name}' discovered")
            except AUTH_INJECTOR_OPERATION_ERRORS as e:
                logger.error(f"OIDC discovery failed for '{name}': {e}")

        logger.info("Auth injector started")

    async def stop(self) -> None:
        """Stop the auth injector."""
        await self._token_refresher.stop()
        logger.info("Auth injector stopped")

    def configure_tool_auth(
        self,
        tool_name: str,
        auth_method: AuthMethod,
        provider_name: str | None = None,
        scopes: list[str] | None = None,
        credential_type: CredentialType | None = None,
        **kwargs: object,
    ) -> None:
        """
        Configure authentication for a specific tool.

        Args:
            tool_name: Tool name
            auth_method: Auth method to use
            provider_name: OAuth2/OIDC provider name
            scopes: Required scopes
            credential_type: Credential type to use
            **kwargs: Additional configuration
        """
        self._tool_auth_configs[tool_name] = {
            "auth_method": auth_method,
            "provider_name": provider_name,
            "scopes": scopes or [],
            "credential_type": credential_type,
            **kwargs,
        }
        logger.info(f"Configured auth for tool '{tool_name}': {auth_method.value}")

    async def inject_auth(
        self,
        context: AuthContext,
        headers: dict[str, str] | None = None,
        params: JSONDict | None = None,
        body: JSONDict | None = None,
    ) -> InjectionResult:
        """
        Inject authentication into a tool request.

        Args:
            context: Authentication context
            headers: Request headers to modify
            params: Request params to modify
            body: Request body to modify

        Returns:
            InjectionResult
        """
        start_time = datetime.now(UTC)
        self._stats["injections_attempted"] += 1

        headers = headers or {}
        params = params or {}
        body = body or {}

        # Get tool name (supports both tool_name and tool_id)
        tool_name = context.get_tool_name()

        # Get tool auth config
        tool_config = self._tool_auth_configs.get(tool_name, {})
        auth_method = context.auth_method or tool_config.get("auth_method", AuthMethod.NONE)

        if auth_method == AuthMethod.NONE:
            return InjectionResult(
                status=InjectionStatus.SKIPPED,
                auth_method=AuthMethod.NONE,
            )

        result = InjectionResult(
            status=InjectionStatus.FAILED,
            auth_method=auth_method,
        )

        try:
            if auth_method == AuthMethod.OAUTH2:
                result = await self._inject_oauth2(context, headers, tool_config)
            elif auth_method == AuthMethod.OIDC:
                result = await self._inject_oidc(context, headers, tool_config)
            elif auth_method in (
                AuthMethod.API_KEY,
                AuthMethod.BEARER_TOKEN,
                AuthMethod.BASIC_AUTH,
            ):
                result = await self._inject_credentials(context, headers, params, body, tool_config)
            else:
                result.error = f"Unsupported auth method: {auth_method}"

        except AUTH_INJECTOR_OPERATION_ERRORS as e:
            result.status = InjectionStatus.FAILED
            result.error = str(e)
            logger.error(f"Auth injection failed for {tool_name}: {e}")

        # Calculate duration
        end_time = datetime.now(UTC)
        result.duration_ms = (end_time - start_time).total_seconds() * 1000

        # Update stats
        if result.status == InjectionStatus.SUCCESS:
            self._stats["injections_successful"] += 1
        else:
            self._stats["injections_failed"] += 1

        # Audit log
        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.CREDENTIAL_INJECTION,
                message=f"Auth injection: {result.status.value}",
                severity=(
                    AuditSeverity.INFO
                    if result.status == InjectionStatus.SUCCESS
                    else AuditSeverity.WARNING
                ),
                success=result.status == InjectionStatus.SUCCESS,
                agent_id=context.agent_id,
                tool_name=tool_name,
                tenant_id=context.tenant_id,
                session_id=context.session_id,
                request_id=context.request_id,
                source_ip=context.source_ip,
                details={
                    "auth_method": auth_method.value,
                    "credentials_used": result.credentials_used,
                    "error": result.error,
                },
            )

        return result

    async def _inject_oauth2(
        self,
        context: AuthContext,
        headers: dict[str, str],
        tool_config: JSONDict,
    ) -> InjectionResult:
        """Inject OAuth2 authentication."""
        provider_name = (
            tool_config.get("provider_name")
            or context.provider_name
            or self.config.default_oauth2_provider
        )

        if not provider_name or provider_name not in self._oauth2_providers:
            return InjectionResult(
                status=InjectionStatus.FAILED,
                auth_method=AuthMethod.OAUTH2,
                error=f"OAuth2 provider not found: {provider_name}",
            )

        provider = self._oauth2_providers[provider_name]
        scopes = tool_config.get("scopes") or context.get_scopes()
        tool_name = context.get_tool_name()

        # Get or acquire token
        cache_key = f"oauth2:{provider_name}:{tool_name}:{context.tenant_id or 'default'}"
        token = self._token_refresher.get_token(cache_key)

        if not token or token.is_expired():
            # Acquire new token
            token = await provider.acquire_token(
                grant_type=OAuth2GrantType.CLIENT_CREDENTIALS,
                scopes=scopes,
                cache_key=cache_key,
            )

            if token:
                # Register for refresh
                await self._token_refresher.register_token(
                    token_id=cache_key,
                    token=token,
                    provider=provider,
                    cache_key=cache_key,
                )
                self._stats["oauth2_tokens_acquired"] += 1

        if not token:
            return InjectionResult(
                status=InjectionStatus.FAILED,
                auth_method=AuthMethod.OAUTH2,
                error="Failed to acquire OAuth2 token",
            )

        # Inject token
        headers["Authorization"] = f"{token.token_type} {token.access_token}"

        return InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.OAUTH2,
            modified_headers={"Authorization": f"{token.token_type} ***"},
            credentials_used=[f"oauth2:{provider_name}"],
        )

    async def _inject_oidc(
        self,
        context: AuthContext,
        headers: dict[str, str],
        tool_config: JSONDict,
    ) -> InjectionResult:
        """Inject OIDC authentication."""
        provider_name = (
            tool_config.get("provider_name")
            or context.provider_name
            or self.config.default_oidc_provider
        )

        if not provider_name or provider_name not in self._oidc_providers:
            return InjectionResult(
                status=InjectionStatus.FAILED,
                auth_method=AuthMethod.OIDC,
                error=f"OIDC provider not found: {provider_name}",
            )

        provider = self._oidc_providers[provider_name]
        scopes = tool_config.get("scopes") or context.get_scopes()
        tool_name = context.get_tool_name()

        # For OIDC, we typically use client credentials or pre-obtained tokens
        cache_key = f"oidc:{provider_name}:{tool_name}:{context.tenant_id or 'default'}"
        managed_token = self._token_refresher.get_managed_token(cache_key)

        if not managed_token or managed_token.token.is_expired():
            # Acquire new tokens via client credentials
            oidc_tokens = await provider.acquire_tokens(
                grant_type=OAuth2GrantType.CLIENT_CREDENTIALS,
                scopes=scopes,
                cache_key=cache_key,
            )

            if oidc_tokens:
                # Register for refresh
                await self._token_refresher.register_token(
                    token_id=cache_key,
                    token=oidc_tokens.oauth2_token,
                    provider=provider._oauth2_provider,
                    cache_key=cache_key,
                )
                self._stats["oidc_tokens_acquired"] += 1
                token = oidc_tokens.oauth2_token
            else:
                token = None
        else:
            token = managed_token.token

        if not token:
            return InjectionResult(
                status=InjectionStatus.FAILED,
                auth_method=AuthMethod.OIDC,
                error="Failed to acquire OIDC token",
            )

        # Inject token
        headers["Authorization"] = f"Bearer {token.access_token}"

        return InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.OIDC,
            modified_headers={"Authorization": "Bearer ***"},
            credentials_used=[f"oidc:{provider_name}"],
        )

    async def _inject_credentials(
        self,
        context: AuthContext,
        headers: dict[str, str],
        params: JSONDict,
        body: JSONDict,
        tool_config: JSONDict,
    ) -> InjectionResult:
        """Inject stored credentials."""
        credential_type = tool_config.get("credential_type")
        tool_name = context.get_tool_name()

        if context.auth_method == AuthMethod.API_KEY:
            credential_type = credential_type or CredentialType.API_KEY
        elif context.auth_method == AuthMethod.BEARER_TOKEN:
            credential_type = credential_type or CredentialType.BEARER_TOKEN
        elif context.auth_method == AuthMethod.BASIC_AUTH:
            credential_type = credential_type or CredentialType.BASIC_AUTH

        # Use credential manager to inject
        injected = await self._credential_manager.inject_credentials(
            tool_name=tool_name,
            request_headers=headers,
            request_params=params,
            request_body=body,
            tenant_id=context.tenant_id,
        )

        if injected["headers"] or injected["params"] or injected["body"]:
            return InjectionResult(
                status=InjectionStatus.SUCCESS,
                auth_method=context.auth_method,
                modified_headers={k: "***" for k in injected["headers"]},
                modified_params={k: "***" for k in injected["params"]},
                modified_body={k: "***" for k in injected["body"]},
                credentials_used=[tool_name],
            )
        else:
            return InjectionResult(
                status=InjectionStatus.NO_CREDENTIALS,
                auth_method=context.auth_method,
                error=f"No credentials found for tool: {tool_name}",
            )

    # OAuth2 convenience methods

    async def acquire_oauth2_token(
        self,
        provider_name: str,
        scopes: list[str] | None = None,
        cache_key: str | None = None,
    ) -> OAuth2Token | None:
        """Acquire OAuth2 token from a provider."""
        if provider_name not in self._oauth2_providers:
            logger.error(f"OAuth2 provider not found: {provider_name}")
            return None

        provider = self._oauth2_providers[provider_name]
        return await provider.acquire_token(
            grant_type=OAuth2GrantType.CLIENT_CREDENTIALS,
            scopes=scopes,
            cache_key=cache_key,
        )

    async def get_oidc_authorization_url(
        self,
        provider_name: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        state: str | None = None,
    ) -> tuple[str, str, str | None] | None:
        """Get OIDC authorization URL for login."""
        if provider_name not in self._oidc_providers:
            logger.error(f"OIDC provider not found: {provider_name}")
            return None

        provider = self._oidc_providers[provider_name]
        return provider.build_authorization_url(
            redirect_uri=redirect_uri,
            scopes=scopes,
            state=state,
        )

    async def handle_oidc_callback(
        self,
        provider_name: str,
        code: str,
        redirect_uri: str,
        state: str | None = None,
        nonce: str | None = None,
    ) -> OIDCTokens | None:
        """Handle OIDC callback and acquire tokens."""
        if provider_name not in self._oidc_providers:
            logger.error(f"OIDC provider not found: {provider_name}")
            return None

        provider = self._oidc_providers[provider_name]

        tokens = await provider.acquire_tokens(
            grant_type=OAuth2GrantType.AUTHORIZATION_CODE,
            code=code,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
        )

        if tokens and self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.OIDC_CALLBACK,
                message=f"OIDC callback handled for {provider_name}",
                success=True,
                details={
                    "provider": provider_name,
                    "subject": tokens.subject,
                    "validated": tokens.validated,
                },
            )

        return tokens

    # Credential management convenience methods

    async def store_api_key(
        self,
        name: str,
        api_key: str,
        tool_names: list[str],
        tenant_id: str | None = None,
    ) -> Credential:
        """Store an API key credential."""
        return await self._credential_manager.store_credential(
            name=name,
            credential_type=CredentialType.API_KEY,
            credential_data={"api_key": api_key},
            tool_names=tool_names,
            tenant_id=tenant_id,
        )

    async def store_bearer_token(
        self,
        name: str,
        token: str,
        tool_names: list[str],
        tenant_id: str | None = None,
    ) -> Credential:
        """Store a bearer token credential."""
        return await self._credential_manager.store_credential(
            name=name,
            credential_type=CredentialType.BEARER_TOKEN,
            credential_data={"token": token},
            tool_names=tool_names,
            tenant_id=tenant_id,
        )

    async def store_basic_auth(
        self,
        name: str,
        username: str,
        password: str,
        tool_names: list[str],
        tenant_id: str | None = None,
    ) -> Credential:
        """Store basic auth credentials."""
        return await self._credential_manager.store_credential(
            name=name,
            credential_type=CredentialType.BASIC_AUTH,
            credential_data={"username": username, "password": password},
            tool_names=tool_names,
            tenant_id=tenant_id,
        )

    # Provider management

    def add_oauth2_provider(
        self,
        name: str,
        config: OAuth2Config,
    ) -> None:
        """Add an OAuth2 provider."""
        self._oauth2_providers[name] = OAuth2Provider(config)
        logger.info(f"Added OAuth2 provider: {name}")

    async def add_oidc_provider(
        self,
        name: str,
        config: OIDCConfig,
        discover: bool = True,
    ) -> None:
        """Add an OIDC provider."""
        provider = OIDCProvider(config)
        if discover:
            await provider.discover()
        self._oidc_providers[name] = provider
        logger.info(f"Added OIDC provider: {name}")

    def remove_provider(self, name: str) -> bool:
        """Remove a provider."""
        if name in self._oauth2_providers:
            del self._oauth2_providers[name]
            return True
        if name in self._oidc_providers:
            del self._oidc_providers[name]
            return True
        return False

    # Status and stats

    def get_stats(self) -> JSONDict:
        """Get injector statistics."""
        return {
            **self._stats,
            "oauth2_providers": list(self._oauth2_providers.keys()),
            "oidc_providers": list(self._oidc_providers.keys()),
            "configured_tools": list(self._tool_auth_configs.keys()),
            "credential_stats": self._credential_manager.get_stats(),
            "token_refresh_stats": self._token_refresher.get_stats(),
            "audit_stats": (
                self._audit_logger.get_stats_snapshot().to_dict() if self._audit_logger else None
            ),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def get_health(self) -> JSONDict:
        """Get health status."""
        oauth2_health = {}
        for name, oauth2_prov in self._oauth2_providers.items():
            oauth2_health[name] = oauth2_prov.get_stats()

        oidc_health = {}
        for name, oidc_prov in self._oidc_providers.items():
            oidc_health[name] = {
                "discovered": oidc_prov.get_metadata() is not None,  # type: ignore[attr-defined]
                "stats": oidc_prov.get_stats(),
            }

        return {
            "healthy": True,
            "oauth2_providers": oauth2_health,
            "oidc_providers": oidc_health,
            "managed_tokens": self._token_refresher.list_tokens(),
            "credentials": len(self._credential_manager.list_credentials()),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    # Additional methods for server.py integration

    async def get_tool_auth_status(self, tool_id: str) -> JSONDict:
        """
        Get authentication status for a specific tool.

        Args:
            tool_id: Tool identifier

        Returns:
            Status dictionary
        """
        config = self._tool_auth_configs.get(tool_id)

        # Find related tokens
        managed_tokens = []
        for token_info in self._token_refresher.list_tokens():
            if tool_id in token_info.get("token_id", ""):
                managed_tokens.append(token_info)

        # Find related credentials
        credentials = []
        for cred in self._credential_manager.list_credentials(tool_name=tool_id):
            credentials.append(
                {
                    "name": cred.name,
                    "type": cred.credential_type.value,
                    "status": cred.status.value,
                }
            )

        return {
            "tool_id": tool_id,
            "configured": config is not None,
            "auth_method": config.get("auth_method", AuthMethod.NONE).value if config else "none",
            "provider": config.get("provider_name") if config else None,
            "scopes": config.get("scopes", []) if config else [],
            "tokens_managed": len(managed_tokens),
            "token_status": managed_tokens[0] if managed_tokens else None,
            "credentials_available": len(credentials),
            "credentials": credentials,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def revoke_auth(
        self,
        tool_id: str | None = None,
        agent_id: str | None = None,
    ) -> JSONDict:
        """
        Revoke authentication for a tool or agent.

        Args:
            tool_id: Optional tool ID to revoke
            agent_id: Optional agent ID to revoke

        Returns:
            Revocation result
        """
        revoked_tokens = 0
        revoked_credentials = 0
        revoked_configs = 0

        # Revoke tokens matching the tool/agent
        tokens_to_remove = []
        for token_info in self._token_refresher.list_tokens():
            token_id = token_info.get("token_id", "")
            if tool_id and tool_id in token_id:
                tokens_to_remove.append(token_id)
            elif agent_id and agent_id in token_id:
                tokens_to_remove.append(token_id)

        for token_id in tokens_to_remove:
            await self._token_refresher.unregister_token(token_id)
            revoked_tokens += 1

        # Remove tool config
        if tool_id and tool_id in self._tool_auth_configs:
            del self._tool_auth_configs[tool_id]
            revoked_configs += 1

        # Revoke credentials
        if tool_id:
            await self._credential_manager.revoke_tool_credentials(tool_id)
            revoked_credentials += 1

        # Audit log
        if self._audit_logger:
            await self._audit_logger.log_event(
                event_type=AuthAuditEventType.TOKEN_REVOKED,
                message=f"Auth revoked for tool={tool_id} agent={agent_id}",
                success=True,
                tool_name=tool_id,
                agent_id=agent_id,
                details={
                    "revoked_tokens": revoked_tokens,
                    "revoked_credentials": revoked_credentials,
                    "revoked_configs": revoked_configs,
                },
            )

        return {
            "success": True,
            "tool_id": tool_id,
            "agent_id": agent_id,
            "revoked_tokens": revoked_tokens,
            "revoked_credentials": revoked_credentials,
            "revoked_configs": revoked_configs,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
