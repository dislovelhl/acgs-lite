"""
Unit tests for MessageProcessor helper functions.
Constitutional Hash: cdd01ef066bc6cf2

Tests for extracted helper methods to reduce C901 complexity while preserving behavior.
"""

import asyncio
import hashlib
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from src.core.shared.constants import CONSTITUTIONAL_HASH

import enhanced_agent_bus.message_processor as message_processor_module
from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.message_processor_components import (
    apply_latency_metadata,
    apply_session_governance_metrics,
    build_dlq_entry,
    calculate_session_resolution_rate,
    compute_message_cache_key,
    enrich_metrics_with_opa_stats,
    enrich_metrics_with_workflow_telemetry,
    extract_pqc_failure_result,
    extract_rejection_reason,
    merge_verification_metadata,
    prepare_message_content_string,
    run_message_validation_gates,
    schedule_background_task,
)
from enhanced_agent_bus.models import AgentMessage, AutonomyTier, MessageType, Priority
from enhanced_agent_bus.validators import ValidationResult


@pytest.fixture
def sample_message():
    """Create a basic AgentMessage for testing."""
    return AgentMessage(
        message_id="test-msg-123",
        from_agent="test-agent",
        to_agent="target-agent",
        message_type=MessageType.COMMAND,
        priority=Priority.MEDIUM,
        autonomy_tier=AutonomyTier.BOUNDED,
        tenant_id="test-tenant",
        constitutional_hash=CONSTITUTIONAL_HASH,
        content="test content",
        metadata={"test": "value"},
    )


@pytest.fixture
def processor():
    """Create a MessageProcessor instance for testing."""
    with patch.multiple(
        "enhanced_agent_bus.message_processor",
        get_dependency=MagicMock(),
        get_feature_flags=MagicMock(return_value={}),
        is_feature_available=MagicMock(return_value=False),
    ):
        processor = MessageProcessor(isolated_mode=True)
        return processor


class TestSetupMemoryProfilingContext:
    """Tests for _setup_memory_profiling_context helper."""

    @patch("enhanced_agent_bus.message_processor.get_memory_profiler")
    def test_profiling_enabled_returns_profiler_context(
        self, mock_get_profiler, processor, sample_message
    ):
        """Test memory profiling context when profiler is enabled."""
        # Arrange
        mock_profiler = Mock()
        mock_profiler.config.enabled = True
        mock_context = Mock()
        mock_profiler.profile_async.return_value = mock_context
        mock_get_profiler.return_value = mock_profiler

        # Act
        result = processor._setup_memory_profiling_context(sample_message)

        # Assert
        assert result == mock_context
        mock_profiler.profile_async.assert_called_once_with(
            "message_processing_command_1", trace_id="test-msg-123"
        )

    @patch("enhanced_agent_bus.message_processor.get_memory_profiler")
    def test_profiling_disabled_returns_null_context(
        self, mock_get_profiler, processor, sample_message
    ):
        """Test memory profiling context when profiler is disabled."""
        # Arrange
        mock_profiler = Mock()
        mock_profiler.config.enabled = False
        mock_get_profiler.return_value = mock_profiler

        # Act
        result = processor._setup_memory_profiling_context(sample_message)

        # Assert
        assert isinstance(result, type(nullcontext()))

    @patch("enhanced_agent_bus.message_processor.get_memory_profiler")
    def test_no_profiler_returns_null_context(self, mock_get_profiler, processor, sample_message):
        """Test memory profiling context when profiler is None."""
        # Arrange
        mock_get_profiler.return_value = None

        # Act
        result = processor._setup_memory_profiling_context(sample_message)

        # Assert
        assert isinstance(result, type(nullcontext()))


class TestAutoSelectStrategy:
    """Tests for _auto_select_strategy helper."""

    def test_isolated_mode_returns_python_strategy(self):
        """Test strategy selection in isolated mode."""
        # Arrange
        with patch.multiple(
            "enhanced_agent_bus.message_processor",
            get_dependency=MagicMock(),
            get_feature_flags=MagicMock(return_value={}),
            is_feature_available=MagicMock(return_value=False),
        ):
            processor = MessageProcessor(isolated_mode=True)

        # Act
        strategy = processor._auto_select_strategy()

        # Assert
        assert strategy is not None
        assert strategy.get_name() == "python"

    @patch("enhanced_agent_bus.message_processor.rust_bus")
    def test_rust_enabled_includes_rust_strategy(self, mock_rust_bus):
        """Test strategy selection when Rust is enabled."""
        # Arrange
        mock_rust_processor = Mock()
        mock_rust_bus.MessageProcessor.return_value = mock_rust_processor

        with patch.multiple(
            "enhanced_agent_bus.message_processor",
            get_dependency=MagicMock(),
            get_feature_flags=MagicMock(return_value={"USE_RUST": True}),
            is_feature_available=MagicMock(return_value=False),
            get_opa_client=MagicMock(return_value=None),
            USE_RUST=True,
        ):
            processor = MessageProcessor(
                isolated_mode=False,
                use_rust=True,
            )
            processor._rust_processor = mock_rust_processor

        # Act
        strategy = processor._auto_select_strategy()

        # Assert
        assert strategy is not None
        # Should return CompositeProcessingStrategy or similar with Rust support

    @patch("enhanced_agent_bus.message_processor.get_opa_client")
    def test_opa_enabled_includes_opa_strategy(self, mock_get_opa_client):
        """Test strategy selection when OPA is enabled."""
        # Arrange
        mock_opa_client = Mock()
        mock_get_opa_client.return_value = mock_opa_client

        with patch.multiple(
            "enhanced_agent_bus.message_processor",
            get_dependency=MagicMock(),
            get_feature_flags=MagicMock(return_value={"POLICY_CLIENT_AVAILABLE": True}),
            is_feature_available=MagicMock(return_value=False),
            POLICY_CLIENT_AVAILABLE=True,
        ):
            processor = MessageProcessor(
                isolated_mode=False,
                use_dynamic_policy=True,
            )
            processor._use_dynamic_policy = True
            processor._opa_client = mock_opa_client

        # Act
        strategy = processor._auto_select_strategy()

        # Assert
        assert strategy is not None


