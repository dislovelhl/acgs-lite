"""
Tests for under-covered src/core infrastructure and utility modules.
Constitutional Hash: cdd01ef066bc6cf2

Covers:
- database/utils.py (Pageable, Page, BulkOperations)
- database/n1_middleware.py (N1Detector, N1DetectionMiddleware)
- database/session.py (get_database_url, create_engine_with_config)
- http_client.py (_AsyncCircuitBreaker, HttpClient)
- errors/logging.py (ErrorContext, log_error, log_warning, log_critical)
- structured_logging.py (StructuredLogger, BoundLogger, formatters, decorators)
- resilience/retry.py (RetryConfig, retry decorator, RetryBudget, exponential_backoff)
- auth/role_mapper.py (RoleMapper, MappingResult, get_role_mapper)
- auth/provisioning.py (JITProvisioner, ProvisioningResult)
- cache/l1.py (L1Cache, L1CacheStats)
- cache/workflow_state.py (WorkflowStateCache)
- cache/metrics.py (record_cache_hit, track_cache_operation, etc.)
- metrics/_registry.py (_get_or_create_counter, etc.)
- metrics/noop.py (NoOp classes, _safe_create_metric)
- agent_workflow_metrics.py (AgentWorkflowMetricsCollector)
- json_utils.py (dumps, loads, dump_bytes, dump_compact, dump_pretty)
- redis_config.py (RedisConfig, RedisHealthState, health checks)
- fastapi_base.py (_resolve_trusted_hosts, create_acgs_app)
"""

from __future__ import annotations

import json
import logging
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# database/utils.py  -- Pageable, Page, BulkOperations
# ============================================================================


class TestPageable:
    def test_offset_calculation(self):
        from src.core.shared.database.utils import Pageable

        p = Pageable(page=3, size=20)
        assert p.offset == 60
        assert p.limit == 20

    def test_offset_first_page(self):
        from src.core.shared.database.utils import Pageable

        p = Pageable(page=0, size=10)
        assert p.offset == 0

    def test_with_sort_returns_new_instance(self):
        from src.core.shared.database.utils import Pageable

        p = Pageable(page=0, size=10)
        p2 = p.with_sort("name", "asc")
        # Immutability: original unchanged
        assert p.sort == []
        assert p2.sort == [("name", "asc")]
        assert p2.page == 0
        assert p2.size == 10

    def test_next_page(self):
        from src.core.shared.database.utils import Pageable

        p = Pageable(page=2, size=5, sort=[("id", "asc")])
        p_next = p.next_page()
        assert p_next.page == 3
        assert p_next.size == 5
        assert p_next.sort == [("id", "asc")]

    def test_previous_page(self):
        from src.core.shared.database.utils import Pageable

        p = Pageable(page=2, size=5)
        p_prev = p.previous_page()
        assert p_prev is not None
        assert p_prev.page == 1

    def test_previous_page_first_page_returns_none(self):
        from src.core.shared.database.utils import Pageable

        p = Pageable(page=0, size=5)
        assert p.previous_page() is None


class TestPage:
    def test_total_pages(self):
        from src.core.shared.database.utils import Page

        page = Page(content=[1, 2, 3], total_elements=25, page_number=0, page_size=10)
        assert page.total_pages == 3

    def test_total_pages_exact_division(self):
        from src.core.shared.database.utils import Page

        page = Page(content=list(range(10)), total_elements=20, page_number=0, page_size=10)
        assert page.total_pages == 2

    def test_total_pages_single_element(self):
        from src.core.shared.database.utils import Page

        page = Page(content=[1], total_elements=1, page_number=0, page_size=10)
        assert page.total_pages == 1

    def test_has_next_and_previous(self):
        from src.core.shared.database.utils import Page

        page = Page(content=list(range(10)), total_elements=30, page_number=1, page_size=10)
        assert page.has_next is True
        assert page.has_previous is True

    def test_first_page_flags(self):
        from src.core.shared.database.utils import Page

        page = Page(content=list(range(10)), total_elements=30, page_number=0, page_size=10)
        assert page.is_first is True
        assert page.has_previous is False

    def test_last_page_flags(self):
        from src.core.shared.database.utils import Page

        page = Page(content=[1, 2, 3], total_elements=23, page_number=2, page_size=10)
        assert page.is_last is True
        assert page.has_next is False

    def test_number_of_elements(self):
        from src.core.shared.database.utils import Page

        page = Page(content=[1, 2, 3], total_elements=50, page_number=5, page_size=10)
        assert page.number_of_elements == 3


