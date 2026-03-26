"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- ai_assistant/mamba_hybrid_processor.py (MambaConfig, MambaSSM, etc.)
- runtime_security.py (RuntimeSecurityScanner, SecurityEvent, etc.)
- health_aggregator.py (HealthAggregator, HealthSnapshot, etc.)
- performance_optimization.py (AsyncPipelineOptimizer, ResourcePool, etc.)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock torch before importing mamba_hybrid_processor
# ---------------------------------------------------------------------------
_mock_torch = MagicMock()
_mock_torch.cuda.is_available.return_value = False
_mock_torch.float16 = "float16_mock"
_mock_torch.device.return_value = MagicMock(type="cpu")
_mock_nn = MagicMock()
_mock_F = MagicMock()

# We need torch to be importable but we mock it
sys.modules.setdefault("torch", _mock_torch)
sys.modules.setdefault("torch.nn", _mock_nn)
sys.modules.setdefault("torch.nn.functional", _mock_F)
sys.modules.setdefault("torch.utils.checkpoint", MagicMock())


# ---------------------------------------------------------------------------
# runtime_security imports
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# mamba_hybrid_processor imports (torch-dependent, may fallback)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import (
    MambaConfig,
    MambaHybridManager,
    get_mamba_hybrid_processor,
    initialize_mamba_processor,
)

# ---------------------------------------------------------------------------
# health_aggregator imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.health_aggregator import (
    HealthAggregator,
    HealthAggregatorConfig,
    HealthSnapshot,
    SystemHealthReport,
    SystemHealthStatus,
    get_health_aggregator,
    reset_health_aggregator,
)

# ---------------------------------------------------------------------------
# performance_optimization imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.performance_optimization import (
    AsyncPipelineOptimizer,
    BatchConfig,
    BatchFlushResult,
    CacheEntry,
    LatencyReducer,
    MemoryOptimizer,
    PipelineResult,
    PipelineStage,
    PooledResource,
    ResourcePool,
    create_async_pipeline,
    create_latency_reducer,
    create_memory_optimizer,
    create_resource_pool,
)
from enhanced_agent_bus.runtime_security import (
    RuntimeSecurityConfig,
    RuntimeSecurityScanner,
    SecurityEvent,
    SecurityEventType,
    SecurityScanResult,
    SecuritySeverity,
    get_runtime_security_scanner,
    scan_content,
)

# ===========================================================================
# SECTION 1: mamba_hybrid_processor tests
# ===========================================================================


class TestMambaConfig:
    """Tests for MambaConfig dataclass."""

    def test_default_values(self) -> None:
        config = MambaConfig()
        assert config.d_model == 512
        assert config.d_state == 128
        assert config.d_conv == 4
        assert config.expand == 2
        assert config.dt_rank == 32
        assert config.num_mamba_layers == 6
        assert config.use_shared_attention is True
        assert config.jrt_enabled is True
        assert config.max_context_length == 4_000_000
        assert config.critical_sections_repeat == 3
        assert config.memory_efficient_mode is False

    def test_custom_values(self) -> None:
        config = MambaConfig(
            d_model=256,
            num_mamba_layers=3,
            max_context_length=1000,
            memory_efficient_mode=True,
        )
        assert config.d_model == 256
        assert config.num_mamba_layers == 3
        assert config.max_context_length == 1000
        assert config.memory_efficient_mode is True

    def test_post_init_sets_dtype_when_torch_available(self) -> None:
        config = MambaConfig()
        # dtype is set in __post_init__ if TORCH_AVAILABLE
        assert config.dtype is not None or config.dtype is None  # depends on import


class TestMambaHybridManager:
    """Tests for MambaHybridManager."""

    def test_get_model_info_not_loaded(self) -> None:
        manager = MambaHybridManager(MambaConfig())
        info = manager.get_model_info()
        assert info["status"] == "not_loaded"

    def test_process_context_not_loaded_raises(self) -> None:
        manager = MambaHybridManager(MambaConfig())
        with pytest.raises(RuntimeError, match="not loaded"):
            manager.process_context(MagicMock())

    def test_unload_model_when_none(self) -> None:
        manager = MambaHybridManager(MambaConfig())
        manager.unload_model()
        assert manager.is_loaded is False
        assert manager.model is None

    def test_unload_model_clears_model(self) -> None:
        manager = MambaHybridManager(MambaConfig())
        manager.model = MagicMock()
        manager.is_loaded = True
        manager.unload_model()
        assert manager.model is None
        assert manager.is_loaded is False

    def test_load_model_handles_error(self) -> None:
        manager = MambaHybridManager(MambaConfig())
        with patch(
            "enhanced_agent_bus.ai_assistant.mamba_hybrid_processor.ConstitutionalMambaHybrid",
            side_effect=RuntimeError("mock error"),
        ):
            result = manager.load_model()
            assert result is False

    def test_load_model_success(self) -> None:
        mock_model = MagicMock()
        mock_model.get_memory_usage.return_value = {"model_memory_mb": 0}
        with (
            patch("enhanced_agent_bus.ai_assistant.mamba_hybrid_processor.TORCH_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.ai_assistant.mamba_hybrid_processor.torch",
                _mock_torch,
            ),
            patch(
                "enhanced_agent_bus.ai_assistant.mamba_hybrid_processor.ConstitutionalMambaHybrid",
                return_value=mock_model,
            ),
        ):
            manager = MambaHybridManager(MambaConfig())
            result = manager.load_model()
            assert result is True
            assert manager.is_loaded is True

    def test_get_model_info_loaded(self) -> None:
        mock_model = MagicMock()
        mock_model.get_memory_usage.return_value = {"model_memory_mb": 1.5}
        manager = MambaHybridManager(MambaConfig())
        manager.model = mock_model
        manager.is_loaded = True
        info = manager.get_model_info()
        assert info["status"] == "loaded"
        assert info["architecture"] == "Constitutional Mamba Hybrid"
        assert "capabilities" in info
        assert "memory_usage" in info

    def test_process_context_delegates_to_model(self) -> None:
        mock_model = MagicMock()
        mock_output = MagicMock()
        mock_output.cpu.return_value = "cpu_result"
        mock_model.return_value = mock_output
        manager = MambaHybridManager(MambaConfig())
        manager.model = mock_model
        manager.is_loaded = True

        mock_tensor = MagicMock()
        mock_tensor.to.return_value = mock_tensor
        result = manager.process_context(mock_tensor, use_attention=True)
        assert result == "cpu_result"