class TestRequiresIndependentValidation:
    """Tests for _requires_independent_validation helper."""

    def test_high_impact_score_requires_validation(self, processor):
        """Test that high impact score requires independent validation."""
        # Arrange
        processor._independent_validator_threshold = 0.8
        message = AgentMessage(
            impact_score=0.9,
            message_type=MessageType.COMMAND,
        )

        # Act
        result = processor._requires_independent_validation(message)

        # Assert
        assert result is True

    def test_low_impact_score_no_validation_required(self, processor):
        """Test that low impact score doesn't require independent validation."""
        # Arrange
        processor._independent_validator_threshold = 0.8
        message = AgentMessage(
            impact_score=0.5,
            message_type=MessageType.COMMAND,
        )

        # Act
        result = processor._requires_independent_validation(message)

        # Assert
        assert result is False

    def test_none_impact_score_no_validation_required(self, processor):
        """Test that None impact score doesn't require independent validation."""
        # Arrange
        processor._independent_validator_threshold = 0.8
        message = AgentMessage(
            impact_score=None,
            message_type=MessageType.COMMAND,
        )

        # Act
        result = processor._requires_independent_validation(message)

        # Assert
        assert result is False

    def test_constitutional_validation_requires_validation(self, processor):
        """Test that constitutional validation message requires independent validation."""
        # Arrange
        processor._independent_validator_threshold = 0.8
        message = AgentMessage(
            impact_score=0.2,
            message_type=MessageType.CONSTITUTIONAL_VALIDATION,
        )

        # Act
        result = processor._requires_independent_validation(message)

        # Assert
        assert result is True

    def test_governance_request_requires_validation(self, processor):
        """Test that governance request requires independent validation."""
        # Arrange
        processor._independent_validator_threshold = 0.8
        message = AgentMessage(
            impact_score=0.2,
            message_type=MessageType.GOVERNANCE_REQUEST,
        )

        # Act
        result = processor._requires_independent_validation(message)

        # Assert
        assert result is True


class TestEnforceIndependentValidatorGate:
    """Tests for _enforce_independent_validator_gate helper."""

    def test_gate_disabled_returns_none(self, processor, sample_message):
        """Test that gate returns None when disabled."""
        # Arrange
        processor._require_independent_validator = False

        # Act
        result = processor._enforce_independent_validator_gate(sample_message)

        # Assert
        assert result is None

    def test_no_validation_required_returns_none(self, processor, sample_message):
        """Test that gate returns None when validation not required."""
        # Arrange
        processor._require_independent_validator = True
        processor._independent_validator_threshold = 0.8
        sample_message.impact_score = 0.2
        sample_message.message_type = MessageType.COMMAND

        # Act
        result = processor._enforce_independent_validator_gate(sample_message)

        # Assert
        assert result is None

    @patch.object(MessageProcessor, "_record_agent_workflow_event")
    def test_missing_validator_returns_error(self, mock_record_event, processor, sample_message):
        """Test that missing validator metadata returns validation error."""
        # Arrange
        processor._require_independent_validator = True
        processor._independent_validator_threshold = 0.8
        sample_message.impact_score = 0.9
        sample_message.metadata = {}

        # Act
        result = processor._enforce_independent_validator_gate(sample_message)

        # Assert
        assert result is not None
        assert result.is_valid is False
        assert any("Independent validator metadata is required" in error for error in result.errors)
        assert result.metadata["rejection_reason"] == "independent_validator_missing"
        mock_record_event.assert_called()

    @patch.object(MessageProcessor, "_record_agent_workflow_event")
    def test_self_validation_returns_error(self, mock_record_event, processor, sample_message):
        """Test that self-validation returns validation error."""
        # Arrange
        processor._require_independent_validator = True
        processor._independent_validator_threshold = 0.8
        sample_message.impact_score = 0.9
        sample_message.from_agent = "test-agent"
        sample_message.metadata = {
            "validated_by_agent": "test-agent",
            "validation_stage": "independent",
        }

        # Act
        result = processor._enforce_independent_validator_gate(sample_message)

        # Assert
        assert result is not None
        assert result.is_valid is False
        assert "Independent validator must not be the originating agent" in result.errors
        assert result.metadata["rejection_reason"] == "independent_validator_self_validation"

    @patch.object(MessageProcessor, "_record_agent_workflow_event")
    def test_invalid_validation_stage_returns_error(
        self, mock_record_event, processor, sample_message
    ):
        """Test that invalid validation stage returns validation error."""
        # Arrange
        processor._require_independent_validator = True
        processor._independent_validator_threshold = 0.8
        sample_message.impact_score = 0.9
        sample_message.metadata = {
            "validated_by_agent": "different-agent",
            "validation_stage": "preliminary",
        }

        # Act
        result = processor._enforce_independent_validator_gate(sample_message)

        # Assert
        assert result is not None
        assert result.is_valid is False
        assert any("validation_stage must be 'independent'" in error for error in result.errors)
        assert result.metadata["rejection_reason"] == "independent_validator_invalid_stage"

    def test_valid_validator_returns_none(self, processor, sample_message):
        """Test that valid validator metadata returns None."""
        # Arrange
        processor._require_independent_validator = True
        processor._independent_validator_threshold = 0.8
        sample_message.impact_score = 0.9
        sample_message.metadata = {
            "validated_by_agent": "different-agent",
            "validation_stage": "independent",
        }

        # Act
        result = processor._enforce_independent_validator_gate(sample_message)

        # Assert
        assert result is None

    def test_independent_validator_id_works(self, processor, sample_message):
        """Test that independent_validator_id field works as alternative."""
        # Arrange
        processor._require_independent_validator = True
        processor._independent_validator_threshold = 0.8
        sample_message.impact_score = 0.9
        sample_message.metadata = {"independent_validator_id": "different-agent"}

        # Act
        result = processor._enforce_independent_validator_gate(sample_message)

        # Assert
        assert result is None


