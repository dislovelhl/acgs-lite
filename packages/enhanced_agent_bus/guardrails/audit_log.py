"""
Audit Log Guardrail Component.

Layer 5 of OWASP guardrails: immutable compliance trail for all guardrail
decisions with support for blockchain and SIEM integration.

Constitutional Hash: 608508a9bd224290
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction
from .models import GuardrailResult

logger = get_logger(__name__)

_AUDIT_LOG_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
)


@dataclass
class AuditLogConfig:
    """Configuration for audit log.

    Attributes:
        enabled: Whether audit logging is enabled
        retention_days: Number of days to retain audit entries
        log_to_blockchain: Whether to log to blockchain ledger
        log_to_siem: Whether to log to SIEM systems
        blockchain_storage_path: Path to blockchain ledger file
        siem_providers: List of SIEM provider configurations for multi-backend support
        siem_timeout_seconds: Timeout for SIEM operations
        siem_fail_silent: Whether to fail silently on SIEM errors (True) or raise (False)
    """

    enabled: bool = True
    retention_days: int = 90
    log_to_blockchain: bool = False
    log_to_siem: bool = False
    blockchain_storage_path: str = "audit_blockchain_ledger.json"
    siem_providers: list[JSONDict] = field(default_factory=list)
    siem_timeout_seconds: float = 30.0
    siem_fail_silent: bool = True


class BlockchainLedger:
    """
    Tamper-evident blockchain ledger for audit log entries.

    Each audit entry is stored as a block cryptographically linked to
    the previous block, creating an immutable audit trail.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, storage_path: str = "audit_blockchain_ledger.json"):
        self.storage_path = os.path.abspath(storage_path)
        self.blocks: list[JSONDict] = []
        self._initialize_chain()

    def _initialize_chain(self) -> None:
        """Initialize blockchain ledger.

        NOTE: This is a synchronous initialization method called from __init__.
        File I/O here uses sync operations as it runs during object construction.
        For async contexts, consider using an async factory pattern.
        """
        parent_dir = os.path.dirname(self.storage_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path) as f:
                    self.blocks = json.load(f)
                    if not self._verify_chain_integrity():
                        logger.error("Blockchain integrity failure! Ledger may be tampered.")
            else:
                self._create_genesis_block()
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load blockchain ledger: {e}")
            self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        genesis = {
            "index": 0,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {"type": "genesis"},
            "previous_hash": "0" * 64,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        genesis["hash"] = self._calculate_block_hash(genesis)
        self.blocks = [genesis]
        self._persist_chain()
        logger.info("Initialized blockchain ledger genesis block")

    def _calculate_block_hash(self, block: JSONDict) -> str:
        content = json.dumps(
            {
                "index": block["index"],
                "timestamp": block["timestamp"],
                "data": block["data"],
                "previous_hash": block["previous_hash"],
                "constitutional_hash": block.get("constitutional_hash", CONSTITUTIONAL_HASH),
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()

    async def add_entry(self, entry_data: JSONDict) -> JSONDict:
        """Add a new audit entry to the blockchain."""
        previous_block = self.blocks[-1]
        new_index = previous_block["index"] + 1

        new_block = {
            "index": new_index,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": entry_data,
            "previous_hash": previous_block["hash"],
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        new_block["hash"] = self._calculate_block_hash(new_block)

        self.blocks.append(new_block)
        await self._persist_chain_async()
        logger.debug(f"Audit entry anchored at block {new_index}")
        return new_block

    def _verify_chain_integrity(self) -> bool:
        for i in range(1, len(self.blocks)):
            prev = self.blocks[i - 1]
            curr = self.blocks[i]

            if curr["previous_hash"] != prev["hash"]:
                return False
            if curr["hash"] != self._calculate_block_hash(curr):
                return False
        return True

    def _persist_chain(self) -> None:
        """Persist blockchain ledger to disk.

        WARNING: Uses blocking sync I/O (with open()). This method is called
        from sync contexts (add_entry). For production async usage, consider
        migrating to aiofiles.open() or wrapping with asyncio.to_thread().
        """
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.blocks, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to persist blockchain ledger: {e}")

    async def _persist_chain_async(self) -> None:
        """Persist the ledger without creating executor threads.

        The blockchain ledger writes a small local JSON file per entry. Running
        this through ``asyncio.to_thread()`` leaves the guardrail tests and
        short-lived CLI reproducers hanging during shutdown in this environment,
        even though the write itself has already completed. Keep the async API
        surface for callers, but execute the tiny write inline.
        """
        self._persist_chain()

    def get_latest_block(self) -> JSONDict:
        return self.blocks[-1]

    def get_block_by_index(self, index: int) -> JSONDict | None:
        for block in self.blocks:
            if block["index"] == index:
                return block
        return None

    def verify_entry(self, block_hash: str) -> bool:
        return any(block["hash"] == block_hash for block in self.blocks)


class AuditLog(GuardrailComponent):
    """Audit Log: Layer 5 of OWASP guardrails.

    Immutable compliance trail for all guardrail decisions.
    Supports blockchain integration for immutability
    and SIEM systems for security monitoring.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: AuditLogConfig | None = None):
        self.config = config or AuditLogConfig()
        self._audit_entries: list[JSONDict] = []
        self._blockchain_ledger: BlockchainLedger | None = None
        self._siem_providers: list = []
        self._siem_metrics = {
            "events_sent": 0,
            "events_failed": 0,
            "providers_configured": 0,
        }

        if self.config.log_to_blockchain:
            self._blockchain_ledger = BlockchainLedger(self.config.blockchain_storage_path)

        # Initialize SIEM providers if enabled
        if self.config.log_to_siem:
            self._initialize_siem_providers()

    def get_layer(self) -> GuardrailLayer:
        return GuardrailLayer.AUDIT_LOG

    async def process(self, data: GuardrailInput, context: JSONDict) -> GuardrailResult:
        """Log the audit entry."""
        trace_id = context.get("trace_id", "")

        audit_entry = {
            "trace_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "layer": context.get("current_layer", "").value if context.get("current_layer") else "",
            "action": context.get("action", "").value if context.get("action") else "",
            "allowed": context.get("allowed", False),
            "violations": [v.to_dict() for v in context.get("violations", [])],
            "processing_time_ms": context.get("processing_time_ms", 0),
            "metadata": context.get("metadata", {}),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        if self.config.enabled:
            self._audit_entries.append(audit_entry)

            # OPTIMIZATION: Only serialize to string if we are actually going to log it to a stream
            # or if blockchain/SIEM is enabled. json.dumps is expensive in the hot path.
            if self.config.log_to_blockchain or self.config.log_to_siem:
                entry_json = json.dumps(audit_entry)
                logger.debug(f"Audit log entry: {entry_json}")

            # Future: Log to blockchain/SIEM
            if self.config.log_to_blockchain:
                await self._log_to_blockchain(audit_entry)
            if self.config.log_to_siem:
                await self._log_to_siem(audit_entry)

        return GuardrailResult(
            action=SafetyAction.ALLOW,
            allowed=True,
            trace_id=trace_id,
        )

    async def _log_to_blockchain(self, entry: JSONDict) -> None:
        """Log entry to blockchain for immutability.

        Creates a cryptographically linked block containing the audit entry,
        ensuring tamper-evident audit trails.
        """
        try:
            if self._blockchain_ledger is None:
                logger.warning("Blockchain logging enabled but ledger not initialized")
                return

            block = await self._blockchain_ledger.add_entry(entry)
            logger.info(
                f"Audit entry anchored to blockchain at block {block['index']} "
                f"with hash {block['hash'][:16]}..."
            )
        except _AUDIT_LOG_OPERATION_ERRORS as e:
            logger.error(f"Failed to anchor audit entry to blockchain: {e}")
            raise

    def _initialize_siem_providers(self) -> None:
        """Initialize SIEM providers from configuration.

        Creates provider instances based on the siem_providers config list.
        Each provider config should specify type, endpoint_url, and auth_token.
        """
        try:
            from .siem_providers import (
                SIEMProviderConfig,
                SIEMProviderType,
                create_siem_provider,
            )

            for provider_config in self.config.siem_providers:
                if not provider_config.get("enabled", True):
                    continue

                try:
                    # Validate required fields
                    provider_type_str = provider_config.get("provider_type", "")
                    endpoint_url = provider_config.get("endpoint_url", "")
                    auth_token = provider_config.get("auth_token", "")

                    if not all([provider_type_str, endpoint_url, auth_token]):
                        logger.warning(
                            f"SIEM provider config missing required fields: {provider_config}"
                        )
                        continue

                    # Create provider config
                    config = SIEMProviderConfig(
                        provider_type=SIEMProviderType(provider_type_str.lower()),
                        endpoint_url=endpoint_url,
                        auth_token=auth_token,
                        index=provider_config.get("index", "acgs2_audit"),
                        source_type=provider_config.get("source_type", "acgs2:audit"),
                        verify_ssl=provider_config.get("verify_ssl", True),
                        timeout_seconds=provider_config.get(
                            "timeout_seconds", self.config.siem_timeout_seconds
                        ),
                        max_retries=provider_config.get("max_retries", 3),
                        enabled=True,
                    )

                    # Create provider instance
                    provider = create_siem_provider(config)
                    self._siem_providers.append(provider)
                    logger.info(f"Initialized {provider_type_str} SIEM provider: {endpoint_url}")

                except _AUDIT_LOG_OPERATION_ERRORS as e:
                    logger.error(f"Failed to initialize SIEM provider: {e}")

            self._siem_metrics["providers_configured"] = len(self._siem_providers)

            if not self._siem_providers and self.config.log_to_siem:
                logger.warning(
                    "SIEM logging enabled but no valid providers configured. "
                    "Check siem_providers configuration."
                )

        except ImportError as e:
            logger.error(f"Failed to import SIEM providers module: {e}")

    async def _log_to_siem(self, entry: JSONDict) -> None:
        """Log entry to SIEM system.

        Ships audit events to configured SIEM providers (Splunk, Elasticsearch).
        Uses fire-and-forget pattern with retry logic for each provider.

        Args:
            entry: The audit entry to ship to SIEM

        Note:
            Errors are handled based on siem_fail_silent config:
            - True: Log errors but don't raise (fail open)
            - False: Raise exceptions on failure (fail closed)
        """
        if not self._siem_providers:
            logger.debug("No SIEM providers configured, skipping SIEM logging")
            return

        # Enrich entry with SIEM-specific metadata
        siem_entry = dict(entry)
        siem_entry["_siem"] = {
            "ingested_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "source": "acgs2_audit_log",
        }

        # Ship to all configured providers
        errors = []
        for provider in self._siem_providers:
            try:
                success = await provider.send_event(siem_entry)
                if success:
                    self._siem_metrics["events_sent"] += 1
                    logger.debug(f"Successfully sent audit entry to {provider.__class__.__name__}")
                else:
                    self._siem_metrics["events_failed"] += 1
                    error_msg = f"Failed to send to {provider.__class__.__name__}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

            except _AUDIT_LOG_OPERATION_ERRORS as e:
                self._siem_metrics["events_failed"] += 1
                error_msg = f"Exception sending to {provider.__class__.__name__}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Handle errors based on configuration
        if errors and not self.config.siem_fail_silent:
            raise RuntimeError(f"SIEM logging failed: {'; '.join(errors)}")

    def get_siem_metrics(self) -> JSONDict:
        """Get SIEM integration metrics.

        Returns:
            Dictionary containing SIEM metrics:
            - events_sent: Total events successfully sent
            - events_failed: Total events that failed
            - providers_configured: Number of configured providers
        """
        return dict(self._siem_metrics)

    async def health_check_siem(self) -> JSONDict:
        """Check health of all SIEM providers.

        Returns:
            Dictionary with health status for each provider
        """
        health_status = {}

        for i, provider in enumerate(self._siem_providers):
            provider_name = f"{provider.__class__.__name__}_{i}"
            try:
                if hasattr(provider, "health_check"):
                    health = await provider.health_check()
                    health_status[provider_name] = health
                else:
                    health_status[provider_name] = {
                        "status": "unknown",
                        "reason": "no health check",
                    }
            except _AUDIT_LOG_OPERATION_ERRORS as e:
                health_status[provider_name] = {"status": "unhealthy", "error": str(e)}

        return health_status

    async def get_metrics(self) -> JSONDict:
        """Get audit log metrics."""
        total_entries = len(self._audit_entries)
        if total_entries == 0:
            return {"total_entries": 0}

        # Calculate metrics
        allowed_count = sum(1 for entry in self._audit_entries if entry.get("allowed", False))
        violation_count = sum(len(entry.get("violations", [])) for entry in self._audit_entries)

        return {
            "total_entries": total_entries,
            "allowed_count": allowed_count,
            "blocked_count": total_entries - allowed_count,
            "allowed_rate": allowed_count / total_entries,
            "violation_rate": violation_count / total_entries,
            "avg_processing_time_ms": sum(
                entry.get("processing_time_ms", 0) for entry in self._audit_entries
            )
            / total_entries,
        }

    def get_entries(self, trace_id: str | None = None) -> list[JSONDict]:
        """Get audit entries, optionally filtered by trace ID."""
        if trace_id:
            return [entry for entry in self._audit_entries if entry.get("trace_id") == trace_id]
        return self._audit_entries.copy()

    def get_blockchain_entries(self) -> list[JSONDict]:
        """Get all blockchain ledger entries if blockchain logging is enabled."""
        if self._blockchain_ledger is None:
            return []
        return self._blockchain_ledger.blocks.copy()

    def verify_blockchain_integrity(self) -> bool:
        """Verify the integrity of the blockchain ledger."""
        if self._blockchain_ledger is None:
            return True
        return self._blockchain_ledger._verify_chain_integrity()

    def get_blockchain_stats(self) -> JSONDict:
        """Get statistics about the blockchain ledger."""
        if self._blockchain_ledger is None:
            return {"enabled": False, "block_count": 0}

        return {
            "enabled": True,
            "block_count": len(self._blockchain_ledger.blocks),
            "latest_block_index": self._blockchain_ledger.get_latest_block()["index"],
            "latest_block_hash": self._blockchain_ledger.get_latest_block()["hash"],
            "storage_path": self._blockchain_ledger.storage_path,
        }