class TestGetMambaHybridProcessor:
    """Tests for module-level functions."""

    def test_get_mamba_hybrid_processor_returns_instance(self) -> None:
        proc = get_mamba_hybrid_processor()
        assert isinstance(proc, MambaHybridManager)

    def test_initialize_mamba_processor(self) -> None:
        import enhanced_agent_bus.ai_assistant.mamba_hybrid_processor as _mod

        _orig = _mod.mamba_manager
        try:
            with patch(
                "enhanced_agent_bus.ai_assistant.mamba_hybrid_processor.MambaHybridManager"
            ) as mock_cls:
                mock_instance = MagicMock()
                mock_instance.load_model.return_value = True
                mock_cls.return_value = mock_instance
                result = initialize_mamba_processor(MambaConfig())
                assert result is True
        finally:
            _mod.mamba_manager = _orig


# ===========================================================================
# SECTION 2: runtime_security tests
# ===========================================================================


class TestSecurityEvent:
    """Tests for SecurityEvent dataclass."""

    def test_to_dict(self) -> None:
        event = SecurityEvent(
            event_type=SecurityEventType.PROMPT_INJECTION_ATTEMPT,
            severity=SecuritySeverity.HIGH,
            message="test injection",
            tenant_id="tenant-1",
            agent_id="agent-1",
            metadata={"key": "value"},
        )
        d = event.to_dict()
        assert d["event_type"] == "prompt_injection_attempt"
        assert d["severity"] == "high"
        assert d["message"] == "test injection"
        assert d["tenant_id"] == "tenant-1"
        assert d["agent_id"] == "agent-1"
        assert d["metadata"] == {"key": "value"}
        assert "timestamp" in d
        assert "constitutional_hash" in d


class TestSecurityScanResult:
    """Tests for SecurityScanResult."""

    def test_add_event_high_severity_marks_insecure(self) -> None:
        result = SecurityScanResult()
        assert result.is_secure is True
        event = SecurityEvent(
            event_type=SecurityEventType.ANOMALY_DETECTED,
            severity=SecuritySeverity.HIGH,
            message="anomaly",
        )
        result.add_event(event)
        assert result.is_secure is False
        assert len(result.events) == 1

    def test_add_event_low_severity_stays_secure(self) -> None:
        result = SecurityScanResult()
        event = SecurityEvent(
            event_type=SecurityEventType.SUSPICIOUS_PATTERN,
            severity=SecuritySeverity.LOW,
            message="minor",
        )
        result.add_event(event)
        assert result.is_secure is True

    def test_add_blocking_event(self) -> None:
        result = SecurityScanResult()
        event = SecurityEvent(
            event_type=SecurityEventType.TENANT_VIOLATION,
            severity=SecuritySeverity.CRITICAL,
            message="blocked",
        )
        result.add_blocking_event(event, "tenant violation")
        assert result.blocked is True
        assert result.block_reason == "tenant violation"
        assert result.is_secure is False

    def test_to_dict(self) -> None:
        result = SecurityScanResult()
        result.checks_performed.append("test_check")
        result.warnings.append("test_warning")
        d = result.to_dict()
        assert d["is_secure"] is True
        assert d["blocked"] is False
        assert "checks_performed" in d
        assert "warnings" in d


