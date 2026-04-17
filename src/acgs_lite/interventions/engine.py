"""InterventionEngine — evaluates rules and fires handlers.

Constitutional Hash: 608508a9bd224290

Note: Throttle and cool-off state is in-memory and not thread-safe.
Intended for single-process use only.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

from acgs_lite.cdp.record import InterventionOutcome
from acgs_lite.interventions.actions import InterventionAction, InterventionRule
from acgs_lite.interventions.conditions import evaluate_condition

logger = logging.getLogger(__name__)


class InterventionEngine:
    """Evaluates intervention rules against a CDP record and fires handlers.

    Rules are evaluated in priority order (ascending). Each matching rule
    produces an InterventionOutcome. Handler failures are caught and logged —
    they never change the original verdict.

    Attributes:
        rules: Ordered list of InterventionRules.
        _throttle_state: In-memory {key: (count, window_start)} for THROTTLE.
        _cooloff_state: In-memory {key: unlock_at_timestamp} for COOL_OFF.
        _webhook_url: Optional webhook URL for NOTIFY action.
    """

    def __init__(
        self,
        rules: list[InterventionRule] | None = None,
        webhook_url: str | None = None,
        quarantine: Any | None = None,
    ) -> None:
        import threading

        self.rules: list[InterventionRule] = sorted((rules or []), key=lambda r: r.priority)
        self._throttle_state: dict[str, tuple[int, float]] = {}
        self._cooloff_state: dict[str, float] = {}
        self._state_lock = threading.Lock()
        self._webhook_url = webhook_url
        self._quarantine = quarantine

    def add_rule(self, rule: InterventionRule) -> None:
        """Add a rule and re-sort by priority."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)

    def evaluate(self, cdp_record_dict: dict[str, Any]) -> list[InterventionOutcome]:
        """Evaluate all rules against a CDP record.

        GovernanceHaltError raised by BLOCK rules is re-raised immediately and
        terminates evaluation. All other handler failures are caught and
        converted to a non-triggered outcome — they never propagate to callers.

        Args:
            cdp_record_dict: The CDP record as a plain dict (from to_dict()).

        Returns:
            List of InterventionOutcome for each rule processed (triggered or not).
        """
        from acgs_lite.circuit_breaker import GovernanceHaltError

        outcomes: list[InterventionOutcome] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            try:
                if evaluate_condition(rule.condition, cdp_record_dict):
                    outcome = self._fire(rule, cdp_record_dict)
                    outcomes.append(outcome)
            except GovernanceHaltError:
                raise  # BLOCK must propagate
            except Exception as exc:
                logger.warning("Intervention rule %s failed: %s", rule.rule_id, type(exc).__name__)
                outcomes.append(
                    InterventionOutcome(
                        action=rule.action.value,
                        triggered=False,
                        reason=f"handler_error: {type(exc).__name__}",
                        metadata={"rule_id": rule.rule_id},
                    )
                )
        return outcomes

    def is_cooled_off(self, key: str) -> bool:
        """Return True if key is currently in a cool-off period."""
        with self._state_lock:
            unlock_at = self._cooloff_state.get(key)
        if unlock_at is None:
            return False
        return time.time() < unlock_at

    def _fire(self, rule: InterventionRule, cdp_record: dict[str, Any]) -> InterventionOutcome:
        """Fire the appropriate handler for a matched rule."""
        action = rule.action
        subject_id = cdp_record.get("subject_id", "unknown")

        if action == InterventionAction.BLOCK:
            return self._handle_block(rule, cdp_record)
        elif action == InterventionAction.THROTTLE:
            return self._handle_throttle(rule, subject_id)
        elif action == InterventionAction.NOTIFY:
            return self._handle_notify(rule, cdp_record)
        elif action == InterventionAction.ESCALATE:
            return self._handle_escalate(rule, cdp_record)
        elif action == InterventionAction.COOL_OFF:
            return self._handle_cool_off(rule, subject_id)
        else:  # LOG_ONLY
            return InterventionOutcome(
                action=action.value,
                triggered=True,
                reason=f"rule:{rule.rule_id}",
                metadata={},
            )

    def _handle_block(
        self, rule: InterventionRule, cdp_record: dict[str, Any]
    ) -> InterventionOutcome:
        """BLOCK: raise GovernanceHaltError."""
        from acgs_lite.circuit_breaker import GovernanceHaltError

        raise GovernanceHaltError(
            system_id=cdp_record.get("subject_id", "unknown"),
            reason=f"Intervention BLOCK triggered by rule '{rule.rule_id}': {rule.name}",
        )

    def _handle_throttle(self, rule: InterventionRule, subject_id: str) -> InterventionOutcome:
        """THROTTLE: in-memory sliding window rate limiter (thread-safe)."""
        window_seconds: float = float(rule.metadata.get("window_seconds", 60))
        max_requests: int = int(rule.metadata.get("max_requests", 10))
        key = f"{rule.rule_id}:{subject_id}"
        now = time.time()
        with self._state_lock:
            count, window_start = self._throttle_state.get(key, (0, now))
            if now - window_start > window_seconds:
                count, window_start = 0, now
            count += 1
            self._throttle_state[key] = (count, window_start)
        triggered = count > max_requests
        return InterventionOutcome(
            action="throttle",
            triggered=triggered,
            reason=f"rate:{count}/{max_requests} in {window_seconds}s" if triggered else "",
            metadata={"count": count, "max": max_requests},
        )

    def _handle_notify(
        self, rule: InterventionRule, cdp_record: dict[str, Any]
    ) -> InterventionOutcome:
        """NOTIFY: fire webhook if configured."""
        url = self._webhook_url or rule.metadata.get("webhook_url")
        if not url:
            return InterventionOutcome(
                action="notify", triggered=False, reason="no_webhook_url", metadata={}
            )
        payload = json.dumps(
            {
                "rule_id": rule.rule_id,
                "cdp_id": cdp_record.get("cdp_id"),
                "verdict": cdp_record.get("verdict"),
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
        return InterventionOutcome(
            action="notify",
            triggered=True,
            reason=f"webhook_status:{status}",
            metadata={"status": status},
        )

    def _handle_escalate(
        self, rule: InterventionRule, cdp_record: dict[str, Any]
    ) -> InterventionOutcome:
        """ESCALATE: mark as requiring review and submit to quarantine if configured."""
        metadata: dict[str, Any] = {"requires_review": True}
        if self._quarantine is not None:
            try:
                item = self._quarantine.submit(
                    action=str(cdp_record.get("action", "")),
                    reason=f"intervention:{rule.rule_id}",
                    sphere=str(cdp_record.get("domain", "")),
                    risk_score=float(cdp_record.get("risk_score", 0.0)),
                    severity=str(cdp_record.get("severity", "")),
                    agent_id=str(cdp_record.get("subject_id", "")),
                    timeout_at=str(rule.metadata.get("timeout_at", "")),
                    timeout_policy=rule.metadata.get("timeout_policy"),
                    metadata={"cdp_id": cdp_record.get("cdp_id"), "rule_id": rule.rule_id},
                )
                metadata["quarantine_id"] = item.quarantine_id
            except Exception as exc:
                logger.error(
                    "Quarantine submit failed for rule %s: %s",
                    rule.rule_id,
                    type(exc).__name__,
                    exc_info=True,
                )
                metadata["quarantine_error"] = type(exc).__name__
        return InterventionOutcome(
            action="escalate",
            triggered=True,
            reason=f"rule:{rule.rule_id}",
            metadata=metadata,
        )

    def _handle_cool_off(self, rule: InterventionRule, subject_id: str) -> InterventionOutcome:
        """COOL_OFF: set time-based lockout (thread-safe)."""
        duration_seconds: float = float(rule.metadata.get("duration_seconds", 86400))  # 24h
        key = f"{rule.rule_id}:{subject_id}"
        unlock_at = time.time() + duration_seconds
        with self._state_lock:
            self._cooloff_state[key] = unlock_at
        return InterventionOutcome(
            action="cool_off",
            triggered=True,
            reason=f"locked until {unlock_at:.0f}",
            metadata={"unlock_at": unlock_at, "duration_seconds": duration_seconds},
        )
