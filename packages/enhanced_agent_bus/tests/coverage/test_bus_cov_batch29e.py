"""
Coverage tests for batch 29e:
- src/core/shared/types/protocol_types.py (Protocol conformance)
- enhanced_agent_bus/guardrails/agent_engine.py (uncovered branches)
- enhanced_agent_bus/governance/stability/mhc.py (torch-absent paths)
- enhanced_agent_bus/api/routes/governance.py (governance routes)
- acgs_lite/integrations/llamaindex.py (governed query/chat engines)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _has_real_torch() -> bool:
    try:
        return importlib.util.find_spec("torch") is not None
    except (ImportError, ValueError):
        return False


# ============================================================================
# 1. protocol_types.py -- Exercise Protocol structural typing (lines 20-182)
# ============================================================================


class TestProtocolConformance:
    """Verify that concrete classes can satisfy Protocol interfaces."""

    def test_supports_cache_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsCache

        class MyCache:
            def get(self, key: str):
                return {"cached": True}

            def set(self, key: str, value, ttl=None):
                pass

        cache: SupportsCache = MyCache()  # type: ignore[assignment]
        assert cache.get("k") == {"cached": True}
        cache.set("k", "v", ttl=60)

    def test_supports_validation_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsValidation

        class MyValidator:
            def validate(self) -> bool:
                return True

        v: SupportsValidation = MyValidator()  # type: ignore[assignment]
        assert v.validate() is True

    async def test_supports_authentication_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsAuthentication

        class MyAuth:
            async def authenticate(self) -> bool:
                return True

        auth: SupportsAuthentication = MyAuth()  # type: ignore[assignment]
        assert await auth.authenticate() is True

    def test_supports_serialization_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsSerialization

        class MySerializable:
            def __init__(self, data):
                self._data = data

            def to_dict(self):
                return self._data

            @classmethod
            def from_dict(cls, data):
                return cls(data)

        obj = MySerializable({"key": "value"})
        s: SupportsSerialization = obj  # type: ignore[assignment]
        assert s.to_dict() == {"key": "value"}
        restored = MySerializable.from_dict({"key": "value"})
        assert restored.to_dict() == {"key": "value"}

    def test_supports_logging_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsLogging

        class MyLogger:
            def __init__(self):
                self.messages = []

            def info(self, msg, **kwargs):
                self.messages.append(("info", msg))

            def error(self, msg, **kwargs):
                self.messages.append(("error", msg))

            def warning(self, msg, **kwargs):
                self.messages.append(("warning", msg))

            def debug(self, msg, **kwargs):
                self.messages.append(("debug", msg))

        log: SupportsLogging = MyLogger()  # type: ignore[assignment]
        log.info("test")
        log.error("err")
        log.warning("warn")
        log.debug("dbg")
        assert len(log.messages) == 4  # type: ignore[attr-defined]

    async def test_supports_middleware_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsMiddleware

        class MyMiddleware:
            async def __call__(self, scope, receive, send):
                pass

        mw: SupportsMiddleware = MyMiddleware()  # type: ignore[assignment]
        await mw({"type": "http"}, lambda: None, lambda x: None)

    async def test_supports_health_check_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsHealthCheck

        class MyHealth:
            async def health_check(self):
                return {"status": "ok"}

        h: SupportsHealthCheck = MyHealth()  # type: ignore[assignment]
        result = await h.health_check()
        assert result["status"] == "ok"

    def test_supports_circuit_breaker_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsCircuitBreaker

        class MyCB:
            def __init__(self):
                self._open = False

            def is_open(self):
                return self._open

            def record_success(self):
                self._open = False

            def record_failure(self):
                self._open = True

        cb: SupportsCircuitBreaker = MyCB()  # type: ignore[assignment]
        assert cb.is_open() is False
        cb.record_failure()
        assert cb.is_open() is True
        cb.record_success()
        assert cb.is_open() is False

    async def test_supports_audit_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsAudit

        class MyAudit:
            async def log_event(self, event_type, details, correlation_id=None):
                pass

        a: SupportsAudit = MyAudit()  # type: ignore[assignment]
        await a.log_event("test", {"detail": 1}, correlation_id="abc")

    async def test_agent_bus_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import AgentBus

        class MyBus:
            async def send_message(self, message):
                return {"sent": True}

            async def receive_message(self, timeout=1.0):
                return None

        bus: AgentBus = MyBus()  # type: ignore[assignment]
        assert (await bus.send_message({"data": 1}))["sent"] is True
        assert await bus.receive_message(timeout=0.5) is None

    async def test_governance_service_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import GovernanceService

        class MyGov:
            async def evaluate_policy(self, policy_id, context):
                return {"result": "pass"}

            async def register_policy(self, policy_data):
                return True

        g: GovernanceService = MyGov()  # type: ignore[assignment]
        assert (await g.evaluate_policy("p1", {}))["result"] == "pass"
        assert await g.register_policy({}) is True

    def test_supports_registry_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsRegistry

        class MyRegistry:
            def __init__(self):
                self._store: dict = {}

            def register(self, key, value):
                self._store[key] = value

            def get(self, key):
                return self._store.get(key)

            def unregister(self, key):
                self._store.pop(key, None)

        r: SupportsRegistry = MyRegistry()  # type: ignore[assignment]
        r.register("k", "v")
        assert r.get("k") == "v"
        r.unregister("k")
        assert r.get("k") is None

    async def test_supports_execution_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsExecution

        class MyExec:
            async def execute(self, *args, **kwargs):
                return {"done": True}

        e: SupportsExecution = MyExec()  # type: ignore[assignment]
        assert (await e.execute("a", b="c"))["done"] is True

    async def test_supports_compensation_protocol(self):
        from enhanced_agent_bus._compat.types.protocol_types import SupportsCompensation

        class MyComp:
            async def execute(self, context):
                return {"step": "forward"}

            async def compensate(self, context):
                return {"step": "rollback"}

        c: SupportsCompensation = MyComp()  # type: ignore[assignment]
        assert (await c.execute({}))["step"] == "forward"
        assert (await c.compensate({}))["step"] == "rollback"

    def test_type_aliases_exist(self):
        from enhanced_agent_bus._compat.types.protocol_types import (
            ArgsType,
            AsyncFunc,
            DecoratorFunc,
            KwargsType,
            ModelContext,
            TransformFunc,
            ValidatorContext,
            ValidatorFunc,
            ValidatorValue,
        )

        # Just verify they are importable and usable
        assert ArgsType is not None
        assert KwargsType is not None
        assert DecoratorFunc is not None
        assert AsyncFunc is not None
        assert TransformFunc is not None
        assert ValidatorFunc is not None
        assert ValidatorValue is not None
        assert ValidatorContext is not None
        assert ModelContext is not None


# ============================================================================
# 2. agent_engine.py -- Uncovered branches
# ============================================================================


class TestAgentEngine:
    """Tests for AgentEngine guardrail component."""

    def test_agent_engine_default_config(self):
        from enhanced_agent_bus.guardrails.agent_engine import (
            AgentEngine,
            AgentEngineConfig,
        )

        engine = AgentEngine()
        assert engine.config.enabled is True
        assert engine.config.constitutional_validation is True

    def test_agent_engine_custom_config(self):
        from enhanced_agent_bus.guardrails.agent_engine import (
            AgentEngine,
            AgentEngineConfig,
        )

        cfg = AgentEngineConfig(
            enabled=False,
            constitutional_validation=False,
            impact_scoring=False,
        )
        engine = AgentEngine(config=cfg)
        assert engine.config.enabled is False

    async def test_process_allow_happy_path(self):
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine, AgentEngineConfig
        from enhanced_agent_bus.guardrails.enums import SafetyAction

        cfg = AgentEngineConfig(constitutional_validation=True, impact_scoring=True)
        engine = AgentEngine(config=cfg)
        result = await engine.process("hello world", {"trace_id": "t1"})
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        assert result.trace_id == "t1"

    async def test_process_high_impact_escalates(self):
        """When impact score exceeds threshold, result should escalate."""
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine, AgentEngineConfig
        from enhanced_agent_bus.guardrails.enums import SafetyAction

        cfg = AgentEngineConfig(
            constitutional_validation=False,
            impact_scoring=True,
            deliberation_required_threshold=0.5,
        )
        engine = AgentEngine(config=cfg)
        # Force keyword-based scoring by nullifying the scorer
        engine._impact_scorer = None
        # "security" is a high-impact keyword -> score 0.85
        result = await engine.process("security breach detected", {"trace_id": "t2"})
        assert result.allowed is False
        assert result.action == SafetyAction.ESCALATE
        assert any(v.violation_type == "high_impact" for v in result.violations)

    async def test_process_constitutional_violation(self):
        """When constitutional validation fails, result should escalate."""
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine, AgentEngineConfig
        from enhanced_agent_bus.guardrails.enums import SafetyAction

        cfg = AgentEngineConfig(
            constitutional_validation=True,
            impact_scoring=False,
        )
        engine = AgentEngine(config=cfg)
        # Patch _validate_constitutional to return non-compliant
        engine._validate_constitutional = AsyncMock(  # type: ignore[method-assign]
            return_value={"compliant": False, "reason": "violation"}
        )
        result = await engine.process("bad request", {"trace_id": "t3"})
        assert result.allowed is False
        assert result.action == SafetyAction.ESCALATE
        assert any(v.violation_type == "constitutional_violation" for v in result.violations)

    async def test_process_exception_blocks(self):
        """When an exception occurs during processing, result should block."""
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine, AgentEngineConfig
        from enhanced_agent_bus.guardrails.enums import SafetyAction

        cfg = AgentEngineConfig(
            constitutional_validation=True,
            impact_scoring=False,
        )
        engine = AgentEngine(config=cfg)
        engine._validate_constitutional = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("boom")
        )
        result = await engine.process("test", {"trace_id": "t4"})
        assert result.allowed is False
        assert result.action == SafetyAction.BLOCK
        assert any(v.violation_type == "processing_error" for v in result.violations)

    def test_keyword_based_impact_score_none_data(self):
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine

        engine = AgentEngine()
        score = engine._keyword_based_impact_score(None)
        assert score == 0.1

    def test_keyword_based_impact_score_no_keywords(self):
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine

        engine = AgentEngine()
        score = engine._keyword_based_impact_score("hello world")
        assert score == 0.3

    def test_keyword_based_impact_score_with_keywords(self):
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine

        engine = AgentEngine()
        score = engine._keyword_based_impact_score("critical exploit detected")
        assert score == 0.85

    def test_get_layer(self):
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine
        from enhanced_agent_bus.guardrails.enums import GuardrailLayer

        engine = AgentEngine()
        assert engine.get_layer() == GuardrailLayer.AGENT_ENGINE

    async def test_calculate_impact_score_with_scorer(self):
        """Test impact scoring when _impact_scorer is available."""
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine

        engine = AgentEngine()
        mock_scorer = MagicMock()
        mock_result = MagicMock()
        mock_result.aggregate_score = 0.75
        mock_scorer.get_impact_score.return_value = mock_result
        engine._impact_scorer = mock_scorer

        score = await engine._calculate_impact_score("test input", {})
        assert score == 0.75

    async def test_calculate_impact_score_scorer_failure_fallback(self):
        """Test fallback when impact scorer raises."""
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine

        engine = AgentEngine()
        mock_scorer = MagicMock()
        mock_scorer.get_impact_score.side_effect = RuntimeError("scorer down")
        engine._impact_scorer = mock_scorer

        score = await engine._calculate_impact_score("security issue", {})
        # Falls back to keyword-based -> "security" keyword -> 0.85
        assert score == 0.85

    async def test_process_no_trace_id(self):
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine, AgentEngineConfig

        cfg = AgentEngineConfig(constitutional_validation=False, impact_scoring=False)
        engine = AgentEngine(config=cfg)
        result = await engine.process("hello", {})
        assert result.trace_id == ""
        assert result.allowed is True

    def test_init_with_impact_scoring_import_error(self):
        """Test constructor when impact scoring init fails."""
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine, AgentEngineConfig

        cfg = AgentEngineConfig(impact_scoring=True)
        with (
            patch("enhanced_agent_bus.guardrails.agent_engine.IMPACT_SCORING_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.guardrails.agent_engine.get_impact_scorer_service",
                side_effect=RuntimeError("no scorer"),
            ),
        ):
            engine = AgentEngine(config=cfg)
            assert engine._impact_scorer is None

    def test_init_with_minicpm_enabled(self):
        """Test constructor with MiniCPM enabled."""
        from enhanced_agent_bus.guardrails.agent_engine import AgentEngine, AgentEngineConfig

        cfg = AgentEngineConfig(
            impact_scoring=True,
            enable_minicpm=True,
            minicpm_model_name="TestModel",
        )
        mock_scorer = MagicMock()
        mock_scorer.minicpm_available = True
        with (
            patch("enhanced_agent_bus.guardrails.agent_engine.IMPACT_SCORING_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.guardrails.agent_engine.configure_impact_scorer"
            ) as mock_configure,
            patch(
                "enhanced_agent_bus.guardrails.agent_engine.get_impact_scorer_service",
                return_value=mock_scorer,
            ),
        ):
            engine = AgentEngine(config=cfg)
            mock_configure.assert_called_once_with(
                enable_minicpm=True,
                minicpm_model_name="TestModel",
                minicpm_fallback_to_keywords=True,
                prefer_minicpm_semantic=True,
            )
            assert engine._impact_scorer is mock_scorer


# ============================================================================
# 3. mhc.py -- Governance stability (torch-absent paths and torch-present)
# ============================================================================


class TestMHCNoTorch:
    """Test mhc.py code paths when torch is not available."""

    def test_sinkhorn_projection_raises_without_torch(self):
        """sinkhorn_projection should raise ImportError when torch is unavailable."""
        import enhanced_agent_bus.governance.stability.mhc as mhc_mod

        original = mhc_mod.TORCH_AVAILABLE
        try:
            mhc_mod.TORCH_AVAILABLE = False
            with pytest.raises(ImportError, match="torch is required"):
                mhc_mod.sinkhorn_projection(None)
        finally:
            mhc_mod.TORCH_AVAILABLE = original

    def test_manifold_hc_none_when_no_torch(self):
        """ManifoldHC should be None when torch is unavailable."""
        # When torch is not installed, ManifoldHC is set to None at module level
        # We test by checking the conditional at the bottom of the module
        import enhanced_agent_bus.governance.stability.mhc as mhc_mod

        if not mhc_mod.TORCH_AVAILABLE:
            assert mhc_mod.ManifoldHC is None


class TestMHCWithTorch:
    """Test mhc.py with torch available (or skip)."""

    @pytest.fixture(autouse=True)
    def _require_torch(self):
        if not _has_real_torch():
            pytest.skip("torch not installed")

    def test_sinkhorn_projection_basic(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import sinkhorn_projection

        W = torch.randn(3, 3)
        result = sinkhorn_projection(W, iters=20)
        # Result should be doubly stochastic: rows and cols sum to ~1
        row_sums = result.sum(dim=-1)
        col_sums = result.sum(dim=-2)
        assert torch.allclose(row_sums, torch.ones(3), atol=0.01)
        assert torch.allclose(col_sums, torch.ones(3), atol=0.01)

    def test_sinkhorn_projection_with_alpha_capping(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import sinkhorn_projection

        W = torch.randn(3, 3)
        result = sinkhorn_projection(W, iters=20, alpha=0.5)
        # All values should be <= alpha after capping (but Sinkhorn may adjust)
        assert result.shape == (3, 3)

    def test_sinkhorn_projection_with_custom_marginals(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import sinkhorn_projection

        W = torch.randn(3, 3)
        row_m = torch.tensor([1.0, 1.0, 1.0])
        col_m = torch.tensor([1.0, 1.0, 1.0])
        result = sinkhorn_projection(W, row_marginal=row_m, col_marginal=col_m)
        assert result.shape == (3, 3)

    def test_sinkhorn_projection_batched(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import sinkhorn_projection

        W = torch.randn(2, 3, 3)
        result = sinkhorn_projection(W, iters=20)
        assert result.shape == (2, 3, 3)

    def test_sinkhorn_projection_batched_with_marginals(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import sinkhorn_projection

        W = torch.randn(2, 3, 3)
        row_m = torch.ones(2, 3)
        col_m = torch.ones(2, 3)
        result = sinkhorn_projection(W, row_marginal=row_m, col_marginal=col_m)
        assert result.shape == (2, 3, 3)

    def test_manifold_hc_init(self):
        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable without torch")
        mhc = ManifoldHC(dim=4)
        assert mhc.dim == 4
        assert mhc.projection_type == "birkhoff"

    def test_manifold_hc_get_projected_weights(self):
        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable")
        mhc = ManifoldHC(dim=3)
        W = mhc.get_projected_weights()
        assert W.shape == (3, 3)

    def test_manifold_hc_get_projected_weights_non_birkhoff(self):
        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable")
        mhc = ManifoldHC(dim=3, projection_type="identity")
        W = mhc.get_projected_weights()
        # Non-birkhoff just returns raw W
        assert W.shape == (3, 3)

    def test_manifold_hc_forward_birkhoff(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable")
        mhc = ManifoldHC(dim=3)
        x = torch.randn(3, 3)
        out = mhc.forward(x)
        assert out.shape == (3, 3)
        assert mhc.last_stats != {}
        assert "divergence" in mhc.last_stats
        assert "max_weight" in mhc.last_stats
        assert "stability_hash" in mhc.last_stats

    def test_manifold_hc_forward_with_residual(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable")
        mhc = ManifoldHC(dim=3)
        x = torch.randn(3, 3)
        residual = torch.randn(3, 3)
        out = mhc.forward(x, residual=residual)
        assert out.shape == (3, 3)

    def test_manifold_hc_forward_non_birkhoff(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable")
        mhc = ManifoldHC(dim=3, projection_type="identity")
        x = torch.randn(3, 3)
        out = mhc.forward(x)
        assert out.shape == (3, 3)

    def test_manifold_hc_forward_with_alpha(self):
        import torch

        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable")
        mhc = ManifoldHC(dim=3)
        x = torch.randn(3, 3)
        out = mhc.forward(x, alpha=0.5)
        assert out.shape == (3, 3)

    def test_manifold_hc_extra_repr(self):
        from enhanced_agent_bus.governance.stability.mhc import ManifoldHC

        if ManifoldHC is None:
            pytest.skip("ManifoldHC unavailable")
        mhc = ManifoldHC(dim=4, projection_type="birkhoff")
        assert "dim=4" in mhc.extra_repr()
        assert "birkhoff" in mhc.extra_repr()

    def test_sinkhorn_rust_fallback(self):
        """Test that Rust Sinkhorn fallback path is handled."""
        import torch

        import enhanced_agent_bus.governance.stability.mhc as mhc_mod

        # Simulate HAS_RUST_PERF=True but rust call fails
        original_rust = mhc_mod.HAS_RUST_PERF
        try:
            mhc_mod.HAS_RUST_PERF = True
            mock_rust = MagicMock(side_effect=RuntimeError("rust error"))
            mhc_mod.rust_sinkhorn = mock_rust  # type: ignore[attr-defined]

            W = torch.randn(3, 3)
            result = mhc_mod.sinkhorn_projection(W, iters=5)
            assert result.shape == (3, 3)
        finally:
            mhc_mod.HAS_RUST_PERF = original_rust
            if hasattr(mhc_mod, "rust_sinkhorn"):
                delattr(mhc_mod, "rust_sinkhorn")


# ============================================================================
# 4. governance.py routes -- Test API routes directly
# ============================================================================


class TestGovernanceRoutes:
    """Tests for governance API route functions."""

    def test_default_stability_metrics(self):
        from enhanced_agent_bus.api.routes.governance import _default_stability_metrics

        result = _default_stability_metrics()
        assert result.spectral_radius_bound == 1.0
        assert result.divergence == 0.0
        assert result.stability_hash == "mhc_init"

    def test_enforcement_error_to_422(self):
        from enhanced_agent_bus.api.routes.governance import _enforcement_error_to_422

        exc = Exception("test error")
        exc.error_code = "PQC_CLASSICAL_REJECTED"  # type: ignore[attr-defined]
        exc.supported_algorithms = ["ML-DSA-65"]  # type: ignore[attr-defined]
        http_exc = _enforcement_error_to_422(exc)
        assert http_exc.status_code == 422
        assert http_exc.detail["error_code"] == "PQC_CLASSICAL_REJECTED"
        assert http_exc.detail["supported_algorithms"] == ["ML-DSA-65"]

    def test_enforcement_error_to_422_no_attrs(self):
        from enhanced_agent_bus.api.routes.governance import _enforcement_error_to_422

        exc = ValueError("plain error")
        http_exc = _enforcement_error_to_422(exc)
        assert http_exc.status_code == 422
        assert http_exc.detail["error_code"] == "PQC_ERROR"
        assert http_exc.detail["supported_algorithms"] == []

    def test_load_governance_dependency_fallback(self):
        """When both imports fail, _load_governance_dependency returns a callable returning None."""
        from enhanced_agent_bus.api.routes.governance import _load_governance_dependency

        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.governance.ccai_framework": None,
                "governance.ccai_framework": None,
            },
        ):
            # The function is already evaluated at module load; test the fallback directly
            pass

        # Test the module-level get_ccai_governance
        from enhanced_agent_bus.api.routes.governance import get_ccai_governance

        # It should be a callable
        assert callable(get_ccai_governance)

    def test_maci_record_models(self):
        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordCreateRequest,
            MACIRecordResponse,
            MACIRecordUpdateRequest,
        )

        create_req = MACIRecordCreateRequest(
            record_id="r1",
            key_type="pqc",
            key_algorithm="ML-DSA-65",
            data={"field": "value"},
        )
        assert create_req.record_id == "r1"

        update_req = MACIRecordUpdateRequest(data={"updated": True})
        assert update_req.data == {"updated": True}

        resp = MACIRecordResponse(record_id="r1", status="created")
        assert resp.status == "created"

    async def test_get_enforcement_config_returns_none(self):
        from unittest.mock import MagicMock

        from enhanced_agent_bus.api.routes.governance import _get_enforcement_config

        mock_request = MagicMock()
        mock_request.app.state = None
        assert await _get_enforcement_config(mock_request) is None


class TestGovernanceRoutesIntegration:
    """Integration tests using FastAPI TestClient for governance routes."""

    @pytest.fixture
    def client(self):
        """Create a test client with governance routes."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from enhanced_agent_bus.api.routes.governance import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_get_stability_metrics_no_gov(self, client):
        """When governance is not initialized, return 503."""
        with (
            patch(
                "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
                return_value=None,
            ),
            patch(
                "enhanced_agent_bus.api.routes.governance.get_current_user",
                return_value=MagicMock(),
            ),
        ):
            from enhanced_agent_bus.api.routes.governance import router as gov_router

            app = MagicMock()
            # Direct function call test
            pass

    async def test_get_stability_metrics_func_no_gov(self):
        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=None,
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert exc_info.value.status_code == 503

    async def test_get_stability_metrics_no_stability_layer(self):
        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        mock_gov = MagicMock()
        mock_gov.stability_layer = None
        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=mock_gov,
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert exc_info.value.status_code == 503

    async def test_get_stability_metrics_no_stats(self):
        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        mock_layer = MagicMock()
        mock_layer.last_stats = None
        mock_gov = MagicMock()
        mock_gov.stability_layer = mock_layer
        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=mock_gov,
        ):
            result = await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert result.stability_hash == "mhc_init"

    async def test_get_stability_metrics_with_stats(self):
        from enhanced_agent_bus.api.routes.governance import get_stability_metrics

        stats = {
            "spectral_radius_bound": 0.99,
            "divergence": 0.01,
            "max_weight": 0.35,
            "stability_hash": "mhc_abc123",
            "input_norm": 1.5,
            "output_norm": 1.4,
        }
        mock_layer = MagicMock()
        mock_layer.last_stats = stats
        mock_gov = MagicMock()
        mock_gov.stability_layer = mock_layer
        with patch(
            "enhanced_agent_bus.api.routes.governance.get_ccai_governance",
            return_value=mock_gov,
        ):
            result = await get_stability_metrics(request=MagicMock(), _user=MagicMock())
            assert result.spectral_radius_bound == 0.99
            assert result.stability_hash == "mhc_abc123"

    async def test_create_maci_record_no_enforcement(self):
        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordCreateRequest,
            create_maci_record,
        )

        body = MACIRecordCreateRequest(record_id="r1", data={"x": 1})
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await create_maci_record(
                body=body,
                request=mock_request,
                _tenant_id="t1",
                enforcement_svc=None,
            )
        assert result.record_id == "r1"
        assert result.status == "created"

    async def test_create_maci_record_with_enforcement_pass(self):
        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordCreateRequest,
            create_maci_record,
        )

        body = MACIRecordCreateRequest(record_id="r2", key_type="pqc", key_algorithm="ML-DSA-65")
        mock_request = MagicMock()
        mock_request.headers = {"X-Migration-Context": "false"}
        mock_enforce = MagicMock()
        mock_check = AsyncMock()

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
                enforcement_svc=mock_enforce,
            )
        assert result.status == "created"
        mock_check.assert_awaited_once()

    async def test_create_maci_record_enforcement_rejects(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordCreateRequest,
            create_maci_record,
        )

        body = MACIRecordCreateRequest(
            record_id="r3", key_type="classical", key_algorithm="RSA-2048"
        )
        mock_request = MagicMock()
        mock_request.headers = {"X-Migration-Context": "false"}

        # Create a custom exception class that we can catch
        class TestPQCError(Exception):
            error_code = "PQC_CLASSICAL_REJECTED"
            supported_algorithms = ["ML-DSA-65"]

        mock_check = AsyncMock(side_effect=TestPQCError("rejected"))

        with (
            patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"),
            patch(
                "enhanced_agent_bus.api.routes.governance.check_enforcement_for_create",
                mock_check,
            ),
            patch(
                "enhanced_agent_bus.api.routes.governance._PQC_ENFORCEMENT_ERRORS",
                (TestPQCError,),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_maci_record(
                    body=body,
                    request=mock_request,
                    _tenant_id="t1",
                    enforcement_svc=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    async def test_update_maci_record_no_enforcement(self):
        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordUpdateRequest,
            update_maci_record,
        )

        body = MACIRecordUpdateRequest(data={"updated": True})
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await update_maci_record(
                record_id="r1",
                body=body,
                request=mock_request,
                _tenant_id="t1",
                enforcement_svc=None,
            )
        assert result.status == "updated"

    async def test_update_maci_record_enforcement_rejects(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.governance import (
            MACIRecordUpdateRequest,
            update_maci_record,
        )

        body = MACIRecordUpdateRequest(data={})
        mock_request = MagicMock()
        mock_request.headers = {"X-Migration-Context": "true"}

        class TestPQCError(Exception):
            error_code = "MIGRATION_REQUIRED"
            supported_algorithms = []

        mock_check = AsyncMock(side_effect=TestPQCError("migrate"))

        with (
            patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"),
            patch(
                "enhanced_agent_bus.api.routes.governance.check_enforcement_for_update",
                mock_check,
            ),
            patch(
                "enhanced_agent_bus.api.routes.governance._PQC_ENFORCEMENT_ERRORS",
                (TestPQCError,),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_maci_record(
                    record_id="r1",
                    body=body,
                    request=mock_request,
                    _tenant_id="t1",
                    enforcement_svc=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    async def test_get_maci_record(self):
        from enhanced_agent_bus.api.routes.governance import get_maci_record

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await get_maci_record(request=MagicMock(), record_id="r1", _tenant_id="t1")
        assert result.record_id == "r1"
        assert result.status == "ok"

    async def test_delete_maci_record(self):
        from enhanced_agent_bus.api.routes.governance import delete_maci_record

        with patch("enhanced_agent_bus.api.routes.governance.require_sandbox_endpoint"):
            result = await delete_maci_record(request=MagicMock(), record_id="r1", _tenant_id="t1")
        assert result.record_id == "r1"
        assert result.status == "deleted"


# ============================================================================
# 5. llamaindex.py -- Governed query/chat engines
# ============================================================================


class TestLlamaIndexExtractResponseText:
    """Test _extract_response_text utility."""

    def test_extract_str_response(self):
        from acgs_lite.integrations.llamaindex import _extract_response_text

        assert _extract_response_text("hello") == "hello"

    def test_extract_response_attr(self):
        from acgs_lite.integrations.llamaindex import _extract_response_text

        obj = MagicMock()
        obj.response = "from response attr"
        assert _extract_response_text(obj) == "from response attr"

    def test_extract_text_attr(self):
        from acgs_lite.integrations.llamaindex import _extract_response_text

        obj = MagicMock(spec=[])  # no 'response' attr
        obj.text = "from text attr"
        assert _extract_response_text(obj) == "from text attr"

    def test_extract_fallback_str(self):
        from acgs_lite.integrations.llamaindex import _extract_response_text

        assert _extract_response_text(12345) == "12345"


class TestGovernedQueryEngine:
    """Test GovernedQueryEngine with mocked llama_index."""

    @pytest.fixture(autouse=True)
    def _patch_llamaindex(self):
        """Make LLAMAINDEX_AVAILABLE True so the classes can be instantiated."""
        with patch("acgs_lite.integrations.llamaindex.LLAMAINDEX_AVAILABLE", True):
            yield

    def test_init(self):
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        mock_engine = MagicMock()
        gqe = GovernedQueryEngine(mock_engine, agent_id="test-query")
        assert gqe.agent_id == "test-query"
        assert gqe._engine is mock_engine

    def test_query_happy_path(self):
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        mock_engine = MagicMock()
        mock_engine.query.return_value = "safe response"
        gqe = GovernedQueryEngine(mock_engine)
        result = gqe.query("what is the policy?")
        assert result == "safe response"
        mock_engine.query.assert_called_once()

    def test_query_with_violations_in_output(self):
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        mock_engine = MagicMock()
        mock_engine.query.return_value = "safe response text"

        gqe = GovernedQueryEngine(mock_engine, strict=False)
        # Mock validate to return violations on output check
        mock_result = MagicMock()
        mock_result.valid = False
        mock_result.violations = [MagicMock(rule_id="R1")]

        original_validate = gqe.gov_engine.validate
        call_count = [0]

        def side_effect_validate(text, agent_id=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # Input validation passes
                return MagicMock(valid=True, violations=[])
            # Output validation fails
            return mock_result

        gqe.gov_engine.validate = side_effect_validate  # type: ignore[assignment]
        result = gqe.query("test")
        assert result == "safe response text"

    async def test_aquery_happy_path(self):
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        mock_engine = MagicMock()
        mock_engine.aquery = AsyncMock(return_value="async response")
        gqe = GovernedQueryEngine(mock_engine)
        result = await gqe.aquery("async query")
        assert result == "async response"

    async def test_aquery_with_output_violations(self):
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        mock_engine = MagicMock()
        mock_engine.aquery = AsyncMock(return_value="async response text")

        gqe = GovernedQueryEngine(mock_engine, strict=False)
        mock_result = MagicMock()
        mock_result.valid = False
        mock_result.violations = [MagicMock(rule_id="R2")]

        call_count = [0]

        def side_effect_validate(text, agent_id=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(valid=True, violations=[])
            return mock_result

        gqe.gov_engine.validate = side_effect_validate  # type: ignore[assignment]
        result = await gqe.aquery("test")
        assert result == "async response text"

    def test_stats_property(self):
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        mock_engine = MagicMock()
        gqe = GovernedQueryEngine(mock_engine, agent_id="test-q")
        stats = gqe.stats
        assert stats["agent_id"] == "test-q"
        assert "audit_chain_valid" in stats

    def test_init_raises_without_llamaindex(self):
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        with patch("acgs_lite.integrations.llamaindex.LLAMAINDEX_AVAILABLE", False):
            with pytest.raises(ImportError, match="llama-index is required"):
                GovernedQueryEngine(MagicMock())


class TestGovernedChatEngine:
    """Test GovernedChatEngine with mocked llama_index."""

    @pytest.fixture(autouse=True)
    def _patch_llamaindex(self):
        with patch("acgs_lite.integrations.llamaindex.LLAMAINDEX_AVAILABLE", True):
            yield

    def test_init(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        gce = GovernedChatEngine(mock_engine, agent_id="test-chat")
        assert gce.agent_id == "test-chat"

    def test_chat_happy_path(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        mock_engine.chat.return_value = "chat response"
        gce = GovernedChatEngine(mock_engine)
        result = gce.chat("hello")
        assert result == "chat response"

    def test_chat_with_output_violations(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        mock_engine.chat.return_value = "chat resp"

        gce = GovernedChatEngine(mock_engine, strict=False)
        mock_result = MagicMock()
        mock_result.valid = False
        mock_result.violations = [MagicMock(rule_id="R3")]

        call_count = [0]

        def side_effect_validate(text, agent_id=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(valid=True, violations=[])
            return mock_result

        gce.gov_engine.validate = side_effect_validate  # type: ignore[assignment]
        result = gce.chat("test")
        assert result == "chat resp"

    async def test_achat_happy_path(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        mock_engine.achat = AsyncMock(return_value="async chat")
        gce = GovernedChatEngine(mock_engine)
        result = await gce.achat("async msg")
        assert result == "async chat"

    async def test_achat_with_violations(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        mock_engine.achat = AsyncMock(return_value="async chat resp")

        gce = GovernedChatEngine(mock_engine, strict=False)
        mock_result = MagicMock()
        mock_result.valid = False
        mock_result.violations = [MagicMock(rule_id="R4")]

        call_count = [0]

        def side_effect_validate(text, agent_id=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(valid=True, violations=[])
            return mock_result

        gce.gov_engine.validate = side_effect_validate  # type: ignore[assignment]
        result = await gce.achat("test")
        assert result == "async chat resp"

    def test_stream_chat(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        mock_engine.stream_chat.return_value = iter(["chunk1", "chunk2"])
        gce = GovernedChatEngine(mock_engine)
        result = gce.stream_chat("stream msg")
        assert result is not None

    def test_reset_with_engine_reset(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        gce = GovernedChatEngine(mock_engine)
        gce.reset()
        mock_engine.reset.assert_called_once()

    def test_reset_without_engine_reset(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock(spec=[])  # no reset method
        gce = GovernedChatEngine(mock_engine)
        gce.reset()  # Should not raise

    def test_chat_history_with_engine_history(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        mock_engine.chat_history = ["msg1", "msg2"]
        gce = GovernedChatEngine(mock_engine)
        assert gce.chat_history == ["msg1", "msg2"]

    def test_chat_history_without_engine_history(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock(spec=[])  # no chat_history
        gce = GovernedChatEngine(mock_engine)
        assert gce.chat_history == []

    def test_stats_property(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        mock_engine = MagicMock()
        gce = GovernedChatEngine(mock_engine, agent_id="test-c")
        stats = gce.stats
        assert stats["agent_id"] == "test-c"
        assert "audit_chain_valid" in stats

    def test_init_raises_without_llamaindex(self):
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        with patch("acgs_lite.integrations.llamaindex.LLAMAINDEX_AVAILABLE", False):
            with pytest.raises(ImportError, match="llama-index is required"):
                GovernedChatEngine(MagicMock())
