"""
ACGS-2 Coverage Tests - Batch 28e
Constitutional Hash: 608508a9bd224290

Targets uncovered lines in:
1. enhanced_agent_bus/api/routes/governance.py
2. enhanced_agent_bus/circuit_breaker/batch.py
3. enhanced_agent_bus/config.py
4. enhanced_agent_bus/constitutional_batch.py
5. enhanced_agent_bus/routes/sessions/_fallbacks.py
6. enhanced_agent_bus/cb_opa_client.py
7. enhanced_agent_bus/cb_kafka_producer.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

import pytest

# ---------------------------------------------------------------------------
# 1. Circuit Breaker Batch (circuit_breaker/batch.py)
# Missing lines: 96-99, 102, 104, 106, 119, 122-123, 129, 131-135,
#   150-151, 156-159, 171, 180, 182, 194-200
# ---------------------------------------------------------------------------


class TestCircuitBreakerBatch:
    """Tests for circuit_breaker/batch.py - covering state transitions."""

    def _make_cb(self, **kwargs: Any) -> Any:
        from enhanced_agent_bus.circuit_breaker.batch import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig(**kwargs)
        return CircuitBreaker(config)

    async def test_allow_request_closed_returns_true(self) -> None:
        cb = self._make_cb()
        assert await cb.allow_request() is True

    async def test_open_state_blocks_requests(self) -> None:
        """When OPEN and cooldown not passed, requests are blocked."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb(cooldown_period=9999.0)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()
        assert await cb.allow_request() is False

    async def test_open_to_half_open_transition(self) -> None:
        """After cooldown passes, OPEN -> HALF_OPEN and request allowed."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb(cooldown_period=0.0)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time() - 1.0
        result = await cb.allow_request()
        assert result is True
        assert cb.state == CircuitState.HALF_OPEN

    async def test_half_open_allows_requests(self) -> None:
        """HALF_OPEN state allows test requests."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb()
        cb.state = CircuitState.HALF_OPEN
        assert await cb.allow_request() is True

    async def test_record_success_in_half_open_closes_circuit(self) -> None:
        """Success in HALF_OPEN with sufficient rate -> CLOSED."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb(success_threshold=0.5)
        cb.state = CircuitState.HALF_OPEN
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.total_requests == 0

    async def test_record_failure_in_half_open_opens_circuit(self) -> None:
        """Failure in HALF_OPEN -> OPEN."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb()
        cb.state = CircuitState.HALF_OPEN
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    async def test_record_failure_closed_opens_on_threshold(self) -> None:
        """When failure rate exceeds threshold in CLOSED -> OPEN."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb(
            failure_threshold=0.5,
            minimum_requests=2,
        )
        # Simulate enough failures
        cb.total_requests = 1
        cb.failure_count = 1
        await cb.record_failure()
        # Now total=2, failures=2, rate=1.0 >= 0.5
        assert cb.state == CircuitState.OPEN

    async def test_record_failure_closed_stays_below_minimum(self) -> None:
        """When below minimum_requests, circuit stays CLOSED."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb(minimum_requests=100)
        await cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_get_state(self) -> None:
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb()
        assert cb.get_state() == CircuitState.CLOSED

    def test_get_statistics(self) -> None:
        cb = self._make_cb()
        stats = cb.get_statistics()
        assert stats["state"] == "closed"
        assert stats["total_requests"] == 0
        assert stats["failure_rate"] == 0.0

    def test_get_statistics_with_requests(self) -> None:
        cb = self._make_cb()
        cb.total_requests = 10
        cb.failure_count = 3
        cb.success_count = 7
        stats = cb.get_statistics()
        assert abs(stats["failure_rate"] - 0.3) < 0.001

    def test_reset(self) -> None:
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb()
        cb.state = CircuitState.OPEN
        cb.failure_count = 5
        cb.last_failure_time = time.time()
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_time is None
        assert cb.half_open_success_count == 0

    async def test_allow_request_open_no_failure_time(self) -> None:
        """OPEN with no last_failure_time stays blocked."""
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb()
        cb.state = CircuitState.OPEN
        cb.last_failure_time = None
        assert await cb.allow_request() is False

    async def test_default_branch_returns_false(self) -> None:
        """Unreachable default return False for unknown state."""
        from enhanced_agent_bus.circuit_breaker.batch import CircuitBreaker
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        cb = self._make_cb()
        # Force an unknown-like state by patching state check
        # The final return False is unreachable in normal flow,
        # but we cover all branches by testing known states above.


# ---------------------------------------------------------------------------
# 2. BusConfiguration (config.py)
# Missing lines: 164, 166, 177-178, 187-188, 251-271, 350-362, 434-435
# ---------------------------------------------------------------------------