class TestEnforceAutonomyTier:
    """Tests for _enforce_autonomy_tier helper."""

    @patch("enhanced_agent_bus.message_processor.enforce_autonomy_tier_rules")
    @patch(
        "enhanced_agent_bus.message_processor._ADVISORY_BLOCKED_TYPES",
        frozenset({"command", "governance_request", "task_request"}),
    )
    def test_calls_enforcement_function_with_correct_parameters(
        self, mock_enforce_rules, processor, sample_message
    ):
        """Test that autonomy tier enforcement calls the helper function correctly."""
        # Arrange
        mock_result = ValidationResult(is_valid=True)
        mock_enforce_rules.return_value = mock_result
        from enhanced_agent_bus.message_processor import _ADVISORY_BLOCKED_TYPES

        # Act
        result = processor._enforce_autonomy_tier(sample_message)

        # Assert
        mock_enforce_rules.assert_called_once_with(
            msg=sample_message, advisory_blocked_types=_ADVISORY_BLOCKED_TYPES
        )
        assert result == mock_result

    @patch("enhanced_agent_bus.message_processor.enforce_autonomy_tier_rules")
    def test_returns_validation_result(self, mock_enforce_rules, processor, sample_message):
        """Test that autonomy tier enforcement returns validation result."""
        # Arrange
        mock_result = ValidationResult(
            is_valid=False,
            errors=["Advisory agent cannot execute commands"],
            metadata={"rejection_reason": "autonomy_tier_violation"},
        )
        mock_enforce_rules.return_value = mock_result

        # Act
        result = processor._enforce_autonomy_tier(sample_message)

        # Assert
        assert result == mock_result
        assert result.is_valid is False

    @patch("enhanced_agent_bus.message_processor.enforce_autonomy_tier_rules")
    def test_returns_none_when_no_violation(self, mock_enforce_rules, processor, sample_message):
        """Test that autonomy tier enforcement returns None when no violation."""
        # Arrange
        mock_enforce_rules.return_value = None

        # Act
        result = processor._enforce_autonomy_tier(sample_message)

        # Assert
        assert result is None


class TestExtractMessageSessionId:
    """Tests for _extract_message_session_id helper."""

    @patch("enhanced_agent_bus.message_processor.extract_session_id_for_pacar")
    def test_calls_pacar_function_with_message(
        self, mock_extract_session, processor, sample_message
    ):
        """Test that session ID extraction calls PACAR function correctly."""
        # Arrange
        expected_session_id = "session-123"
        mock_extract_session.return_value = expected_session_id

        # Act
        result = processor._extract_message_session_id(sample_message)

        # Assert
        mock_extract_session.assert_called_once_with(sample_message)
        assert result == expected_session_id

    @patch("enhanced_agent_bus.message_processor.extract_session_id_for_pacar")
    def test_returns_none_when_no_session_id(self, mock_extract_session, processor, sample_message):
        """Test that session ID extraction returns None when no session ID found."""
        # Arrange
        mock_extract_session.return_value = None

        # Act
        result = processor._extract_message_session_id(sample_message)

        # Assert
        assert result is None