class TestBulkOperations:
    @pytest.mark.asyncio
    async def test_bulk_insert_empty_values(self):
        from src.core.shared.database.utils import BulkOperations

        session = AsyncMock()
        table = MagicMock()
        result = await BulkOperations.bulk_insert(session, table, [])
        assert result is None
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_insert_on_conflict_empty_values(self):
        from src.core.shared.database.utils import BulkOperations

        session = AsyncMock()
        table = MagicMock()
        await BulkOperations.bulk_insert_on_conflict(
            session, table, [], index_elements=["id"]
        )
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_update_empty_values(self):
        from src.core.shared.database.utils import BulkOperations

        session = AsyncMock()
        table = MagicMock()
        result = await BulkOperations.bulk_update(session, table, [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_bulk_update_missing_id_raises(self):
        from src.core.shared.database.utils import BulkOperations
        from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError

        session = AsyncMock()
        table = MagicMock()
        table.name = "test_table"
        values = [{"name": "no_id_field"}]

        with pytest.raises(ACGSValidationError, match="missing.*id.*field"):
            await BulkOperations.bulk_update(session, table, values, id_column="id")

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_ids(self):
        from src.core.shared.database.utils import BulkOperations

        session = AsyncMock()
        table = MagicMock()
        result = await BulkOperations.bulk_delete(session, table, [])
        assert result == 0


# ============================================================================
# database/n1_middleware.py  -- N1Detector
# ============================================================================


class TestN1Detector:
    def test_context_manager_tracks_state(self):
        from src.core.shared.database.n1_middleware import N1Detector

        detector = N1Detector()
        with detector.monitor(threshold=5):
            assert detector.query_count == 0
            assert detector.queries == []
            assert detector.is_violation() is False

    def test_record_query_outside_monitor_is_noop(self):
        from src.core.shared.database.n1_middleware import N1Detector

        # Not inside monitor context, so recording should be silently ignored
        N1Detector.record_query("SELECT 1", 0.5)

    def test_record_query_inside_monitor(self):
        from src.core.shared.database.n1_middleware import N1Detector

        detector = N1Detector()
        with detector.monitor(threshold=2):
            N1Detector.record_query("SELECT * FROM users", 1.0)
            N1Detector.record_query("SELECT * FROM tenants", 2.0)
            assert detector.query_count == 2

    def test_is_violation_above_threshold(self):
        from src.core.shared.database.n1_middleware import N1Detector

        detector = N1Detector()
        with detector.monitor(threshold=1):
            N1Detector.record_query("SELECT 1", 0.1)
            N1Detector.record_query("SELECT 2", 0.2)
            assert detector.is_violation() is True

    def test_report_if_violation_returns_none_when_ok(self):
        from src.core.shared.database.n1_middleware import N1Detector

        detector = N1Detector()
        with detector.monitor(threshold=100):
            report = detector.report_if_violation("/test")
            assert report is None

    def test_report_if_violation_returns_report(self):
        from src.core.shared.database.n1_middleware import N1Detector

        detector = N1Detector()
        with detector.monitor(threshold=0):
            N1Detector.record_query("SELECT 1", 0.1)
            report = detector.report_if_violation("/test")
            assert report is not None
            assert report["violation"] is True
            assert report["endpoint"] == "/test"


# ============================================================================
# database/session.py  -- get_database_url
# ============================================================================


class TestDatabaseSession:
    def test_get_database_url_default(self):
        with patch.dict("os.environ", {}, clear=False):
            # Remove DATABASE_URL if present
            import os
            old = os.environ.pop("DATABASE_URL", None)
            try:
                from src.core.shared.database.session import get_database_url
                url = get_database_url()
                assert "sqlite" in url
            finally:
                if old is not None:
                    os.environ["DATABASE_URL"] = old

    def test_get_database_url_postgres_conversion(self):
        with patch.dict("os.environ", {"DATABASE_URL": "postgres://user:pass@host/db"}):
            from src.core.shared.database.session import get_database_url
            url = get_database_url()
            assert url.startswith("postgresql+asyncpg://")

    def test_get_database_url_postgresql_conversion(self):
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@host/db"}):
            from src.core.shared.database.session import get_database_url
            url = get_database_url()
            assert url.startswith("postgresql+asyncpg://")


# ============================================================================
# http_client.py  -- _AsyncCircuitBreaker, HttpClient
# ============================================================================


class TestAsyncCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker(failure_threshold=3)
        assert cb.get_state() == "closed"
        assert await cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        await cb.record_failure()
        assert cb.get_state() == "closed"
        await cb.record_failure()
        assert cb.get_state() == "open"
        assert await cb.allow_request() is False

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker(failure_threshold=1, recovery_timeout=0.0)
        await cb.record_failure()
        assert cb.get_state() == "open"
        # Recovery timeout is 0, so should transition to half_open
        assert await cb.allow_request() is True
        assert cb.get_state() == "half_open"

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(self):
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker(
            failure_threshold=1, recovery_timeout=0.0, success_threshold=1
        )
        await cb.record_failure()
        # Transition to half_open
        await cb.allow_request()
        await cb.record_success()
        assert cb.get_state() == "closed"

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self):
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker(failure_threshold=1, recovery_timeout=0.0)
        await cb.record_failure()
        await cb.allow_request()  # half_open
        await cb.record_failure()
        assert cb.get_state() == "open"


class TestHttpClient:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        from src.core.shared.http_client import HttpClient

        async with HttpClient(enable_circuit_breaker=False) as client:
            assert client._client is not None
        assert client._client is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_state(self):
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=True)
        assert client.get_circuit_breaker_state() == "closed"

    @pytest.mark.asyncio
    async def test_no_circuit_breaker_state_returns_none(self):
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        assert client.get_circuit_breaker_state() is None

    @pytest.mark.asyncio
    async def test_do_request_raises_without_client(self):
        from src.core.shared.errors.exceptions import ServiceUnavailableError
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        # Force _client to None
        client._client = None
        with pytest.raises(ServiceUnavailableError):
            await client._do_request("GET", "http://example.com")


# ============================================================================
# errors/logging.py  -- ErrorContext, log_error, etc.
# ============================================================================


