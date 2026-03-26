# mypy: disable-error-code="no-redef"
"""Governance and control configuration: MACI, Voting, CircuitBreaker.

Constitutional Hash: 608508a9bd224290
"""

import os
from typing import Final

from pydantic import Field, SecretStr

try:
    from pydantic_settings import BaseSettings

    HAS_PYDANTIC_SETTINGS: Final[bool] = True
except ImportError:
    HAS_PYDANTIC_SETTINGS: Final[bool] = False  # type: ignore[misc]
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]


if HAS_PYDANTIC_SETTINGS:

    class MACISettings(BaseSettings):
        """MACI (Multi-Agent Constitutional Intelligence) enforcement settings."""

        strict_mode: bool = Field(True, validation_alias="MACI_STRICT_MODE")
        default_role: str | None = Field(None, validation_alias="MACI_DEFAULT_ROLE")
        config_path: str | None = Field(None, validation_alias="MACI_CONFIG_PATH")

    class VotingSettings(BaseSettings):
        """Voting and deliberation settings for event-driven vote collection."""

        default_timeout_seconds: int = Field(30, validation_alias="VOTING_DEFAULT_TIMEOUT_SECONDS")
        vote_topic_pattern: str = Field(
            "acgs.tenant.{tenant_id}.votes", validation_alias="VOTING_VOTE_TOPIC_PATTERN"
        )
        audit_topic_pattern: str = Field(
            "acgs.tenant.{tenant_id}.audit.votes", validation_alias="VOTING_AUDIT_TOPIC_PATTERN"
        )
        redis_election_prefix: str = Field(
            "election:", validation_alias="VOTING_REDIS_ELECTION_PREFIX"
        )
        enable_weighted_voting: bool = Field(True, validation_alias="VOTING_ENABLE_WEIGHTED")
        signature_algorithm: str = Field(
            "HMAC-SHA256", validation_alias="VOTING_SIGNATURE_ALGORITHM"
        )
        audit_signature_key: SecretStr | None = Field(None, validation_alias="AUDIT_SIGNATURE_KEY")
        timeout_check_interval_seconds: int = Field(
            5, validation_alias="VOTING_TIMEOUT_CHECK_INTERVAL"
        )

    class CircuitBreakerSettings(BaseSettings):
        """
        Circuit Breaker Configuration Settings.

        Constitutional Hash: 608508a9bd224290
        Expert Reference: Michael Nygard (Release It!)

        Configures thresholds for external service circuit breakers:
        - failure_threshold: Number of failures before opening circuit
        - timeout_seconds: How long circuit stays open before half-open
        - half_open_requests: Requests allowed in half-open state for recovery testing

        Service-specific configurations per T002 requirements:
        - policy_registry: failure_threshold=3, timeout=10s, fallback=cached_policy
        - opa_evaluator: failure_threshold=5, timeout=5s, fallback=fail_closed (critical)
        - blockchain_anchor: failure_threshold=10, timeout=60s, fallback=queue_for_retry
        - redis_cache: failure_threshold=3, timeout=1s, fallback=skip_cache
        - kafka_producer: failure_threshold=5, timeout=30s, fallback=queue_for_retry
        """

        # Global defaults
        default_failure_threshold: int = Field(5, validation_alias="CB_DEFAULT_FAILURE_THRESHOLD")
        default_timeout_seconds: float = Field(30.0, validation_alias="CB_DEFAULT_TIMEOUT_SECONDS")
        default_half_open_requests: int = Field(3, validation_alias="CB_DEFAULT_HALF_OPEN_REQUESTS")

        # Policy Registry circuit breaker
        policy_registry_failure_threshold: int = Field(
            3, validation_alias="CB_POLICY_REGISTRY_FAILURE_THRESHOLD"
        )
        policy_registry_timeout_seconds: float = Field(
            10.0, validation_alias="CB_POLICY_REGISTRY_TIMEOUT_SECONDS"
        )
        policy_registry_fallback_ttl_seconds: int = Field(
            300, validation_alias="CB_POLICY_REGISTRY_FALLBACK_TTL"
        )

        # OPA Evaluator circuit breaker (CRITICAL - fail-closed)
        opa_evaluator_failure_threshold: int = Field(
            5, validation_alias="CB_OPA_EVALUATOR_FAILURE_THRESHOLD"
        )
        opa_evaluator_timeout_seconds: float = Field(
            5.0, validation_alias="CB_OPA_EVALUATOR_TIMEOUT_SECONDS"
        )

        # Blockchain Anchor circuit breaker
        blockchain_anchor_failure_threshold: int = Field(
            10, validation_alias="CB_BLOCKCHAIN_ANCHOR_FAILURE_THRESHOLD"
        )
        blockchain_anchor_timeout_seconds: float = Field(
            60.0, validation_alias="CB_BLOCKCHAIN_ANCHOR_TIMEOUT_SECONDS"
        )
        blockchain_anchor_max_queue_size: int = Field(
            10000, validation_alias="CB_BLOCKCHAIN_ANCHOR_MAX_QUEUE_SIZE"
        )
        blockchain_anchor_retry_interval_seconds: int = Field(
            300, validation_alias="CB_BLOCKCHAIN_ANCHOR_RETRY_INTERVAL"
        )

        # Redis Cache circuit breaker
        redis_cache_failure_threshold: int = Field(
            3, validation_alias="CB_REDIS_CACHE_FAILURE_THRESHOLD"
        )
        redis_cache_timeout_seconds: float = Field(
            1.0, validation_alias="CB_REDIS_CACHE_TIMEOUT_SECONDS"
        )

        # Kafka Producer circuit breaker
        kafka_producer_failure_threshold: int = Field(
            5, validation_alias="CB_KAFKA_PRODUCER_FAILURE_THRESHOLD"
        )
        kafka_producer_timeout_seconds: float = Field(
            30.0, validation_alias="CB_KAFKA_PRODUCER_TIMEOUT_SECONDS"
        )
        kafka_producer_max_queue_size: int = Field(
            10000, validation_alias="CB_KAFKA_PRODUCER_MAX_QUEUE_SIZE"
        )

        # Audit Service circuit breaker
        audit_service_failure_threshold: int = Field(
            5, validation_alias="CB_AUDIT_SERVICE_FAILURE_THRESHOLD"
        )
        audit_service_timeout_seconds: float = Field(
            30.0, validation_alias="CB_AUDIT_SERVICE_TIMEOUT_SECONDS"
        )
        audit_service_max_queue_size: int = Field(
            5000, validation_alias="CB_AUDIT_SERVICE_MAX_QUEUE_SIZE"
        )

        # Deliberation Layer circuit breaker (CRITICAL)
        deliberation_layer_failure_threshold: int = Field(
            7, validation_alias="CB_DELIBERATION_LAYER_FAILURE_THRESHOLD"
        )
        deliberation_layer_timeout_seconds: float = Field(
            45.0, validation_alias="CB_DELIBERATION_LAYER_TIMEOUT_SECONDS"
        )

        # Health monitoring
        health_check_enabled: bool = Field(True, validation_alias="CB_HEALTH_CHECK_ENABLED")
        metrics_enabled: bool = Field(True, validation_alias="CB_METRICS_ENABLED")

