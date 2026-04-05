"""
ACGS-2 Deliberation Layer - Timeout Checker
Constitutional Hash: 608508a9bd224290

Background task to check election expiration and trigger escalation events.
"""

import asyncio
from datetime import UTC, datetime, timezone

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from .redis_election_store import get_election_store
except ImportError:
    get_election_store = None  # type: ignore[misc, assignment]

try:
    from .vote_models import VoteEventType
except ImportError:
    VoteEventType = None  # type: ignore[misc, assignment]

try:
    from enhanced_agent_bus._compat.config import settings
except ImportError:
    from enhanced_agent_bus._compat.config import settings  # type: ignore[import-untyped]

logger = get_logger(__name__)
_TIMEOUT_CHECKER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class TimeoutChecker:
    """
    Background task to check election expiration and trigger escalation.

    Runs every N seconds (configurable via settings.voting.timeout_check_interval_seconds),
    scans Redis for expired elections, marks them as EXPIRED, sets result=DENY,
    and publishes escalation events to Kafka audit topic.
    """

    def __init__(self, kafka_bus: object | None = None):
        """
        Initialize timeout checker.

        Args:
            kafka_bus: Optional KafkaEventBus instance for publishing escalation events
        """
        self.kafka_bus = kafka_bus
        self._running = False
        self._task: asyncio.Task | None = None
        self.check_interval = settings.voting.timeout_check_interval_seconds

    async def start(self) -> None:
        """Start the timeout checker background task."""
        if self._running:
            logger.warning("TimeoutChecker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(f"TimeoutChecker started (check interval: {self.check_interval}s)")

    async def stop(self) -> None:
        """Stop the timeout checker background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TimeoutChecker stopped")

    async def _check_loop(self) -> None:
        """Main loop for checking election expiration."""
        while self._running:
            try:
                await self._check_expired_elections()
            except _TIMEOUT_CHECKER_ERRORS as e:
                logger.error(f"Error in timeout checker loop: {e}")

            # Wait for next check interval
            await asyncio.sleep(self.check_interval)

    async def _check_expired_elections(self) -> None:
        """Check for expired elections and trigger escalation."""
        election_store = await get_election_store()
        if not election_store:
            return

        try:
            # Scan for all elections
            election_ids = await election_store.scan_elections()
            current_time = datetime.now(UTC)

            for election_id in election_ids:
                try:
                    election_data = await election_store.get_election(election_id)
                    if not election_data:
                        continue

                    status = election_data.get("status", "OPEN")
                    if status != "OPEN":
                        continue  # Already resolved or expired

                    expires_at_str = election_data.get("expires_at")
                    if not expires_at_str:
                        continue

                    # Parse expires_at
                    if isinstance(expires_at_str, str):
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    else:
                        expires_at = expires_at_str

                    # Check if expired
                    if current_time > expires_at:
                        await self._handle_expired_election(election_id, election_data)
                except _TIMEOUT_CHECKER_ERRORS as e:
                    logger.error(f"Error checking election {election_id}: {e}")
        except _TIMEOUT_CHECKER_ERRORS as e:
            logger.error(f"Error scanning elections: {e}")

    async def _handle_expired_election(self, election_id: str, election_data: dict) -> None:
        """Handle an expired election: mark as EXPIRED, set result=DENY, publish escalation event."""
        election_store = await get_election_store()
        if not election_store:
            return

        try:
            # Update status to EXPIRED
            await election_store.update_election_status(election_id, "EXPIRED")

            # Update election data with result
            election_data["status"] = "EXPIRED"
            election_data["result"] = "DENY"
            election_data["expired_at"] = datetime.now(UTC).isoformat()

            # Save updated election
            ttl = settings.voting.default_timeout_seconds
            await election_store.save_election(election_id, election_data, ttl)

            logger.info(f"Election {election_id} expired and marked as DENY")

            # Publish escalation event to Kafka audit topic
            if self.kafka_bus:
                await self._publish_escalation_event(election_id, election_data)
        except _TIMEOUT_CHECKER_ERRORS as e:
            logger.error(f"Error handling expired election {election_id}: {e}")

    async def _publish_escalation_event(self, election_id: str, election_data: dict) -> None:
        """Publish escalation event to Kafka audit topic."""
        try:
            tenant_id = election_data.get("tenant_id", "default")
            message_id = election_data.get("message_id", "")
            expires_at_str = election_data.get("expires_at", "")

            # Calculate timeout duration
            timeout_seconds = settings.voting.default_timeout_seconds
            if expires_at_str:
                try:
                    if isinstance(expires_at_str, str):
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    else:
                        expires_at = expires_at_str
                    created_at_str = election_data.get("created_at", "")
                    if created_at_str:
                        if isinstance(created_at_str, str):
                            created_at = datetime.fromisoformat(
                                created_at_str.replace("Z", "+00:00")
                            )
                        else:
                            created_at = created_at_str
                        timeout_seconds = int((expires_at - created_at).total_seconds())
                except (ValueError, TypeError):
                    pass

            escalation_event = {
                "election_id": election_id,
                "message_id": message_id,
                "timeout_seconds": timeout_seconds,
                "escalation_reason": "election_timeout",
                "escalated_at": datetime.now(UTC).isoformat(),
            }

            # Create audit record
            from .audit_signature import sign_audit_record

            signature_key = settings.voting.audit_signature_key
            if signature_key:
                signature = sign_audit_record(escalation_event, signature_key.get_secret_value())
            else:
                signature = ""

            audit_record = {
                "event_type": (
                    VoteEventType.ESCALATION_TRIGGERED.value
                    if VoteEventType
                    else "escalation_triggered"
                ),
                "election_id": election_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "signature": signature,
                "payload": escalation_event,
            }

            await self.kafka_bus.publish_audit_record(tenant_id, audit_record)

        except _TIMEOUT_CHECKER_ERRORS as e:
            logger.error(f"Failed to publish escalation event: {e}")