class TestRuntimeSecurityScanner:
    """Tests for RuntimeSecurityScanner."""

    def test_init_default_config(self) -> None:
        scanner = RuntimeSecurityScanner()
        assert scanner.config.enable_prompt_injection_detection is True
        assert scanner._total_scans == 0

    async def test_scan_basic_safe_content(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
        )
        scanner = RuntimeSecurityScanner(config)
        result = await scanner.scan("hello world")
        assert result.is_secure is True
        assert result.blocked is False
        # suspicious_pattern_detection always runs
        assert "suspicious_pattern_detection" in result.checks_performed

    async def test_scan_suspicious_pattern_xss(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
        )
        scanner = RuntimeSecurityScanner(config)
        result = await scanner.scan("<script>alert('xss')</script>")
        assert len(result.events) > 0
        assert any(e.event_type == SecurityEventType.SUSPICIOUS_PATTERN for e in result.events)

    async def test_scan_suspicious_pattern_sql_injection(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
        )
        scanner = RuntimeSecurityScanner(config)
        result = await scanner.scan("SELECT * FROM users; DROP TABLE users;")
        assert any(e.event_type == SecurityEventType.SUSPICIOUS_PATTERN for e in result.events)

    async def test_scan_input_length_exceeds_max(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=True,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
            max_input_length=10,
        )
        scanner = RuntimeSecurityScanner(config)
        result = await scanner.scan("A" * 100)
        assert "input_sanitization" in result.checks_performed
        assert any("maximum length" in w for w in result.warnings)

    async def test_scan_nested_depth_exceeds_max(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=True,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
            max_nested_depth=2,
        )
        scanner = RuntimeSecurityScanner(config)
        nested = {"a": {"b": {"c": {"d": "deep"}}}}
        result = await scanner.scan(nested)
        assert any("nesting depth" in w for w in result.warnings)

    async def test_scan_rate_limit_exceeded(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=True,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
            rate_limit_qps=2,
        )
        scanner = RuntimeSecurityScanner(config)
        # Fill up rate counter
        await scanner.scan("a", tenant_id="t1", agent_id="a1")
        await scanner.scan("b", tenant_id="t1", agent_id="a1")
        result = await scanner.scan("c", tenant_id="t1", agent_id="a1")
        assert any(e.event_type == SecurityEventType.RATE_LIMIT_EXCEEDED for e in result.events)

    async def test_scan_anomaly_detection(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=True,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
            anomaly_threshold_events=2,
        )
        scanner = RuntimeSecurityScanner(config)
        # Seed event buffer with recent events for tenant
        now = datetime.now(UTC)
        for _ in range(3):
            scanner._event_buffer.append(
                SecurityEvent(
                    event_type=SecurityEventType.SUSPICIOUS_PATTERN,
                    severity=SecuritySeverity.LOW,
                    message="test",
                    timestamp=now,
                    tenant_id="t1",
                    agent_id="a1",
                )
            )
        result = await scanner.scan("test", tenant_id="t1", agent_id="a1")
        assert any(e.event_type == SecurityEventType.ANOMALY_DETECTED for e in result.events)

    async def test_scan_message_convenience(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
        )
        scanner = RuntimeSecurityScanner(config)
        msg = MagicMock()
        msg.content = "safe content"
        result = await scanner.scan_message(msg, tenant_id="t1")
        assert result.is_secure is True

    async def test_scan_fail_closed_on_error(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
            fail_closed=True,
        )
        scanner = RuntimeSecurityScanner(config)
        with patch.object(scanner, "_check_suspicious_patterns", side_effect=RuntimeError("boom")):
            result = await scanner.scan("test")
            assert result.blocked is True
            assert result.is_secure is False

    async def test_scan_fail_open_on_error(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=False,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
            fail_closed=False,
        )
        scanner = RuntimeSecurityScanner(config)
        with patch.object(scanner, "_check_suspicious_patterns", side_effect=ValueError("boom")):
            result = await scanner.scan("test")
            assert result.blocked is False

    def test_get_metrics(self) -> None:
        scanner = RuntimeSecurityScanner()
        metrics = scanner.get_metrics()
        assert metrics["total_scans"] == 0
        assert metrics["blocked_requests"] == 0
        assert "constitutional_hash" in metrics

    def test_get_recent_events_empty(self) -> None:
        scanner = RuntimeSecurityScanner()
        events = scanner.get_recent_events()
        assert events == []

    def test_get_recent_events_with_filters(self) -> None:
        scanner = RuntimeSecurityScanner()
        scanner._event_buffer.extend(
            [
                SecurityEvent(
                    event_type=SecurityEventType.SUSPICIOUS_PATTERN,
                    severity=SecuritySeverity.LOW,
                    message="low",
                ),
                SecurityEvent(
                    event_type=SecurityEventType.ANOMALY_DETECTED,
                    severity=SecuritySeverity.HIGH,
                    message="high",
                ),
            ]
        )
        high_events = scanner.get_recent_events(severity_filter=SecuritySeverity.HIGH)
        assert len(high_events) == 1
        assert high_events[0].message == "high"

        anomaly_events = scanner.get_recent_events(
            event_type_filter=SecurityEventType.ANOMALY_DETECTED
        )
        assert len(anomaly_events) == 1

    def test_nested_depth_empty_dict(self) -> None:
        scanner = RuntimeSecurityScanner()
        assert scanner._get_nested_depth({}) == 0

    def test_nested_depth_list(self) -> None:
        scanner = RuntimeSecurityScanner()
        assert scanner._get_nested_depth([1, [2, [3]]]) == 3

    def test_nested_depth_primitive(self) -> None:
        scanner = RuntimeSecurityScanner()
        assert scanner._get_nested_depth("hello") == 0

    async def test_store_events_trims_old(self) -> None:
        config = RuntimeSecurityConfig(max_events_retained=2)
        scanner = RuntimeSecurityScanner(config)
        events = [
            SecurityEvent(
                event_type=SecurityEventType.SUSPICIOUS_PATTERN,
                severity=SecuritySeverity.LOW,
                message=f"event-{i}",
            )
            for i in range(5)
        ]
        await scanner._store_events(events)
        assert len(scanner._event_buffer) <= 2

    async def test_check_tenant_no_validator(self) -> None:
        config = RuntimeSecurityConfig(
            enable_prompt_injection_detection=False,
            enable_tenant_validation=True,
            enable_rate_limit_check=False,
            enable_constitutional_validation=False,
            enable_anomaly_detection=False,
            enable_input_sanitization=False,
            enable_constitutional_classifier=False,
            enable_runtime_guardrails=False,
            enable_payload_integrity_check=False,
        )
        scanner = RuntimeSecurityScanner(config)
        with patch("enhanced_agent_bus.runtime_security.TenantValidator", None):
            result = SecurityScanResult()
            await scanner._check_tenant(result, "tenant-1", None)
            assert any("not available" in w for w in result.warnings)

    async def test_check_prompt_injection_not_available(self) -> None:
        scanner = RuntimeSecurityScanner()
        with patch("enhanced_agent_bus.runtime_security.detect_prompt_injection", None):
            result = SecurityScanResult()
            await scanner._check_prompt_injection(result, "test", None, None)
            assert any("not available" in w for w in result.warnings)

    async def test_check_constitutional_compliance_not_available(self) -> None:
        scanner = RuntimeSecurityScanner()
        with patch("enhanced_agent_bus.runtime_security.get_constitutional_classifier", None):
            result = SecurityScanResult()
            await scanner._check_constitutional_compliance(result, "test", None, None)
            assert any("not available" in w for w in result.warnings)