else:
    from dataclasses import dataclass, field

    @dataclass
    class MACISettings:  # type: ignore[no-redef]
        """MACI (Multi-Agent Constitutional Intelligence) role enforcement settings (dataclass fallback)."""

        strict_mode: bool = field(
            default_factory=lambda: os.getenv("MACI_STRICT_MODE", "true").lower() == "true"
        )
        default_role: str | None = field(default_factory=lambda: os.getenv("MACI_DEFAULT_ROLE"))
        config_path: str | None = field(default_factory=lambda: os.getenv("MACI_CONFIG_PATH"))

    @dataclass
    class VotingSettings:  # type: ignore[no-redef]
        """Voting and deliberation settings for event-driven vote collection."""

        default_timeout_seconds: int = field(
            default_factory=lambda: int(os.getenv("VOTING_DEFAULT_TIMEOUT_SECONDS", "30"))
        )
        vote_topic_pattern: str = field(
            default_factory=lambda: os.getenv(
                "VOTING_VOTE_TOPIC_PATTERN", "acgs.tenant.{tenant_id}.votes"
            )
        )
        audit_topic_pattern: str = field(
            default_factory=lambda: os.getenv(
                "VOTING_AUDIT_TOPIC_PATTERN", "acgs.tenant.{tenant_id}.audit.votes"
            )
        )
        redis_election_prefix: str = field(
            default_factory=lambda: os.getenv("VOTING_REDIS_ELECTION_PREFIX", "election:")
        )
        enable_weighted_voting: bool = field(
            default_factory=lambda: os.getenv("VOTING_ENABLE_WEIGHTED", "true").lower() == "true"
        )
        signature_algorithm: str = field(
            default_factory=lambda: os.getenv("VOTING_SIGNATURE_ALGORITHM", "HMAC-SHA256")
        )
        audit_signature_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("AUDIT_SIGNATURE_KEY", ""))
                if os.getenv("AUDIT_SIGNATURE_KEY")
                else None
            )
        )
        timeout_check_interval_seconds: int = field(
            default_factory=lambda: int(os.getenv("VOTING_TIMEOUT_CHECK_INTERVAL", "5"))
        )

    @dataclass
    class CircuitBreakerSettings:  # type: ignore[no-redef]
        """Circuit Breaker Configuration - Constitutional Hash: 608508a9bd224290."""

        # Global defaults
        default_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_DEFAULT_FAILURE_THRESHOLD", "5"))
        )
        default_timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("CB_DEFAULT_TIMEOUT_SECONDS", "30.0"))
        )
        default_half_open_requests: int = field(
            default_factory=lambda: int(os.getenv("CB_DEFAULT_HALF_OPEN_REQUESTS", "3"))
        )

        # Policy Registry
        policy_registry_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_POLICY_REGISTRY_FAILURE_THRESHOLD", "3"))
        )
        policy_registry_timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("CB_POLICY_REGISTRY_TIMEOUT_SECONDS", "10.0"))
        )
        policy_registry_fallback_ttl_seconds: int = field(
            default_factory=lambda: int(os.getenv("CB_POLICY_REGISTRY_FALLBACK_TTL", "300"))
        )

        # OPA Evaluator (CRITICAL)
        opa_evaluator_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_OPA_EVALUATOR_FAILURE_THRESHOLD", "5"))
        )
        opa_evaluator_timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("CB_OPA_EVALUATOR_TIMEOUT_SECONDS", "5.0"))
        )

        # Blockchain Anchor
        blockchain_anchor_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_BLOCKCHAIN_ANCHOR_FAILURE_THRESHOLD", "10"))
        )
        blockchain_anchor_timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("CB_BLOCKCHAIN_ANCHOR_TIMEOUT_SECONDS", "60.0"))
        )
        blockchain_anchor_max_queue_size: int = field(
            default_factory=lambda: int(os.getenv("CB_BLOCKCHAIN_ANCHOR_MAX_QUEUE_SIZE", "10000"))
        )
        blockchain_anchor_retry_interval_seconds: int = field(
            default_factory=lambda: int(os.getenv("CB_BLOCKCHAIN_ANCHOR_RETRY_INTERVAL", "300"))
        )

        # Redis Cache
        redis_cache_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_REDIS_CACHE_FAILURE_THRESHOLD", "3"))
        )
        redis_cache_timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("CB_REDIS_CACHE_TIMEOUT_SECONDS", "1.0"))
        )

        # Kafka Producer
        kafka_producer_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_KAFKA_PRODUCER_FAILURE_THRESHOLD", "5"))
        )
        kafka_producer_timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("CB_KAFKA_PRODUCER_TIMEOUT_SECONDS", "30.0"))
        )
        kafka_producer_max_queue_size: int = field(
            default_factory=lambda: int(os.getenv("CB_KAFKA_PRODUCER_MAX_QUEUE_SIZE", "10000"))
        )

        # Audit Service
        audit_service_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_AUDIT_SERVICE_FAILURE_THRESHOLD", "5"))
        )
        audit_service_timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("CB_AUDIT_SERVICE_TIMEOUT_SECONDS", "30.0"))
        )
        audit_service_max_queue_size: int = field(
            default_factory=lambda: int(os.getenv("CB_AUDIT_SERVICE_MAX_QUEUE_SIZE", "5000"))
        )

        # Deliberation Layer (CRITICAL)
        deliberation_layer_failure_threshold: int = field(
            default_factory=lambda: int(os.getenv("CB_DELIBERATION_LAYER_FAILURE_THRESHOLD", "7"))
        )
        deliberation_layer_timeout_seconds: float = field(
            default_factory=lambda: float(
                os.getenv("CB_DELIBERATION_LAYER_TIMEOUT_SECONDS", "45.0")
            )
        )

        # Health monitoring
        health_check_enabled: bool = field(
            default_factory=lambda: os.getenv("CB_HEALTH_CHECK_ENABLED", "true").lower() == "true"
        )
        metrics_enabled: bool = field(
            default_factory=lambda: os.getenv("CB_METRICS_ENABLED", "true").lower() == "true"
        )