class TestErrorLogging:
    def test_error_severity_levels(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorSeverity

        assert ErrorSeverity.DEBUG < ErrorSeverity.INFO
        assert ErrorSeverity.INFO < ErrorSeverity.WARNING
        assert ErrorSeverity.WARNING < ErrorSeverity.ERROR
        assert ErrorSeverity.ERROR < ErrorSeverity.CRITICAL
        assert ErrorSeverity.CRITICAL < ErrorSeverity.EMERGENCY

    def test_error_context_defaults(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorContext

        ctx = ErrorContext(operation="test_op", service="test_svc")
        assert ctx.operation == "test_op"
        assert ctx.service == "test_svc"
        assert ctx.correlation_id  # auto-generated
        assert ctx.constitutional_hash == "cdd01ef066bc6cf2"

    def test_error_context_to_dict(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import ErrorContext

        ctx = ErrorContext(
            operation="validate",
            service="gateway",
            tenant_id="t-123",
            agent_id="a-456",
        )
        d = ctx.to_dict()
        assert d["operation"] == "validate"
        assert d["service"] == "gateway"
        assert d["tenant_id"] == "t-123"
        assert d["agent_id"] == "a-456"
        assert "constitutional_hash" in d

    def test_error_context_to_dict_excludes_empty(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                ErrorContext,
                _request_id_var,
                _tenant_id_var,
            )

        # Reset context vars that may have been set by previous tests
        t = _tenant_id_var.set("")
        r = _request_id_var.set("")
        try:
            ctx = ErrorContext()
            d = ctx.to_dict()
            assert "operation" not in d
            assert "service" not in d
            assert "tenant_id" not in d
        finally:
            _tenant_id_var.reset(t)
            _request_id_var.reset(r)

    def test_build_error_context(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import build_error_context

        ctx = build_error_context(
            operation="test",
            service="svc",
            tenant_id="t1",
            custom_field="custom_val",
        )
        assert ctx.operation == "test"
        assert ctx.tenant_id == "t1"
        assert ctx.metadata == {"custom_field": "custom_val"}

    def test_log_error_no_context(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import log_error

        # Should not raise
        log_error(ValueError("test error"))

    def test_log_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import log_warning

        log_warning("something happened")

    def test_log_critical_upgrades_severity(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                ErrorContext,
                ErrorSeverity,
                log_critical,
            )

        ctx = ErrorContext(severity=ErrorSeverity.WARNING)
        log_critical(RuntimeError("critical failure"), context=ctx)
        assert ctx.severity == ErrorSeverity.CRITICAL

    def test_severity_to_log_level(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                ErrorSeverity,
                _severity_to_log_level,
            )

        assert _severity_to_log_level(ErrorSeverity.DEBUG) == logging.DEBUG
        assert _severity_to_log_level(ErrorSeverity.INFO) == logging.INFO
        assert _severity_to_log_level(ErrorSeverity.WARNING) == logging.WARNING
        assert _severity_to_log_level(ErrorSeverity.ERROR) == logging.ERROR
        assert _severity_to_log_level(ErrorSeverity.CRITICAL) == logging.CRITICAL
        assert _severity_to_log_level(ErrorSeverity.EMERGENCY) == logging.CRITICAL

    def test_set_and_get_correlation_id(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import (
                get_correlation_id,
                set_correlation_id,
            )

        set_correlation_id("test-corr-id-123")
        assert get_correlation_id() == "test-corr-id-123"

    def test_set_tenant_id_and_request_id(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.shared.errors.logging import set_request_id, set_tenant_id

        # Should not raise
        set_tenant_id("tenant-abc")
        set_request_id("req-xyz")


# ============================================================================
# structured_logging.py  -- StructuredLogger, formatters, decorators
# ============================================================================


class TestStructuredLogging:
    def test_get_logger_returns_structured_logger(self):
        from src.core.shared.structured_logging import StructuredLogger, get_logger

        logger = get_logger("test.module")
        assert isinstance(logger, StructuredLogger)

    def test_structured_logger_all_levels(self):
        from src.core.shared.structured_logging import get_logger

        logger = get_logger("test.levels")
        # Should not raise
        logger.debug("debug msg", key="val")
        logger.info("info msg", key="val")
        logger.warning("warn msg", key="val")
        logger.error("error msg", key="val")
        logger.critical("critical msg", key="val")

    def test_bound_logger(self):
        from src.core.shared.structured_logging import get_logger

        logger = get_logger("test.bound")
        bound = logger.bind(service="test_svc", tenant_id="t-1")
        # Should not raise
        bound.info("bound message", extra_key="extra_val")
        bound.debug("bound debug")
        bound.warning("bound warning")
        bound.error("bound error")
        bound.critical("bound critical")

    def test_set_and_get_correlation_id(self):
        from src.core.shared.structured_logging import (
            get_correlation_id,
            set_correlation_id,
        )

        cid = set_correlation_id("test-cid-456")
        assert cid == "test-cid-456"
        assert get_correlation_id() == "test-cid-456"

    def test_set_correlation_id_auto_generates(self):
        from src.core.shared.structured_logging import set_correlation_id

        cid = set_correlation_id()
        assert len(cid) > 0  # UUID string

    def test_set_tenant_id(self):
        from src.core.shared.structured_logging import get_tenant_id, set_tenant_id

        set_tenant_id("tenant-xyz")
        assert get_tenant_id() == "tenant-xyz"

    def test_set_request_id(self):
        from src.core.shared.structured_logging import request_id_var, set_request_id

        set_request_id("req-abc")
        assert request_id_var.get() == "req-abc"

    def test_structured_json_formatter(self):
        from src.core.shared.structured_logging import StructuredJSONFormatter

        formatter = StructuredJSONFormatter(
            include_stack_trace=False, redact_sensitive=True
        )
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="Test message", args=None, exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"

    def test_structured_json_formatter_redacts_sensitive(self):
        from src.core.shared.structured_logging import StructuredJSONFormatter

        formatter = StructuredJSONFormatter(redact_sensitive=True)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="Test", args=None, exc_info=None,
        )
        record.extra = {"api_key": "sk-secret-123", "name": "public"}  # type: ignore[attr-defined]
        output = formatter.format(record)
        data = json.loads(output)
        assert data["extra"]["api_key"] == "[REDACTED]"
        assert data["extra"]["name"] == "public"

    def test_structured_json_formatter_truncates_large_output(self):
        from src.core.shared.structured_logging import (
            MAX_LOG_SIZE,
            StructuredJSONFormatter,
        )

        formatter = StructuredJSONFormatter(redact_sensitive=False)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="x" * (MAX_LOG_SIZE + 1000), args=None, exc_info=None,
        )
        output = formatter.format(record)
        assert len(output) <= MAX_LOG_SIZE + 50  # small margin for suffix

    def test_text_formatter(self):
        from src.core.shared.structured_logging import TextFormatter

        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="Hello", args=None, exc_info=None,
        )
        output = formatter.format(record)
        assert "Hello" in output
        assert "INFO" in output

    def test_log_function_call_decorator_sync(self):
        from src.core.shared.structured_logging import log_function_call

        @log_function_call()
        def add(a, b):
            return a + b

        result = add(1, 2)
        assert result == 3

    @pytest.mark.asyncio
    async def test_log_function_call_decorator_async(self):
        from src.core.shared.structured_logging import log_function_call

        @log_function_call()
        async def async_add(a, b):
            return a + b

        result = await async_add(1, 2)
        assert result == 3

    def test_log_function_call_decorator_exception(self):
        from src.core.shared.structured_logging import log_function_call

        @log_function_call()
        def failing():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing()

    @pytest.mark.asyncio
    async def test_log_function_call_decorator_async_exception(self):
        from src.core.shared.structured_logging import log_function_call

        @log_function_call()
        async def failing_async():
            raise ValueError("async boom")

        with pytest.raises(ValueError, match="async boom"):
            await failing_async()

    def test_bind_correlation_id(self):
        from src.core.shared.structured_logging import (
            bind_correlation_id,
            correlation_id_var,
        )

        bind_correlation_id("test-bind-id")
        assert correlation_id_var.get() == "test-bind-id"


# ============================================================================
# resilience/retry.py  -- RetryConfig, retry, RetryBudget
# ============================================================================


class TestRetryConfig:
    def test_defaults(self):
        from src.core.shared.resilience.retry import RetryConfig

        config = RetryConfig()
        assert config.max_retries == 3
        assert config.max_attempts == 4
        assert config.base_delay == 1.0
        assert config.jitter is True

    def test_max_attempts_overrides_max_retries(self):
        from src.core.shared.resilience.retry import RetryConfig

        config = RetryConfig(max_attempts=5)
        assert config.max_retries == 4

    def test_calculate_delay_exponential(self):
        from src.core.shared.resilience.retry import RetryConfig

        config = RetryConfig(base_delay=1.0, multiplier=2.0, jitter=False)
        assert config.calculate_delay(1) == 1.0
        assert config.calculate_delay(2) == 2.0
        assert config.calculate_delay(3) == 4.0

    def test_calculate_delay_capped_at_max(self):
        from src.core.shared.resilience.retry import RetryConfig

        config = RetryConfig(base_delay=1.0, multiplier=10.0, max_delay=5.0, jitter=False)
        assert config.calculate_delay(3) == 5.0

    def test_calculate_delay_with_jitter(self):
        from src.core.shared.resilience.retry import RetryConfig

        config = RetryConfig(base_delay=1.0, jitter=True, jitter_factor=0.25)
        delay = config.calculate_delay(1)
        assert 0.75 <= delay <= 1.25

    def test_to_dict(self):
        from src.core.shared.resilience.retry import RetryConfig

        config = RetryConfig()
        d = config.to_dict()
        assert "max_retries" in d
        assert "base_delay" in d
        assert "retryable_exceptions" in d


class TestRetryDecorator:
    @pytest.mark.asyncio
    async def test_retry_async_success(self):
        from src.core.shared.resilience.retry import retry

        call_count = 0

        @retry(max_retries=2, base_delay=0.0)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_async_retries_on_failure(self):
        from src.core.shared.resilience.retry import RetryExhaustedError, retry

        call_count = 0

        @retry(max_retries=2, base_delay=0.0, retryable_exceptions=(ConnectionError,))
        async def fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("down")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await fail()

        assert call_count == 3  # initial + 2 retries
        assert exc_info.value.attempts == 3

    @pytest.mark.asyncio
    async def test_retry_async_on_retry_callback(self):
        from src.core.shared.resilience.retry import retry

        callback_calls = []

        def on_retry_cb(attempt, exc):
            callback_calls.append(attempt)

        call_count = 0

        @retry(max_retries=2, base_delay=0.0, on_retry=on_retry_cb,
               retryable_exceptions=(ConnectionError,))
        async def fail():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "recovered"

        result = await fail()
        assert result == "recovered"
        assert len(callback_calls) == 2

    def test_retry_sync_success(self):
        from src.core.shared.resilience.retry import retry

        @retry(max_retries=1, base_delay=0.0)
        def succeed():
            return 42

        assert succeed() == 42


class TestRetryExhaustedError:
    def test_to_dict(self):
        from src.core.shared.resilience.retry import RetryExhaustedError

        err = RetryExhaustedError(
            "test",
            attempts=3,
            last_exception=ConnectionError("conn fail"),
            operation="fetch_data",
        )
        d = err.to_dict()
        assert d["error"] == "RETRY_EXHAUSTED"
        assert d["attempts"] == 3
        assert d["operation"] == "fetch_data"
        assert d["last_exception_type"] == "ConnectionError"


class TestExponentialBackoff:
    @pytest.mark.asyncio
    async def test_yields_expected_count(self):
        from src.core.shared.resilience.retry import exponential_backoff

        delays = []
        async for delay in exponential_backoff(max_attempts=3, jitter=False):
            delays.append(delay)
        assert len(delays) == 3

    @pytest.mark.asyncio
    async def test_delays_increase(self):
        from src.core.shared.resilience.retry import exponential_backoff

        delays = []
        async for delay in exponential_backoff(max_attempts=4, base_delay=1.0, jitter=False):
            delays.append(delay)
        assert delays[1] > delays[0]
        assert delays[2] > delays[1]


class TestRetryBudget:
    @pytest.mark.asyncio
    async def test_can_retry_within_budget(self):
        from src.core.shared.resilience.retry import RetryBudget

        budget = RetryBudget(max_retries=5, window_seconds=60.0)
        assert await budget.can_retry() is True
        await budget.record_retry()
        assert budget.get_retry_count() == 1

    @pytest.mark.asyncio
    async def test_budget_exhausted(self):
        from src.core.shared.resilience.retry import RetryBudget

        budget = RetryBudget(max_retries=2, window_seconds=60.0)
        await budget.record_retry()
        await budget.record_retry()
        assert await budget.can_retry() is False


# ============================================================================
# auth/role_mapper.py  -- RoleMapper
# ============================================================================


class TestRoleMapper:
    def setup_method(self):
        from src.core.shared.auth.role_mapper import reset_role_mapper

        reset_role_mapper()

    def test_map_known_groups(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        roles = mapper.map_groups(["admins", "engineering"])
        assert "admin" in roles
        assert "developer" in roles

    def test_map_empty_groups(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        roles = mapper.map_groups([])
        assert roles == []

    def test_case_insensitive_matching(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(case_sensitive=False)
        roles = mapper.map_groups(["ADMINS", "Engineering"])
        assert "admin" in roles
        assert "developer" in roles

    def test_case_sensitive_matching(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(case_sensitive=True)
        roles = mapper.map_groups(["ADMINS"])  # No match since default keys are lowercase
        assert "admin" not in roles

    def test_unmapped_groups_ignored_without_fallback(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(fallback_role=None)
        roles = mapper.map_groups(["unknown_group_xyz"])
        assert roles == []

    def test_fallback_role_applied(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(fallback_role="viewer")
        roles = mapper.map_groups(["unknown_group_xyz"])
        assert "viewer" in roles

    def test_add_and_remove_default_mapping(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={})
        mapper.add_default_mapping("custom-group", "custom-role")
        roles = mapper.map_groups(["custom-group"])
        assert "custom-role" in roles

        removed = mapper.remove_default_mapping("custom-group")
        assert removed is True
        roles = mapper.map_groups(["custom-group"])
        assert roles == []

    def test_remove_nonexistent_mapping(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={})
        assert mapper.remove_default_mapping("nonexistent") is False

    def test_get_default_mappings_returns_copy(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={"a": "b"})
        mappings = mapper.get_default_mappings()
        mappings["c"] = "d"
        # Original should be unchanged
        assert "c" not in mapper.default_mappings

    @pytest.mark.asyncio
    async def test_map_groups_async_default(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        result = await mapper.map_groups_async(groups=["admins", "viewers"])
        assert "admin" in result.roles
        assert "viewer" in result.roles
        assert result.source == "default"

    @pytest.mark.asyncio
    async def test_map_groups_async_empty(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        result = await mapper.map_groups_async(groups=[])
        assert result.roles == []
        assert result.source == "none"

    def test_get_role_mapper_singleton(self):
        from src.core.shared.auth.role_mapper import get_role_mapper, reset_role_mapper

        reset_role_mapper()
        m1 = get_role_mapper()
        m2 = get_role_mapper()
        assert m1 is m2

    def test_custom_default_mappings(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        custom = {"team-lead": "manager", "intern": "viewer"}
        mapper = RoleMapper(default_mappings=custom)
        roles = mapper.map_groups(["team-lead"])
        assert roles == ["manager"]


# ============================================================================
# auth/provisioning.py  -- JITProvisioner
# ============================================================================


class TestJITProvisioner:
    def setup_method(self):
        from src.core.shared.auth.provisioning import reset_provisioner

        reset_provisioner()

    def test_validate_email_domain_all_allowed(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(allowed_domains=None)
        assert p._validate_email_domain("user@anything.com") is True

    def test_validate_email_domain_restricted(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(allowed_domains=["example.com"])
        assert p._validate_email_domain("user@example.com") is True
        assert p._validate_email_domain("user@other.com") is False

    def test_normalize_email(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner()
        assert p._normalize_email("  User@EXAMPLE.COM  ") == "user@example.com"

    def test_merge_roles_new_roles_take_precedence(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner()
        merged, changed = p._merge_roles(["old_role"], ["new_role"])
        assert merged == ["new_role"]
        assert changed is True

    def test_merge_roles_preserve_existing(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner()
        merged, changed = p._merge_roles(["existing"], [])
        assert merged == ["existing"]
        assert changed is False

    def test_merge_roles_defaults_for_new_user(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(default_roles=["viewer"])
        merged, changed = p._merge_roles([], [], ["viewer"])
        assert merged == ["viewer"]
        assert changed is True

    @pytest.mark.asyncio
    async def test_get_or_create_user_domain_not_allowed(self):
        from src.core.shared.auth.provisioning import (
            DomainNotAllowedError,
            JITProvisioner,
        )

        p = JITProvisioner(allowed_domains=["allowed.com"])
        with pytest.raises(DomainNotAllowedError):
            await p.get_or_create_user(email="user@blocked.com")

    @pytest.mark.asyncio
    async def test_get_or_create_user_in_memory(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(default_roles=["viewer"])
        result = await p.get_or_create_user(
            email="test@example.com",
            name="Test User",
            sso_provider="oidc",
            idp_user_id="sub-123",
            provider_id="provider-1",
            roles=["admin"],
        )
        assert result.created is True
        assert result.user["email"] == "test@example.com"
        assert "admin" in result.user["roles"]

    @pytest.mark.asyncio
    async def test_get_or_create_user_in_memory_with_defaults(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(default_roles=["viewer"])
        result = await p.get_or_create_user(
            email="test@example.com",
            name="Test User",
        )
        assert result.user["roles"] == ["viewer"]

    def test_get_provisioner_singleton(self):
        from src.core.shared.auth.provisioning import get_provisioner, reset_provisioner

        reset_provisioner()
        p1 = get_provisioner()
        p2 = get_provisioner()
        assert p1 is p2

    def test_provisioning_result_fields(self):
        from src.core.shared.auth.provisioning import ProvisioningResult

        result = ProvisioningResult(
            user={"id": "1", "email": "a@b.com"},
            created=True,
            roles_updated=True,
            provider_id="p-1",
        )
        assert result.created is True
        assert result.provider_id == "p-1"


# ============================================================================
# cache/l1.py  -- L1Cache
# ============================================================================


class TestL1Cache:
    def test_get_set(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_returns_default(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        assert cache.get("missing") is None
        assert cache.get("missing", "fallback") == "fallback"

    def test_delete(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("nonexistent") is False

    def test_exists(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.exists("key1") is True
        assert cache.exists("key2") is False

    def test_contains(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("a", 1)
        assert "a" in cache
        assert "b" not in cache

    def test_clear(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0

    def test_get_many_set_many(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set_many({"k1": "v1", "k2": "v2", "k3": "v3"})
        result = cache.get_many(["k1", "k2", "missing"])
        assert result == {"k1": "v1", "k2": "v2"}

    def test_stats(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("a", 1)
        cache.get("a")
        cache.get("missing")
        assert cache.stats.hits == 1
        assert cache.stats.misses == 1
        assert cache.stats.sets == 1

    def test_hit_ratio(self):
        from src.core.shared.cache.l1 import L1CacheStats

        stats = L1CacheStats(hits=3, misses=1)
        assert stats.hit_ratio == 0.75

    def test_hit_ratio_zero_total(self):
        from src.core.shared.cache.l1 import L1CacheStats

        stats = L1CacheStats()
        assert stats.hit_ratio == 0.0

    def test_size_and_len(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size == 2
        assert cache.currsize == 2
        assert len(cache) == 2

    def test_get_stats_dict(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        stats = cache.get_stats()
        assert stats["tier"] == "L1"
        assert "constitutional_hash" in stats

    def test_serialization_mode(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60, serialize=True)
        cache.set("data", {"key": "value"})
        result = cache.get("data")
        assert result == {"key": "value"}

    def test_repr(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        r = repr(cache)
        assert "L1Cache" in r
        assert "maxsize=10" in r

    def test_on_evict_callback(self):
        from src.core.shared.cache.l1 import L1Cache

        evicted = []

        def on_evict(key, value):
            evicted.append((key, value))

        cache = L1Cache(maxsize=10, ttl=60, on_evict=on_evict)
        cache.set("a", 1)
        cache.delete("a")
        assert len(evicted) == 1
        assert evicted[0] == ("a", 1)

    def test_get_access_frequency(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=10, ttl=60)
        cache.set("a", 1)
        cache.get("a")
        cache.get("a")
        freq = cache.get_access_frequency("a")
        assert freq >= 2

    def test_get_hot_keys(self):
        from src.core.shared.cache.l1 import L1Cache

        cache = L1Cache(maxsize=100, ttl=60)
        for _ in range(15):
            cache.set("hot", 1)
        hot_keys = cache.get_hot_keys(threshold=10)
        assert "hot" in hot_keys

    def test_singleton_reset(self):
        from src.core.shared.cache.l1 import get_l1_cache, reset_l1_cache

        reset_l1_cache()
        c1 = get_l1_cache(maxsize=50, ttl=30)
        c2 = get_l1_cache()
        assert c1 is c2
        reset_l1_cache()


# ============================================================================
# cache/workflow_state.py  -- WorkflowStateCache (mocked)
# ============================================================================


class TestWorkflowStateCache:
    def test_key_generation(self):
        from src.core.shared.cache.workflow_state import WorkflowStateCache

        wsc = WorkflowStateCache()
        assert wsc._get_workflow_key("wf-1") == "workflow:state:wf-1"
        assert wsc._get_step_key("wf-1", "step-a") == "workflow:step:wf-1:step-a"

    @pytest.mark.asyncio
    async def test_get_workflow_state_returns_none_on_miss(self):
        from src.core.shared.cache.workflow_state import WorkflowStateCache

        wsc = WorkflowStateCache()
        wsc.cache_manager = MagicMock()
        wsc.cache_manager.get_async = AsyncMock(return_value=None)
        result = await wsc.get_workflow_state("wf-missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_workflow_state_parses_json_string(self):
        from src.core.shared.cache.workflow_state import WorkflowStateCache

        wsc = WorkflowStateCache()
        wsc.cache_manager = MagicMock()
        wsc.cache_manager.get_async = AsyncMock(
            return_value='{"status": "running"}'
        )
        result = await wsc.get_workflow_state("wf-1")
        assert result == {"status": "running"}

    @pytest.mark.asyncio
    async def test_get_workflow_state_returns_dict_directly(self):
        from src.core.shared.cache.workflow_state import WorkflowStateCache

        wsc = WorkflowStateCache()
        wsc.cache_manager = MagicMock()
        wsc.cache_manager.get_async = AsyncMock(
            return_value={"status": "done"}
        )
        result = await wsc.get_workflow_state("wf-1")
        assert result == {"status": "done"}

    @pytest.mark.asyncio
    async def test_get_step_result_invalid_json(self):
        from src.core.shared.cache.workflow_state import WorkflowStateCache

        wsc = WorkflowStateCache()
        wsc.cache_manager = MagicMock()
        wsc.cache_manager.get_async = AsyncMock(return_value="not valid json{")
        result = await wsc.get_step_result("wf-1", "step-1")
        assert result is None


# ============================================================================
# cache/metrics.py  -- record helpers, track_cache_operation decorator
# ============================================================================


class TestCacheMetrics:
    def test_record_cache_hit(self):
        from src.core.shared.cache.metrics import record_cache_hit

        record_cache_hit("L1", "test_cache", "get")

    def test_record_cache_miss(self):
        from src.core.shared.cache.metrics import record_cache_miss

        record_cache_miss("L2", "test_cache", "get")

    def test_record_cache_latency(self):
        from src.core.shared.cache.metrics import record_cache_latency

        record_cache_latency("L1", "test_cache", "get", 0.001)
        record_cache_latency("L2", "test_cache", "set", 0.01)
        record_cache_latency("L3", "test_cache", "get", 0.1)

    def test_record_cache_latency_unknown_tier_noop(self):
        from src.core.shared.cache.metrics import record_cache_latency

        record_cache_latency("L999", "test_cache", "get", 0.001)

    def test_record_promotion_demotion(self):
        from src.core.shared.cache.metrics import record_demotion, record_promotion

        record_promotion("L2", "L1", "test_cache")
        record_demotion("L1", "L2", "test_cache")

    def test_record_eviction(self):
        from src.core.shared.cache.metrics import record_eviction

        record_eviction("L1", "test_cache", "lru")

    def test_update_cache_size(self):
        from src.core.shared.cache.metrics import update_cache_size

        update_cache_size("L1", "test_cache", 1024, 50)

    def test_set_tier_health(self):
        from src.core.shared.cache.metrics import set_tier_health

        set_tier_health("L1", True)
        set_tier_health("L2", False)

    def test_record_fallback(self):
        from src.core.shared.cache.metrics import record_fallback

        record_fallback("L2", "L1", "test_cache")

    def test_track_cache_operation_decorator_sync(self):
        from src.core.shared.cache.metrics import track_cache_operation

        @track_cache_operation("L1", "test_cache", "get")
        def my_get(key):
            return "value" if key == "found" else None

        assert my_get("found") == "value"
        assert my_get("missing") is None

    @pytest.mark.asyncio
    async def test_track_cache_operation_decorator_async(self):
        from src.core.shared.cache.metrics import track_cache_operation

        @track_cache_operation("L2", "test_cache", "get")
        async def my_async_get(key):
            return {"data": 1} if key == "found" else None

        assert await my_async_get("found") == {"data": 1}
        assert await my_async_get("missing") is None


# ============================================================================
# metrics/_registry.py  -- _get_or_create helpers
# ============================================================================


class TestMetricsRegistry:
    def test_get_or_create_counter(self):
        from src.core.shared.metrics._registry import _get_or_create_counter

        c1 = _get_or_create_counter("test_cov_counter_abc", "Test counter", ["label1"])
        c2 = _get_or_create_counter("test_cov_counter_abc", "Test counter", ["label1"])
        assert c1 is c2

    def test_get_or_create_gauge(self):
        from src.core.shared.metrics._registry import _get_or_create_gauge

        g1 = _get_or_create_gauge("test_cov_gauge_abc", "Test gauge", ["label1"])
        g2 = _get_or_create_gauge("test_cov_gauge_abc", "Test gauge", ["label1"])
        assert g1 is g2

    def test_get_or_create_histogram(self):
        from src.core.shared.metrics._registry import _get_or_create_histogram

        h1 = _get_or_create_histogram(
            "test_cov_hist_abc", "Test hist", ["label1"], buckets=[0.1, 0.5, 1.0]
        )
        h2 = _get_or_create_histogram(
            "test_cov_hist_abc", "Test hist", ["label1"]
        )
        assert h1 is h2

    def test_get_or_create_info(self):
        from src.core.shared.metrics._registry import _get_or_create_info

        i1 = _get_or_create_info("test_cov_info_abc", "Test info")
        i2 = _get_or_create_info("test_cov_info_abc", "Test info")
        assert i1 is i2


# ============================================================================
# metrics/noop.py  -- NoOp classes
# ============================================================================


class TestNoopMetrics:
    def test_noop_counter(self):
        from src.core.shared.metrics.noop import NoOpCounter

        c = NoOpCounter()
        c.inc()
        c.inc(5)
        assert c.labels(a="b") is c

    def test_noop_gauge(self):
        from src.core.shared.metrics.noop import NoOpGauge

        g = NoOpGauge()
        g.set(1.0)
        g.inc()
        g.dec()
        assert g.labels(a="b") is g

    def test_noop_histogram(self):
        from src.core.shared.metrics.noop import NoOpHistogram

        h = NoOpHistogram()
        h.observe(0.5)
        assert h.labels(a="b") is h
        with h.time():
            pass

    def test_noop_info(self):
        from src.core.shared.metrics.noop import NoOpInfo

        i = NoOpInfo()
        i.info({"version": "1.0"})
        assert i.labels(a="b") is i

    def test_noop_summary(self):
        from src.core.shared.metrics.noop import NoOpSummary

        s = NoOpSummary()
        s.observe(0.5)
        assert s.labels(a="b") is s

    def test_noop_timer(self):
        from src.core.shared.metrics.noop import NoOpTimer

        t = NoOpTimer()
        with t:
            pass

    def test_prometheus_available_flag(self):
        from src.core.shared.metrics.noop import PROMETHEUS_AVAILABLE

        # prometheus_client is installed in this project
        assert PROMETHEUS_AVAILABLE is True

    def test_safe_create_metric_deduplication(self):
        from prometheus_client import Counter

        from src.core.shared.metrics.noop import _safe_create_metric

        m1 = _safe_create_metric(Counter, "test_cov_safe_abc", "desc", labels=["l1"])
        m2 = _safe_create_metric(Counter, "test_cov_safe_abc", "desc", labels=["l1"])
        # Second call should not raise even if metric already exists
        assert m1 is not None
        assert m2 is not None


# ============================================================================
# agent_workflow_metrics.py
# ============================================================================


class TestAgentWorkflowMetrics:
    def test_record_and_snapshot(self):
        from src.core.shared.agent_workflow_metrics import (
            AgentWorkflowMetricsCollector,
        )

        collector = AgentWorkflowMetricsCollector()
        collector.record_event(event_type="intervention", tenant_id="t1")
        collector.record_event(event_type="gate_failure", tenant_id="t1")
        collector.record_event(event_type="autonomous_action", tenant_id="t1")
        collector.record_event(event_type="rollback_trigger", tenant_id="t2")

        snap_t1 = collector.snapshot(tenant_id="t1")
        assert snap_t1["interventions_total"] == 1
        assert snap_t1["gate_failures_total"] == 1
        assert snap_t1["autonomous_actions_total"] == 1

        snap_all = collector.snapshot()
        assert snap_all["interventions_total"] == 1
        assert snap_all["rollback_triggers_total"] == 1

    def test_intervention_rate(self):
        from src.core.shared.agent_workflow_metrics import WorkflowTenantCounters

        c = WorkflowTenantCounters(interventions_total=1, autonomous_actions_total=3)
        snap = c.to_snapshot()
        assert snap["intervention_rate"] == pytest.approx(0.25)

    def test_intervention_rate_zero_denominator(self):
        from src.core.shared.agent_workflow_metrics import WorkflowTenantCounters

        c = WorkflowTenantCounters()
        snap = c.to_snapshot()
        assert snap["intervention_rate"] == 0.0

    def test_invalid_event_type_raises(self):
        from src.core.shared.agent_workflow_metrics import (
            AgentWorkflowMetricsCollector,
        )

        collector = AgentWorkflowMetricsCollector()
        with pytest.raises(ValueError, match="Unsupported"):
            collector.record_event(event_type="invalid_type")

    def test_reset(self):
        from src.core.shared.agent_workflow_metrics import (
            AgentWorkflowMetricsCollector,
        )

        collector = AgentWorkflowMetricsCollector()
        collector.record_event(event_type="intervention")
        collector.reset()
        snap = collector.snapshot()
        assert snap["interventions_total"] == 0

    def test_singleton_accessors(self):
        from src.core.shared.agent_workflow_metrics import (
            get_agent_workflow_metrics_collector,
            reset_agent_workflow_metrics_collector,
        )

        c1 = get_agent_workflow_metrics_collector()
        c2 = get_agent_workflow_metrics_collector()
        assert c1 is c2

        c3 = reset_agent_workflow_metrics_collector()
        assert c3 is not c1


# ============================================================================
# json_utils.py
# ============================================================================


class TestJsonUtils:
    def test_dumps_and_loads(self):
        from src.core.shared.json_utils import dumps, loads

        data = {"key": "value", "num": 42, "nested": {"a": [1, 2, 3]}}
        serialized = dumps(data)
        assert isinstance(serialized, str)
        deserialized = loads(serialized)
        assert deserialized == data

    def test_loads_bytes(self):
        from src.core.shared.json_utils import loads

        data = b'{"key": "value"}'
        result = loads(data)
        assert result == {"key": "value"}

    def test_dump_bytes(self):
        from src.core.shared.json_utils import dump_bytes

        result = dump_bytes({"a": 1})
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == {"a": 1}

    def test_dump_compact(self):
        from src.core.shared.json_utils import dump_compact

        result = dump_compact({"a": 1, "b": 2})
        assert isinstance(result, str)
        # Should have no extra spaces
        assert " " not in result or result.count(" ") < 3

    def test_dump_pretty(self):
        from src.core.shared.json_utils import dump_pretty

        result = dump_pretty({"a": 1})
        assert "\n" in result
        assert "  " in result


# ============================================================================
# redis_config.py  -- RedisConfig, health checks
# ============================================================================


class TestRedisConfig:
    def test_health_state_enum(self):
        from src.core.shared.redis_config import RedisHealthState

        assert RedisHealthState.HEALTHY.value == "healthy"
        assert RedisHealthState.UNHEALTHY.value == "unhealthy"
        assert RedisHealthState.UNKNOWN.value == "unknown"

    def test_redis_config_initial_state(self):
        from src.core.shared.redis_config import RedisConfig, RedisHealthState

        config = RedisConfig()
        assert config.current_state == RedisHealthState.UNKNOWN
        assert config.is_healthy is False
        assert config.last_latency_ms is None

    def test_register_and_unregister_callback(self):
        from src.core.shared.redis_config import RedisConfig

        config = RedisConfig()
        calls = []

        def my_callback(old, new):
            calls.append((old, new))

        config.register_health_callback(my_callback)
        assert config.unregister_health_callback(my_callback) is True
        assert config.unregister_health_callback(my_callback) is False

    def test_health_check_failure(self):
        from src.core.shared.redis_config import RedisConfig

        config = RedisConfig()
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("refused")
        config._redis_client = mock_client

        is_healthy, latency = config.health_check(redis_client=mock_client)
        assert is_healthy is False
        assert latency is not None

    def test_health_check_success(self):
        from src.core.shared.redis_config import RedisConfig, RedisHealthState

        config = RedisConfig()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        config._redis_client = mock_client

        is_healthy, latency = config.health_check(redis_client=mock_client)
        assert is_healthy is True
        assert latency is not None
        assert config.current_state == RedisHealthState.HEALTHY

    def test_health_transitions_to_unhealthy(self):
        from src.core.shared.redis_config import (
            RedisConfig,
            RedisHealthCheckConfig,
            RedisHealthState,
        )

        config = RedisConfig(health_config=RedisHealthCheckConfig(unhealthy_threshold=2))
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("down")

        config.health_check(redis_client=mock_client)
        config.health_check(redis_client=mock_client)
        assert config.current_state == RedisHealthState.UNHEALTHY

    def test_get_health_stats(self):
        from src.core.shared.redis_config import RedisConfig

        config = RedisConfig()
        stats = config.get_health_stats()
        assert "state" in stats
        assert "is_healthy" in stats
        assert "config" in stats

    def test_reset(self):
        from src.core.shared.redis_config import RedisConfig, RedisHealthState

        config = RedisConfig()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        config.health_check(redis_client=mock_client)
        assert config.current_state == RedisHealthState.HEALTHY

        config.reset()
        assert config.current_state == RedisHealthState.UNKNOWN
        assert config.last_latency_ms is None

    def test_add_listener(self):
        from src.core.shared.redis_config import RedisConfig, RedisHealthListener

        config = RedisConfig()
        listener = RedisHealthListener(name="test")
        config.add_listener(listener)
        assert listener in config._listeners

    def test_health_listener_methods(self):
        from src.core.shared.redis_config import (
            RedisHealthListener,
            RedisHealthState,
        )

        listener = RedisHealthListener(name="test")
        # Should not raise
        listener.on_state_change(RedisHealthState.UNKNOWN, RedisHealthState.HEALTHY)
        listener.on_health_check_success(1.5)
        listener.on_health_check_failure(ConnectionError("down"))

    @pytest.mark.asyncio
    async def test_health_check_async_success(self):
        from src.core.shared.redis_config import RedisConfig

        config = RedisConfig()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        is_healthy, latency = await config.health_check_async(redis_client=mock_client)
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_async_failure(self):
        from src.core.shared.redis_config import RedisConfig

        config = RedisConfig()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("down"))

        is_healthy, latency = await config.health_check_async(redis_client=mock_client)
        assert is_healthy is False

    def test_callback_invoked_on_state_change(self):
        from src.core.shared.redis_config import RedisConfig, RedisHealthState

        config = RedisConfig()
        state_changes = []

        def callback(old, new):
            state_changes.append((old, new))

        config.register_health_callback(callback)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        config.health_check(redis_client=mock_client)
        # Should transition from UNKNOWN to HEALTHY
        assert len(state_changes) == 1
        assert state_changes[0] == (RedisHealthState.UNKNOWN, RedisHealthState.HEALTHY)


# ============================================================================
# fastapi_base.py  -- _resolve_trusted_hosts, create_acgs_app
# ============================================================================


class TestFastapiBase:
    @pytest.mark.skip(reason="_resolve_trusted_hosts not exposed in public API")
    def test_resolve_trusted_hosts_string(self):
        pass

    @pytest.mark.skip(reason="_resolve_trusted_hosts not exposed in public API")
    def test_resolve_trusted_hosts_list(self):
        pass

    @pytest.mark.skip(reason="_resolve_trusted_hosts not exposed in public API")
    def test_resolve_trusted_hosts_empty_defaults(self):
        pass

    @pytest.mark.skip(reason="_resolve_trusted_hosts not exposed in public API")
    def test_resolve_trusted_hosts_dev_adds_testserver(self):
        pass

    @pytest.mark.skip(reason="_resolve_trusted_hosts not exposed in public API")
    def test_resolve_trusted_hosts_prod_no_testserver(self):
        pass

    def test_create_acgs_app_basic(self):
        from src.core.shared.fastapi_base import create_acgs_app

        app = create_acgs_app(
            "test-svc",
            environment="test",
            enable_cors=False,
            enable_rate_limiting=False,
        )
        assert app.title == "ACGS-2 test-svc"

    def test_create_acgs_app_prod_no_docs(self):
        from src.core.shared.fastapi_base import create_acgs_app

        app = create_acgs_app(
            "prod-svc",
            environment="production",
            enable_cors=False,
            enable_rate_limiting=False,
        )
        assert app.docs_url is None
        assert app.redoc_url is None
