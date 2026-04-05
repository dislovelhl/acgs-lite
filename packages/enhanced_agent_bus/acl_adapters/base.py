from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")


class AdapterState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AdapterError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "message": str(self),
            "constitutional_hash": self.constitutional_hash,
        }


class AdapterTimeoutError(AdapterError):
    def __init__(self, adapter_name: str, timeout_ms: int) -> None:
        self.adapter_name = adapter_name
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Adapter {adapter_name} timed out after {timeout_ms}ms [{CONSTITUTIONAL_HASH}]"
        )

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"adapter": self.adapter_name, "timeout_ms": self.timeout_ms})
        return data


class AdapterCircuitOpenError(AdapterError):
    def __init__(self, adapter_name: str, recovery_time_s: float) -> None:
        self.adapter_name = adapter_name
        self.recovery_time_s = recovery_time_s
        super().__init__(
            f"Adapter {adapter_name} circuit is open; recovery in {recovery_time_s:.1f}s [{CONSTITUTIONAL_HASH}]"
        )

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"adapter": self.adapter_name, "recovery_time_s": self.recovery_time_s})
        return data


class RateLimitExceededError(AdapterError):
    def __init__(self, adapter_name: str, limit_per_second: float) -> None:
        self.adapter_name = adapter_name
        self.limit_per_second = limit_per_second
        super().__init__(
            f"Adapter {adapter_name} rate limit exceeded at {limit_per_second}/s [{CONSTITUTIONAL_HASH}]"
        )

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"adapter": self.adapter_name, "limit_per_second": self.limit_per_second})
        return data


@dataclass(slots=True)
class AdapterConfig:
    timeout_ms: int = 5000
    connect_timeout_ms: int = 1000
    max_retries: int = 3
    retry_base_delay_ms: int = 100
    retry_max_delay_ms: int = 5000
    retry_exponential_base: float = 2.0
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_s: float = 30.0
    circuit_half_open_max_calls: int = 3
    rate_limit_per_second: float = 100.0
    rate_limit_burst: int = 10
    cache_enabled: bool = True
    cache_ttl_s: int = 300
    fallback_enabled: bool = True


@dataclass(slots=True)
class AdapterResult(Generic[ResponseT]):
    success: bool
    data: ResponseT | None = None
    latency_ms: float | None = None
    error: Exception | None = None
    from_cache: bool = False
    from_fallback: bool = False
    retry_count: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.success,
            "data": self.data,
            "latency_ms": self.latency_ms,
            "from_cache": self.from_cache,
            "from_fallback": self.from_fallback,
            "retry_count": self.retry_count,
            "constitutional_hash": self.constitutional_hash,
        }
        if self.error is not None:
            payload["error"] = str(self.error)
            payload["error_details"] = (
                self.error.to_dict()
                if hasattr(self.error, "to_dict")
                else {"error": type(self.error).__name__}
            )
        else:
            payload.pop("data", None)
            payload["data"] = self.data
        if self.error is None:
            payload.pop("error", None)
        return payload


class SimpleCircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 30.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_max_calls = half_open_max_calls
        self._state = AdapterState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None

    @property
    def state(self) -> AdapterState:
        if (
            self._state is AdapterState.OPEN
            and self._last_failure_time is not None
            and (time.monotonic() - self._last_failure_time) >= self.recovery_timeout_s
        ):
            self._state = AdapterState.HALF_OPEN
            self._success_count = 0
        return self._state

    @property
    def time_until_recovery(self) -> float:
        if self.state is not AdapterState.OPEN or self._last_failure_time is None:
            return 0.0
        remaining = self.recovery_timeout_s - (time.monotonic() - self._last_failure_time)
        return max(0.0, remaining)

    def record_success(self) -> None:
        current_state = self.state
        if current_state is AdapterState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self.reset()
            return
        if self._failure_count > 0:
            self._failure_count -= 1

    def record_failure(self) -> None:
        current_state = self.state
        if current_state is AdapterState.HALF_OPEN:
            self._state = AdapterState.OPEN
            self._last_failure_time = time.monotonic()
            self._success_count = 0
            return
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = AdapterState.OPEN
            self._last_failure_time = time.monotonic()

    def reset(self) -> None:
        self._state = AdapterState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class TokenBucketRateLimiter:
    def __init__(self, rate_per_second: float, burst: int) -> None:
        self.rate_per_second = rate_per_second
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._last_refill = now
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate_per_second)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class ACLAdapter(ABC, Generic[RequestT, ResponseT]):
    def __init__(self, name: str, config: AdapterConfig | None = None) -> None:
        self.name = name
        self.config = config or AdapterConfig()
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self.circuit_breaker = SimpleCircuitBreaker(
            failure_threshold=self.config.circuit_failure_threshold,
            recovery_timeout_s=self.config.circuit_recovery_timeout_s,
            half_open_max_calls=self.config.circuit_half_open_max_calls,
        )
        self.rate_limiter = TokenBucketRateLimiter(
            rate_per_second=self.config.rate_limit_per_second,
            burst=self.config.rate_limit_burst,
        )
        self._cache: dict[str, tuple[float, ResponseT]] = {}
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "cache_hits": 0,
            "fallback_uses": 0,
        }

    @abstractmethod
    async def _execute(self, request: RequestT) -> ResponseT:
        raise NotImplementedError

    @abstractmethod
    def _validate_response(self, response: ResponseT) -> bool:
        raise NotImplementedError

    @abstractmethod
    def _get_cache_key(self, request: RequestT) -> str:
        raise NotImplementedError

    def _get_fallback_response(self, request: RequestT) -> ResponseT | None:
        return None

    async def call(self, request: RequestT) -> AdapterResult[ResponseT]:
        started = time.perf_counter()
        self._metrics["total_calls"] += 1

        allowed = await self.rate_limiter.acquire()
        if not allowed:
            error = RateLimitExceededError(self.name, self.config.rate_limit_per_second)
            self._metrics["failed_calls"] += 1
            return AdapterResult(success=False, error=error, latency_ms=self._latency_ms(started))

        if self.circuit_breaker.state is AdapterState.OPEN:
            fallback = self._fallback_result(request, started)
            if fallback is not None:
                return fallback
            error = AdapterCircuitOpenError(self.name, self.circuit_breaker.time_until_recovery)
            self._metrics["failed_calls"] += 1
            return AdapterResult(success=False, error=error, latency_ms=self._latency_ms(started))

        cache_key = self._get_cache_key(request)
        if self.config.cache_enabled:
            cached = self._cache.get(cache_key)
            if cached is not None:
                cached_at, cached_value = cached
                if (time.monotonic() - cached_at) <= self.config.cache_ttl_s:
                    self._metrics["cache_hits"] += 1
                    return AdapterResult(
                        success=True,
                        data=cached_value,
                        latency_ms=self._latency_ms(started),
                        from_cache=True,
                    )
                self._cache.pop(cache_key, None)

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._execute(request),
                    timeout=self.config.timeout_ms / 1000,
                )
                if not self._validate_response(response):
                    raise ValueError(f"Invalid response from {self.name}")
                self.circuit_breaker.record_success()
                self._metrics["successful_calls"] += 1
                if self.config.cache_enabled:
                    self._cache[cache_key] = (time.monotonic(), response)
                return AdapterResult(
                    success=True,
                    data=response,
                    latency_ms=self._latency_ms(started),
                    retry_count=attempt,
                )
            except asyncio.TimeoutError:
                last_error = AdapterTimeoutError(self.name, self.config.timeout_ms)
            except Exception as exc:
                last_error = exc
            self.circuit_breaker.record_failure()
            if attempt < self.config.max_retries:
                delay_ms = min(
                    self.config.retry_max_delay_ms,
                    self.config.retry_base_delay_ms * (self.config.retry_exponential_base**attempt),
                )
                await asyncio.sleep(delay_ms / 1000)

        self._metrics["failed_calls"] += 1
        fallback = self._fallback_result(request, started, retry_count=self.config.max_retries)
        if fallback is not None:
            return fallback
        return AdapterResult(
            success=False,
            error=last_error,
            latency_ms=self._latency_ms(started),
            retry_count=self.config.max_retries,
        )

    def _fallback_result(
        self,
        request: RequestT,
        started: float,
        retry_count: int = 0,
    ) -> AdapterResult[ResponseT] | None:
        if not self.config.fallback_enabled:
            return None
        fallback = self._get_fallback_response(request)
        if fallback is None:
            return None
        self._metrics["fallback_uses"] += 1
        return AdapterResult(
            success=True,
            data=fallback,
            latency_ms=self._latency_ms(started),
            from_fallback=True,
            retry_count=retry_count,
        )

    def clear_cache(self) -> None:
        self._cache.clear()

    def reset_circuit_breaker(self) -> None:
        self.circuit_breaker.reset()

    def get_metrics(self) -> dict[str, Any]:
        total_calls = self._metrics["total_calls"]
        successful_calls = self._metrics["successful_calls"]
        return {
            "adapter_name": self.name,
            "constitutional_hash": self.constitutional_hash,
            **self._metrics,
            "success_rate": (successful_calls / total_calls) if total_calls else 0.0,
            "circuit_state": self.circuit_breaker.state.value,
        }

    def get_health(self) -> dict[str, Any]:
        return {
            "healthy": self.circuit_breaker.state is not AdapterState.OPEN,
            "adapter_name": self.name,
            "constitutional_hash": self.constitutional_hash,
            "state": self.circuit_breaker.state.value,
            "time_until_recovery": self.circuit_breaker.time_until_recovery,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    @staticmethod
    def _latency_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ACLAdapter",
    "AdapterCircuitOpenError",
    "AdapterConfig",
    "AdapterResult",
    "AdapterState",
    "AdapterTimeoutError",
    "RateLimitExceededError",
    "SimpleCircuitBreaker",
    "TokenBucketRateLimiter",
]
