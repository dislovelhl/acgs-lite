"""
Credential Manager for MCP Tool Authentication.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Provides per-tool credential management:
- Secure credential storage
- Credential scoping and isolation
- Automatic credential injection
- Credential lifecycle management
"""

import asyncio
import base64
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

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

# Optional cryptography for encryption
CRYPTO_AVAILABLE = False
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTO_AVAILABLE = True
except ImportError:
    Fernet = None  # type: ignore[misc, assignment]

logger = get_logger(__name__)
CREDENTIAL_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class CredentialType(str, Enum):
    """Type of credential."""

    API_KEY = "api_key"
    OAUTH2_TOKEN = "oauth2_token"
    BASIC_AUTH = "basic_auth"
    BEARER_TOKEN = "bearer_token"
    CLIENT_CREDENTIALS = "client_credentials"
    CERTIFICATE = "certificate"
    HMAC_SECRET = "hmac_secret"
    CUSTOM = "custom"


class CredentialScope(str, Enum):
    """Scope of credential access."""

    GLOBAL = "global"  # Available to all tools
    TOOL_SPECIFIC = "tool_specific"  # Specific tool only
    CATEGORY = "category"  # Tools in a category
    TENANT = "tenant"  # Tenant-scoped
    SESSION = "session"  # Session-scoped


class CredentialStatus(str, Enum):
    """Status of a credential."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING = "pending"
    ROTATION_PENDING = "rotation_pending"


@dataclass
class Credential:
    """A stored credential."""

    credential_id: str
    name: str
    credential_type: CredentialType
    scope: CredentialScope

    # Encrypted credential data
    encrypted_data: bytes | None = None
    data_hash: str | None = None  # For integrity verification

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    status: CredentialStatus = CredentialStatus.ACTIVE

    # Scope details
    tool_names: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    tenant_id: str | None = None

    # Usage tracking
    usage_count: int = 0
    max_usage: int | None = None  # None = unlimited

    # Rotation
    rotation_interval_days: int | None = None
    last_rotation: datetime | None = None

    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def is_expired(self) -> bool:
        """Check if credential is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) >= self.expires_at

    def needs_rotation(self) -> bool:
        """Check if credential needs rotation."""
        if not self.rotation_interval_days:
            return False
        if not self.last_rotation:
            self.last_rotation = self.created_at
        rotation_due = self.last_rotation + timedelta(days=self.rotation_interval_days)
        return datetime.now(UTC) >= rotation_due

    def to_dict(self, include_sensitive: bool = False) -> JSONDict:
        """Convert to dictionary."""
        result = {
            "credential_id": self.credential_id,
            "name": self.name,
            "credential_type": self.credential_type.value,
            "scope": self.scope.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "status": self.status.value,
            "tool_names": self.tool_names,
            "categories": self.categories,
            "tenant_id": self.tenant_id,
            "usage_count": self.usage_count,
            "is_expired": self.is_expired(),
            "needs_rotation": self.needs_rotation(),
            "constitutional_hash": self.constitutional_hash,
        }
        if include_sensitive:
            result["data_hash"] = self.data_hash
        return result


@dataclass
class ToolCredential:
    """Credential binding for a specific tool."""

    tool_name: str
    credential: Credential
    injection_target: str = "headers"  # headers, query, body
    injection_key: str = "Authorization"  # Header name or param name
    injection_prefix: str = ""  # E.g., "Bearer " for tokens
    transform: str | None = None  # Optional transformation
    priority: int = 0  # Higher = preferred


@dataclass
class CredentialManagerConfig:
    """Configuration for credential manager."""

    # Storage
    storage_path: str = "/var/lib/agent-runtime/credentials"
    encryption_enabled: bool = True
    encryption_key: str = ""  # Set via env var in production

    # Redis for distributed cache
    redis_url: str | None = None
    cache_ttl_seconds: int = 300

    # Limits
    max_credentials_per_tool: int = 5
    max_total_credentials: int = 1000

    # Security
    require_encryption: bool = True
    audit_access: bool = True
    mask_values_in_logs: bool = True