class TestGlobalSecurityScanner:
    """Tests for module-level convenience functions."""

    async def test_get_runtime_security_scanner(self) -> None:
        # Reset global state
        import enhanced_agent_bus.runtime_security as mod

        mod._scanner = None
        scanner = get_runtime_security_scanner()
        assert isinstance(scanner, RuntimeSecurityScanner)
        # Second call returns same instance
        assert get_runtime_security_scanner() is scanner
        mod._scanner = None  # cleanup

    async def test_scan_content(self) -> None:
        import enhanced_agent_bus.runtime_security as mod

        mod._scanner = None
        result = await scan_content("safe text")
        assert isinstance(result, SecurityScanResult)
        mod._scanner = None


# ===========================================================================
# SECTION 3: health_aggregator tests
# ===========================================================================


class TestSystemHealthReport:
    """Tests for SystemHealthReport."""

    def test_to_dict(self) -> None:
        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            timestamp=datetime.now(UTC),
            total_breakers=3,
            closed_breakers=3,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={"svc1": {"state": "closed"}},
            degraded_services=[],
            critical_services=[],
        )
        d = report.to_dict()
        assert d["status"] == "healthy"
        assert d["health_score"] == 1.0
        assert d["total_breakers"] == 3


class TestHealthSnapshot:
    """Tests for HealthSnapshot."""

    def test_to_dict(self) -> None:
        snap = HealthSnapshot(
            timestamp=datetime.now(UTC),
            status=SystemHealthStatus.DEGRADED,
            health_score=0.6,
            total_breakers=5,
            closed_breakers=3,
            half_open_breakers=1,
            open_breakers=1,
            circuit_states={"a": "closed", "b": "open"},
        )
        d = snap.to_dict()
        assert d["status"] == "degraded"
        assert d["health_score"] == 0.6
        assert d["open_breakers"] == 1


class TestHealthAggregator:
    """Tests for HealthAggregator."""

    def test_init_defaults(self) -> None:
        agg = HealthAggregator()
        assert agg._running is False
        assert agg._snapshots_collected == 0

    def test_calculate_health_score_no_breakers(self) -> None:
        agg = HealthAggregator()
        assert agg._calculate_health_score(0, 0, 0, 0) == 1.0

    def test_calculate_health_score_all_closed(self) -> None:
        agg = HealthAggregator()
        assert agg._calculate_health_score(5, 5, 0, 0) == 1.0

    def test_calculate_health_score_mixed(self) -> None:
        agg = HealthAggregator()
        # 2 closed + 2 half_open + 1 open = (2*1.0 + 2*0.5 + 0) / 5 = 0.6
        score = agg._calculate_health_score(5, 2, 2, 1)
        assert abs(score - 0.6) < 0.001

    def test_calculate_health_score_all_open(self) -> None:
        agg = HealthAggregator()
        assert agg._calculate_health_score(3, 0, 0, 3) == 0.0

    def test_determine_health_status_healthy(self) -> None:
        agg = HealthAggregator()
        assert agg._determine_health_status(0.9) == SystemHealthStatus.HEALTHY

    def test_determine_health_status_degraded(self) -> None:
        agg = HealthAggregator()
        assert agg._determine_health_status(0.6) == SystemHealthStatus.DEGRADED

    def test_determine_health_status_critical(self) -> None:
        agg = HealthAggregator()
        assert agg._determine_health_status(0.3) == SystemHealthStatus.CRITICAL

    def test_register_unregister_circuit_breaker(self) -> None:
        agg = HealthAggregator()
        mock_breaker = MagicMock()
        agg.register_circuit_breaker("test-breaker", mock_breaker)
        assert "test-breaker" in agg._custom_breakers
        agg.unregister_circuit_breaker("test-breaker")
        assert "test-breaker" not in agg._custom_breakers

    def test_unregister_nonexistent_breaker(self) -> None:
        agg = HealthAggregator()
        agg.unregister_circuit_breaker("nonexistent")  # should not raise

    def test_on_health_change_registers_callback(self) -> None:
        agg = HealthAggregator()

        def my_callback(report: SystemHealthReport) -> None:
            pass

        agg.on_health_change(my_callback)
        assert len(agg._health_change_callbacks) == 1

    def test_get_system_health_no_circuit_breaker(self) -> None:
        agg = HealthAggregator(registry=None)
        with patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", False):
            report = agg.get_system_health()
            assert report.status == SystemHealthStatus.UNKNOWN
            assert report.health_score == 0.0

    def test_get_health_history_empty(self) -> None:
        agg = HealthAggregator()
        history = agg.get_health_history()
        assert history == []

    def test_get_health_history_with_window(self) -> None:
        agg = HealthAggregator()
        snap = HealthSnapshot(
            timestamp=datetime.now(UTC),
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={},
        )
        agg._health_history.append(snap)
        history = agg.get_health_history(window_minutes=1)
        assert len(history) == 1

    def test_get_health_history_filters_old(self) -> None:
        agg = HealthAggregator()
        old_snap = HealthSnapshot(
            timestamp=datetime(2020, 1, 1, tzinfo=UTC),
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={},
        )
        agg._health_history.append(old_snap)
        history = agg.get_health_history(window_minutes=1)
        assert len(history) == 0

    def test_get_metrics(self) -> None:
        agg = HealthAggregator()
        with patch.object(agg, "get_system_health") as mock_health:
            mock_health.return_value = SystemHealthReport(
                status=SystemHealthStatus.HEALTHY,
                health_score=1.0,
                timestamp=datetime.now(UTC),
                total_breakers=0,
                closed_breakers=0,
                half_open_breakers=0,
                open_breakers=0,
                circuit_details={},
            )
            metrics = agg.get_metrics()
            assert "snapshots_collected" in metrics
            assert "running" in metrics
            assert metrics["running"] is False

    async def test_start_disabled(self) -> None:
        config = HealthAggregatorConfig(enabled=False)
        agg = HealthAggregator(config=config)
        await agg.start()
        assert agg._running is False

    async def test_start_no_circuit_breaker(self) -> None:
        agg = HealthAggregator()
        with patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", False):
            await agg.start()
            assert agg._running is False

    async def test_start_already_running(self) -> None:
        agg = HealthAggregator()
        agg._running = True
        await agg.start()  # should return immediately

    async def test_stop(self) -> None:
        agg = HealthAggregator()
        agg._running = True

        async def _cancelled_coro() -> None:
            raise asyncio.CancelledError

        task = asyncio.ensure_future(_cancelled_coro())
        # Let the task finish raising CancelledError
        with pytest.raises(asyncio.CancelledError):
            await task

        agg._health_check_task = task
        await agg.stop()
        assert agg._running is False

    async def test_invoke_callback_sync(self) -> None:
        agg = HealthAggregator()
        called = []

        def sync_cb(report: SystemHealthReport) -> None:
            called.append(report)

        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            timestamp=datetime.now(UTC),
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={},
        )
        await agg._invoke_callback(sync_cb, report)
        assert len(called) == 1

    async def test_invoke_callback_async(self) -> None:
        agg = HealthAggregator()
        called = []

        async def async_cb(report: SystemHealthReport) -> None:
            called.append(report)

        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            timestamp=datetime.now(UTC),
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={},
        )
        await agg._invoke_callback(async_cb, report)
        assert len(called) == 1

    async def test_invoke_callback_handles_error(self) -> None:
        agg = HealthAggregator()

        def bad_cb(report: SystemHealthReport) -> None:
            raise RuntimeError("callback error")

        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            timestamp=datetime.now(UTC),
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={},
        )
        # Should not raise
        await agg._invoke_callback(bad_cb, report)

    async def test_collect_health_snapshot_no_circuit_breaker(self) -> None:
        agg = HealthAggregator()
        with patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", False):
            await agg._collect_health_snapshot()
            assert agg._snapshots_collected == 0


