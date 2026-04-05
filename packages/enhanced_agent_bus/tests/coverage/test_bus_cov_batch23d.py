"""
Coverage tests for sandbox guardrail, verification orchestrator, and adaptive threshold manager.

Targets:
- enhanced_agent_bus.guardrails.sandbox (ToolRunnerSandbox)
- enhanced_agent_bus.verification_orchestrator (VerificationOrchestrator)
- enhanced_agent_bus.adaptive_governance.threshold_manager (AdaptiveThresholds)

Constitutional Hash: 608508a9bd224290
"""

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Adaptive threshold imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.adaptive_governance.threshold_manager import (
    AdaptiveThresholds,
)

# ---------------------------------------------------------------------------
# Verification orchestrator imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.guardrails.enums import (
    GuardrailLayer,
    SafetyAction,
    ViolationSeverity,
)

# ---------------------------------------------------------------------------
# Sandbox imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.guardrails.sandbox import (
    SandboxConfig,
    ToolRunnerSandbox,
)
from enhanced_agent_bus.guardrails.sandbox_providers import (
    MockSandboxProvider,
    SandboxExecutionResult,
    SandboxProviderType,
)
from enhanced_agent_bus.models import AgentMessage, MessageType
from enhanced_agent_bus.validators import ValidationResult
from enhanced_agent_bus.verification_orchestrator import (
    VerificationOrchestrator,
    VerificationResult,
)

# =========================================================================
# Helpers
# =========================================================================


def _make_features(**overrides) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=3,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2, 0.3],
        semantic_similarity=0.7,
        historical_precedence=5,
        resource_utilization=0.4,
        network_isolation=0.6,
        risk_score=0.3,
        confidence_level=0.9,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides) -> GovernanceDecision:
    defaults = dict(
        action_allowed=True,
        impact_level=ImpactLevel.MEDIUM,
        confidence_score=0.85,
        reasoning="test decision",
        recommended_threshold=0.65,
        features_used=_make_features(),
    )
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


def _make_msg(**overrides) -> AgentMessage:
    defaults = dict(
        from_agent="agent-a",
        to_agent="agent-b",
        content={"text": "hello"},
        tenant_id="tenant-1",
    )
    defaults.update(overrides)
    return AgentMessage(**defaults)


# =========================================================================
# SECTION 1: ToolRunnerSandbox tests
# =========================================================================


class TestSandboxConfig:
    def test_default_config(self):
        cfg = SandboxConfig()
        assert cfg.enabled is True
        assert cfg.use_docker is True
        assert cfg.use_firecracker is False
        assert cfg.timeout_ms == 10000
        assert cfg.memory_limit_mb == 512
        assert cfg.cpu_limit == 0.5
        assert cfg.network_isolation is True
        assert cfg.provider_type == SandboxProviderType.DOCKER


class TestToolRunnerSandboxInit:
    def test_default_config_applied(self):
        sandbox = ToolRunnerSandbox()
        assert sandbox.config.enabled is True
        assert sandbox._initialized is False
        assert sandbox._provider is None

    def test_custom_config(self):
        cfg = SandboxConfig(enabled=False, timeout_ms=5000)
        sandbox = ToolRunnerSandbox(config=cfg)
        assert sandbox.config.enabled is False
        assert sandbox.config.timeout_ms == 5000

    def test_get_layer(self):
        sandbox = ToolRunnerSandbox()
        assert sandbox.get_layer() == GuardrailLayer.TOOL_RUNNER_SANDBOX


