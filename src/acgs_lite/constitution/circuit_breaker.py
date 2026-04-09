"""exp191: GovernanceCircuitBreaker — cascading failure prevention.

Circuit breaker for governance validation pipelines.  When a downstream
validator fails repeatedly the circuit opens, returning a configurable
fallback decision instead of propagating errors.  After a recovery timeout
the circuit enters half-open state to probe recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class FallbackPolicy(Enum):
    DENY = "deny"
    ALLOW = "allow"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class CircuitEvent:
    state_from: CircuitState
    state_to: CircuitState
    reason: str
    timestamp: datetime
    failure_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_from": self.state_from.value,
            "state_to": self.state_to.value,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "failure_count": self.failure_count,
        }


@dataclass
class CircuitBreakerPolicy:
    failure_threshold: int = 5
    recovery_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=30))
    half_open_max_calls: int = 3
    fallback: FallbackPolicy = FallbackPolicy.DENY
    success_threshold: int = 2


class GovernanceCircuitBreaker:
    """Circuit breaker for governance validation pipelines.

    Example::

        cb = GovernanceCircuitBreaker(CircuitBreakerPolicy(failure_threshold=3))
        cb.record_failure("timeout from OPA")
        cb.record_failure("timeout from OPA")
        cb.record_failure("timeout from OPA")
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()
    """

    def __init__(self, policy: CircuitBreakerPolicy | None = None) -> None:
        self._policy = policy or CircuitBreakerPolicy()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_at: datetime | None = None
        self._opened_at: datetime | None = None
        self._events: list[CircuitEvent] = []
        self._total_failures = 0
        self._total_successes = 0
        self._total_rejections = 0

    @property
    def state(self) -> CircuitState:
        self._check_recovery()
        return self._state

    @property
    def policy(self) -> CircuitBreakerPolicy:
        return self._policy

    def allow_request(self) -> bool:
        """Check whether a request should be allowed through."""
        self._check_recovery()

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self._policy.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        self._total_rejections += 1
        return False

    def record_success(self) -> None:
        """Record a successful governance call."""
        self._total_successes += 1

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._policy.success_threshold:
                self._transition(CircuitState.CLOSED, "recovery confirmed")
                self._failure_count = 0
                self._success_count = 0
                self._half_open_calls = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self, reason: str = "") -> None:
        """Record a governance call failure."""
        now = datetime.now(timezone.utc)
        self._total_failures += 1
        self._last_failure_at = now

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN, reason or "half-open probe failed")
            self._opened_at = now
            self._success_count = 0
            self._half_open_calls = 0
            return

        if self._state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self._policy.failure_threshold:
                self._transition(CircuitState.OPEN, reason or "failure threshold reached")
                self._opened_at = now

    def fallback_decision(self) -> str:
        """Return the fallback decision when circuit is open."""
        return self._policy.fallback.value

    def reset(self) -> None:
        """Force-reset to closed state."""
        if self._state != CircuitState.CLOSED:
            self._transition(CircuitState.CLOSED, "manual reset")
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0

    def summary(self) -> dict[str, Any]:
        self._check_recovery()
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "total_rejections": self._total_rejections,
            "last_failure_at": self._last_failure_at.isoformat() if self._last_failure_at else None,
            "opened_at": self._opened_at.isoformat() if self._opened_at else None,
            "events": len(self._events),
            "policy": {
                "failure_threshold": self._policy.failure_threshold,
                "recovery_timeout_seconds": int(self._policy.recovery_timeout.total_seconds()),
                "half_open_max_calls": self._policy.half_open_max_calls,
                "fallback": self._policy.fallback.value,
                "success_threshold": self._policy.success_threshold,
            },
        }

    def history(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]

    def _check_recovery(self) -> None:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return
        now = datetime.now(timezone.utc)
        if now >= self._opened_at + self._policy.recovery_timeout:
            self._transition(CircuitState.HALF_OPEN, "recovery timeout elapsed")
            self._half_open_calls = 0
            self._success_count = 0

    def _transition(self, new_state: CircuitState, reason: str) -> None:
        event = CircuitEvent(
            state_from=self._state,
            state_to=new_state,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
            failure_count=self._failure_count,
        )
        self._events.append(event)
        self._state = new_state