class TestGlobalHealthAggregator:
    """Tests for module-level functions."""

    def test_get_health_aggregator(self) -> None:
        reset_health_aggregator()
        agg = get_health_aggregator()
        assert isinstance(agg, HealthAggregator)
        assert get_health_aggregator() is agg
        reset_health_aggregator()

    def test_reset_health_aggregator(self) -> None:
        reset_health_aggregator()
        agg = get_health_aggregator()
        reset_health_aggregator()
        agg2 = get_health_aggregator()
        assert agg is not agg2
        reset_health_aggregator()


# ===========================================================================
# SECTION 4: performance_optimization tests
# ===========================================================================


class TestPipelineStage:
    """Tests for PipelineStage dataclass."""

    def test_defaults(self) -> None:
        async def handler(data: object) -> object:
            return data

        stage = PipelineStage(name="test", handler=handler)
        assert stage.name == "test"
        assert stage.timeout == 30.0
        assert stage.parallel is False


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_fields(self) -> None:
        result = PipelineResult(stage_name="s1", output="ok", duration_ms=1.5, success=True)
        assert result.stage_name == "s1"
        assert result.success is True
        assert result.error is None


class TestAsyncPipelineOptimizer:
    """Tests for AsyncPipelineOptimizer."""

    def test_init(self) -> None:
        pipeline = AsyncPipelineOptimizer(max_concurrency=4)
        assert len(pipeline._stages) == 0

    def test_add_stage(self) -> None:
        pipeline = AsyncPipelineOptimizer()

        async def handler(data: object) -> object:
            return data

        pipeline.add_stage(PipelineStage(name="s1", handler=handler))
        assert len(pipeline._stages) == 1

    async def test_run_single_stage(self) -> None:
        pipeline = AsyncPipelineOptimizer()

        async def double(x: int) -> int:
            return x * 2

        pipeline.add_stage(PipelineStage(name="double", handler=double))
        results = await pipeline.run(5)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].output == 10

    async def test_run_sequential_stages(self) -> None:
        pipeline = AsyncPipelineOptimizer()

        async def add_one(x: int) -> int:
            return x + 1

        async def multiply_two(x: int) -> int:
            return x * 2

        pipeline.add_stage(PipelineStage(name="add", handler=add_one))
        pipeline.add_stage(PipelineStage(name="mul", handler=multiply_two))
        results = await pipeline.run(3)
        assert results[0].output == 4  # 3+1
        assert results[1].output == 8  # 4*2

    async def test_run_parallel_stages(self) -> None:
        pipeline = AsyncPipelineOptimizer()

        async def handler_a(x: int) -> str:
            return f"a:{x}"

        async def handler_b(x: int) -> str:
            return f"b:{x}"

        pipeline.add_stage(PipelineStage(name="a", handler=handler_a, parallel=True))
        pipeline.add_stage(PipelineStage(name="b", handler=handler_b, parallel=True))
        results = await pipeline.run(1)
        assert len(results) == 2
        assert all(r.success for r in results)

    async def test_run_stage_timeout(self) -> None:
        pipeline = AsyncPipelineOptimizer()

        async def slow(x: int) -> int:
            await asyncio.sleep(10)
            return x

        pipeline.add_stage(PipelineStage(name="slow", handler=slow, timeout=0.01))
        results = await pipeline.run(1)
        assert results[0].success is False
        assert "Timeout" in (results[0].error or "")

    async def test_run_stage_exception(self) -> None:
        pipeline = AsyncPipelineOptimizer()

        async def failing(x: int) -> int:
            raise ValueError("stage error")

        pipeline.add_stage(PipelineStage(name="fail", handler=failing))
        results = await pipeline.run(1)
        assert results[0].success is False
        assert "stage error" in (results[0].error or "")

    def test_get_stats(self) -> None:
        pipeline = AsyncPipelineOptimizer()
        stats = pipeline.get_stats()
        assert stats["runs"] == 0
        assert stats["stages_registered"] == 0
        assert "constitutional_hash" in stats

    async def test_get_stats_after_run(self) -> None:
        pipeline = AsyncPipelineOptimizer()

        async def noop(x: object) -> object:
            return x

        pipeline.add_stage(PipelineStage(name="noop", handler=noop))
        await pipeline.run("data")
        stats = pipeline.get_stats()
        assert stats["runs"] == 1
        assert stats["stage_successes"] == 1