class TestComputeCacheKey:
    """Tests for _compute_cache_key helper."""

    def test_rejects_invalid_cache_hash_mode(self):
        """Test that invalid cache hash mode is rejected."""
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="invalid")  # type: ignore[arg-type]

    def test_cache_key_includes_all_dimensions(self, processor, sample_message):
        """Test that cache key includes all security dimensions."""
        # Act
        result = processor._compute_cache_key(sample_message)

        # Assert
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hash length
        # Verify it's a valid hex string
        int(result, 16)

    def test_cache_key_consistent_for_same_message(self, processor, sample_message):
        """Test that cache key is consistent for the same message."""
        # Act
        result1 = processor._compute_cache_key(sample_message)
        result2 = processor._compute_cache_key(sample_message)

        # Assert
        assert result1 == result2

    def test_cache_key_different_for_different_content(self, processor, sample_message):
        """Test that cache key differs for different message content."""
        # Arrange
        message2 = AgentMessage(**sample_message.__dict__)
        message2.content = "different content"

        # Act
        result1 = processor._compute_cache_key(sample_message)
        result2 = processor._compute_cache_key(message2)

        # Assert
        assert result1 != result2

    def test_cache_key_different_for_different_tenant(self, processor, sample_message):
        """Test that cache key differs for different tenant."""
        # Arrange
        message2 = AgentMessage(**sample_message.__dict__)
        message2.tenant_id = "different-tenant"

        # Act
        result1 = processor._compute_cache_key(sample_message)
        result2 = processor._compute_cache_key(message2)

        # Assert
        assert result1 != result2

    def test_cache_key_handles_non_string_content(self, processor, sample_message):
        """Test that cache key handles non-string content."""
        # Arrange
        sample_message.content = {"key": "value", "number": 123}

        # Act
        result = processor._compute_cache_key(sample_message)

        # Assert
        assert isinstance(result, str)
        assert len(result) == 64

    def test_cache_key_handles_none_autonomy_tier(self, processor, sample_message):
        """Test that cache key handles None autonomy tier."""
        # Arrange
        sample_message.autonomy_tier = None

        # Act
        result = processor._compute_cache_key(sample_message)

        # Assert
        assert isinstance(result, str)
        assert len(result) == 64

    def test_cache_key_calculation_logic(self, processor):
        """Test cache key calculation with known values."""
        # Arrange
        message = AgentMessage(
            content="test content",
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id="test-tenant",
            from_agent="test-agent",
            message_type=MessageType.COMMAND,
            autonomy_tier=AutonomyTier.BOUNDED,
        )

        # Act
        result = processor._compute_cache_key(message)

        # Assert
        # Calculate expected hash manually to verify logic
        cache_dimensions = (
            f"test content:{CONSTITUTIONAL_HASH}:test-tenant:test-agent:command:bounded"
        )
        expected = hashlib.sha256(cache_dimensions.encode()).hexdigest()

        assert result == expected


class TestComputeMessageCacheKey:
    def test_helper_matches_method_sha256_logic(self, processor, sample_message):
        result = compute_message_cache_key(
            sample_message,
            cache_hash_mode="sha256",
            fast_hash_available=False,
        )

        assert result == processor._compute_cache_key(sample_message)

    def test_helper_uses_fast_hash_when_available(self, sample_message):
        called = {"value": False}

        def fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        result = compute_message_cache_key(
            sample_message,
            cache_hash_mode="fast",
            fast_hash_available=True,
            fast_hash_func=fake_fast_hash,
        )

        assert called["value"] is True
        assert result == "fast:000000000000beef"


class TestPrepareMessageContentString:
    def test_returns_string_content_unchanged(self, sample_message):
        sample_message.content = "already a string"

        assert prepare_message_content_string(sample_message) == "already a string"

    def test_converts_non_string_content(self, sample_message):
        sample_message.content = {"nested": [1, 2, 3]}

        assert prepare_message_content_string(sample_message) == str({"nested": [1, 2, 3]})

    @pytest.mark.asyncio
    async def test_execute_verification_passes_normalized_content(self, processor, sample_message):
        sample_message.content = {"nested": [1, 2, 3]}
        verification_result = Mock(
            sdpc_metadata={},
            pqc_metadata={},
            pqc_result=None,
        )
        processor._verification_orchestrator.verify = AsyncMock(return_value=verification_result)
        processor._processing_strategy.process = AsyncMock(
            return_value=ValidationResult(is_valid=True, metadata={})
        )
        processor._handle_successful_processing = AsyncMock()
        processor._handle_failed_processing = AsyncMock()

        await processor._execute_verification_and_processing(sample_message, "cache-key", 0.0)

        processor._verification_orchestrator.verify.assert_awaited_once_with(
            sample_message, str({"nested": [1, 2, 3]})
        )


