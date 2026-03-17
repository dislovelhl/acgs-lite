"""
Secret Storage Backends
Constitutional Hash: cdd01ef066bc6cf2

Abstract base class and implementations for secret storage backends.
Supports in-memory (testing), HashiCorp Vault, and extensible backends.
"""

import os
from abc import ABC, abstractmethod

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


class SecretBackend(ABC):
    """
    Abstract base class for secret storage backends.

    Implementations can support Vault, Kubernetes secrets, AWS Secrets Manager, etc.
    """

    @abstractmethod
    async def get_secret(self, name: str, version_id: str | None = None) -> str | None:
        """Retrieve a secret value."""
        pass

    @abstractmethod
    async def store_secret(self, name: str, value: str, version_id: str) -> bool:
        """Store a secret value."""
        pass

    @abstractmethod
    async def delete_secret_version(self, name: str, version_id: str) -> bool:
        """Delete a specific secret version."""
        pass

    @abstractmethod
    async def list_versions(self, name: str) -> list[str]:
        """List all versions of a secret."""
        pass


class InMemorySecretBackend(SecretBackend):
    """
    In-memory secret backend for development and testing.

    WARNING: Not for production use - secrets are not persisted.
    """

    def __init__(self) -> None:
        self._secrets: dict[str, dict[str, str]] = {}  # {name: {version_id: value}}

    async def get_secret(self, name: str, version_id: str | None = None) -> str | None:
        """Retrieve a secret value."""
        if name not in self._secrets:
            return None
        versions = self._secrets[name]
        if version_id:
            return versions.get(version_id)
        # Return latest version if no version specified
        if versions:
            return list(versions.values())[-1]
        return None

    async def store_secret(self, name: str, value: str, version_id: str) -> bool:
        """Store a secret value."""
        if name not in self._secrets:
            self._secrets[name] = {}
        self._secrets[name][version_id] = value
        return True

    async def delete_secret_version(self, name: str, version_id: str) -> bool:
        """Delete a specific secret version."""
        if name in self._secrets and version_id in self._secrets[name]:
            del self._secrets[name][version_id]
            return True
        return False

    async def list_versions(self, name: str) -> list[str]:
        """List all versions of a secret."""
        if name not in self._secrets:
            return []
        return list(self._secrets[name].keys())


class VaultSecretBackend(SecretBackend):
    """
    HashiCorp Vault secret backend.

    Supports KV v2 secrets engine with versioning.
    """

    def __init__(
        self,
        vault_url: str | None = None,
        vault_token: str | None = None,
        mount_point: str = "secret",
        path_prefix: str = "acgs2/secrets",
    ) -> None:
        self._vault_url = vault_url or os.environ.get("VAULT_ADDR", "http://localhost:8200")
        self._vault_token = vault_token or os.environ.get("VAULT_TOKEN")
        self._mount_point = mount_point
        self._path_prefix = path_prefix
        self._client: object = None

    async def _get_client(self) -> object:
        """Get or create Vault client."""
        if self._client is None:
            try:
                import hvac

                self._client = hvac.Client(url=self._vault_url, token=self._vault_token)
            except ImportError:
                logger.warning("hvac library not available for Vault backend")
                return None
        return self._client

    async def get_secret(self, name: str, version_id: str | None = None) -> str | None:
        """Retrieve a secret from Vault."""
        client = await self._get_client()
        if not client:
            return None

        try:
            path = f"{self._path_prefix}/{name}"
            if version_id:
                # Get specific version
                response = client.secrets.kv.v2.read_secret_version(
                    path=path,
                    mount_point=self._mount_point,
                    version=int(version_id.split("-")[-1]) if "-" in version_id else None,
                )
            else:
                response = client.secrets.kv.v2.read_secret_version(
                    path=path,
                    mount_point=self._mount_point,
                )
            return response["data"]["data"].get("value")
        except (RuntimeError, ValueError, KeyError) as e:
            logger.error(f"Failed to get secret from Vault ({type(e).__name__}): {e}")
            return None

    async def store_secret(self, name: str, value: str, version_id: str) -> bool:
        """Store a secret in Vault."""
        client = await self._get_client()
        if not client:
            return False

        try:
            path = f"{self._path_prefix}/{name}"
            client.secrets.kv.v2.create_or_update_secret(
                path=path,
                mount_point=self._mount_point,
                secret={"value": value, "version_id": version_id},
            )
            return True
        except (RuntimeError, ValueError, KeyError) as e:
            logger.error(f"Failed to store secret in Vault ({type(e).__name__}): {e}")
            return False

    async def delete_secret_version(self, name: str, version_id: str) -> bool:
        """Delete a secret version in Vault."""
        client = await self._get_client()
        if not client:
            return False

        try:
            path = f"{self._path_prefix}/{name}"
            version_num = int(version_id.split("-")[-1]) if "-" in version_id else 1
            client.secrets.kv.v2.delete_secret_versions(
                path=path,
                mount_point=self._mount_point,
                versions=[version_num],
            )
            return True
        except (RuntimeError, ValueError, KeyError) as e:
            logger.error(f"Failed to delete secret version from Vault ({type(e).__name__}): {e}")
            return False

    async def list_versions(self, name: str) -> list[str]:
        """List secret versions in Vault."""
        client = await self._get_client()
        if not client:
            return []

        try:
            path = f"{self._path_prefix}/{name}"
            response = client.secrets.kv.v2.read_secret_metadata(
                path=path,
                mount_point=self._mount_point,
            )
            versions = response["data"]["versions"]
            return [f"{name}-v{v}" for v in versions.keys()]
        except (RuntimeError, ValueError, KeyError) as e:
            logger.debug(f"Failed to list secret versions from Vault ({type(e).__name__}): {e}")
            return []


__all__ = [
    "InMemorySecretBackend",
    "SecretBackend",
    "VaultSecretBackend",
]