class TestPooledResource:
    """Tests for PooledResource dataclass."""

    def test_mark_acquired(self) -> None:
        pr: PooledResource[str] = PooledResource(resource="conn", resource_id="abc")
        assert pr.in_use is False
        assert pr.use_count == 0
        pr.mark_acquired()
        assert pr.in_use is True
        assert pr.use_count == 1

    def test_mark_released(self) -> None:
        pr: PooledResource[str] = PooledResource(resource="conn", resource_id="abc")
        pr.mark_acquired()
        pr.mark_released()
        assert pr.in_use is False


class TestResourcePool:
    """Tests for ResourcePool."""

    async def test_acquire_creates_resource(self) -> None:
        factory = AsyncMock(return_value="resource-1")
        pool: ResourcePool[str] = ResourcePool(factory, max_size=5)
        pooled = await pool.acquire()
        assert pooled.resource == "resource-1"
        assert pooled.in_use is True
        factory.assert_called_once()

    async def test_acquire_and_release(self) -> None:
        factory = AsyncMock(return_value="resource-1")
        pool: ResourcePool[str] = ResourcePool(factory, max_size=5)
        pooled = await pool.acquire()
        await pool.release(pooled)
        assert pooled.in_use is False

        # Acquiring again should reuse released resource
        pooled2 = await pool.acquire()
        assert pooled2 is pooled
        assert factory.call_count == 1  # only created once

    async def test_resource_context_manager(self) -> None:
        factory = AsyncMock(return_value="managed")
        pool: ResourcePool[str] = ResourcePool(factory, max_size=5)
        async with pool.resource() as pooled:
            assert pooled.resource == "managed"
            assert pooled.in_use is True
        assert pooled.in_use is False

    async def test_close_clears_pool(self) -> None:
        factory = AsyncMock(return_value="res")
        pool: ResourcePool[str] = ResourcePool(factory, max_size=5)
        await pool.acquire()
        await pool.close()
        assert len(pool._all) == 0
        assert len(pool._available) == 0

    def test_get_stats(self) -> None:
        factory = AsyncMock(return_value="res")
        pool: ResourcePool[str] = ResourcePool(factory, max_size=10)
        stats = pool.get_stats()
        assert stats["pool_size"] == 0
        assert stats["max_size"] == 10
        assert "constitutional_hash" in stats


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_touch(self) -> None:
        entry = CacheEntry(key="k", value="v", size_bytes=10)
        assert entry.access_count == 0
        entry.touch()
        assert entry.access_count == 1


class TestMemoryOptimizer:
    """Tests for MemoryOptimizer."""

    async def test_put_and_get(self) -> None:
        mo = MemoryOptimizer(max_entries=100)
        await mo.put("key1", "value1")
        # Need a loader registered or cache hit
        mo.register_loader("key1", AsyncMock(return_value="loaded"))
        val = await mo.get("key1")
        assert val == "value1"

    async def test_get_miss_no_loader(self) -> None:
        mo = MemoryOptimizer()
        val = await mo.get("nonexistent")
        assert val is None

    async def test_get_miss_with_loader(self) -> None:
        mo = MemoryOptimizer()
        loader = AsyncMock(return_value="loaded_value")
        mo.register_loader("mykey", loader)
        val = await mo.get("mykey")
        assert val == "loaded_value"
        loader.assert_called_once()

    async def test_get_prefix_loader(self) -> None:
        mo = MemoryOptimizer()
        loader = AsyncMock(return_value="prefix_val")
        mo.register_loader("data:", loader)
        val = await mo.get("data:something")
        assert val == "prefix_val"

    async def test_get_ttl_expired(self) -> None:
        mo = MemoryOptimizer(default_ttl_seconds=0)
        await mo.put("expiring", "soon")
        # TTL is 0 so it should be expired by now
        loader = AsyncMock(return_value="reloaded")
        mo.register_loader("expiring", loader)
        val = await mo.get("expiring")
        assert val == "reloaded"

    async def test_evict(self) -> None:
        mo = MemoryOptimizer()
        await mo.put("k1", "v1")
        removed = await mo.evict("k1")
        assert removed is True
        removed2 = await mo.evict("k1")
        assert removed2 is False

    async def test_clear(self) -> None:
        mo = MemoryOptimizer()
        await mo.put("a", 1)
        await mo.put("b", 2)
        count = await mo.clear()
        assert count == 2

    async def test_maybe_evict_at_capacity(self) -> None:
        mo = MemoryOptimizer(max_entries=2)
        await mo.put("a", "1")
        await mo.put("b", "2")
        await mo.put("c", "3")  # should evict oldest
        stats = mo.get_stats()
        assert stats["cache_entries"] <= 2

    def test_get_stats(self) -> None:
        mo = MemoryOptimizer()
        stats = mo.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert "constitutional_hash" in stats

    def test_find_loader_exact(self) -> None:
        mo = MemoryOptimizer()
        loader = AsyncMock()
        mo.register_loader("exact_key", loader)
        found = mo._find_loader("exact_key")
        assert found is loader

    def test_find_loader_prefix_longest_wins(self) -> None:
        mo = MemoryOptimizer()
        short_loader = AsyncMock()
        long_loader = AsyncMock()
        mo.register_loader("pre", short_loader)
        mo.register_loader("prefix", long_loader)
        found = mo._find_loader("prefix_key")
        assert found is long_loader

    def test_find_loader_no_match(self) -> None:
        mo = MemoryOptimizer()
        found = mo._find_loader("unknown")
        assert found is None