class TestMergeVerificationMetadata:
    def test_merges_pqc_metadata_over_sdpc_metadata(self):
        result = merge_verification_metadata(
            {"sdpc": "ok", "shared": "sdpc"},
            {"pqc": "ok", "shared": "pqc"},
        )

        assert result == {"sdpc": "ok", "pqc": "ok", "shared": "pqc"}

    def test_returns_copy_when_pqc_metadata_empty(self):
        sdpc_metadata = {"sdpc": "ok"}

        result = merge_verification_metadata(sdpc_metadata, {})

        assert result == {"sdpc": "ok"}
        assert result is not sdpc_metadata

    @pytest.mark.asyncio
    async def test_execute_verification_applies_merged_metadata_to_result(
        self, processor, sample_message
    ):
        verification_result = Mock(
            sdpc_metadata={"sdpc": "ok", "shared": "sdpc"},
            pqc_metadata={"pqc": "ok", "shared": "pqc"},
            pqc_result=None,
        )
        process_result = ValidationResult(is_valid=True, metadata={})
        processor._verification_orchestrator.verify = AsyncMock(return_value=verification_result)
        processor._processing_strategy.process = AsyncMock(return_value=process_result)
        processor._handle_successful_processing = AsyncMock()
        processor._handle_failed_processing = AsyncMock()

        result = await processor._execute_verification_and_processing(
            sample_message, "cache-key", 0.0
        )

        assert result.metadata["sdpc"] == "ok"
        assert result.metadata["pqc"] == "ok"
        assert result.metadata["shared"] == "pqc"


class TestExtractPqcFailureResult:
    def test_returns_none_when_pqc_passes(self):
        verification_result = Mock(pqc_result=None)

        assert extract_pqc_failure_result(verification_result) is None

    @pytest.mark.asyncio
    async def test_execute_verification_returns_pqc_failure_and_increments_count(
        self, processor, sample_message
    ):
        pqc_failure = ValidationResult(is_valid=False, errors=["pqc failed"], metadata={})
        verification_result = Mock(
            sdpc_metadata={"sdpc": "ok"},
            pqc_metadata={"pqc": "meta"},
            pqc_result=pqc_failure,
        )
        processor._verification_orchestrator.verify = AsyncMock(return_value=verification_result)
        processor._processing_strategy.process = AsyncMock()
        starting_failed_count = processor._failed_count

        result = await processor._execute_verification_and_processing(
            sample_message, "cache-key", 0.0
        )

        assert result is pqc_failure
        assert processor._failed_count == starting_failed_count + 1
        processor._processing_strategy.process.assert_not_awaited()