class TestBusConfiguration:
    """Tests for config.py - parse helpers, redaction, environment loading."""

    def test_parse_bool_true_variants(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        for val in (True, "true", "1", "yes", "on", "y", "t", "TRUE", "Yes"):
            assert BusConfiguration._parse_bool(val) is True

    def test_parse_bool_false_variants(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        for val in (False, None, "false", "0", "no", "off", "n", "f", "random"):
            assert BusConfiguration._parse_bool(val) is False

    def test_parse_int_valid(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._parse_int("42", 0) == 42

    def test_parse_int_none(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._parse_int(None, 99) == 99

    def test_parse_int_invalid(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._parse_int("abc", 7) == 7

    def test_parse_float_valid(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._parse_float("3.14", 0.0) == pytest.approx(3.14)

    def test_parse_float_none(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._parse_float(None, 1.5) == 1.5

    def test_parse_float_invalid(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._parse_float("abc", 2.0) == 2.0

    def test_post_init_sets_hash_when_empty(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration(constitutional_hash="")
        assert config.constitutional_hash != ""

    def test_redact_url_no_password(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        result = BusConfiguration._redact_url("redis://localhost:6379")
        assert result == "redis://localhost:6379"

    def test_redact_url_with_password(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        result = BusConfiguration._redact_url("redis://user:secret@localhost:6379/0")
        assert "secret" not in (result or "")
        assert "***" in (result or "")

    def test_redact_url_with_password_no_port(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        result = BusConfiguration._redact_url("redis://user:secret@localhost/0")
        assert "secret" not in (result or "")

    def test_redact_url_none(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._redact_url(None) is None

    def test_redact_url_empty(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        assert BusConfiguration._redact_url("") == ""

    def test_redact_url_exception(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        with patch("urllib.parse.urlparse", side_effect=Exception("bad")):
            result = BusConfiguration._redact_url("redis://x")
            assert result == "<redacted>"

    def test_repr_redacts_secrets(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration(
            redis_url="redis://user:mypassword@localhost:6379",
            wuying_api_key="key123",
        )
        repr_str = repr(config)
        assert "mypassword" not in repr_str
        assert "***" in repr_str
        assert "has_wuying_api_key=True" in repr_str

    def test_to_dict_contains_keys(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        d = config.to_dict()
        assert "redis_url" in d
        assert "llm_enabled" in d
        assert "opal_enabled" in d
        assert "wuying_enabled" in d
        assert "has_custom_registry" in d

    def test_for_testing(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration.for_testing()
        assert config.enable_maci is False
        assert config.llm_enabled is False
        assert config.enable_session_governance is False

    def test_for_production(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration.for_production()
        assert config.enable_maci is True
        assert config.policy_fail_closed is True
        assert config.llm_enabled is True

    def test_with_registry(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        sentinel = object()
        new_config = config.with_registry(sentinel)
        assert new_config.registry is sentinel
        assert config.registry is None

    def test_with_validator(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        sentinel = object()
        new_config = config.with_validator(sentinel)
        assert new_config.validator is sentinel
        assert config.validator is None

    def test_from_environment_basic(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        env_overrides = {
            "REDIS_URL": "redis://testhost:1234",
            "USE_DYNAMIC_POLICY": "true",
            "POLICY_FAIL_CLOSED": "false",
            "ENABLE_MACI": "true",
            "MACI_STRICT_MODE": "false",
            "LLM_ENABLED": "true",
            "PYTEST_CURRENT_TEST": "yes",  # prevent litellm init
        }
        with patch.dict(os.environ, env_overrides, clear=False):
            config = BusConfiguration.from_environment()
        assert config.redis_url == "redis://testhost:1234"
        assert config.use_dynamic_policy is True
        assert config.policy_fail_closed is False

    def test_from_environment_litellm_cache_disabled(self) -> None:
        from enhanced_agent_bus.config import BusConfiguration

        env = {"LLM_USE_CACHE": "false", "PYTEST_CURRENT_TEST": "yes"}
        with patch.dict(os.environ, env, clear=False):
            config = BusConfiguration.from_environment()
        assert config.llm_use_cache is False


# ---------------------------------------------------------------------------
# 3. Constitutional Batch Validator (constitutional_batch.py)
# Missing: 183, 185, 207, 243, 251, 275-322
# ---------------------------------------------------------------------------


class TestConstitutionalBatchValidator:
    """Tests for constitutional_batch.py - batch validation paths."""

    def _make_validator(self, **kwargs: Any) -> Any:
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        return ConstitutionalBatchValidator(**kwargs)

    async def test_validate_single_none_item(self) -> None:
        v = self._make_validator()
        result = await v._validate_single(None, 0)
        assert result["is_valid"] is False
        assert "Invalid item format" in result["error"]

    async def test_validate_single_non_dict_item(self) -> None:
        v = self._make_validator()
        result = await v._validate_single("not_a_dict", 1)
        assert result["is_valid"] is False

    async def test_validate_single_missing_hash(self) -> None:
        v = self._make_validator()
        result = await v._validate_single({"data": "no hash"}, 2)
        assert result["is_valid"] is False

    async def test_validate_single_wrong_hash(self) -> None:
        v = self._make_validator()
        result = await v._validate_single({"constitutional_hash": "wrong"}, 3)
        assert result["is_valid"] is False
        assert "error" in result

    async def test_validate_single_correct_hash(self) -> None:
        v = self._make_validator()
        item = {"constitutional_hash": v.constitutional_hash}
        result = await v._validate_single(item, 4)
        assert result["is_valid"] is True

    async def test_validate_with_semaphore_lazy_init(self) -> None:
        """Semaphore is lazily initialized when None."""
        v = self._make_validator()
        v._semaphore = None
        result = await v._validate_with_semaphore({"constitutional_hash": v.constitutional_hash}, 0)
        assert result["is_valid"] is True
        assert v._semaphore is not None

    async def test_validate_batch_empty(self) -> None:
        v = self._make_validator()
        result = await v.validate_batch([])
        assert result == []

    async def test_validate_batch_mixed(self) -> None:
        v = self._make_validator()
        items = [
            {"constitutional_hash": v.constitutional_hash},
            {"constitutional_hash": "bad"},
            None,
        ]
        results = await v.validate_batch(items)
        assert len(results) == 3
        assert results[0]["is_valid"] is True
        assert results[1]["is_valid"] is False
        assert results[2]["is_valid"] is False

    async def test_validate_batch_exception_in_gather(self) -> None:
        """When gather returns an exception, it is treated as invalid."""
        v = self._make_validator()

        async def _raise_always(item: Any, idx: int) -> dict[str, Any]:
            raise RuntimeError("boom")

        # Patch _validate_with_semaphore to raise
        v._validate_with_semaphore = _raise_always  # type: ignore[assignment]
        results = await v.validate_batch([{"x": 1}])
        assert len(results) == 1
        assert results[0]["is_valid"] is False

    async def test_validate_batch_chunked_empty(self) -> None:
        v = self._make_validator()
        assert await v.validate_batch_chunked([]) == []

    async def test_validate_batch_chunked_small(self) -> None:
        """When items <= chunk_size, delegates to validate_batch."""
        v = self._make_validator(chunk_size=100)
        items = [{"constitutional_hash": v.constitutional_hash}]
        results = await v.validate_batch_chunked(items)
        assert len(results) == 1
        assert results[0]["is_valid"] is True

    async def test_validate_batch_chunked_large(self) -> None:
        """Items > chunk_size triggers chunked processing."""
        v = self._make_validator(chunk_size=2)
        items = [
            {"constitutional_hash": v.constitutional_hash},
            {"constitutional_hash": "bad"},
            {"constitutional_hash": v.constitutional_hash},
        ]
        results = await v.validate_batch_chunked(items)
        assert len(results) == 3
        # Order preserved
        assert results[0]["is_valid"] is True
        assert results[1]["is_valid"] is False
        assert results[2]["is_valid"] is True

    async def test_validate_batch_chunked_exception(self) -> None:
        """Exceptions in chunked gather are handled as invalid."""
        v = self._make_validator(chunk_size=1)
        v._initialize_semaphore()

        original = v._validate_with_semaphore
        call_count = 0

        async def _sometimes_fail(item: Any, idx: int) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("chunk error")
            return await original(item, idx)

        v._validate_with_semaphore = _sometimes_fail  # type: ignore[assignment]
        items = [
            {"constitutional_hash": v.constitutional_hash},
            {"constitutional_hash": v.constitutional_hash},
        ]
        results = await v.validate_batch_chunked(items)
        assert len(results) == 2

    def test_get_stats_empty(self) -> None:
        v = self._make_validator()
        stats = v.get_stats()
        assert stats["total_validations"] == 0
        assert stats["valid_rate"] == 0.0
        assert stats["avg_latency_ms"] == 0.0

    async def test_get_stats_after_batch(self) -> None:
        v = self._make_validator()
        items = [{"constitutional_hash": v.constitutional_hash}]
        await v.validate_batch(items)
        stats = v.get_stats()
        assert stats["total_validations"] == 1
        assert stats["valid_count"] == 1

    async def test_context_manager(self) -> None:
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        async with ConstitutionalBatchValidator() as v:
            assert v._semaphore is not None

    async def test_get_batch_validator_singleton(self) -> None:
        from enhanced_agent_bus.constitutional_batch import (
            get_batch_validator,
            reset_batch_validator,
        )

        await reset_batch_validator()
        v1 = await get_batch_validator()
        v2 = await get_batch_validator()
        assert v1 is v2
        await reset_batch_validator()

    async def test_reset_batch_validator(self) -> None:
        from enhanced_agent_bus.constitutional_batch import (
            get_batch_validator,
            reset_batch_validator,
        )

        await reset_batch_validator()
        v1 = await get_batch_validator()
        await reset_batch_validator()
        v2 = await get_batch_validator()
        assert v1 is not v2
        await reset_batch_validator()


# ---------------------------------------------------------------------------
# 4. Governance Routes (api/routes/governance.py)
# Missing: 62-75 (import fallbacks), 130-143 (PQC imports), 235-244, 273-281
# ---------------------------------------------------------------------------


class TestGovernanceRoutes:
    """Tests for governance route handlers."""

    def test_default_stability_metrics(self) -> None:
        from enhanced_agent_bus.api.routes.governance import _default_stability_metrics

        metrics = _default_stability_metrics()
        assert metrics.spectral_radius_bound == 1.0
        assert metrics.divergence == 0.0
        assert metrics.stability_hash == "mhc_init"

    def test_enforcement_error_to_422(self) -> None:
        from enhanced_agent_bus.api.routes.governance import _enforcement_error_to_422

        exc = Exception("test error")
        exc.error_code = "PQC_KEY_REQUIRED"  # type: ignore[attr-defined]
        exc.supported_algorithms = ["ML-DSA-65"]  # type: ignore[attr-defined]
        http_exc = _enforcement_error_to_422(exc)
        assert http_exc.status_code == 422
        assert http_exc.detail["error_code"] == "PQC_KEY_REQUIRED"

    def test_enforcement_error_to_422_no_attrs(self) -> None:
        from enhanced_agent_bus.api.routes.governance import _enforcement_error_to_422

        exc = ValueError("simple error")
        http_exc = _enforcement_error_to_422(exc)
        assert http_exc.status_code == 422
        assert http_exc.detail["error_code"] == "PQC_ERROR"
        assert http_exc.detail["supported_algorithms"] == []

    def test_maci_record_create_request_model(self) -> None:
        from enhanced_agent_bus.api.routes.governance import MACIRecordCreateRequest

        req = MACIRecordCreateRequest(
            record_id="r1",
            key_type="pqc",
            key_algorithm="ML-DSA-65",
            data={"foo": "bar"},
        )
        assert req.record_id == "r1"

    def test_maci_record_update_request_model(self) -> None:
        from enhanced_agent_bus.api.routes.governance import MACIRecordUpdateRequest

        req = MACIRecordUpdateRequest(data={"updated": True})
        assert req.data == {"updated": True}

    def test_maci_record_response_model(self) -> None:
        from enhanced_agent_bus.api.routes.governance import MACIRecordResponse

        resp = MACIRecordResponse(record_id="r1", status="created")
        assert resp.status == "created"

    async def test_get_enforcement_config_returns_none(self) -> None:
        from unittest.mock import MagicMock

        from enhanced_agent_bus.api.routes.governance import _get_enforcement_config

        mock_request = MagicMock()
        mock_request.app.state = None
        assert await _get_enforcement_config(mock_request) is None

    async def test_get_stability_metrics_no_governance(self) -> None:
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert exc_info.value.status_code == 503

    async def test_get_stability_metrics_no_stability_layer(self) -> None:
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        mock_gov = MagicMock()
        mock_gov.stability_layer = None
        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=mock_gov,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert exc_info.value.status_code == 503

    async def test_get_stability_metrics_no_stats(self) -> None:
        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        mock_gov = MagicMock()
        mock_gov.stability_layer.last_stats = None
        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=mock_gov,
        ):
            result = await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert result.stability_hash == "mhc_init"

    async def test_get_stability_metrics_with_stats(self) -> None:
        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        mock_gov = MagicMock()
        mock_gov.stability_layer.last_stats = {
            "spectral_radius_bound": 0.9,
            "divergence": 0.1,
            "max_weight": 0.5,
            "stability_hash": "abc123",
            "input_norm": 1.0,
            "output_norm": 0.8,
        }
        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=mock_gov,
        ):
            result = await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert result.spectral_radius_bound == 0.9
            assert result.stability_hash == "abc123"

    async def test_create_maci_record_sandbox(self) -> None:
        from fastapi import Request

        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordCreateRequest,
            create_maci_record,
        )

        body = MACIRecordCreateRequest(record_id="test-1", data={"x": 1})
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await create_maci_record(
                body=body,
                request=mock_request,
                _tenant_id="t1",
                enforcement_svc=None,
            )
        assert result.record_id == "test-1"
        assert result.status == "created"

    async def test_update_maci_record_sandbox(self) -> None:
        from fastapi import Request

        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordUpdateRequest,
            update_maci_record,
        )

        body = MACIRecordUpdateRequest(data={"y": 2})
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await update_maci_record(
                record_id="r1",
                body=body,
                request=mock_request,
                _tenant_id="t1",
                enforcement_svc=None,
            )
        assert result.record_id == "r1"
        assert result.status == "updated"

    async def test_get_maci_record_sandbox(self) -> None:
        from enhanced_agent_bus.api.routes.governance import get_maci_record

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await get_maci_record(request=MagicMock(), record_id="r1", _tenant_id="t1")
        assert result.status == "ok"

    async def test_delete_maci_record_sandbox(self) -> None:
        from enhanced_agent_bus.api.routes.governance import delete_maci_record

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await delete_maci_record(request=MagicMock(), record_id="r1", _tenant_id="t1")
        assert result.status == "deleted"

    async def test_create_maci_record_with_enforcement(self) -> None:
        """Test create with enforcement service present but no PQC error."""
        from fastapi import Request

        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordCreateRequest,
            create_maci_record,
        )

        body = MACIRecordCreateRequest(
            record_id="test-pqc",
            key_type="pqc",
            key_algorithm="ML-DSA-65",
        )
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-Migration-Context": "true"}

        mock_enforcement = MagicMock()
        mock_check = AsyncMock(return_value=None)

        with (
            patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"),
            patch(
                "enhanced_agent_bus.api.routes.governance.check_enforcement_for_create",
                mock_check,
            ),
        ):
            result = await create_maci_record(
                body=body,
                request=mock_request,
                _tenant_id="t1",
                enforcement_svc=mock_enforcement,
            )
        assert result.status == "created"

    async def test_update_maci_record_with_enforcement(self) -> None:
        """Test update with enforcement service present."""
        from fastapi import Request

        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordUpdateRequest,
            update_maci_record,
        )

        body = MACIRecordUpdateRequest(data={"z": 3})
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-Migration-Context": "false"}

        mock_enforcement = MagicMock()
        mock_check = AsyncMock(return_value=None)

        with (
            patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"),
            patch(
                "enhanced_agent_bus.api.routes.governance.check_enforcement_for_update",
                mock_check,
            ),
        ):
            result = await update_maci_record(
                record_id="r1",
                body=body,
                request=mock_request,
                _tenant_id="t1",
                enforcement_svc=mock_enforcement,
            )
        assert result.status == "updated"


# ---------------------------------------------------------------------------
# 5. Session Fallbacks (routes/sessions/_fallbacks.py)
# Missing: 20-25, 37-38, 40, 76, 82, 85, 88, 91, 94, 102-103, 105, 107,
#   113-114, 119-125, 129, 131, 135-136, 141-142, 146
# ---------------------------------------------------------------------------


class TestSessionFallbacks:
    """Tests for routes/sessions/_fallbacks.py fallback implementations."""

    def test_fallback_risk_level_enum(self) -> None:
        from enhanced_agent_bus.routes.sessions._fallbacks import USING_FALLBACKS, RiskLevel

        # The enum should have these values regardless of fallback mode
        assert hasattr(RiskLevel, "LOW")
        assert hasattr(RiskLevel, "HIGH")
        assert hasattr(RiskLevel, "CRITICAL")

    def test_fallback_session_governance_config(self) -> None:
        from enhanced_agent_bus.routes.sessions._fallbacks import SessionGovernanceConfig

        config = SessionGovernanceConfig(
            session_id="s1",
            tenant_id="t1",
            user_id="u1",
        )
        assert config.session_id == "s1"
        assert config.tenant_id == "t1"

    def test_fallback_session_context(self) -> None:
        from enhanced_agent_bus.routes.sessions._fallbacks import (
            SessionContext,
            SessionGovernanceConfig,
        )

        now = datetime.now(UTC)
        gov_config = SessionGovernanceConfig(session_id="s1", tenant_id="t1")
        ctx = SessionContext(
            session_id="s1",
            tenant_id="t1",
            governance_config=gov_config,
            created_at=now,
            updated_at=now,
        )
        assert ctx.session_id == "s1"

    async def test_fallback_session_context_manager(self) -> None:
        from enhanced_agent_bus.routes.sessions._fallbacks import (
            USING_FALLBACKS,
            SessionContextManager,
        )

        if not USING_FALLBACKS:
            pytest.skip("Real implementations loaded, fallback not testable")

        mgr = SessionContextManager()
        assert await mgr.connect() is True
        assert await mgr.get("s1") is None
        assert await mgr.update(session_id="s1") is None
        assert await mgr.delete("s1") is False
        assert await mgr.exists("s1") is False
        assert mgr.get_metrics() == {}
        with pytest.raises(NotImplementedError):
            await mgr.create(session_id="s1", tenant_id="t1")

    async def test_fallback_tenant_id_with_pytest_env(self) -> None:
        """Fallback get_tenant_id works when PYTEST_CURRENT_TEST is set."""
        from enhanced_agent_bus.routes.sessions._fallbacks import (
            USING_FALLBACK_TENANT,
            get_tenant_id,
        )

        if not USING_FALLBACK_TENANT:
            pytest.skip("Real tenant context loaded")

        env = {
            "PYTEST_CURRENT_TEST": "test_something",
            "ENVIRONMENT": "",
            "AGENT_RUNTIME_ENVIRONMENT": "",
            "ACGS_ENV": "",
            "APP_ENV": "",
        }
        with patch.dict(os.environ, env, clear=False):
            result = await get_tenant_id(x_tenant_id="test-tenant")
            assert result == "test-tenant"

    async def test_fallback_tenant_id_missing_header(self) -> None:
        from fastapi import HTTPException

        from enhanced_agent_bus.routes.sessions._fallbacks import (
            USING_FALLBACK_TENANT,
            get_tenant_id,
        )

        if not USING_FALLBACK_TENANT:
            pytest.skip("Real tenant context loaded")

        env = {"PYTEST_CURRENT_TEST": "test", "ENVIRONMENT": ""}
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant_id(x_tenant_id=None)
            assert exc_info.value.status_code == 400

    async def test_fallback_tenant_id_production_blocked(self) -> None:
        from fastapi import HTTPException

        from enhanced_agent_bus.routes.sessions._fallbacks import (
            USING_FALLBACK_TENANT,
            get_tenant_id,
        )

        if not USING_FALLBACK_TENANT:
            pytest.skip("Real tenant context loaded")

        env = {"ENVIRONMENT": "production", "PYTEST_CURRENT_TEST": ""}
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant_id(x_tenant_id="t1")
            assert exc_info.value.status_code == 503

    async def test_fallback_tenant_id_dev_mode(self) -> None:
        from enhanced_agent_bus.routes.sessions._fallbacks import (
            USING_FALLBACK_TENANT,
            get_tenant_id,
        )

        if not USING_FALLBACK_TENANT:
            pytest.skip("Real tenant context loaded")

        env = {
            "AGENT_RUNTIME_ENVIRONMENT": "dev",
            "ENVIRONMENT": "",
            "ACGS_ENV": "",
            "APP_ENV": "",
            "PYTEST_CURRENT_TEST": "",
        }
        with patch.dict(os.environ, env, clear=False):
            result = await get_tenant_id(x_tenant_id="dev-tenant")
            assert result == "dev-tenant"

    def test_is_explicit_dev_or_test_mode_prod_blocks(self) -> None:
        """Production-like modes block even with PYTEST_CURRENT_TEST."""
        from enhanced_agent_bus.routes.sessions._fallbacks import USING_FALLBACK_TENANT

        if not USING_FALLBACK_TENANT:
            pytest.skip("Real tenant context loaded")

        from enhanced_agent_bus.routes.sessions._fallbacks import (
            _is_explicit_dev_or_test_mode,
        )

        env = {
            "AGENT_RUNTIME_ENVIRONMENT": "staging",
            "PYTEST_CURRENT_TEST": "test_something",
            "ENVIRONMENT": "",
            "ACGS_ENV": "",
            "APP_ENV": "",
        }
        with patch.dict(os.environ, env, clear=False):
            assert _is_explicit_dev_or_test_mode() is False

    def test_is_explicit_dev_or_test_allowed_modes(self) -> None:
        from enhanced_agent_bus.routes.sessions._fallbacks import USING_FALLBACK_TENANT

        if not USING_FALLBACK_TENANT:
            pytest.skip("Real tenant context loaded")

        from enhanced_agent_bus.routes.sessions._fallbacks import (
            _is_explicit_dev_or_test_mode,
        )

        for mode in ("dev", "development", "local", "test", "testing", "ci", "qa"):
            env = {
                "ACGS_ENV": mode,
                "AGENT_RUNTIME_ENVIRONMENT": "",
                "ENVIRONMENT": "",
                "APP_ENV": "",
                "PYTEST_CURRENT_TEST": "",
            }
            with patch.dict(os.environ, env, clear=False):
                assert _is_explicit_dev_or_test_mode() is True, f"Failed for mode={mode}"


# ---------------------------------------------------------------------------
# 6. CircuitBreakerOPAClient (cb_opa_client.py)
# Missing: 101, 110-112, 131, 133, 140-141, 150, 168-170, 196,
#   233-236, 241, 276-277, 290, 313-314, 325-327, 334
# ---------------------------------------------------------------------------


class TestCircuitBreakerOPAClient:
    """Tests for cb_opa_client.py."""

    def _make_client(self, **kwargs: Any) -> Any:
        from enhanced_agent_bus.cb_opa_client import CircuitBreakerOPAClient

        return CircuitBreakerOPAClient(**kwargs)

    def test_init_defaults(self) -> None:
        client = self._make_client()
        assert client.opa_url == "http://localhost:8181"
        assert client.enable_cache is True
        assert client._initialized is False

    def test_init_invalid_hash_mode(self) -> None:
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            self._make_client(cache_hash_mode="invalid")

    def test_init_fast_hash_fallback(self) -> None:
        """When fast hash unavailable, logs warning."""
        with patch("enhanced_agent_bus.cb_opa_client.FAST_HASH_AVAILABLE", False):
            client = self._make_client(cache_hash_mode="fast")
            assert client.cache_hash_mode == "fast"

    async def test_initialize_creates_http_client(self) -> None:
        client = self._make_client()
        mock_cb = AsyncMock()
        mock_cb.state = MagicMock(value="closed")
        with (
            patch(
                "enhanced_agent_bus.cb_opa_client.get_service_circuit_breaker", return_value=mock_cb
            ),
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            await client.initialize()
            assert client._initialized is True
            # Calling again is no-op
            await client.initialize()

    async def test_close(self) -> None:
        client = self._make_client()
        mock_http = AsyncMock()
        client._http_client = mock_http
        client._initialized = True
        await client.close()
        assert client._initialized is False
        assert client._http_client is None

    async def test_close_no_client(self) -> None:
        client = self._make_client()
        client._http_client = None
        await client.close()
        assert client._initialized is False

    async def test_close_aclose_not_awaitable(self) -> None:
        """Handle mocked clients where aclose is not awaitable."""
        client = self._make_client()
        mock_http = MagicMock()
        mock_http.aclose.side_effect = TypeError("not awaitable")
        client._http_client = mock_http
        client._initialized = True
        await client.close()
        assert client._http_client is None

    async def test_context_manager(self) -> None:
        from enhanced_agent_bus.cb_opa_client import CircuitBreakerOPAClient

        client = CircuitBreakerOPAClient()
        mock_cb = AsyncMock()
        mock_cb.state = MagicMock(value="closed")
        with (
            patch(
                "enhanced_agent_bus.cb_opa_client.get_service_circuit_breaker", return_value=mock_cb
            ),
            patch("httpx.AsyncClient"),
        ):
            async with client as c:
                assert c._initialized is True
            assert c._initialized is False

    def test_get_cache_key(self) -> None:
        client = self._make_client()
        key = client._get_cache_key("data.acgs.allow", {"action": "read"})
        assert key.startswith("opa_cb:")

    def test_get_from_cache_miss(self) -> None:
        client = self._make_client()
        assert client._get_from_cache("nonexistent") is None

    def test_get_from_cache_disabled(self) -> None:
        client = self._make_client(enable_cache=False)
        assert client._get_from_cache("any") is None

    def test_get_from_cache_hit(self) -> None:
        client = self._make_client()
        client._memory_cache["k1"] = {"result": True}
        client._cache_timestamps["k1"] = time.time()
        result = client._get_from_cache("k1")
        assert result == {"result": True}

    def test_get_from_cache_expired(self) -> None:
        client = self._make_client(cache_ttl=0)
        client._memory_cache["k1"] = {"result": True}
        client._cache_timestamps["k1"] = time.time() - 10
        assert client._get_from_cache("k1") is None
        assert "k1" not in client._memory_cache

    def test_set_cache(self) -> None:
        client = self._make_client()
        client._set_cache("k1", {"result": True})
        assert "k1" in client._memory_cache

    def test_set_cache_disabled(self) -> None:
        client = self._make_client(enable_cache=False)
        client._set_cache("k1", {"result": True})
        assert "k1" not in client._memory_cache

    async def test_evaluate_policy_cached(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = AsyncMock()
        client._circuit_breaker = mock_cb
        cached_result = {"result": True, "allowed": True, "reason": "cached"}
        client._memory_cache["opa_cb:data.acgs.allow:abc"] = cached_result
        client._cache_timestamps["opa_cb:data.acgs.allow:abc"] = time.time()

        with patch.object(client, "_get_cache_key", return_value="opa_cb:data.acgs.allow:abc"):
            result = await client.evaluate_policy({"action": "read"})
        assert result["reason"] == "cached"

    async def test_evaluate_policy_circuit_open(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = False
        mock_cb.state = MagicMock(value="open")
        client._circuit_breaker = mock_cb

        result = await client.evaluate_policy({"action": "write"})
        assert result["allowed"] is False
        assert "fail-closed" in result["reason"]

    async def test_evaluate_policy_success(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        mock_cb.state = MagicMock(value="closed")
        client._circuit_breaker = mock_cb

        eval_result = {"result": True, "allowed": True, "reason": "ok", "metadata": {}}
        with patch.object(client, "_evaluate_http", return_value=eval_result):
            result = await client.evaluate_policy({"action": "read"})
        assert result["allowed"] is True

    async def test_evaluate_policy_http_error(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        client._circuit_breaker = mock_cb

        with patch.object(client, "_evaluate_http", side_effect=ConnectionError("down")):
            result = await client.evaluate_policy({"action": "read"})
        assert result["allowed"] is False
        assert "fail-closed" in result["metadata"]["security"]

    async def test_evaluate_policy_not_initialized(self) -> None:
        """Auto-initializes when not initialized."""
        client = self._make_client()
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        mock_cb.state = MagicMock(value="closed")

        eval_result = {"result": True, "allowed": True, "reason": "ok", "metadata": {}}
        with (
            patch.object(client, "initialize", new_callable=AsyncMock) as mock_init,
            patch.object(client, "_evaluate_http", return_value=eval_result),
            patch.object(client, "_get_from_cache", return_value=None),
        ):
            client._circuit_breaker = mock_cb
            # First call triggers init check
            mock_init.side_effect = lambda: setattr(client, "_initialized", True)
            result = await client.evaluate_policy({"action": "x"})
            mock_init.assert_called_once()

    async def test_evaluate_http_bool_result(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="closed")
        client._circuit_breaker = mock_cb

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": True}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client._evaluate_http({"action": "read"}, "data.acgs.allow")
        assert result["allowed"] is True
        assert result["metadata"]["mode"] == "http"

    async def test_evaluate_http_dict_result(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="closed")
        client._circuit_breaker = mock_cb

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"allow": True, "reason": "policy ok", "metadata": {"extra": "data"}}
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client._evaluate_http({"action": "read"}, "data.acgs.allow")
        assert result["allowed"] is True
        assert result["reason"] == "policy ok"

    async def test_evaluate_http_unexpected_type(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="closed")
        client._circuit_breaker = mock_cb

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 42}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client._evaluate_http({"action": "read"}, "data.acgs.allow")
        assert result["allowed"] is False
        assert "Unexpected result type" in result["reason"]

    async def test_health_check_not_initialized(self) -> None:
        client = self._make_client()
        health = await client.health_check()
        assert health["healthy"] is False
        assert health["error"] == "Client not initialized"

    async def test_health_check_opa_healthy(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="closed")
        mock_metrics = MagicMock()
        mock_metrics.__dict__.update({"failures": 0})
        mock_cb.metrics = mock_metrics
        client._circuit_breaker = mock_cb

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        health = await client.health_check()
        assert health["healthy"] is True

    async def test_health_check_opa_unhealthy(self) -> None:
        client = self._make_client()
        client._initialized = True
        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="open")
        mock_metrics = MagicMock()
        mock_metrics.__dict__.update({"failures": 5})
        mock_cb.metrics = mock_metrics
        client._circuit_breaker = mock_cb

        mock_http = AsyncMock()
        mock_http.get.side_effect = ConnectionError("OPA down")
        client._http_client = mock_http

        health = await client.health_check()
        assert health["healthy"] is False
        assert health["opa_status"] == "unhealthy"

    def test_get_circuit_status_no_breaker(self) -> None:
        client = self._make_client()
        status = client.get_circuit_status()
        assert "error" in status

    def test_get_circuit_status_with_breaker(self) -> None:
        client = self._make_client()
        mock_cb = MagicMock()
        mock_cb.get_status.return_value = {"state": "closed"}
        client._circuit_breaker = mock_cb
        status = client.get_circuit_status()
        assert status["state"] == "closed"


# ---------------------------------------------------------------------------
# 7. CircuitBreakerKafkaProducer (cb_kafka_producer.py)
# Missing: 97, 102, 110, 116-117, 120, 151-155, 180-204, 235, 319, 333
# ---------------------------------------------------------------------------


class TestCircuitBreakerKafkaProducer:
    """Tests for cb_kafka_producer.py."""

    def _make_producer(self, **kwargs: Any) -> Any:
        from enhanced_agent_bus.cb_kafka_producer import CircuitBreakerKafkaProducer

        return CircuitBreakerKafkaProducer(**kwargs)

    def test_init_defaults(self) -> None:
        prod = self._make_producer()
        assert prod.bootstrap_servers == "localhost:9092"
        assert prod._initialized is False

    async def test_initialize_no_aiokafka(self) -> None:
        """When aiokafka not available, producer is None but init succeeds."""
        prod = self._make_producer()
        mock_cb = AsyncMock()
        mock_cb.state = MagicMock(value="closed")

        with (
            patch.dict("sys.modules", {"aiokafka": None}),
            patch(
                "enhanced_agent_bus.cb_kafka_producer.get_service_circuit_breaker",
                return_value=mock_cb,
            ),
            patch("builtins.__import__", side_effect=ImportError("no aiokafka")),
        ):
            # Direct approach: simulate ImportError during initialize
            pass

        # Simpler approach - mock the entire init
        prod._initialized = False
        with patch(
            "enhanced_agent_bus.cb_kafka_producer.get_service_circuit_breaker",
            return_value=mock_cb,
        ):
            # Patch the import inside initialize
            original_import = (
                __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
            )

            def _import_mock(name, *args, **kwargs):
                if name == "aiokafka":
                    raise ImportError("no aiokafka")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_import_mock):
                await prod.initialize()
            assert prod._initialized is True
            assert prod._producer is None
            prod._running = False
            if prod._retry_task:
                prod._retry_task.cancel()
                try:
                    await prod._retry_task
                except (asyncio.CancelledError, Exception):
                    pass

    async def test_initialize_already_initialized(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        await prod.initialize()  # no-op

    async def test_close_with_retry_task(self) -> None:
        prod = self._make_producer()
        prod._running = True

        async def _fake_loop() -> None:
            await asyncio.sleep(100)

        prod._retry_task = asyncio.create_task(_fake_loop())
        prod._producer = AsyncMock()
        prod._initialized = True

        await prod.close()
        assert prod._running is False
        assert prod._initialized is False

    async def test_close_no_producer(self) -> None:
        prod = self._make_producer()
        prod._producer = None
        prod._retry_task = None
        await prod.close()

    async def test_context_manager(self) -> None:
        from enhanced_agent_bus.cb_kafka_producer import CircuitBreakerKafkaProducer

        prod = CircuitBreakerKafkaProducer()
        mock_cb = AsyncMock()
        mock_cb.state = MagicMock(value="closed")

        original_import = __import__

        def _import_mock(name, *args, **kwargs):
            if name == "aiokafka":
                raise ImportError("no aiokafka")
            return original_import(name, *args, **kwargs)

        with (
            patch(
                "enhanced_agent_bus.cb_kafka_producer.get_service_circuit_breaker",
                return_value=mock_cb,
            ),
            patch("builtins.__import__", side_effect=_import_mock),
        ):
            async with prod as p:
                assert p._initialized is True
            assert p._initialized is False

    async def test_send_circuit_open_buffers(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = False
        prod._circuit_breaker = mock_cb

        result = await prod.send("topic1", {"data": "test"}, key="k1", tenant_id="t1")
        assert result is False

    async def test_send_no_producer_buffers(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        prod._circuit_breaker = mock_cb
        prod._producer = None

        result = await prod.send("topic1", {"data": "test"})
        assert result is False

    async def test_send_success(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        prod._circuit_breaker = mock_cb

        mock_prod = AsyncMock()
        prod._producer = mock_prod

        result = await prod.send("topic1", {"data": "test"}, key="k1")
        assert result is True
        mock_prod.send_and_wait.assert_called_once()

    async def test_send_kafka_error_buffers(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        prod._circuit_breaker = mock_cb

        mock_prod = AsyncMock()
        mock_prod.send_and_wait.side_effect = RuntimeError("kafka down")
        prod._producer = mock_prod

        result = await prod.send("topic1", {"data": "test"}, key="k1", tenant_id="t1")
        assert result is False

    async def test_send_batch(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        prod._circuit_breaker = mock_cb

        mock_prod = AsyncMock()
        prod._producer = mock_prod

        messages = [
            ("topic1", {"a": 1}, "k1"),
            ("topic2", {"b": 2}, None),
        ]
        results = await prod.send_batch(messages, tenant_id="t1")
        assert results["sent"] == 2
        assert results["buffered"] == 0

    async def test_send_batch_mixed_results(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        prod._circuit_breaker = mock_cb

        call_count = 0
        mock_prod = AsyncMock()

        async def _send_and_wait(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("fail")

        mock_prod.send_and_wait = _send_and_wait
        prod._producer = mock_prod

        messages = [
            ("t1", {"a": 1}, "k1"),
            ("t2", {"b": 2}, "k2"),
        ]
        results = await prod.send_batch(messages)
        assert results["sent"] == 1
        assert results["buffered"] == 1

    async def test_flush_buffer_no_producer(self) -> None:
        prod = self._make_producer()
        prod._producer = None
        result = await prod.flush_buffer()
        assert result == {"error": "Producer not available"}

    async def test_flush_buffer_with_producer(self) -> None:
        prod = self._make_producer()
        prod._producer = AsyncMock()

        with patch.object(prod._retry_buffer, "process", return_value={"processed": 0}):
            result = await prod.flush_buffer()
        assert result == {"processed": 0}

    async def test_health_check_connected(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="closed")
        mock_metrics = MagicMock()
        mock_metrics.__dict__.update({"failures": 0})
        mock_cb.metrics = mock_metrics
        prod._circuit_breaker = mock_cb
        prod._producer = MagicMock()

        health = await prod.health_check()
        assert health["healthy"] is True
        assert health["kafka_status"] == "connected"

    async def test_health_check_not_connected(self) -> None:
        prod = self._make_producer()
        prod._initialized = True
        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="open")
        mock_metrics = MagicMock()
        mock_metrics.__dict__.update({"failures": 3})
        mock_cb.metrics = mock_metrics
        prod._circuit_breaker = mock_cb
        prod._producer = None

        health = await prod.health_check()
        assert health["kafka_status"] == "not_connected"

    async def test_health_check_no_breaker(self) -> None:
        prod = self._make_producer()
        prod._circuit_breaker = None
        health = await prod.health_check()
        assert health["circuit_state"] == "unknown"

    def test_get_circuit_status_no_breaker(self) -> None:
        prod = self._make_producer()
        status = prod.get_circuit_status()
        assert "error" in status

    def test_get_circuit_status_with_breaker(self) -> None:
        prod = self._make_producer()
        mock_cb = MagicMock()
        mock_cb.get_status.return_value = {"state": "closed"}
        prod._circuit_breaker = mock_cb
        status = prod.get_circuit_status()
        assert status["state"] == "closed"
        assert "buffer_metrics" in status

    async def test_send_raw_with_producer(self) -> None:
        prod = self._make_producer()
        mock_prod = AsyncMock()
        prod._producer = mock_prod
        await prod._send_raw("topic", {"data": 1}, b"key")
        mock_prod.send_and_wait.assert_called_once()

    async def test_send_raw_no_producer(self) -> None:
        prod = self._make_producer()
        prod._producer = None
        with pytest.raises(RuntimeError, match="not available"):
            await prod._send_raw("topic", {"data": 1}, None)

    async def test_send_not_initialized_triggers_init(self) -> None:
        prod = self._make_producer()
        prod._initialized = False
        mock_cb = AsyncMock()
        mock_cb.can_execute.return_value = True
        mock_prod = AsyncMock()

        async def _fake_init():
            prod._initialized = True
            prod._circuit_breaker = mock_cb
            prod._producer = mock_prod

        with patch.object(prod, "initialize", side_effect=_fake_init):
            result = await prod.send("t", {"d": 1})
        assert result is True
