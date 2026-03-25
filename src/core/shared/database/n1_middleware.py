"""
ACGS-2 N+1 Query Detection Middleware
Constitutional Hash: 608508a9bd224290

Development middleware to detect N+1 query patterns in real-time.
Integrates with FastAPI to monitor query counts per request.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
# Context variable to track query count in request scope
_query_count: ContextVar[int] = ContextVar("query_count", default=0)
_queries_executed: ContextVar[list[str] | None] = ContextVar("queries_executed", default=None)
_n1_detection_enabled: ContextVar[bool] = ContextVar("n1_detection_enabled", default=False)


class N1Detector:
    """Query monitoring context manager for detecting N+1 patterns.

    Usage:
        detector = N1Detector()

        @app.middleware("http")
        async def detect_n1(request: Request, call_next):
            with detector.monitor(threshold=10):
                response = await call_next(request)
                detector.report_if_violation(request.url.path)
                return response
    """

    def __init__(self) -> None:
        self.threshold = 10
        self._query_times: list[tuple[str, float]] = []

    def monitor(self, threshold: int = 10):
        """Context manager to monitor queries in a block."""
        self.threshold = threshold
        return self

    def __enter__(self):
        """Start monitoring."""
        _query_count.set(0)
        _queries_executed.set([])
        _n1_detection_enabled.set(True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop monitoring."""
        _n1_detection_enabled.set(False)

    @staticmethod
    def record_query(sql: str, duration_ms: float) -> None:
        """Record a query execution (called by SQLAlchemy event handler)."""
        if not _n1_detection_enabled.get():
            return

        try:
            count = _query_count.get()
            _query_count.set(count + 1)

            queries = _queries_executed.get()
            if queries is None:
                queries = []
            queries.append(f"{sql[:100]}... ({duration_ms:.2f}ms)")
            _queries_executed.set(queries)
        except LookupError:
            pass

    @property
    def query_count(self) -> int:
        """Get current query count."""
        try:
            return _query_count.get()
        except LookupError:
            return 0

    @property
    def queries(self) -> list[str]:
        """Get list of executed queries."""
        try:
            return _queries_executed.get() or []
        except LookupError:
            return []

    def is_violation(self) -> bool:
        """Check if N+1 threshold was exceeded."""
        return self.query_count > self.threshold

    def report_if_violation(self, endpoint: str) -> dict | None:
        """Report if N+1 violation detected."""
        if self.is_violation():
            report = {
                "endpoint": endpoint,
                "query_count": self.query_count,
                "threshold": self.threshold,
                "violation": True,
                "sample_queries": self.queries[:5],
            }

            logger.warning(
                f"N+1 Query Violation detected in {endpoint}: "
                f"{self.query_count} queries executed (threshold: {self.threshold})\n"
                f"Sample queries: {self.queries[:3]}"
            )

            return report

        return None


class N1DetectionMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for automatic N+1 query detection.

    Usage:
        from fastapi import FastAPI

        app = FastAPI()
        app.add_middleware(N1DetectionMiddleware, threshold=15)

    The middleware will:
    1. Count queries executed during each request
    2. Log warnings when threshold is exceeded
    3. Add N1-Query-Count header to responses (in dev mode)
    """

    def __init__(
        self,
        app,
        threshold: int = 15,
        enabled: bool = True,
        add_headers: bool = True,
    ):
        super().__init__(app)
        self.threshold = threshold
        self.enabled = enabled
        self.add_headers = add_headers
        self.detector = N1Detector()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with N+1 monitoring."""
        if not self.enabled:
            return await call_next(request)

        with self.detector.monitor(threshold=self.threshold):
            response = await call_next(request)

            # Check for violation
            violation = self.detector.report_if_violation(request.url.path)

            # Add headers if enabled
            if self.add_headers:
                response.headers["X-Query-Count"] = str(self.detector.query_count)
                response.headers["X-N1-Threshold"] = str(self.threshold)

                if violation:
                    response.headers["X-N1-Violation"] = "true"

            return response


def setup_n1_detection(app, threshold: int = 15, enabled: bool = True) -> None:
    """Convenience function to setup N+1 detection on FastAPI app.

    Args:
        app: FastAPI application
        threshold: Query count threshold for N+1 warning
        enabled: Whether detection is enabled
    """
    app.add_middleware(
        N1DetectionMiddleware,
        threshold=threshold,
        enabled=enabled,
        add_headers=enabled,
    )

    if enabled:
        logger.info(f"N+1 Query Detection enabled with threshold={threshold}")


# SQLAlchemy event handler for query monitoring
async def before_cursor_execute(
    conn,
    cursor,
    statement: str,
    parameters: tuple,
    context: dict,
    _executemany: bool,
):
    """SQLAlchemy event handler - records query start time."""
    context["_query_start_time"] = time.monotonic()


async def after_cursor_execute(
    conn,
    cursor,
    statement: str,
    parameters: tuple,
    context: dict,
    _executemany: bool,
):
    """SQLAlchemy event handler - records query execution."""
    start_time = context.pop("_query_start_time", None)

    if start_time:
        duration_ms = (time.monotonic() - start_time) * 1000
        N1Detector.record_query(statement, duration_ms)


def attach_query_listeners(engine) -> None:
    """Attach SQLAlchemy event listeners for query monitoring.

    Args:
        engine: SQLAlchemy engine instance
    """
    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)

    logger.info("SQLAlchemy query listeners attached for N+1 detection")


# Example usage in FastAPI app
if __name__ == "__main__":
    from fastapi import FastAPI

    app = FastAPI()

    # Setup N+1 detection
    setup_n1_detection(app, threshold=10, enabled=True)

    @app.get("/tenants")
    async def list_tenants():
        """Example endpoint - will trigger N+1 warning if not optimized."""
        # This would trigger N+1 if we access relationships without eager loading
        return {"message": "Tenants listed"}
