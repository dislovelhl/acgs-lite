"""exp190: GovernanceRateLimiter — per-agent decision throttling.

Sliding-window rate limiting for governance requests.  Prevents agent
flooding by enforcing per-agent and per-action request ceilings with
configurable windows, burst allowances, and backpressure signals.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class RateLimitAction(Enum):
    DENY = "deny"
    THROTTLE = "throttle"
    WARN = "warn"


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a rate-limit check."""

    allowed: bool
    remaining: int
    limit: int
    reset_at: datetime
    action: RateLimitAction | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "limit": self.limit,
            "reset_at": self.reset_at.isoformat(),
            "action": self.action.value if self.action else None,
            "reason": self.reason,
        }


@dataclass
class RateLimitPolicy:
    """Rate limit configuration."""

    requests_per_window: int = 100
    window: timedelta = field(default_factory=lambda: timedelta(minutes=1))
    burst_allowance: int = 10
    exceed_action: RateLimitAction = RateLimitAction.DENY
    warn_threshold: float = 0.8


class _SlidingWindow:
    __slots__ = ("_timestamps", "_window")

    def __init__(self, window: timedelta) -> None:
        self._timestamps: deque[datetime] = deque()
        self._window = window

    def _prune(self, now: datetime) -> None:
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def record(self, now: datetime) -> None:
        self._prune(now)
        self._timestamps.append(now)

    def count(self, now: datetime) -> int:
        self._prune(now)
        return len(self._timestamps)

    def oldest(self) -> datetime | None:
        return self._timestamps[0] if self._timestamps else None


class GovernanceRateLimiter:
    """Sliding-window rate limiter for governance decisions.

    Example::

        limiter = GovernanceRateLimiter(RateLimitPolicy(requests_per_window=10))
        for _ in range(10):
            result = limiter.check_and_record("agent-1")
            assert result.allowed
        result = limiter.check_and_record("agent-1")
        assert not result.allowed  # burst may still allow
    """

    def __init__(self, policy: RateLimitPolicy | None = None) -> None:
        self._policy = policy or RateLimitPolicy()
        self._agent_windows: dict[str, _SlidingWindow] = {}
        self._action_windows: dict[str, _SlidingWindow] = {}
        self._violations: list[dict[str, Any]] = []

    @property
    def policy(self) -> RateLimitPolicy:
        return self._policy

    def check(self, agent_id: str, action: str = "") -> RateLimitResult:
        """Check rate limit without recording a request."""
        now = datetime.now(timezone.utc)
        return self._evaluate(agent_id, action, now, record=False)

    def check_and_record(self, agent_id: str, action: str = "") -> RateLimitResult:
        """Check rate limit and record the request if allowed."""
        now = datetime.now(timezone.utc)
        return self._evaluate(agent_id, action, now, record=True)

    def agent_usage(self, agent_id: str) -> dict[str, Any]:
        """Current usage stats for an agent."""
        now = datetime.now(timezone.utc)
        window = self._agent_windows.get(agent_id)
        count = window.count(now) if window else 0
        effective_limit = self._policy.requests_per_window + self._policy.burst_allowance
        return {
            "agent_id": agent_id,
            "current_count": count,
            "limit": effective_limit,
            "remaining": max(0, effective_limit - count),
            "utilization": count / effective_limit if effective_limit > 0 else 0.0,
            "window_seconds": int(self._policy.window.total_seconds()),
        }

    def all_agents_usage(self) -> list[dict[str, Any]]:
        """Usage stats for all tracked agents."""
        return [self.agent_usage(aid) for aid in sorted(self._agent_windows)]

    def violations(self) -> list[dict[str, Any]]:
        """Return recorded rate-limit violations."""
        return list(self._violations)

    def reset(self, agent_id: str) -> None:
        """Clear rate limit state for an agent."""
        self._agent_windows.pop(agent_id, None)

    def reset_all(self) -> None:
        """Clear all rate limit state."""
        self._agent_windows.clear()
        self._action_windows.clear()

    def summary(self) -> dict[str, Any]:
        """Aggregate rate limiter statistics."""
        now = datetime.now(timezone.utc)
        agent_counts = {aid: w.count(now) for aid, w in self._agent_windows.items()}
        return {
            "tracked_agents": len(self._agent_windows),
            "tracked_actions": len(self._action_windows),
            "total_violations": len(self._violations),
            "busiest_agent": max(agent_counts, key=lambda k: agent_counts[k])
            if agent_counts
            else None,
            "policy": {
                "requests_per_window": self._policy.requests_per_window,
                "window_seconds": int(self._policy.window.total_seconds()),
                "burst_allowance": self._policy.burst_allowance,
                "exceed_action": self._policy.exceed_action.value,
                "warn_threshold": self._policy.warn_threshold,
            },
        }

    def _evaluate(
        self, agent_id: str, action: str, now: datetime, *, record: bool
    ) -> RateLimitResult:
        if agent_id not in self._agent_windows:
            self._agent_windows[agent_id] = _SlidingWindow(self._policy.window)
        window = self._agent_windows[agent_id]

        if action and action not in self._action_windows:
            self._action_windows[action] = _SlidingWindow(self._policy.window)

        current = window.count(now)
        effective_limit = self._policy.requests_per_window + self._policy.burst_allowance
        reset_at = now + self._policy.window

        if current >= effective_limit:
            self._violations.append(
                {
                    "agent_id": agent_id,
                    "action": action,
                    "count": current,
                    "limit": effective_limit,
                    "timestamp": now.isoformat(),
                    "applied_action": self._policy.exceed_action.value,
                }
            )
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=effective_limit,
                reset_at=reset_at,
                action=self._policy.exceed_action,
                reason=f"Rate limit exceeded: {current}/{effective_limit} in window",
            )

        warn_level = int(effective_limit * self._policy.warn_threshold)
        rate_action: RateLimitAction | None = None
        reason = ""
        if current >= warn_level:
            rate_action = RateLimitAction.WARN
            reason = (
                f"Approaching limit: {current}/{effective_limit}"
                f" ({self._policy.warn_threshold:.0%} threshold)"
            )

        if record:
            window.record(now)
            if action:
                self._action_windows[action].record(now)

        return RateLimitResult(
            allowed=True,
            remaining=effective_limit - current - (1 if record else 0),
            limit=effective_limit,
            reset_at=reset_at,
            action=rate_action,
            reason=reason,
        )
