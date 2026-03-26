# mypy: disable-error-code="no-redef"
"""Infrastructure configuration: Redis, Database, AI, Blockchain.

Constitutional Hash: 608508a9bd224290
"""

import os
from typing import Final

from pydantic import Field, SecretStr, field_validator

from src.core.shared.constants import CONSTITUTIONAL_HASH

try:
    from pydantic_settings import BaseSettings

    HAS_PYDANTIC_SETTINGS: Final[bool] = True
except ImportError:
    HAS_PYDANTIC_SETTINGS: Final[bool] = False  # type: ignore[misc]
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]


if HAS_PYDANTIC_SETTINGS:

    class RedisSettings(BaseSettings):
        """Redis connection settings."""

        url: str = Field("redis://localhost:6379", validation_alias="REDIS_URL")
        host: str = Field("localhost", validation_alias="REDIS_HOST")
        port: int = Field(6379, validation_alias="REDIS_PORT")
        db: int = Field(0, validation_alias="REDIS_DB")
        max_connections: int = Field(100, validation_alias="REDIS_MAX_CONNECTIONS")
        socket_timeout: float = Field(5.0, validation_alias="REDIS_SOCKET_TIMEOUT")
        retry_on_timeout: bool = Field(True, validation_alias="REDIS_RETRY_ON_TIMEOUT")
        ssl: bool = Field(False, validation_alias="REDIS_SSL")
        ssl_cert_reqs: str = Field(
            "none", validation_alias="REDIS_SSL_CERT_REQS"
        )  # none, optional, required
        ssl_ca_certs: str | None = Field(None, validation_alias="REDIS_SSL_CA_CERTS")
        socket_keepalive: bool = Field(True, validation_alias="REDIS_SOCKET_KEEPALIVE")
        health_check_interval: int = Field(30, validation_alias="REDIS_HEALTH_CHECK_INTERVAL")

    class DatabaseSettings(BaseSettings):
        """PostgreSQL database connection settings."""

        url: str = Field(
            "postgresql+asyncpg://localhost:5432/acgs2",
            validation_alias="DATABASE_URL",
        )
        pool_size: int = Field(100, validation_alias="DATABASE_POOL_SIZE")
        max_overflow: int = Field(20, validation_alias="DATABASE_MAX_OVERFLOW")
        pool_pre_ping: bool = Field(True, validation_alias="DATABASE_POOL_PRE_PING")
        echo: bool = Field(False, validation_alias="DATABASE_ECHO")

        @field_validator("url")
        @classmethod
        def normalize_url(cls, v: str) -> str:
            """Normalize database URL for asyncpg compatibility."""
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+asyncpg://", 1)
            if v.startswith("postgresql://") and "+asyncpg" not in v:
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
            return v

    class AISettings(BaseSettings):
        """AI Service settings."""

        openrouter_api_key: SecretStr | None = Field(None, validation_alias="OPENROUTER_API_KEY")
        hf_token: SecretStr | None = Field(None, validation_alias="HF_TOKEN")
        openai_api_key: SecretStr | None = Field(None, validation_alias="OPENAI_API_KEY")
        constitutional_hash: str = Field(
            CONSTITUTIONAL_HASH, validation_alias="CONSTITUTIONAL_HASH"
        )

    class BlockchainSettings(BaseSettings):
        """Blockchain integration settings."""

        eth_l2_network: str = Field("optimism", validation_alias="ETH_L2_NETWORK")
        eth_rpc_url: str = Field("https://mainnet.optimism.io", validation_alias="ETH_RPC_URL")
        contract_address: str | None = Field(None, validation_alias="AUDIT_CONTRACT_ADDRESS")
        private_key: SecretStr | None = Field(None, validation_alias="BLOCKCHAIN_PRIVATE_KEY")

else:
    from dataclasses import dataclass, field

    @dataclass
    class RedisSettings:  # type: ignore[no-redef]
        """Redis connection settings (dataclass fallback when pydantic-settings is unavailable)."""

        url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
        host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
        port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
        db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
        max_connections: int = field(
            default_factory=lambda: int(os.getenv("REDIS_MAX_CONNECTIONS", "100"))
        )
        socket_timeout: float = field(
            default_factory=lambda: float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
        )
        retry_on_timeout: bool = field(
            default_factory=lambda: os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
        )
        ssl: bool = field(default_factory=lambda: os.getenv("REDIS_SSL", "false").lower() == "true")
        ssl_cert_reqs: str = field(default_factory=lambda: os.getenv("REDIS_SSL_CERT_REQS", "none"))
        ssl_ca_certs: str | None = field(default_factory=lambda: os.getenv("REDIS_SSL_CA_CERTS"))
        socket_keepalive: bool = field(
            default_factory=lambda: os.getenv("REDIS_SOCKET_KEEPALIVE", "true").lower() == "true"
        )
        health_check_interval: int = field(
            default_factory=lambda: int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
        )

    @dataclass
    class DatabaseSettings:  # type: ignore[no-redef]
        """PostgreSQL database connection settings (dataclass fallback)."""

        url: str = field(
            default_factory=lambda: os.getenv(
                "DATABASE_URL", "postgresql+asyncpg://localhost:5432/acgs2"
            )
        )
        pool_size: int = field(default_factory=lambda: int(os.getenv("DATABASE_POOL_SIZE", "5")))
        max_overflow: int = field(
            default_factory=lambda: int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
        )
        pool_pre_ping: bool = field(
            default_factory=lambda: os.getenv("DATABASE_POOL_PRE_PING", "true").lower() == "true"
        )
        echo: bool = field(
            default_factory=lambda: os.getenv("DATABASE_ECHO", "false").lower() == "true"
        )

        def __post_init__(self):
            """Normalize database URL for asyncpg compatibility."""
            if self.url.startswith("postgres://"):
                self.url = self.url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif self.url.startswith("postgresql://") and "+asyncpg" not in self.url:
                self.url = self.url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @dataclass
    class AISettings:  # type: ignore[no-redef]
        """AI provider API keys and constitutional hash settings (dataclass fallback)."""

        openrouter_api_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("OPENROUTER_API_KEY", ""))
                if os.getenv("OPENROUTER_API_KEY")
                else None
            )
        )
        hf_token: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("HF_TOKEN", "")) if os.getenv("HF_TOKEN") else None
            )
        )
        openai_api_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("OPENAI_API_KEY", "")) if os.getenv("OPENAI_API_KEY") else None
            )
        )
        constitutional_hash: str = field(
            default_factory=lambda: os.getenv("CONSTITUTIONAL_HASH", CONSTITUTIONAL_HASH)
        )

    @dataclass
    class BlockchainSettings:  # type: ignore[no-redef]
        """Blockchain/Ethereum L2 audit anchor settings (dataclass fallback)."""

        eth_l2_network: str = field(default_factory=lambda: os.getenv("ETH_L2_NETWORK", "optimism"))
        eth_rpc_url: str = field(
            default_factory=lambda: os.getenv("ETH_RPC_URL", "https://mainnet.optimism.io")
        )
        contract_address: str | None = field(
            default_factory=lambda: os.getenv("AUDIT_CONTRACT_ADDRESS")
        )
        private_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("BLOCKCHAIN_PRIVATE_KEY", ""))
                if os.getenv("BLOCKCHAIN_PRIVATE_KEY")
                else None
            )
        )