class TestApplyLatencyMetadata:
    def test_sets_latency_metadata(self):
        result = ValidationResult(is_valid=True, metadata={})

        apply_latency_metadata(result, 12.5)

        assert result.metadata["latency_ms"] == 12.5

    @pytest.mark.asyncio
    async def test_execute_verification_applies_latency_metadata(self, processor, sample_message):
        verification_result = Mock(
            sdpc_metadata={},
            pqc_metadata={},
            pqc_result=None,
        )
        process_result = ValidationResult(is_valid=True, metadata={})
        processor._verification_orchestrator.verify = AsyncMock(return_value=verification_result)
        processor._processing_strategy.process = AsyncMock(return_value=process_result)
        processor._handle_successful_processing = AsyncMock()
        processor._handle_failed_processing = AsyncMock()

        result = await processor._execute_verification_and_processing(
            sample_message, "cache-key", 0.0
        )

        assert "latency_ms" in result.metadata
        assert isinstance(result.metadata["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_execute_verification_passes_same_latency_to_success_handler(
        self, processor, sample_message
    ):
        verification_result = Mock(
            sdpc_metadata={},
            pqc_metadata={},
            pqc_result=None,
        )
        process_result = ValidationResult(is_valid=True, metadata={})
        processor._verification_orchestrator.verify = AsyncMock(return_value=verification_result)
        processor._processing_strategy.process = AsyncMock(return_value=process_result)
        processor._handle_successful_processing = AsyncMock()
        processor._handle_failed_processing = AsyncMock()

        result = await processor._execute_verification_and_processing(
            sample_message, "cache-key", 0.0
        )

        await_args = processor._handle_successful_processing.await_args
        assert await_args is not None
        passed_latency = await_args.args[3]
        assert passed_latency == result.metadata["latency_ms"]


class TestBuildDlqEntry:
    def test_builds_expected_dlq_shape(self, sample_message):
        result = ValidationResult(is_valid=False, errors=["failed"], metadata={})

        entry = build_dlq_entry(sample_message, result, 123.45)

        assert entry == {
            "message_id": sample_message.message_id,
            "from_agent": sample_message.from_agent,
            "to_agent": sample_message.to_agent,
            "message_type": sample_message.message_type.value,
            "errors": ["failed"],
            "timestamp": 123.45,
        }


class TestCalculateSessionResolutionRate:
    def test_returns_zero_when_no_session_attempts(self):
        assert calculate_session_resolution_rate(0, 0, 0) == 0.0

    def test_calculates_rate_from_all_session_outcomes(self):
        assert calculate_session_resolution_rate(2, 1, 1) == 0.5


class TestApplySessionGovernanceMetrics:
    def test_adds_enabled_session_metrics(self):
        metrics = {"processed_count": 1}

        apply_session_governance_metrics(
            metrics,
            enabled=True,
            resolved_count=2,
            not_found_count=1,
            error_count=0,
            resolution_rate=2 / 3,
        )

        assert metrics["session_governance_enabled"] is True
        assert metrics["session_resolved_count"] == 2
        assert metrics["session_not_found_count"] == 1
        assert metrics["session_error_count"] == 0
        assert metrics["session_resolution_rate"] == 2 / 3

    def test_marks_session_governance_disabled(self):
        metrics = {"processed_count": 1}

        apply_session_governance_metrics(
            metrics,
            enabled=False,
            resolved_count=0,
            not_found_count=0,
            error_count=0,
            resolution_rate=0.0,
        )

        assert metrics["session_governance_enabled"] is False


class TestEnrichMetricsWithOpaStats:
    def test_applies_opa_stats_to_metrics(self):
        metrics = {}
        opa_client = Mock()
        opa_client.get_stats.return_value = {
            "multipath_evaluation_count": 11,
            "multipath_last_path_count": 4,
            "multipath_last_diversity_ratio": 0.5,
            "multipath_last_support_family_count": 3,
        }

        enrich_metrics_with_opa_stats(metrics, opa_client)

        assert metrics["opa_multipath_evaluation_count"] == 11
        assert metrics["opa_multipath_last_path_count"] == 4
        assert metrics["opa_multipath_last_diversity_ratio"] == 0.5
        assert metrics["opa_multipath_last_support_family_count"] == 3

    def test_defaults_opa_stats_when_client_errors(self):
        metrics = {}
        opa_client = Mock()
        opa_client.get_stats.side_effect = ValueError("broken stats")

        enrich_metrics_with_opa_stats(metrics, opa_client)

        assert metrics["opa_multipath_evaluation_count"] == 0
        assert metrics["opa_multipath_last_path_count"] == 0
        assert metrics["opa_multipath_last_diversity_ratio"] == 0.0
        assert metrics["opa_multipath_last_support_family_count"] == 0


class TestEnrichMetricsWithWorkflowTelemetry:
    def test_updates_metrics_from_workflow_collector(self):
        metrics = {}
        collector = Mock()
        collector.snapshot.return_value = {
            "intervention_rate": 0.25,
            "gate_failures_total": 3,
            "rollback_triggers_total": 1,
            "autonomous_actions_total": 8,
        }

        enriched = enrich_metrics_with_workflow_telemetry(metrics, collector)

        assert enriched is True
        assert metrics["workflow_intervention_rate"] == 0.25
        assert metrics["workflow_gate_failures_total"] == 3
        assert metrics["workflow_rollback_triggers_total"] == 1
        assert metrics["workflow_autonomous_actions_total"] == 8

    def test_returns_false_when_workflow_collector_missing(self):
        metrics = {}

        enriched = enrich_metrics_with_workflow_telemetry(metrics, None)

        assert enriched is False
        assert metrics == {}

    def test_raises_when_workflow_collector_raises(self):
        metrics = {}
        collector = Mock()
        collector.snapshot.side_effect = RuntimeError("broken collector")

        with pytest.raises(RuntimeError, match="broken collector"):
            enrich_metrics_with_workflow_telemetry(metrics, collector)


class TestRunMessageValidationGates:
    @pytest.mark.asyncio
    async def test_returns_autonomy_result_and_increments_failure(self, sample_message):
        autonomy_result = ValidationResult(
            is_valid=False,
            errors=["blocked"],
            metadata={"rejection_reason": "autonomy_tier_violation"},
        )
        increment_failure = Mock()
        security_scan = AsyncMock()
        independent_gate = Mock()
        prompt_injection_gate = Mock()

        result = await run_message_validation_gates(
            msg=sample_message,
            autonomy_gate=Mock(return_value=autonomy_result),
            security_scan=security_scan,
            independent_validator_gate=independent_gate,
            prompt_injection_gate=prompt_injection_gate,
            increment_failure=increment_failure,
        )

        assert result == autonomy_result
        increment_failure.assert_called_once_with()
        security_scan.assert_not_called()
        independent_gate.assert_not_called()
        prompt_injection_gate.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_security_result_without_extra_failure_increment(self, sample_message):
        security_result = ValidationResult(
            is_valid=False,
            errors=["security blocked"],
            metadata={"rejection_reason": "security_violation"},
        )
        increment_failure = Mock()

        result = await run_message_validation_gates(
            msg=sample_message,
            autonomy_gate=Mock(return_value=None),
            security_scan=AsyncMock(return_value=security_result),
            independent_validator_gate=Mock(),
            prompt_injection_gate=Mock(),
            increment_failure=increment_failure,
        )

        assert result == security_result
        increment_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_independent_validator_result_and_increments_failure(
        self, sample_message
    ):
        validator_result = ValidationResult(
            is_valid=False,
            errors=["validator blocked"],
            metadata={"rejection_reason": "independent_validator_missing"},
        )
        increment_failure = Mock()
        prompt_injection_gate = Mock()

        result = await run_message_validation_gates(
            msg=sample_message,
            autonomy_gate=Mock(return_value=None),
            security_scan=AsyncMock(return_value=None),
            independent_validator_gate=Mock(return_value=validator_result),
            prompt_injection_gate=prompt_injection_gate,
            increment_failure=increment_failure,
        )

        assert result == validator_result
        increment_failure.assert_called_once_with()
        prompt_injection_gate.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_prompt_injection_result_and_increments_failure(self, sample_message):
        injection_result = ValidationResult(
            is_valid=False,
            errors=["prompt injection"],
            metadata={"rejection_reason": "prompt_injection_detected"},
        )
        increment_failure = Mock()

        result = await run_message_validation_gates(
            msg=sample_message,
            autonomy_gate=Mock(return_value=None),
            security_scan=AsyncMock(return_value=None),
            independent_validator_gate=Mock(return_value=None),
            prompt_injection_gate=Mock(return_value=injection_result),
            increment_failure=increment_failure,
        )

        assert result == injection_result
        increment_failure.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_returns_none_when_all_gates_pass(self, sample_message):
        increment_failure = Mock()

        result = await run_message_validation_gates(
            msg=sample_message,
            autonomy_gate=Mock(return_value=None),
            security_scan=AsyncMock(return_value=None),
            independent_validator_gate=Mock(return_value=None),
            prompt_injection_gate=Mock(return_value=None),
            increment_failure=increment_failure,
        )

        assert result is None
        increment_failure.assert_not_called()


class TestScheduleBackgroundTask:
    @pytest.mark.asyncio
    async def test_tracks_and_discards_completed_task(self):
        background_tasks: set[asyncio.Task[object]] = set()

        async def noop() -> None:
            return None

        task = schedule_background_task(noop(), background_tasks)

        assert task in background_tasks
        await task
        await asyncio.sleep(0)
        assert task not in background_tasks


class TestBackgroundTaskSchedulingIntegration:
    @pytest.mark.asyncio
    async def test_successful_processing_uses_scheduler_for_metering(
        self, monkeypatch, processor, sample_message
    ):
        scheduled: list[object] = []

        def fake_schedule(coroutine, background_tasks):
            scheduled.append(coroutine)
            coroutine.close()
            return Mock()

        monkeypatch.setattr(message_processor_module, "schedule_background_task", fake_schedule)
        processor._metering_hooks = Mock()

        result = ValidationResult(is_valid=True, metadata={})

        await processor._handle_successful_processing(sample_message, result, "cache-key", 12.5)

        assert len(scheduled) == 1

    @pytest.mark.asyncio
    async def test_failed_processing_uses_scheduler_for_dlq(
        self, monkeypatch, processor, sample_message
    ):
        scheduled: list[tuple[object, object]] = []

        def fake_schedule(coroutine, background_tasks):
            scheduled.append((coroutine, background_tasks))
            coroutine.close()
            return Mock()

        monkeypatch.setattr(message_processor_module, "schedule_background_task", fake_schedule)
        processor._record_agent_workflow_event = Mock()

        result = ValidationResult(is_valid=False, metadata={})

        await processor._handle_failed_processing(sample_message, result)

        assert len(scheduled) == 1
        assert scheduled[0][1] is processor._background_tasks

    def test_cache_key_fast_mode_uses_kernel(self, monkeypatch, sample_message):
        """Test that fast mode uses Rust hash kernel when available."""
        import sys

        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        # PM-015: under importlib mode, enhanced_agent_bus.X and packages.enhanced_agent_bus.X
        # can be separate module objects. Patch both paths so _compute_cache_key.__globals__
        # sees the updated FAST_HASH_AVAILABLE regardless of which module was loaded first.
        for _mod_path in (
            "enhanced_agent_bus.message_processor",
            "enhanced_agent_bus.message_processor",
        ):
            _mod = sys.modules.get(_mod_path)
            if _mod is not None:
                monkeypatch.setattr(_mod, "FAST_HASH_AVAILABLE", True)
                monkeypatch.setattr(_mod, "fast_hash", _fake_fast_hash, raising=False)

        processor = MessageProcessor(isolated_mode=True, cache_hash_mode="fast")
        result = processor._compute_cache_key(sample_message)

        assert called["value"] is True
        assert result == "fast:000000000000beef"

    def test_cache_key_fast_mode_falls_back_to_sha256(self, monkeypatch):
        """Test that fast mode falls back to SHA-256 when kernel unavailable."""
        monkeypatch.setattr(message_processor_module, "FAST_HASH_AVAILABLE", False)

        message = AgentMessage(
            content="test content",
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id="test-tenant",
            from_agent="test-agent",
            message_type=MessageType.COMMAND,
            autonomy_tier=AutonomyTier.BOUNDED,
        )
        processor = MessageProcessor(isolated_mode=True, cache_hash_mode="fast")
        result = processor._compute_cache_key(message)

        cache_dimensions = (
            f"test content:{CONSTITUTIONAL_HASH}:test-tenant:test-agent:command:bounded"
        )
        expected = hashlib.sha256(cache_dimensions.encode()).hexdigest()
        assert result == expected


class TestExtractRejectionReason:
    """Tests for _extract_rejection_reason static method."""

    def test_helper_extracts_rejection_reason_from_metadata(self):
        result = ValidationResult(
            is_valid=False, metadata={"rejection_reason": "custom_rejection_reason"}
        )

        assert extract_rejection_reason(result) == "custom_rejection_reason"

    def test_helper_returns_default_when_metadata_missing_reason(self):
        result = ValidationResult(is_valid=False)

        assert extract_rejection_reason(result) == "validation_failed"

    def test_extracts_rejection_reason_from_metadata(self):
        """Test extraction of rejection reason from result metadata."""
        # Arrange
        result = ValidationResult(
            is_valid=False, metadata={"rejection_reason": "custom_rejection_reason"}
        )

        # Act
        reason = MessageProcessor._extract_rejection_reason(result)

        # Assert
        assert reason == "custom_rejection_reason"

    def test_returns_default_when_no_metadata(self):
        """Test default rejection reason when no metadata."""
        # Arrange
        result = ValidationResult(is_valid=False)

        # Act
        reason = MessageProcessor._extract_rejection_reason(result)

        # Assert
        assert reason == "validation_failed"

    def test_returns_default_when_empty_rejection_reason(self):
        """Test default rejection reason when rejection reason is empty."""
        # Arrange
        result = ValidationResult(is_valid=False, metadata={"rejection_reason": ""})

        # Act
        reason = MessageProcessor._extract_rejection_reason(result)

        # Assert
        assert reason == "validation_failed"

    def test_returns_default_when_non_string_rejection_reason(self):
        """Test default rejection reason when rejection reason is not a string."""
        # Arrange
        result = ValidationResult(is_valid=False, metadata={"rejection_reason": 123})

        # Act
        reason = MessageProcessor._extract_rejection_reason(result)

        # Assert
        assert reason == "validation_failed"

    def test_returns_default_when_metadata_not_dict(self):
        """Test default rejection reason when metadata is not a dictionary."""
        # Arrange
        result = ValidationResult(
            is_valid=False,
            metadata="not a dict",  # type: ignore
        )

        # Act
        reason = MessageProcessor._extract_rejection_reason(result)

        # Assert
        assert reason == "validation_failed"


class TestDetectPromptInjection:
    """Tests for _detect_prompt_injection helper."""

    def test_calls_security_scanner(self, processor, sample_message):
        """Test that prompt injection detection calls security scanner."""
        # Arrange
        mock_result = ValidationResult(is_valid=True)
        processor._security_scanner = Mock()
        processor._security_scanner.detect_prompt_injection.return_value = mock_result

        # Act
        result = processor._detect_prompt_injection(sample_message)

        # Assert
        processor._security_scanner.detect_prompt_injection.assert_called_once_with(sample_message)
        assert result == mock_result

    def test_returns_validation_result_when_injection_detected(self, processor, sample_message):
        """Test return value when prompt injection is detected."""
        # Arrange
        mock_result = ValidationResult(
            is_valid=False,
            errors=["Prompt injection detected"],
            metadata={"rejection_reason": "prompt_injection"},
        )
        processor._security_scanner = Mock()
        processor._security_scanner.detect_prompt_injection.return_value = mock_result

        # Act
        result = processor._detect_prompt_injection(sample_message)

        # Assert
        assert result == mock_result
        assert result.is_valid is False

    def test_returns_none_when_no_injection(self, processor, sample_message):
        """Test return value when no prompt injection detected."""
        # Arrange
        processor._security_scanner = Mock()
        processor._security_scanner.detect_prompt_injection.return_value = None

        # Act
        result = processor._detect_prompt_injection(sample_message)

        # Assert
        assert result is None


@pytest.mark.constitutional
class TestHelperIntegration:
    """Integration tests for helper functions working together."""

    def test_cache_key_consistency_with_session_extraction(self, processor):
        """Test that cache key remains consistent with session ID extraction."""
        # Arrange
        message1 = AgentMessage(
            content="test",
            session_id="session-123",
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id="tenant1",
            from_agent="agent1",
            message_type=MessageType.COMMAND,
            autonomy_tier=AutonomyTier.BOUNDED,
        )

        message2 = AgentMessage(
            content="test",
            session_id="session-456",  # Different session ID
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id="tenant1",
            from_agent="agent1",
            message_type=MessageType.COMMAND,
            autonomy_tier=AutonomyTier.BOUNDED,
        )

        # Act
        key1 = processor._compute_cache_key(message1)
        key2 = processor._compute_cache_key(message2)

        # Assert
        # Cache key should be the same since session_id is not part of cache dimensions
        assert key1 == key2

    def test_validation_helpers_work_with_different_message_types(self, processor):
        """Test that validation helpers work correctly with different message types."""
        # Arrange
        processor._require_independent_validator = True
        processor._independent_validator_threshold = 0.8

        governance_msg = AgentMessage(
            message_type=MessageType.GOVERNANCE_REQUEST,
            impact_score=0.5,  # Low score but governance type
            metadata={"validated_by_agent": "validator-agent"},
        )

        command_msg = AgentMessage(
            message_type=MessageType.COMMAND,
            impact_score=0.9,  # High score
            metadata={"validated_by_agent": "validator-agent"},
        )

        # Act & Assert
        assert processor._requires_independent_validation(governance_msg) is True
        assert processor._requires_independent_validation(command_msg) is True
        assert processor._enforce_independent_validator_gate(governance_msg) is None
        assert processor._enforce_independent_validator_gate(command_msg) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