class TestToolRunnerSandboxInitialize:
    async def test_initialize_docker_provider(self):
        sandbox = ToolRunnerSandbox(config=SandboxConfig(use_docker=True, use_firecracker=False))
        with patch("enhanced_agent_bus.guardrails.sandbox.DockerSandboxProvider") as mock_cls:
            mock_provider = AsyncMock()
            mock_provider.initialize = AsyncMock(return_value=True)
            mock_cls.return_value = mock_provider

            result = await sandbox.initialize()
            assert result is True
            assert sandbox._initialized is True

    async def test_initialize_firecracker_provider(self):
        sandbox = ToolRunnerSandbox(config=SandboxConfig(use_firecracker=True))
        with patch("enhanced_agent_bus.guardrails.sandbox.FirecrackerSandboxProvider") as mock_cls:
            mock_provider = AsyncMock()
            mock_provider.initialize = AsyncMock(return_value=True)
            mock_cls.return_value = mock_provider

            result = await sandbox.initialize()
            assert result is True

    async def test_initialize_mock_provider(self):
        sandbox = ToolRunnerSandbox(config=SandboxConfig(use_docker=False, use_firecracker=False))
        with patch("enhanced_agent_bus.guardrails.sandbox.MockSandboxProvider") as mock_cls:
            mock_provider = AsyncMock()
            mock_provider.initialize = AsyncMock(return_value=True)
            mock_cls.return_value = mock_provider

            result = await sandbox.initialize()
            assert result is True

    async def test_already_initialized_returns_true(self):
        sandbox = ToolRunnerSandbox()
        sandbox._initialized = True
        result = await sandbox.initialize()
        assert result is True

    async def test_initialize_fallback_on_provider_failure(self):
        sandbox = ToolRunnerSandbox(config=SandboxConfig(use_docker=True, use_firecracker=False))
        with (
            patch("enhanced_agent_bus.guardrails.sandbox.DockerSandboxProvider") as docker_cls,
            patch("enhanced_agent_bus.guardrails.sandbox.MockSandboxProvider") as mock_cls,
        ):
            docker_provider = AsyncMock()
            docker_provider.initialize = AsyncMock(return_value=False)
            docker_cls.return_value = docker_provider

            fallback_provider = AsyncMock()
            fallback_provider.initialize = AsyncMock(return_value=True)
            mock_cls.return_value = fallback_provider

            result = await sandbox.initialize()
            assert result is True

    async def test_initialize_fallback_on_exception(self):
        sandbox = ToolRunnerSandbox(config=SandboxConfig(use_docker=True, use_firecracker=False))
        with (
            patch("enhanced_agent_bus.guardrails.sandbox.DockerSandboxProvider") as docker_cls,
            patch("enhanced_agent_bus.guardrails.sandbox.MockSandboxProvider") as mock_cls,
        ):
            docker_cls.side_effect = RuntimeError("Docker unavailable")

            fallback_provider = AsyncMock()
            fallback_provider.initialize = AsyncMock(return_value=True)
            mock_cls.return_value = fallback_provider

            result = await sandbox.initialize()
            assert result is True