class CredentialManager:
    """
    Manages credentials for MCP tools.

    Features:
    - Secure encrypted storage
    - Per-tool credential binding
    - Automatic injection
    - Usage tracking and rotation

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: CredentialManagerConfig | None = None):
        self.config = config or CredentialManagerConfig()
        self._storage_path = Path(self.config.storage_path)

        # Credentials store
        self._credentials: dict[str, Credential] = {}
        self._tool_bindings: dict[str, list[ToolCredential]] = {}

        # Encryption
        self._cipher: object = None
        if self.config.encryption_enabled and CRYPTO_AVAILABLE:
            self._init_encryption()

        # Redis
        self._redis: object = None

        # Lock
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "credentials_stored": 0,
            "credentials_retrieved": 0,
            "credentials_rotated": 0,
            "credentials_expired": 0,
            "injection_count": 0,
        }

    def _init_encryption(self) -> None:
        """Initialize encryption cipher."""
        if not CRYPTO_AVAILABLE:
            logger.warning("cryptography not available, encryption disabled")
            return

        if not self.config.encryption_key:
            # Generate a key for development (should be set via env in prod)
            logger.warning("No encryption key configured, generating ephemeral key")
            self.config.encryption_key = Fernet.generate_key().decode()

        # Derive key from passphrase
        key = self.config.encryption_key.encode()
        if len(key) != 44:  # Not a Fernet key
            # Use PBKDF2 to derive key
            salt = b"acgs2-credential-salt"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(key))

        self._cipher = Fernet(key)

    def _encrypt(self, data: bytes) -> bytes:
        """Encrypt data."""
        if self._cipher:
            return bytes(self._cipher.encrypt(data))
        return data

    def _decrypt(self, data: bytes) -> bytes:
        """Decrypt data."""
        if self._cipher:
            return bytes(self._cipher.decrypt(data))
        return data

    async def store_credential(
        self,
        name: str,
        credential_type: CredentialType,
        credential_data: JSONDict,
        scope: CredentialScope = CredentialScope.TOOL_SPECIFIC,
        tool_names: list[str] | None = None,
        categories: list[str] | None = None,
        tenant_id: str | None = None,
        expires_at: datetime | None = None,
        rotation_interval_days: int | None = None,
        metadata: JSONDict | None = None,
    ) -> Credential:
        """
        Store a new credential.

        Args:
            name: Credential name
            credential_type: Type of credential
            credential_data: The actual credential data
            scope: Credential scope
            tool_names: Tools this credential applies to
            categories: Tool categories this credential applies to
            tenant_id: Tenant ID for tenant-scoped credentials
            expires_at: Expiration time
            rotation_interval_days: Auto-rotation interval
            metadata: Additional metadata

        Returns:
            Stored Credential
        """
        credential_id = secrets.token_hex(16)

        # Encrypt credential data
        data_json = json.dumps(credential_data).encode()
        encrypted_data = self._encrypt(data_json)
        data_hash = hashlib.sha256(data_json).hexdigest()

        credential = Credential(
            credential_id=credential_id,
            name=name,
            credential_type=credential_type,
            scope=scope,
            encrypted_data=encrypted_data,
            data_hash=data_hash,
            expires_at=expires_at,
            tool_names=tool_names or [],
            categories=categories or [],
            tenant_id=tenant_id,
            rotation_interval_days=rotation_interval_days,
            metadata=metadata or {},
        )

        async with self._lock:
            self._credentials[credential_id] = credential

            # Create tool bindings
            for tool_name in credential.tool_names:
                if tool_name not in self._tool_bindings:
                    self._tool_bindings[tool_name] = []

                binding = self._create_default_binding(tool_name, credential)
                self._tool_bindings[tool_name].append(binding)

        self._stats["credentials_stored"] += 1
        await self._persist_credential(credential)

        logger.info(f"Stored credential: {name} ({credential_type.value})")
        return credential

    def _create_default_binding(
        self,
        tool_name: str,
        credential: Credential,
    ) -> ToolCredential:
        """Create default tool credential binding."""
        # Determine injection based on credential type
        if credential.credential_type == CredentialType.BEARER_TOKEN:
            return ToolCredential(
                tool_name=tool_name,
                credential=credential,
                injection_target="headers",
                injection_key="Authorization",
                injection_prefix="Bearer ",
            )
        elif credential.credential_type == CredentialType.API_KEY:
            return ToolCredential(
                tool_name=tool_name,
                credential=credential,
                injection_target="headers",
                injection_key="X-API-Key",
            )
        elif credential.credential_type == CredentialType.BASIC_AUTH:
            return ToolCredential(
                tool_name=tool_name,
                credential=credential,
                injection_target="headers",
                injection_key="Authorization",
                injection_prefix="Basic ",
                transform="base64",
            )
        else:
            return ToolCredential(
                tool_name=tool_name,
                credential=credential,
            )

    async def get_credential(
        self,
        credential_id: str,
        decrypt: bool = True,
    ) -> tuple[Credential, JSONDict | None] | None:
        """
        Get a credential by ID.

        Args:
            credential_id: Credential ID
            decrypt: Whether to decrypt credential data

        Returns:
            Tuple of (Credential, decrypted_data) or None
        """
        async with self._lock:
            credential = self._credentials.get(credential_id)

        if not credential:
            return None

        # Update usage
        credential.last_used_at = datetime.now(UTC)
        credential.usage_count += 1
        self._stats["credentials_retrieved"] += 1

        # Check status
        if credential.is_expired():
            credential.status = CredentialStatus.EXPIRED
            self._stats["credentials_expired"] += 1

        # Decrypt data
        decrypted_data = None
        if decrypt and credential.encrypted_data:
            try:
                decrypted_bytes = self._decrypt(credential.encrypted_data)
                decrypted_data = json.loads(decrypted_bytes)
            except CREDENTIAL_OPERATION_ERRORS as e:
                logger.error(f"Credential decryption failed: {e}")

        return credential, decrypted_data

    async def get_credentials_for_tool(
        self,
        tool_name: str,
        credential_type: CredentialType | None = None,
        tenant_id: str | None = None,
    ) -> list[ToolCredential]:
        """
        Get all credentials applicable to a tool.

        Args:
            tool_name: Tool name
            credential_type: Filter by credential type
            tenant_id: Filter by tenant

        Returns:
            List of ToolCredential bindings
        """
        async with self._lock:
            bindings = self._tool_bindings.get(tool_name, [])

        # Filter
        result = []
        for binding in bindings:
            cred = binding.credential

            # Check type filter
            if credential_type and cred.credential_type != credential_type:
                continue

            # Check tenant filter
            if tenant_id and cred.tenant_id and cred.tenant_id != tenant_id:
                continue

            # Check status
            if cred.status != CredentialStatus.ACTIVE:
                continue

            # Check expiry
            if cred.is_expired():
                continue

            result.append(binding)

        # Sort by priority
        result.sort(key=lambda x: x.priority, reverse=True)
        return result

    async def inject_credentials(
        self,
        tool_name: str,
        request_headers: dict[str, str] | None = None,
        request_params: JSONDict | None = None,
        request_body: JSONDict | None = None,
        tenant_id: str | None = None,
    ) -> JSONDict:
        """
        Inject credentials into a tool request.

        Args:
            tool_name: Tool name
            request_headers: Request headers to modify
            request_params: Request params to modify
            request_body: Request body to modify
            tenant_id: Tenant ID

        Returns:
            Modified request components
        """
        request_headers = request_headers or {}
        request_params = request_params or {}
        request_body = request_body or {}

        bindings = await self.get_credentials_for_tool(tool_name, tenant_id=tenant_id)

        for binding in bindings:
            _, cred_data = await self.get_credential(
                binding.credential.credential_id,
                decrypt=True,
            )

            if not cred_data:
                continue

            # Get value to inject
            value = self._extract_value(cred_data, binding.credential.credential_type)
            if not value:
                continue

            # Apply transformation
            if binding.transform == "base64":
                value = base64.b64encode(value.encode()).decode()

            # Apply prefix
            if binding.injection_prefix:
                value = binding.injection_prefix + value

            # Inject
            if binding.injection_target == "headers":
                request_headers[binding.injection_key] = value
            elif binding.injection_target == "query":
                request_params[binding.injection_key] = value
            elif binding.injection_target == "body":
                request_body[binding.injection_key] = value

            self._stats["injection_count"] += 1

        return {
            "headers": request_headers,
            "params": request_params,
            "body": request_body,
        }

    def _extract_value(
        self,
        cred_data: JSONDict,
        cred_type: CredentialType,
    ) -> str | None:
        """Extract injectable value from credential data."""
        if cred_type == CredentialType.API_KEY:
            raw = cred_data.get("api_key") or cred_data.get("key")
            return str(raw) if raw is not None else None
        elif cred_type == CredentialType.BEARER_TOKEN:
            raw = cred_data.get("token") or cred_data.get("access_token")
            return str(raw) if raw is not None else None
        elif cred_type == CredentialType.BASIC_AUTH:
            username = cred_data.get("username", "")
            password = cred_data.get("password", "")
            return f"{username}:{password}"
        elif cred_type == CredentialType.HMAC_SECRET:
            raw = cred_data.get("secret")
            return str(raw) if raw is not None else None
        else:
            raw = cred_data.get("value")
            return str(raw) if raw is not None else None

    async def rotate_credential(
        self,
        credential_id: str,
        new_data: JSONDict,
    ) -> Credential | None:
        """
        Rotate a credential with new data.

        Args:
            credential_id: Credential to rotate
            new_data: New credential data

        Returns:
            Updated Credential or None
        """
        async with self._lock:
            credential = self._credentials.get(credential_id)
            if not credential:
                return None

            # Encrypt new data
            data_json = json.dumps(new_data).encode()
            credential.encrypted_data = self._encrypt(data_json)
            credential.data_hash = hashlib.sha256(data_json).hexdigest()
            credential.last_rotation = datetime.now(UTC)
            credential.updated_at = datetime.now(UTC)

        self._stats["credentials_rotated"] += 1
        await self._persist_credential(credential)

        logger.info(f"Rotated credential: {credential.name}")
        return credential

    async def revoke_credential(self, credential_id: str) -> bool:
        """Revoke a credential."""
        async with self._lock:
            credential = self._credentials.get(credential_id)
            if not credential:
                return False

            credential.status = CredentialStatus.REVOKED
            credential.updated_at = datetime.now(UTC)

            # Remove from bindings
            for tool_name, bindings in self._tool_bindings.items():
                self._tool_bindings[tool_name] = [
                    b for b in bindings if b.credential.credential_id != credential_id
                ]

        logger.info(f"Revoked credential: {credential.name}")
        return True

    async def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential."""
        async with self._lock:
            if credential_id not in self._credentials:
                return False

            del self._credentials[credential_id]

            # Remove from bindings
            for tool_name in list(self._tool_bindings.keys()):
                self._tool_bindings[tool_name] = [
                    b
                    for b in self._tool_bindings[tool_name]
                    if b.credential.credential_id != credential_id
                ]

        # Delete from storage
        cred_file = self._storage_path / f"{credential_id}.json"
        if cred_file.exists():
            cred_file.unlink()

        logger.info(f"Deleted credential: {credential_id}")
        return True

    async def _persist_credential(self, credential: Credential) -> None:
        """Persist credential to storage."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        cred_file = self._storage_path / f"{credential.credential_id}.json"

        data = {
            "credential_id": credential.credential_id,
            "name": credential.name,
            "credential_type": credential.credential_type.value,
            "scope": credential.scope.value,
            "encrypted_data": (
                base64.b64encode(credential.encrypted_data).decode()
                if credential.encrypted_data
                else None
            ),
            "data_hash": credential.data_hash,
            "created_at": credential.created_at.isoformat(),
            "updated_at": credential.updated_at.isoformat(),
            "expires_at": credential.expires_at.isoformat() if credential.expires_at else None,
            "status": credential.status.value,
            "tool_names": credential.tool_names,
            "categories": credential.categories,
            "tenant_id": credential.tenant_id,
            "rotation_interval_days": credential.rotation_interval_days,
            "last_rotation": (
                credential.last_rotation.isoformat() if credential.last_rotation else None
            ),
            "metadata": credential.metadata,
        }

        await asyncio.to_thread(cred_file.write_text, json.dumps(data, indent=2))

    async def load_credentials(self) -> int:
        """Load credentials from storage."""
        if not self._storage_path.exists():
            return 0

        count = 0
        for cred_file in self._storage_path.glob("*.json"):
            try:
                data = json.loads(await asyncio.to_thread(cred_file.read_text))

                credential = Credential(
                    credential_id=data["credential_id"],
                    name=data["name"],
                    credential_type=CredentialType(data["credential_type"]),
                    scope=CredentialScope(data["scope"]),
                    encrypted_data=(
                        base64.b64decode(data["encrypted_data"])
                        if data.get("encrypted_data")
                        else None
                    ),
                    data_hash=data.get("data_hash"),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    expires_at=(
                        datetime.fromisoformat(data["expires_at"])
                        if data.get("expires_at")
                        else None
                    ),
                    status=CredentialStatus(data.get("status", "active")),
                    tool_names=data.get("tool_names", []),
                    categories=data.get("categories", []),
                    tenant_id=data.get("tenant_id"),
                    rotation_interval_days=data.get("rotation_interval_days"),
                    last_rotation=(
                        datetime.fromisoformat(data["last_rotation"])
                        if data.get("last_rotation")
                        else None
                    ),
                    metadata=data.get("metadata", {}),
                )

                self._credentials[credential.credential_id] = credential

                # Create bindings
                for tool_name in credential.tool_names:
                    if tool_name not in self._tool_bindings:
                        self._tool_bindings[tool_name] = []
                    binding = self._create_default_binding(tool_name, credential)
                    self._tool_bindings[tool_name].append(binding)

                count += 1

            except CREDENTIAL_OPERATION_ERRORS as e:
                logger.error(f"Failed to load credential from {cred_file}: {e}")

        logger.info(f"Loaded {count} credentials from storage")
        return count

    def list_credentials(
        self,
        tool_name: str | None = None,
        credential_type: CredentialType | None = None,
        include_expired: bool = False,
    ) -> list[Credential]:
        """List credentials with optional filters."""
        result = []
        for credential in self._credentials.values():
            # Filter by tool
            if tool_name and tool_name not in credential.tool_names:
                continue

            # Filter by type
            if credential_type and credential.credential_type != credential_type:
                continue

            # Filter expired
            if not include_expired and credential.is_expired():
                continue

            result.append(credential)

        return result

    async def revoke_tool_credentials(self, tool_name: str) -> int:
        """
        Revoke all credentials for a specific tool.

        Args:
            tool_name: Tool name to revoke credentials for

        Returns:
            Number of credentials revoked
        """
        count = 0
        async with self._lock:
            # Find and revoke credentials for this tool
            for credential in list(self._credentials.values()):
                if tool_name in credential.tool_names:
                    credential.status = CredentialStatus.REVOKED
                    credential.updated_at = datetime.now(UTC)
                    count += 1

            # Remove tool bindings
            if tool_name in self._tool_bindings:
                del self._tool_bindings[tool_name]

        logger.info(f"Revoked {count} credentials for tool: {tool_name}")
        return count

    def get_stats(self) -> JSONDict:
        """Get manager statistics."""
        return {
            **self._stats,
            "total_credentials": len(self._credentials),
            "tool_bindings": len(self._tool_bindings),
            "encryption_enabled": self._cipher is not None,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
