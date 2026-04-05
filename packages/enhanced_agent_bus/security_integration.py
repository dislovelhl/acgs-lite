# Constitutional Hash: 608508a9bd224290
"""Security integration layer for Enhanced Agent Bus.

Bridges the OWASP Agentic AI security modules into the message processing
pipeline. Provides a unified SecurityGate that can be called from the
MessageProcessor's validation gates.

Integration points:
- Drift detection: records observations and checks for anomalies
- Payload integrity: validates HMAC signatures on message payloads
- Agent checksum: verifies ach JWT claim against expected agent builds
- Cert binding: validates certificate-bound tokens

Usage in MessageProcessor:
    gate = SecurityGate(drift_detector=detector)
    result = await gate.evaluate(msg, auth_context)
    if not result.passed:
        return ValidationResult(is_valid=False, reason=result.reason)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.structured_logging import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)


from enhanced_agent_bus.drift_detector import (
    DriftAlert,
    DriftDetector,
    DriftDetectorConfig,
)
from enhanced_agent_bus.models import AgentMessage

logger = get_logger(__name__)


@dataclass(frozen=True)
class SecurityGateResult:
    """Result of the security gate evaluation."""

    passed: bool
    reason: str | None = None
    drift_alerts: tuple[DriftAlert, ...] = ()
    payload_valid: bool = True
    checksum_valid: bool = True
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SecurityGate:
    """Unified security gate for the message processing pipeline.

    Evaluates messages against multiple security dimensions:
    1. Drift detection — flags agents with anomalous behavior patterns
    2. Payload integrity — validates HMAC signatures (when present)
    3. Agent checksum — validates ach claims (when expected checksums registered)

    The gate is fail-open for optional checks (drift detection logs warnings
    but does not block) and fail-closed for mandatory checks (payload integrity
    blocks on tampering).
    """

    def __init__(
        self,
        drift_detector: DriftDetector | None = None,
        drift_config: DriftDetectorConfig | None = None,
        block_on_drift: bool = False,
        payload_secret: str | None = None,
    ) -> None:
        self._drift = drift_detector or DriftDetector(config=drift_config or DriftDetectorConfig())
        self._block_on_drift = block_on_drift
        self._payload_secret = payload_secret
        self._agent_checksums: dict[str, str] = {}  # agent_id → expected checksum

    def register_agent_checksum(self, agent_id: str, checksum: str) -> None:
        """Register the expected checksum for an agent.

        Args:
            agent_id: Agent identifier.
            checksum: Expected SHA-256 agent checksum (ach claim value).
        """
        self._agent_checksums[agent_id] = checksum

    def deregister_agent_checksum(self, agent_id: str) -> None:
        """Remove a registered agent checksum."""
        self._agent_checksums.pop(agent_id, None)

    async def evaluate(
        self,
        msg: AgentMessage,
        impact_score: float | None = None,
        decision: str | None = None,
        consensus_vote: float | None = None,
        token_claims: dict | None = None,
    ) -> SecurityGateResult:
        """Evaluate a message through all security gates.

        Args:
            msg: The agent message being processed.
            impact_score: Impact score from the scorer (for drift tracking).
            decision: Decision made (APPROVED/BLOCKED) (for drift tracking).
            consensus_vote: MACI consensus vote (for drift tracking).
            token_claims: Decoded JWT claims (for checksum verification).

        Returns:
            SecurityGateResult with pass/fail and details.
        """
        agent_id = msg.from_agent
        tenant_id = getattr(msg, "tenant_id", "default")
        drift_alerts: list[DriftAlert] = []
        checksum_valid = True

        # --- 1. Record observation for drift tracking ---
        if impact_score is not None:
            self._drift.record_observation(
                agent_id=agent_id,
                tenant_id=tenant_id,
                impact_score=impact_score,
                decision=decision,
                consensus_vote=consensus_vote,
            )

        # --- 2. Check for drift anomalies ---
        alerts = self._drift.check_all(agent_id, tenant_id)
        if alerts:
            drift_alerts.extend(alerts)
            for alert in alerts:
                logger.warning(
                    "Drift alert detected",
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    drift_type=alert.drift_type.value,
                    severity=alert.severity,
                    description=alert.description,
                )

            if self._block_on_drift:
                return SecurityGateResult(
                    passed=False,
                    reason=f"Agent drift detected: {alerts[0].description}",
                    drift_alerts=tuple(drift_alerts),
                )

        # --- 3. Verify agent checksum (if registered) ---
        if token_claims and agent_id in self._agent_checksums:
            expected = self._agent_checksums[agent_id]
            actual = token_claims.get("ach")
            if actual is None:
                logger.warning(
                    "Agent checksum missing from token",
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                )
                checksum_valid = False
            elif not _constant_time_compare(actual, expected):
                logger.warning(
                    "Agent checksum mismatch",
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                )
                return SecurityGateResult(
                    passed=False,
                    reason="Agent code integrity check failed (ach mismatch)",
                    drift_alerts=tuple(drift_alerts),
                    checksum_valid=False,
                )

        # --- 4. Validate payload integrity (if secret configured) ---
        payload_valid = True
        if self._payload_secret:
            payload_valid = self._check_payload_integrity(msg)
            if not payload_valid:
                return SecurityGateResult(
                    passed=False,
                    reason="Payload integrity check failed (HMAC mismatch)",
                    drift_alerts=tuple(drift_alerts),
                    payload_valid=False,
                )

        return SecurityGateResult(
            passed=True,
            drift_alerts=tuple(drift_alerts),
            payload_valid=payload_valid,
            checksum_valid=checksum_valid,
        )

    def _check_payload_integrity(self, msg: AgentMessage) -> bool:
        """Verify HMAC signature on message payload."""
        if not self._payload_secret:
            return True

        payload_hmac = getattr(msg, "payload_hmac", None)
        if payload_hmac is None:
            # No HMAC present — pass (backward compatibility)
            return True

        try:
            from enhanced_agent_bus.payload_integrity import verify_payload

            payload_dict = {"content": msg.content}
            key = self._payload_secret.encode("utf-8")
            return bool(verify_payload(payload_dict, payload_hmac, key=key))
        except (ImportError, AttributeError):
            logger.warning("Payload integrity module not available")
            return True

    @property
    def drift_detector(self) -> DriftDetector:
        """Access the underlying drift detector."""
        return self._drift

    def get_stats(self) -> dict:
        """Get security gate statistics."""
        return {
            "drift_detector": self._drift.get_stats(),
            "registered_checksums": len(self._agent_checksums),
            "block_on_drift": self._block_on_drift,
            "payload_integrity_enabled": self._payload_secret is not None,
        }


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b, strict=True):
        result |= ord(x) ^ ord(y)
    return result == 0


__all__ = [
    "SecurityGate",
    "SecurityGateResult",
]