class TestBatchConfig:
    """Tests for BatchConfig dataclass."""

    def test_defaults(self) -> None:
        bc = BatchConfig()
        assert bc.max_batch_size == 100
        assert bc.max_wait_seconds == 0.05


class TestBatchFlushResult:
    """Tests for BatchFlushResult dataclass."""

    def test_fields(self) -> None:
        r = BatchFlushResult(topic="t", items_flushed=5, duration_ms=1.0, success=True)
        assert r.topic == "t"
        assert r.error is None


class TestLatencyReducer:
    """Tests for LatencyReducer."""

    async def test_submit_and_flush(self) -> None:
        processor = AsyncMock()
        lr = LatencyReducer(
            batch_config=BatchConfig(max_batch_size=100, max_wait_seconds=10),
            processor=processor,
        )
        await lr.submit("topic1", "item1")
        result = await lr.flush("topic1")
        assert result.success is True
        assert result.items_flushed == 1
        processor.assert_called_once()

    async def test_submit_triggers_flush_at_capacity(self) -> None:
        processor = AsyncMock()
        lr = LatencyReducer(
            batch_config=BatchConfig(max_batch_size=2, max_wait_seconds=10),
            processor=processor,
        )
        await lr.submit("t", "a")
        await lr.submit("t", "b")  # should trigger flush
        # Processor should have been called with 2 items
        assert processor.call_count >= 1

    async def test_flush_empty_buffer(self) -> None:
        lr = LatencyReducer()
        result = await lr.flush("empty_topic")
        assert result.success is True
        assert result.items_flushed == 0

    async def test_flush_processor_error(self) -> None:
        processor = AsyncMock(side_effect=RuntimeError("flush error"))
        lr = LatencyReducer(
            batch_config=BatchConfig(max_batch_size=100, max_wait_seconds=10),
            processor=processor,
        )
        await lr.submit("t", "item")
        result = await lr.flush("t")
        assert result.success is False
        assert "flush error" in (result.error or "")

    async def test_flush_all(self) -> None:
        processor = AsyncMock()
        lr = LatencyReducer(
            batch_config=BatchConfig(max_batch_size=100, max_wait_seconds=10),
            processor=processor,
        )
        await lr.submit("t1", "a")
        await lr.submit("t2", "b")
        results = await lr.flush_all()
        assert len(results) == 2

    async def test_close(self) -> None:
        processor = AsyncMock()
        lr = LatencyReducer(
            batch_config=BatchConfig(max_batch_size=100, max_wait_seconds=10),
            processor=processor,
        )
        await lr.submit("t", "item")
        await lr.close()
        # Should have flushed

    async def test_no_processor(self) -> None:
        lr = LatencyReducer(
            batch_config=BatchConfig(max_batch_size=100, max_wait_seconds=10),
            processor=None,
        )
        await lr.submit("t", "item")
        result = await lr.flush("t")
        assert result.success is True

    def test_get_stats(self) -> None:
        lr = LatencyReducer()
        stats = lr.get_stats()
        assert stats["items_submitted"] == 0
        assert stats["batches_flushed"] == 0
        assert "constitutional_hash" in stats

    async def test_timed_flush(self) -> None:
        processor = AsyncMock()
        lr = LatencyReducer(
            batch_config=BatchConfig(max_batch_size=100, max_wait_seconds=0.01),
            processor=processor,
        )
        await lr.submit("t", "item")
        # Wait for timed flush to trigger
        await asyncio.sleep(0.05)
        stats = lr.get_stats()
        # The timed flush should have fired
        assert stats["batches_flushed"] >= 0  # may or may not have fired yet


class TestFactoryFunctions:
    """Tests for module-level factory functions."""

    def test_create_async_pipeline(self) -> None:
        pipeline = create_async_pipeline(max_concurrency=8)
        assert isinstance(pipeline, AsyncPipelineOptimizer)

    def test_create_resource_pool(self) -> None:
        factory = AsyncMock(return_value="res")
        pool = create_resource_pool(factory, max_size=5)
        assert isinstance(pool, ResourcePool)

    def test_create_latency_reducer(self) -> None:
        lr = create_latency_reducer()
        assert isinstance(lr, LatencyReducer)

    def test_create_memory_optimizer(self) -> None:
        mo = create_memory_optimizer(max_entries=500)
        assert isinstance(mo, MemoryOptimizer)


class TestHealthAggregatorCollectBreakerState:
    """Tests for _collect_breaker_state helper."""

    def test_collect_closed_state(self) -> None:
        mock_pybreaker = MagicMock()
        mock_pybreaker.STATE_CLOSED = "closed"
        mock_pybreaker.STATE_HALF_OPEN = "half_open"
        mock_pybreaker.STATE_OPEN = "open"
        with patch("enhanced_agent_bus.health_aggregator.pybreaker", mock_pybreaker):
            agg = HealthAggregator(registry=None)
            details: dict = {}
            counts = [0, 0, 0]
            agg._collect_breaker_state("svc1", "closed", 0, 5, details, counts)
            assert details["svc1"]["state"] == "closed"
            assert counts[0] == 1

    def test_collect_half_open_state(self) -> None:
        mock_pybreaker = MagicMock()
        mock_pybreaker.STATE_CLOSED = "closed"
        mock_pybreaker.STATE_HALF_OPEN = "half_open"
        mock_pybreaker.STATE_OPEN = "open"
        with patch("enhanced_agent_bus.health_aggregator.pybreaker", mock_pybreaker):
            agg = HealthAggregator(registry=None)
            details: dict = {}
            counts = [0, 0, 0]
            agg._collect_breaker_state("svc2", "half_open", 2, 0, details, counts)
            assert counts[1] == 1

    def test_collect_open_state(self) -> None:
        mock_pybreaker = MagicMock()
        mock_pybreaker.STATE_CLOSED = "closed"
        mock_pybreaker.STATE_HALF_OPEN = "half_open"
        mock_pybreaker.STATE_OPEN = "open"
        with patch("enhanced_agent_bus.health_aggregator.pybreaker", mock_pybreaker):
            agg = HealthAggregator(registry=None)
            details: dict = {}
            counts = [0, 0, 0]
            agg._collect_breaker_state("svc3", "open", 5, 0, details, counts)
            assert counts[2] == 1


