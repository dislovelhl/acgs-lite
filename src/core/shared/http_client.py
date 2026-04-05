"""
HTTP Client for ACGS-2
Constitutional Hash: 608508a9bd224290

Standardized HTTP client with configured timeouts, retry integration, and circuit breaker support.
Replaces scattered requests/aiohttp usage across the codebase.
"""

import asyncio
import time
from types import TracebackType

import httpx

from src.core.shared.errors.exceptions import ServiceUnavailableError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

from .errors.retry import RetryBudget, exponential_backoff

logger = get_logger(__name__)


class _AsyncCircuitBreaker:
    """Async circuit breaker for the HTTP client's internal use.

    For standalone circuit breaker usage outside of HttpClient, use
    ``src.core.shared.errors.circuit_breaker.SimpleCircuitBreaker`` or the
    ``@circuit_breaker`` decorator instead.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._state = "closed"
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def _now() -> float:
        """Return monotonic event-loop time, with process fallback."""
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return time.monotonic()

    async def allow_request(self) -> bool:
        """Check if request is allowed based on circuit state."""
        async with self._lock:
            if self._state == "closed":
                return True
            elif self._state == "open":
                if self._now() - self._last_failure_time >= self._recovery_timeout:
                    self._state = "half_open"
                    self._success_count = 0
                    logger.info("Circuit breaker transitioning to half-open")
                    return True
                return False
            elif self._state == "half_open":
                return True
            return True

    async def record_success(self) -> None:
        """Record a successful request."""
        async with self._lock:
            if self._state == "half_open":
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    self._state = "closed"
                    self._failure_count = 0
                    logger.info("Circuit breaker closed after recovery")
            elif self._state == "closed":
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed request."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = self._now()

            if self._state == "half_open":
                self._state = "open"
                logger.warning("Circuit breaker reopened after failed recovery attempt")
            elif self._state == "closed":
                if self._failure_count >= self._failure_threshold:
                    self._state = "open"
                    logger.warning(
                        "Circuit breaker opened",
                        extra={"failure_count": self._failure_count},
                    )

    def get_state(self) -> str:
        """Get current circuit state."""
        return self._state


class HttpClient:
    """
    Standardized async HTTP client with resilience features.

    Features:
    - Configured timeouts (connect, read, write, pool)
    - Automatic retry with exponential backoff
    - Circuit breaker for cascading failure prevention
    - Connection pooling with limits
    - Request/response logging

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        timeout: float = 30.0,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        write_timeout: float | None = None,
        pool_timeout: float | None = None,
        max_retries: int = 3,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        enable_circuit_breaker: bool = True,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: float = 60.0,
        retry_budget: RetryBudget | None = None,
        headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
    ):
        """
        Initialize HTTP client.

        Args:
            timeout: Overall timeout in seconds (default: 30.0)
            connect_timeout: Connection timeout in seconds
            read_timeout: Read timeout in seconds
            write_timeout: Write timeout in seconds
            pool_timeout: Pool acquisition timeout in seconds
            max_retries: Maximum retry attempts (default: 3)
            max_connections: Maximum connection pool size (default: 100)
            max_keepalive_connections: Maximum keepalive connections (default: 20)
            enable_circuit_breaker: Enable circuit breaker (default: True)
            circuit_breaker_threshold: Failures before opening circuit
            circuit_breaker_timeout: Recovery timeout in seconds
            retry_budget: Optional RetryBudget for rate limiting
            headers: Default headers for all requests
            verify_ssl: Verify SSL certificates (default: True)
        """
        self.timeout = httpx.Timeout(
            timeout=timeout,
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        )
        self.max_retries = max_retries
        self._enable_circuit_breaker = enable_circuit_breaker
        self._circuit_breaker = (
            _AsyncCircuitBreaker(
                failure_threshold=circuit_breaker_threshold,
                recovery_timeout=circuit_breaker_timeout,
            )
            if enable_circuit_breaker
            else None
        )
        self._retry_budget = retry_budget
        self._default_headers = headers or {}
        self._verify_ssl = verify_ssl

        self._client: httpx.AsyncClient | None = None
        self._client_kwargs: JSONDict = {
            "timeout": self.timeout,
            "limits": httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
            "verify": verify_ssl,
        }

    async def __aenter__(self):
        """Enter context manager."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager."""
        await self.close()

    async def start(self) -> None:
        """Start HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(**self._client_kwargs)
            logger.info("HTTP client started")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client closed")

    async def get(
        self,
        url: str,
        params: JSONDict | None = None,
        headers: dict[str, str] | None = None,
        retry_on_failure: bool = True,
    ) -> httpx.Response:
        """
        Perform GET request with retry and circuit breaker.

        Args:
            url: Request URL
            params: Query parameters
            headers: Request headers (merged with defaults)
            retry_on_failure: Enable retry on failure (default: True)

        Returns:
            httpx.Response
        """
        return await self.request(
            "GET",
            url,
            params=params,
            headers=headers,
            retry_on_failure=retry_on_failure,
        )

    async def post(
        self,
        url: str,
        json: JSONDict | None = None,
        data: bytes | str | JSONDict | None = None,
        headers: dict[str, str] | None = None,
        retry_on_failure: bool = True,
    ) -> httpx.Response:
        """
        Perform POST request with retry and circuit breaker.

        Args:
            url: Request URL
            json: JSON body
            data: Request body (non-JSON)
            headers: Request headers (merged with defaults)
            retry_on_failure: Enable retry on failure (default: True)

        Returns:
            httpx.Response
        """
        return await self.request(
            "POST",
            url,
            json=json,
            data=data,
            headers=headers,
            retry_on_failure=retry_on_failure,
        )

    async def put(
        self,
        url: str,
        json: JSONDict | None = None,
        data: bytes | str | JSONDict | None = None,
        headers: dict[str, str] | None = None,
        retry_on_failure: bool = True,
    ) -> httpx.Response:
        """Perform PUT request."""
        return await self.request(
            "PUT",
            url,
            json=json,
            data=data,
            headers=headers,
            retry_on_failure=retry_on_failure,
        )

    async def delete(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        retry_on_failure: bool = True,
    ) -> httpx.Response:
        """Perform DELETE request."""
        return await self.request(
            "DELETE",
            url,
            headers=headers,
            retry_on_failure=retry_on_failure,
        )

    async def request(
        self,
        method: str,
        url: str,
        params: JSONDict | None = None,
        json: JSONDict | None = None,
        data: bytes | str | JSONDict | None = None,
        headers: dict[str, str] | None = None,
        retry_on_failure: bool = True,
    ) -> httpx.Response:
        """
        Perform HTTP request with retry and circuit breaker.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            url: Request URL
            params: Query parameters
            json: JSON body
            data: Request body (non-JSON)
            headers: Request headers (merged with defaults)
            retry_on_failure: Enable retry on failure (default: True)

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPError: If request fails after retries or circuit breaker is open
        """
        if not self._client:
            await self.start()

        merged_headers = {**self._default_headers, **(headers or {})}

        # Check circuit breaker
        if self._enable_circuit_breaker and self._circuit_breaker:
            if not await self._circuit_breaker.allow_request():
                raise httpx.ConnectError("Circuit breaker is open")

        # Check retry budget
        if self._retry_budget and retry_on_failure:
            if not await self._retry_budget.can_retry():
                raise httpx.ConnectError("Retry budget exhausted")
            await self._retry_budget.record_retry()

        # Perform request with retry
        if retry_on_failure:
            return await self._request_with_retry(
                method,
                url,
                params=params,
                json=json,
                data=data,
                headers=merged_headers,
            )
        else:
            return await self._do_request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                headers=merged_headers,
            )

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        params: JSONDict | None = None,
        json: JSONDict | None = None,
        data: bytes | str | JSONDict | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """
        Perform request with exponential backoff retry.

        Args:
            method: HTTP method
            url: Request URL
            params: Query parameters
            json: JSON body
            data: Request body
            headers: Request headers

        Returns:
            httpx.Response
        """
        last_exception: Exception | None = None

        async for delay in exponential_backoff(max_attempts=self.max_retries):
            try:
                response = await self._do_request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=data,
                    headers=headers,
                )

                # Record success on circuit breaker
                if self._enable_circuit_breaker and self._circuit_breaker:
                    await self._circuit_breaker.record_success()

                return response

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                logger.warning(
                    "Request failed, retrying",
                    extra={"error": str(e), "retry_delay_s": round(delay, 2)},
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        if self._enable_circuit_breaker and self._circuit_breaker:
            await self._circuit_breaker.record_failure()

        raise last_exception if last_exception else httpx.HTTPError("Request failed")

    async def _do_request(
        self,
        method: str,
        url: str,
        params: JSONDict | None = None,
        json: JSONDict | None = None,
        data: bytes | str | JSONDict | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """
        Perform actual HTTP request.

        Args:
            method: HTTP method
            url: Request URL
            params: Query parameters
            json: JSON body
            data: Request body
            headers: Request headers

        Returns:
            httpx.Response
        """
        if self._client is None:
            raise ServiceUnavailableError(
                "HTTP client is not initialized",
                error_code="HTTP_CLIENT_NOT_INITIALIZED",
            )

        response = await self._client.request(
            method,
            url,
            params=params,
            json=json,
            data=data,
            headers=headers,
        )

        response.raise_for_status()
        return response

    def get_circuit_breaker_state(self) -> str | None:
        """Get circuit breaker state."""
        if self._circuit_breaker:
            return self._circuit_breaker.get_state()
        return None
