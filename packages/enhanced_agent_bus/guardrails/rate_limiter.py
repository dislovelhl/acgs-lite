"""
Rate Limiter Guardrail Component.

Implements OWASP DoS protection through request rate limiting using a
token bucket algorithm with blacklist/whitelist support.

Constitutional Hash: 608508a9bd224290
"""

import time
from dataclasses import dataclass, field

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .base import GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction, ViolationSeverity
from .models import GuardrailResult, Violation


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiter (OWASP DoS protection)."""

    enabled: bool = True
    requests_per_minute: int = 1000
    burst_limit: int = 200
    window_seconds: int = 60
    block_duration_seconds: int = 300  # 5 minutes
    whitelist: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)


class RateLimiter(GuardrailComponent):
    """Rate Limiter: OWASP DoS protection layer.

    .. deprecated::
        Use ``src.core.shared.security.rate_limiter.SlidingWindowRateLimiter`` (or
        ``RateLimitMiddleware``) instead.
        This local implementation in the agent bus guardrails layer exists for
        historical reasons and is not maintained as the canonical version.

    Prevents abuse through request rate limiting using token bucket algorithm.
    Supports whitelisting trusted clients and blacklisting abusive ones.
    """

    def __init__(self, config: RateLimiterConfig | None = None):
        self.config = config or RateLimiterConfig()
        # Simple in-memory rate limiting (use Redis in production)
        self._request_counts: dict[str, list[float]] = {}
        self._blocked_until: dict[str, float] = {}

    def reset(self):
        """Reset rate limiter state for testing."""
        self._request_counts.clear()
        self._blocked_until.clear()

    def get_layer(self) -> GuardrailLayer:
        return GuardrailLayer.RATE_LIMITER

    async def process(self, data: GuardrailInput, context: JSONDict) -> GuardrailResult:
        """Apply rate limiting to the request."""
        start_time = time.monotonic()
        trace_id = context.get("trace_id", "")

        # Extract client identifier (IP, user ID, API key, etc.)
        client_id = self._extract_client_id(context)

        # Check whitelist/blacklist first
        if client_id in self.config.blacklist:
            return GuardrailResult(
                action=SafetyAction.BLOCK,
                allowed=False,
                violations=[
                    Violation(
                        layer=self.get_layer(),
                        violation_type="blacklisted_client",
                        severity=ViolationSeverity.CRITICAL,
                        message=f"Client {client_id} is blacklisted",
                        trace_id=trace_id,
                    )
                ],
                processing_time_ms=(time.monotonic() - start_time) * 1000,
                trace_id=trace_id,
            )

        if client_id in self.config.whitelist:
            return GuardrailResult(
                action=SafetyAction.ALLOW,
                allowed=True,
                processing_time_ms=(time.monotonic() - start_time) * 1000,
                trace_id=trace_id,
            )

        # Check if client is currently blocked
        current_time = time.time()
        if client_id in self._blocked_until:
            if current_time < self._blocked_until[client_id]:
                return GuardrailResult(
                    action=SafetyAction.BLOCK,
                    allowed=False,
                    violations=[
                        Violation(
                            layer=self.get_layer(),
                            violation_type="rate_limit_blocked",
                            severity=ViolationSeverity.HIGH,
                            message=f"Client {client_id} is rate limited until {self._blocked_until[client_id]}",
                            trace_id=trace_id,
                        )
                    ],
                    processing_time_ms=(time.monotonic() - start_time) * 1000,
                    trace_id=trace_id,
                )
            else:
                # Block period expired, remove from blocked list
                del self._blocked_until[client_id]

        # Apply token bucket rate limiting
        if self._is_rate_limited(client_id, current_time):
            # Add to blocked list
            self._blocked_until[client_id] = current_time + self.config.block_duration_seconds

            return GuardrailResult(
                action=SafetyAction.BLOCK,
                allowed=False,
                violations=[
                    Violation(
                        layer=self.get_layer(),
                        violation_type="rate_limit_exceeded",
                        severity=ViolationSeverity.MEDIUM,
                        message=f"Rate limit exceeded for client {client_id}",
                        trace_id=trace_id,
                    )
                ],
                processing_time_ms=(time.monotonic() - start_time) * 1000,
                trace_id=trace_id,
            )

        return GuardrailResult(
            action=SafetyAction.ALLOW,
            allowed=True,
            processing_time_ms=(time.monotonic() - start_time) * 1000,
            trace_id=trace_id,
        )

    def _extract_client_id(self, context: JSONDict) -> str:
        """Extract client identifier from request context."""
        # Priority order: API key > User ID > IP address > session ID
        client_id = (
            context.get("api_key")
            or context.get("user_id")
            or context.get("ip_address")
            or context.get("session_id")
            or "anonymous"
        )
        return str(client_id)

    def _is_rate_limited(self, client_id: str, current_time: float) -> bool:
        """Check if client has exceeded rate limits using token bucket algorithm."""
        if client_id not in self._request_counts:
            self._request_counts[client_id] = []

        request_times = self._request_counts[client_id]

        # Remove requests outside the time window
        window_start = current_time - self.config.window_seconds
        request_times[:] = [t for t in request_times if t > window_start]

        # Check burst limit (requests in very short time)
        recent_requests = [t for t in request_times if t > current_time - 1.0]  # Last second
        if len(recent_requests) >= self.config.burst_limit:
            return True

        # Check sustained rate limit
        if len(request_times) >= self.config.requests_per_minute:
            return True

        # Add current request
        request_times.append(current_time)

        # Clean up old entries periodically
        if len(request_times) > self.config.requests_per_minute * 2:
            # Keep only recent entries
            cutoff = current_time - (self.config.window_seconds * 2)
            request_times[:] = [t for t in request_times if t > cutoff]

        return False