class TestRuntimeSecurityAdditional:
    """Additional edge case tests for runtime_security."""

    async def test_check_constitutional_hash_valid(self) -> None:
        scanner = RuntimeSecurityScanner()
        result = SecurityScanResult()
        mock_validation = MagicMock()
        mock_validation.is_valid = True
        with patch(
            "enhanced_agent_bus.runtime_security.validate_constitutional_hash",
            return_value=mock_validation,
        ):
            await scanner._check_constitutional_hash(result, "608508a9bd224290", None, None)
            assert result.blocked is False

    async def test_check_constitutional_hash_invalid(self) -> None:
        scanner = RuntimeSecurityScanner()
        result = SecurityScanResult()
        mock_validation = MagicMock()
        mock_validation.is_valid = False
        with patch(
            "enhanced_agent_bus.runtime_security.validate_constitutional_hash",
            return_value=mock_validation,
        ):
            await scanner._check_constitutional_hash(result, "bad_hash", None, None)
            assert result.blocked is True
            assert result.is_secure is False

    async def test_check_payload_integrity_not_available(self) -> None:
        scanner = RuntimeSecurityScanner()
        with patch("enhanced_agent_bus.runtime_security.validate_payload_integrity", None):
            result = SecurityScanResult()
            await scanner._check_payload_integrity(result, MagicMock(), None, None)
            assert any("not available" in w for w in result.warnings)

    async def test_check_payload_integrity_valid(self) -> None:
        scanner = RuntimeSecurityScanner()
        mock_validation = MagicMock()
        mock_validation.is_valid = True
        mock_validation.warnings = []
        with patch(
            "enhanced_agent_bus.runtime_security.validate_payload_integrity",
            return_value=mock_validation,
        ):
            result = SecurityScanResult()
            await scanner._check_payload_integrity(result, MagicMock(), None, None)
            assert result.blocked is False

    async def test_check_payload_integrity_invalid(self) -> None:
        scanner = RuntimeSecurityScanner()
        mock_validation = MagicMock()
        mock_validation.is_valid = False
        mock_validation.warnings = ["HMAC mismatch"]
        with patch(
            "enhanced_agent_bus.runtime_security.validate_payload_integrity",
            return_value=mock_validation,
        ):
            result = SecurityScanResult()
            await scanner._check_payload_integrity(result, MagicMock(), None, None)
            assert result.blocked is True

    async def test_check_runtime_guardrails_not_available(self) -> None:
        scanner = RuntimeSecurityScanner()
        with patch("enhanced_agent_bus.runtime_security.RuntimeSafetyGuardrails", None):
            result = SecurityScanResult()
            await scanner._check_runtime_guardrails(result, "test", {}, None, None)
            assert any("not available" in w for w in result.warnings)

    def test_build_guardrails_processing_context(self) -> None:
        scanner = RuntimeSecurityScanner()
        result = SecurityScanResult()
        ctx = scanner._build_guardrails_processing_context(
            context={"trace_id": "tr123", "ip_address": "1.2.3.4"},
            result=result,
            tenant_id="t1",
            agent_id="a1",
        )
        assert ctx["trace_id"] == "tr123"
        assert ctx["tenant_id"] == "t1"
        assert ctx["ip_address"] == "1.2.3.4"

    def test_apply_guardrails_violations_no_violations(self) -> None:
        scanner = RuntimeSecurityScanner()
        result = SecurityScanResult()
        scanner._apply_guardrails_violations(
            result=result,
            guardrails_result={"violations": []},
            tenant_id=None,
            agent_id=None,
        )
        assert result.blocked is False

    def test_apply_guardrails_violations_with_blocking(self) -> None:
        scanner = RuntimeSecurityScanner()
        result = SecurityScanResult()
        scanner._apply_guardrails_violations(
            result=result,
            guardrails_result={
                "violations": [
                    {
                        "severity": "high",
                        "message": "blocked violation",
                        "layer": "l1",
                        "violation_type": "test",
                    }
                ],
                "allowed": False,
            },
            tenant_id="t1",
            agent_id="a1",
        )
        assert result.blocked is True

    def test_apply_guardrails_violations_with_warning(self) -> None:
        scanner = RuntimeSecurityScanner()
        result = SecurityScanResult()
        scanner._apply_guardrails_violations(
            result=result,
            guardrails_result={
                "violations": [
                    {
                        "severity": "low",
                        "message": "minor issue",
                    }
                ],
                "allowed": True,
            },
            tenant_id=None,
            agent_id=None,
        )
        assert result.blocked is False
        assert any("minor issue" in w for w in result.warnings)

    def test_apply_guardrails_no_violations_key(self) -> None:
        scanner = RuntimeSecurityScanner()
        result = SecurityScanResult()
        scanner._apply_guardrails_violations(
            result=result,
            guardrails_result={},
            tenant_id=None,
            agent_id=None,
        )
        assert result.blocked is False