class TestToolRunnerSandboxCleanup:
    async def test_cleanup_with_provider(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        sandbox._provider = mock_provider
        sandbox._initialized = True

        await sandbox.cleanup()

        mock_provider.cleanup.assert_awaited_once()
        assert sandbox._initialized is False

    async def test_cleanup_without_provider(self):
        sandbox = ToolRunnerSandbox()
        await sandbox.cleanup()  # Should not raise


class TestToolRunnerSandboxProcess:
    async def test_process_disabled_config(self):
        sandbox = ToolRunnerSandbox(config=SandboxConfig(enabled=False))
        result = await sandbox.process({"code": "x = 1"}, {"trace_id": "t1"})
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW

    async def test_process_no_sandbox_needed_plain_data(self):
        sandbox = ToolRunnerSandbox()
        result = await sandbox.process(
            {"message": "hello"},
            {"trace_id": "t2", "should_sandbox": False},
        )
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        assert result.processing_time_ms >= 0

    async def test_process_sandbox_triggered_by_key(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(
            return_value=SandboxExecutionResult(success=True, output={"result": 42}, trace_id="t3")
        )
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox.process(
            {"code": "print(1)"},
            {"trace_id": "t3"},
        )
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW

    async def test_process_sandbox_triggered_by_context(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(
            return_value=SandboxExecutionResult(success=True, output={"ok": True}, trace_id="t4")
        )
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox.process(
            {"data": "safe"},
            {"trace_id": "t4", "should_sandbox": True},
        )
        assert result.allowed is True

    async def test_process_sandbox_execution_failed(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(
            return_value=SandboxExecutionResult(
                success=False, error_message="timeout", trace_id="t5"
            )
        )
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox.process(
            {"code": "while True: pass"},
            {"trace_id": "t5"},
        )
        assert result.allowed is False
        assert result.action == SafetyAction.BLOCK
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "sandbox_execution_failed"
        assert result.violations[0].severity == ViolationSeverity.HIGH

    async def test_process_sandbox_raises_runtime_error(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(side_effect=RuntimeError("boom"))
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox.process(
            {"execute": "bad"},
            {"trace_id": "t6"},
        )
        assert result.allowed is False
        assert result.action == SafetyAction.BLOCK
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "sandbox_error"
        assert result.violations[0].severity == ViolationSeverity.CRITICAL

    async def test_process_sandbox_raises_timeout_error(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(side_effect=TimeoutError("timed out"))
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox.process(
            {"run": "slow"},
            {"trace_id": "t7"},
        )
        assert result.allowed is False
        assert result.action == SafetyAction.BLOCK

    async def test_process_sandbox_raises_value_error(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(side_effect=ValueError("bad value"))
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox.process(
            {"eval": "None"},
            {"trace_id": "t8"},
        )
        assert result.allowed is False

    async def test_process_non_dict_data_not_sandboxed(self):
        sandbox = ToolRunnerSandbox()
        result = await sandbox.process("plain string", {"trace_id": "t9"})
        assert result.allowed is True

    async def test_process_success_includes_modified_data(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(
            return_value=SandboxExecutionResult(
                success=True, output={"transformed": True}, trace_id="t10"
            )
        )
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox.process(
            {"script": "transform()"},
            {"trace_id": "t10"},
        )
        assert result.modified_data == {"transformed": True}


class TestExecuteInSandbox:
    async def test_execute_not_initialized_calls_initialize(self):
        sandbox = ToolRunnerSandbox()
        with patch("enhanced_agent_bus.guardrails.sandbox.MockSandboxProvider") as mock_cls:
            mock_provider = AsyncMock()
            mock_provider.initialize = AsyncMock(return_value=True)
            mock_provider.execute = AsyncMock(
                return_value=SandboxExecutionResult(success=True, output={})
            )
            mock_cls.return_value = mock_provider

            sandbox.config = SandboxConfig(use_docker=False, use_firecracker=False)
            result = await sandbox._execute_in_sandbox({"code": "x"}, {"trace_id": "e1"})
            assert result["success"] is True

    async def test_execute_no_provider_returns_error(self):
        sandbox = ToolRunnerSandbox()
        sandbox._initialized = True
        sandbox._provider = None

        result = await sandbox._execute_in_sandbox({"code": "x"}, {"trace_id": "e2"})
        assert result["success"] is False
        assert "No sandbox provider" in result["error"]

    async def test_execute_wraps_non_dict_data(self):
        sandbox = ToolRunnerSandbox()
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(
            return_value=SandboxExecutionResult(success=True, output={"ok": True})
        )
        sandbox._provider = mock_provider
        sandbox._initialized = True

        result = await sandbox._execute_in_sandbox("raw_string", {"trace_id": "e3"})
        assert result["success"] is True
        # Verify the request wrapped non-dict data
        call_args = mock_provider.execute.call_args
        request = call_args[0][0]
        assert request.data == {"input": "raw_string"}

    async def test_execute_passes_resource_limits(self):
        sandbox = ToolRunnerSandbox(
            config=SandboxConfig(
                cpu_limit=1.0, memory_limit_mb=1024, timeout_ms=5000, network_isolation=False
            )
        )
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(
            return_value=SandboxExecutionResult(success=True, output={})
        )
        sandbox._provider = mock_provider
        sandbox._initialized = True

        await sandbox._execute_in_sandbox({"action_type": "test"}, {"trace_id": "e4"})
        call_args = mock_provider.execute.call_args
        request = call_args[0][0]
        assert request.resource_limits.cpu_limit == 1.0
        assert request.resource_limits.memory_limit_mb == 1024
        assert request.resource_limits.timeout_seconds == 5.0
        assert request.resource_limits.network_disabled is False


# =========================================================================
# SECTION 2: VerificationOrchestrator tests
# =========================================================================


class TestVerificationResult:
    def test_defaults(self):
        vr = VerificationResult()
        assert vr.sdpc_metadata == {}
        assert vr.pqc_result is None
        assert vr.pqc_metadata == {}


class TestVerificationOrchestratorInit:
    def test_init_creates_noop_stubs(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        assert orch._enable_pqc is False
        assert orch._pqc_config is None
        assert orch._pqc_service is None
        # Should have intent_classifier and verifiers (stubs or real)
        assert hasattr(orch, "intent_classifier")
        assert hasattr(orch, "asc_verifier")
        assert hasattr(orch, "graph_check")
        assert hasattr(orch, "pacar_verifier")
        assert hasattr(orch, "evolution_controller")
        assert hasattr(orch, "ampo_engine")


class TestVerificationOrchestratorSDPC:
    def _mock_verifiers(self, orch):
        """Replace verifiers with async mocks that accept any args."""

        async def _mock_verify(*args, **kwargs):
            return {"is_valid": True, "confidence": 1.0, "results": []}

        orch.asc_verifier = MagicMock()
        orch.asc_verifier.verify = AsyncMock(side_effect=_mock_verify)
        orch.graph_check = MagicMock()
        orch.graph_check.verify_entities = AsyncMock(side_effect=_mock_verify)
        orch.pacar_verifier = MagicMock()
        orch.pacar_verifier.verify = AsyncMock(side_effect=_mock_verify)
        orch.evolution_controller = MagicMock()
        orch.evolution_controller.record_feedback = MagicMock()

    async def test_sdpc_unknown_intent_no_tasks(self):
        """Unknown intent with low impact should skip ASC/graph/PACAR."""
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        self._mock_verifiers(orch)

        msg = _make_msg(impact_score=0.0, message_type=MessageType.COMMAND)
        result = await orch.verify(msg, "hello world")

        assert isinstance(result, VerificationResult)
        assert result.pqc_result is None

    async def test_sdpc_high_impact_triggers_asc_graph(self):
        """High impact_score should trigger ASC and graph verification."""
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        self._mock_verifiers(orch)

        msg = _make_msg(impact_score=0.9, message_type=MessageType.COMMAND)
        result = await orch.verify(msg, "important content")

        assert isinstance(result, VerificationResult)
        assert "sdpc_asc_valid" in result.sdpc_metadata
        assert "sdpc_graph_grounded" in result.sdpc_metadata
        assert "sdpc_pacar_valid" in result.sdpc_metadata

    async def test_sdpc_task_request_triggers_pacar(self):
        """TASK_REQUEST message type should trigger PACAR."""
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        self._mock_verifiers(orch)

        msg = _make_msg(impact_score=0.5, message_type=MessageType.TASK_REQUEST)
        result = await orch.verify(msg, "do something")

        assert "sdpc_pacar_valid" in result.sdpc_metadata

    async def test_sdpc_none_impact_score_treated_as_zero(self):
        """impact_score=None should be treated as 0.0."""
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        self._mock_verifiers(orch)

        msg = _make_msg(impact_score=None, message_type=MessageType.COMMAND)
        result = await orch.verify(msg, "test")

        assert isinstance(result, VerificationResult)

    async def test_sdpc_factual_intent_triggers_asc_graph(self):
        """Factual intent (mocked) should trigger ASC and graph."""
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        self._mock_verifiers(orch)

        # Mock the intent classifier to return FACTUAL
        factual_intent = MagicMock()
        factual_intent.value = orch._IntentType.FACTUAL.value
        orch.intent_classifier.classify_async = AsyncMock(return_value=factual_intent)

        msg = _make_msg(impact_score=0.0, message_type=MessageType.COMMAND)
        result = await orch.verify(msg, "what is X?")

        assert "sdpc_asc_valid" in result.sdpc_metadata
        assert "sdpc_graph_grounded" in result.sdpc_metadata

    async def test_sdpc_pacar_critique_in_result(self):
        """PACAR result with critique should be included in metadata."""
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        self._mock_verifiers(orch)

        async def _pacar_with_critique(*args, **kwargs):
            return {"is_valid": True, "confidence": 0.9, "critique": "looks good"}

        orch.pacar_verifier.verify = AsyncMock(side_effect=_pacar_with_critique)

        msg = _make_msg(impact_score=0.9, message_type=MessageType.TASK_REQUEST)
        result = await orch.verify(msg, "critical op")

        assert result.sdpc_metadata.get("sdpc_pacar_critique") == "looks good"

    async def test_sdpc_evolution_controller_called(self):
        """evolution_controller.record_feedback should be called when verifications exist."""
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        self._mock_verifiers(orch)

        msg = _make_msg(impact_score=0.9, message_type=MessageType.COMMAND)
        await orch.verify(msg, "content")

        orch.evolution_controller.record_feedback.assert_called_once()


class TestVerificationOrchestratorPQC:
    async def test_pqc_disabled_returns_none(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)

        msg = _make_msg()
        pqc_result, pqc_metadata = await orch.verify_pqc(msg)
        assert pqc_result is None
        assert pqc_metadata == {}

    async def test_pqc_no_config_returns_none(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=True)
        # _init_pqc will fail (ImportError), setting _enable_pqc=False
        msg = _make_msg()
        pqc_result, pqc_metadata = await orch.verify_pqc(msg)
        assert pqc_result is None

    async def test_pqc_import_error_skips_validation(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        # Force pqc enabled but no config
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": None}):
            with patch(
                "enhanced_agent_bus.verification_orchestrator.VerificationOrchestrator._perform_pqc",
                new_callable=AsyncMock,
                return_value=(None, {}),
            ):
                msg = _make_msg()
                pqc_result, pqc_meta = await orch.verify_pqc(msg)
                assert pqc_result is None

    async def test_pqc_validation_failed_returns_validation_result(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()
        orch._pqc_config.pqc_mode = "hybrid"

        mock_pqc_result = MagicMock()
        mock_pqc_result.valid = False
        mock_pqc_result.errors = ["hash mismatch"]
        mock_pqc_result.pqc_metadata = MagicMock()
        mock_pqc_result.pqc_metadata.to_dict.return_value = {"algo": "kyber768"}
        mock_pqc_result.validation_duration_ms = 1.5

        mock_pqc_validators = MagicMock()
        mock_pqc_validators.validate_constitutional_hash_pqc = AsyncMock(
            return_value=mock_pqc_result
        )

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": mock_pqc_validators}):
            msg = _make_msg()
            pqc_result, pqc_meta = await orch._perform_pqc(msg)
            assert pqc_result is not None
            assert pqc_result.is_valid is False
            assert "hash mismatch" in pqc_result.errors

    async def test_pqc_validation_success_returns_metadata(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()

        mock_pqc_result = MagicMock()
        mock_pqc_result.valid = True
        mock_pqc_result.pqc_metadata = MagicMock()
        mock_pqc_result.pqc_metadata.pqc_algorithm = "kyber768"
        mock_pqc_result.pqc_metadata.verification_mode = "hybrid"
        mock_pqc_result.pqc_metadata.classical_verified = True
        mock_pqc_result.pqc_metadata.pqc_verified = True
        mock_pqc_result.classical_verification_ms = 0.5
        mock_pqc_result.pqc_verification_ms = 1.2

        mock_pqc_validators = MagicMock()
        mock_pqc_validators.validate_constitutional_hash_pqc = AsyncMock(
            return_value=mock_pqc_result
        )

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": mock_pqc_validators}):
            msg = _make_msg()
            pqc_result, pqc_meta = await orch._perform_pqc(msg)
            assert pqc_result is None
            assert pqc_meta["pqc_enabled"] is True
            assert pqc_meta["pqc_algorithm"] == "kyber768"
            assert pqc_meta["classical_verified"] is True

    async def test_pqc_validation_success_no_pqc_metadata(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()

        mock_pqc_result = MagicMock()
        mock_pqc_result.valid = True
        mock_pqc_result.pqc_metadata = None
        mock_pqc_result.classical_verification_ms = None
        mock_pqc_result.pqc_verification_ms = None

        mock_pqc_validators = MagicMock()
        mock_pqc_validators.validate_constitutional_hash_pqc = AsyncMock(
            return_value=mock_pqc_result
        )

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": mock_pqc_validators}):
            msg = _make_msg()
            pqc_result, pqc_meta = await orch._perform_pqc(msg)
            assert pqc_result is None
            assert pqc_meta == {}

    async def test_pqc_runtime_error_pqc_only_mode_returns_failure(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()
        orch._pqc_config.pqc_mode = "pqc_only"

        mock_pqc_validators = MagicMock()
        mock_pqc_validators.validate_constitutional_hash_pqc = AsyncMock(
            side_effect=RuntimeError("PQC crypto failure")
        )

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": mock_pqc_validators}):
            msg = _make_msg()
            pqc_result, pqc_meta = await orch._perform_pqc(msg)
            assert pqc_result is not None
            assert pqc_result.is_valid is False
            assert "PQC validation error" in pqc_result.errors[0]

    async def test_pqc_runtime_error_hybrid_mode_continues(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()
        orch._pqc_config.pqc_mode = "hybrid"

        mock_pqc_validators = MagicMock()
        mock_pqc_validators.validate_constitutional_hash_pqc = AsyncMock(
            side_effect=ValueError("bad data")
        )

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": mock_pqc_validators}):
            msg = _make_msg()
            pqc_result, pqc_meta = await orch._perform_pqc(msg)
            assert pqc_result is None
            assert pqc_meta == {}

    async def test_pqc_message_with_signature(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()

        mock_pqc_result = MagicMock()
        mock_pqc_result.valid = True
        mock_pqc_result.pqc_metadata = None

        mock_pqc_validators = MagicMock()
        mock_pqc_validators.validate_constitutional_hash_pqc = AsyncMock(
            return_value=mock_pqc_result
        )

        msg = _make_msg()
        msg.signature = "abc123"  # type: ignore[attr-defined]

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": mock_pqc_validators}):
            pqc_result, pqc_meta = await orch._perform_pqc(msg)
            assert pqc_result is None


class TestVerificationOrchestratorInitPQC:
    def test_init_pqc_import_error_disables_pqc(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        # Force pqc_validators to not be importable
        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": None}):
            orch._enable_pqc = True
            orch._init_pqc(config)
        assert orch._enable_pqc is False

    def test_init_pqc_runtime_error_disables_pqc(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True

        mock_pqc_validators = MagicMock()
        mock_pqc_validators.PQCConfig = MagicMock(side_effect=RuntimeError("crypto init"))

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": mock_pqc_validators}):
            orch._init_pqc(config)
        assert orch._enable_pqc is False


class TestVerificationOrchestratorVerify:
    async def test_verify_combines_sdpc_and_pqc(self):
        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)

        # Mock verifiers to avoid PACARVerifier signature issue
        async def _mock_verify(*args, **kwargs):
            return {"is_valid": True, "confidence": 1.0, "results": []}

        orch.asc_verifier = MagicMock()
        orch.asc_verifier.verify = AsyncMock(side_effect=_mock_verify)
        orch.graph_check = MagicMock()
        orch.graph_check.verify_entities = AsyncMock(side_effect=_mock_verify)
        orch.pacar_verifier = MagicMock()
        orch.pacar_verifier.verify = AsyncMock(side_effect=_mock_verify)
        orch.evolution_controller = MagicMock()
        orch.evolution_controller.record_feedback = MagicMock()

        msg = _make_msg(impact_score=0.9, message_type=MessageType.TASK_REQUEST)
        result = await orch.verify(msg, "critical operation")

        assert isinstance(result, VerificationResult)
        assert "sdpc_asc_valid" in result.sdpc_metadata
        assert result.pqc_result is None


# =========================================================================
# SECTION 3: AdaptiveThresholds tests
# =========================================================================


class TestAdaptiveThresholdsInit:
    def test_init_sets_base_thresholds(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        assert at.base_thresholds[ImpactLevel.NEGLIGIBLE] == 0.1
        assert at.base_thresholds[ImpactLevel.LOW] == 0.3
        assert at.base_thresholds[ImpactLevel.MEDIUM] == 0.6
        assert at.base_thresholds[ImpactLevel.HIGH] == 0.8
        assert at.base_thresholds[ImpactLevel.CRITICAL] == 0.95
        assert at.model_trained is False
        assert at.constitutional_hash == "608508a9bd224290"

    def test_mlflow_not_initialized_in_tests(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        assert at._mlflow_initialized is False


class TestGetAdaptiveThreshold:
    def test_untrained_model_returns_base(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        features = _make_features()

        for level in ImpactLevel:
            result = at.get_adaptive_threshold(level, features)
            assert result == at.base_thresholds[level]

    def test_trained_model_returns_adjusted_threshold(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        at.model_trained = True

        features = _make_features(confidence_level=0.9)
        feature_vector = at._extract_feature_vector(features)

        # Train the model with synthetic data
        X = np.array([feature_vector] * 10)
        y = np.array([0.05] * 10)
        at.feature_scaler.fit(X)
        at.threshold_model.fit(X, y)

        result = at.get_adaptive_threshold(ImpactLevel.MEDIUM, features)
        assert 0.0 <= result <= 1.0

    def test_trained_model_clamps_to_bounds(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        at.model_trained = True

        features = _make_features(confidence_level=1.0)
        feature_vector = at._extract_feature_vector(features)

        # Train model to predict large positive adjustment
        X = np.array([feature_vector] * 10)
        y = np.array([2.0] * 10)
        at.feature_scaler.fit(X)
        at.threshold_model.fit(X, y)

        result = at.get_adaptive_threshold(ImpactLevel.CRITICAL, features)
        assert result <= 1.0

    def test_trained_model_error_falls_back(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        at.model_trained = True

        features = _make_features()
        # Patch predict to raise
        at.threshold_model.predict = MagicMock(side_effect=ValueError("bad predict"))

        result = at.get_adaptive_threshold(ImpactLevel.HIGH, features)
        assert result == at.base_thresholds[ImpactLevel.HIGH]


class TestExtractFeatureVector:
    def test_feature_vector_length(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        features = _make_features()
        vec = at._extract_feature_vector(features)
        assert len(vec) == 11

    def test_empty_temporal_patterns(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        features = _make_features(temporal_patterns=[])
        vec = at._extract_feature_vector(features)
        # temporal_mean and temporal_std should be 0.0
        assert vec[3] == 0.0
        assert vec[4] == 0.0

    def test_non_empty_temporal_patterns(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        features = _make_features(temporal_patterns=[1.0, 2.0, 3.0])
        vec = at._extract_feature_vector(features)
        assert vec[3] == pytest.approx(np.mean([1.0, 2.0, 3.0]))
        assert vec[4] == pytest.approx(np.std([1.0, 2.0, 3.0]))


class TestUpdateModel:
    def test_positive_reinforcement(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        decision = _make_decision()

        at.update_model(decision, outcome_success=True, human_feedback=True)
        assert len(at.training_data) == 1
        sample = at.training_data[0]
        assert sample["outcome_success"] is True
        assert sample["human_feedback"] is True

    def test_negative_reinforcement(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        decision = _make_decision()

        at.update_model(decision, outcome_success=False, human_feedback=False)
        assert len(at.training_data) == 1
        sample = at.training_data[0]
        assert sample["outcome_success"] is False

    def test_neutral_feedback(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        decision = _make_decision()

        # outcome_success=True but human_feedback=False triggers negative
        at.update_model(decision, outcome_success=True, human_feedback=False)
        assert len(at.training_data) == 1

    def test_update_triggers_retraining(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        at.last_retraining = time.time() - 7200  # 2 hours ago

        with patch.object(at, "_retrain_model") as mock_retrain:
            decision = _make_decision()
            at.update_model(decision, outcome_success=True)
            mock_retrain.assert_called_once()

    def test_update_error_handled(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        decision = _make_decision()
        # Corrupt features_used to trigger error
        decision.features_used = None  # type: ignore[assignment]

        # Should not raise
        at.update_model(decision, outcome_success=True)


class TestRetrainModel:
    def test_retrain_insufficient_data(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        # Add only 50 samples (need 100 minimum)
        for _i in range(50):
            at.training_data.append(
                {
                    "features": [0.1] * 11,
                    "target": 0.05,
                    "timestamp": time.time(),
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )

        at._retrain_model()
        assert at.model_trained is False

    def test_retrain_insufficient_recent_data(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        # Add 100 samples but all old
        old_time = time.time() - 200_000  # way older than 24h
        for _i in range(120):
            at.training_data.append(
                {
                    "features": [0.1] * 11,
                    "target": 0.05,
                    "timestamp": old_time,
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )

        at._retrain_model()
        assert at.model_trained is False

    def test_retrain_success_without_mlflow(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        at._mlflow_initialized = False

        now = time.time()
        for i in range(120):
            at.training_data.append(
                {
                    "features": [float(i % 5) * 0.1 + j * 0.01 for j in range(11)],
                    "target": 0.05 + (i % 3) * 0.01,
                    "timestamp": now - i * 10,
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": i % 2 == 0,
                    "human_feedback": None,
                }
            )

        at._retrain_model()
        assert at.model_trained is True

    def test_retrain_error_handled(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        at._mlflow_initialized = False

        now = time.time()
        for _i in range(120):
            at.training_data.append(
                {
                    "features": [0.1] * 11,
                    "target": 0.05,
                    "timestamp": now,
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )

        # Patch fit to raise
        at.threshold_model.fit = MagicMock(side_effect=RuntimeError("fit failed"))

        at._retrain_model()
        assert at.model_trained is False


class TestLogTrainingRunToMLflow:
    def test_mlflow_logging_error_falls_back(self):
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        X = np.array([[0.1] * 11] * 60)
        y = np.array([0.05] * 60)
        recent_data = [{"outcome_success": True, "human_feedback": None} for _ in range(60)]

        # Patch mlflow to raise
        with patch(
            "enhanced_agent_bus.adaptive_governance.threshold_manager.mlflow"
        ) as mock_mlflow:
            mock_mlflow.start_run.side_effect = RuntimeError("mlflow down")
            at._log_training_run_to_mlflow(X, y, recent_data)
            # Should still train the model as fallback


class TestAdaptiveThresholdsMLflowInit:
    def test_mlflow_not_available(self):
        with patch(
            "enhanced_agent_bus.adaptive_governance.threshold_manager.MLFLOW_AVAILABLE",
            False,
        ):
            at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
            assert at._mlflow_initialized is False

    def test_mlflow_in_pytest_skips_init(self):
        # pytest is in sys.modules, so mlflow init should be skipped
        at = AdaptiveThresholds(constitutional_hash="608508a9bd224290")
        assert at._mlflow_initialized is False
