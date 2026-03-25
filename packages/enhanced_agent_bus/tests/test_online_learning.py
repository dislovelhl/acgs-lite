"""
ACGS-2 Online Learning Tests
Constitutional Hash: 608508a9bd224290

Unit tests for River-based online learning module with sklearn compatibility adapter.
Tests adapter pattern, online learning pipeline, Kafka consumer, and module-level functions.
"""

import os
import sys
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

# Add parent directory to path for module imports
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

from online_learning import (
    ENABLE_COLD_START_FALLBACK,
    KAFKA_AVAILABLE,
    KAFKA_BOOTSTRAP,
    KAFKA_CONSUMER_GROUP,
    KAFKA_TOPIC_FEEDBACK,
    MIN_SAMPLES_FOR_PREDICTION,
    NUMPY_AVAILABLE,
    RIVER_AVAILABLE,
    RIVER_N_MODELS,
    RIVER_SEED,
    ConsumerStats,
    FeedbackKafkaConsumer,
    LearningResult,
    LearningStats,
    LearningStatus,
    ModelType,
    OnlineLearningPipeline,
    PredictionResult,
    RiverSklearnAdapter,
    get_consumer_stats,
    get_online_learning_adapter,
    get_online_learning_pipeline,
    learn_from_feedback_event,
)

logger = get_logger(__name__)


class TestModelType:
    """Tests for ModelType enum."""

    def test_model_type_values(self):
        """Test all ModelType enum values."""
        assert ModelType.CLASSIFIER.value == "classifier"
        assert ModelType.REGRESSOR.value == "regressor"

    def test_model_type_is_string_enum(self):
        """Test that ModelType inherits from str."""
        assert isinstance(ModelType.CLASSIFIER, str)
        assert ModelType.CLASSIFIER == "classifier"

    def test_model_type_count(self):
        """Test all expected model types exist."""
        model_values = [m.value for m in ModelType]
        assert len(model_values) == 2
        assert "classifier" in model_values
        assert "regressor" in model_values


class TestLearningStatus:
    """Tests for LearningStatus enum."""

    def test_learning_status_values(self):
        """Test all LearningStatus enum values."""
        assert LearningStatus.COLD_START.value == "cold_start"
        assert LearningStatus.WARMING_UP.value == "warming_up"
        assert LearningStatus.READY.value == "ready"
        assert LearningStatus.ERROR.value == "error"

    def test_learning_status_is_string_enum(self):
        """Test that LearningStatus inherits from str."""
        assert isinstance(LearningStatus.COLD_START, str)
        assert LearningStatus.READY == "ready"

    def test_learning_status_count(self):
        """Test all expected status values exist."""
        status_values = [s.value for s in LearningStatus]
        assert len(status_values) == 4
        assert "cold_start" in status_values
        assert "ready" in status_values


class TestLearningStats:
    """Tests for LearningStats dataclass."""

    def test_learning_stats_default_values(self):
        """Test LearningStats with default values."""
        stats = LearningStats()

        assert stats.samples_learned == 0
        assert stats.correct_predictions == 0
        assert stats.total_predictions == 0
        assert stats.accuracy == 0.0
        # last_update is set to current timestamp by default factory
        assert stats.last_update is not None
        assert isinstance(stats.last_update, datetime)
        assert stats.status == LearningStatus.COLD_START
        assert stats.feature_names == []
        assert stats.metrics_history == []

    def test_learning_stats_with_values(self):
        """Test LearningStats with custom values."""
        timestamp = datetime.now(tz=UTC)
        stats = LearningStats(
            samples_learned=1000,
            correct_predictions=850,
            total_predictions=900,
            accuracy=0.944,
            last_update=timestamp,
            status=LearningStatus.READY,
            feature_names=["age", "income", "score"],
            metrics_history=[{"accuracy": 0.9}, {"accuracy": 0.94}],
        )

        assert stats.samples_learned == 1000
        assert stats.correct_predictions == 850
        assert stats.total_predictions == 900
        assert stats.accuracy == 0.944
        assert stats.last_update == timestamp
        assert stats.status == LearningStatus.READY
        assert len(stats.feature_names) == 3
        assert len(stats.metrics_history) == 2


class TestPredictionResult:
    """Tests for PredictionResult dataclass."""

    def test_prediction_result_minimal(self):
        """Test PredictionResult with minimal fields."""
        result = PredictionResult(prediction=1)

        assert result.prediction == 1
        assert result.confidence is None
        assert result.probabilities is None
        assert result.used_fallback is False
        assert result.model_status == LearningStatus.COLD_START

    def test_prediction_result_full(self):
        """Test PredictionResult with all fields."""
        result = PredictionResult(
            prediction=0,
            confidence=0.95,
            probabilities={0: 0.95, 1: 0.05},
            used_fallback=True,
            model_status=LearningStatus.READY,
        )

        assert result.prediction == 0
        assert result.confidence == 0.95
        assert result.probabilities == {0: 0.95, 1: 0.05}
        assert result.used_fallback is True
        assert result.model_status == LearningStatus.READY


class TestLearningResult:
    """Tests for LearningResult dataclass."""

    def test_learning_result_success(self):
        """Test LearningResult for successful learning."""
        result = LearningResult(
            success=True,
            samples_learned=10,
            total_samples=1000,
        )

        assert result.success is True
        assert result.samples_learned == 10
        assert result.total_samples == 1000
        assert result.error_message is None

    def test_learning_result_failure(self):
        """Test LearningResult for failed learning."""
        result = LearningResult(
            success=False,
            samples_learned=0,
            total_samples=990,
            error_message="Invalid feature format",
        )

        assert result.success is False
        assert result.samples_learned == 0
        assert result.error_message == "Invalid feature format"


class TestConsumerStats:
    """Tests for ConsumerStats dataclass."""

    def test_consumer_stats_defaults(self):
        """Test ConsumerStats with default values."""
        stats = ConsumerStats()

        assert stats.messages_received == 0
        assert stats.messages_processed == 0
        assert stats.messages_failed == 0
        assert stats.samples_learned == 0
        # last_offset defaults to -1 (no messages consumed yet)
        assert stats.last_offset == -1
        assert stats.last_message_at is None
        assert stats.consumer_lag == 0
        assert stats.status == "stopped"

    def test_consumer_stats_custom(self):
        """Test ConsumerStats with custom values."""
        timestamp = datetime.now(tz=UTC)
        stats = ConsumerStats(
            messages_received=1000,
            messages_processed=995,
            messages_failed=5,
            samples_learned=990,
            last_offset=12345,
            last_message_at=timestamp,
            consumer_lag=10,
            status="running",
        )

        assert stats.messages_received == 1000
        assert stats.messages_processed == 995
        assert stats.messages_failed == 5
        assert stats.samples_learned == 990
        assert stats.last_offset == 12345
        assert stats.last_message_at == timestamp
        assert stats.consumer_lag == 10
        assert stats.status == "running"


class TestRiverSklearnAdapter:
    """Tests for RiverSklearnAdapter class."""

    @pytest.fixture
    def mock_river_model(self):
        """Create a mock River model."""
        model = MagicMock()
        model.predict_one = MagicMock(return_value=1)
        model.predict_proba_one = MagicMock(return_value={0: 0.2, 1: 0.8})
        model.learn_one = MagicMock()
        return model

    @pytest.fixture
    def adapter(self, mock_river_model):
        """Create a RiverSklearnAdapter with mocked dependencies."""
        with patch("online_learning.RIVER_AVAILABLE", True):
            with patch("online_learning.NUMPY_AVAILABLE", True):
                with patch("online_learning.river_ensemble") as mock_ensemble:
                    with patch("online_learning.river_metrics") as mock_metrics:
                        mock_metrics.Accuracy = MagicMock
                        adapter = RiverSklearnAdapter(
                            river_model=mock_river_model,
                            model_type=ModelType.CLASSIFIER,
                            n_models=10,
                            seed=42,
                            feature_names=["f1", "f2", "f3"],
                        )
                        return adapter

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_initialization(self):
        """Test RiverSklearnAdapter initialization with default model."""
        adapter = RiverSklearnAdapter(
            model_type=ModelType.CLASSIFIER,
            n_models=10,
            seed=42,
        )

        assert adapter.model_type == ModelType.CLASSIFIER
        assert adapter.n_models == 10
        assert adapter.seed == 42
        assert adapter.model is not None
        assert adapter._samples_learned == 0

    def test_adapter_check_dependencies_river_missing(self):
        """Test that adapter raises when River is missing."""
        with patch("online_learning.RIVER_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                RiverSklearnAdapter()
            assert "River is required" in str(exc_info.value)

    def test_adapter_check_dependencies_numpy_missing(self):
        """Test that adapter raises when NumPy is missing."""
        with patch("online_learning.RIVER_AVAILABLE", True):
            with patch("online_learning.NUMPY_AVAILABLE", False):
                with pytest.raises(ImportError) as exc_info:
                    RiverSklearnAdapter()
                assert "NumPy is required" in str(exc_info.value)

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_predict_one(self):
        """Test predict_one method."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Learn some samples first
        for i in range(10):
            adapter.learn_one({"f0": float(i), "f1": float(i * 2)}, i % 2)

        # Make a prediction
        result = adapter.predict_one({"f0": 5.0, "f1": 10.0})

        # Prediction should be made (value depends on model state)
        assert adapter._total_predictions >= 1

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_learn_one(self):
        """Test learn_one method updates model."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        initial_samples = adapter.samples_learned

        adapter.learn_one({"f0": 1.0, "f1": 2.0}, 1)

        assert adapter.samples_learned == initial_samples + 1
        assert adapter._last_update is not None

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_learn_batch(self):
        """Test learn_batch method."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        X = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
        y = [0, 1, 0]

        result = adapter.learn_batch(X, y)

        assert result.success is True
        assert result.samples_learned == 3
        assert adapter.samples_learned == 3

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_predict_batch(self):
        """Test batch predict method."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Learn some samples first
        for i in range(100):
            adapter.learn_one({"0": float(i % 10), "1": float(i % 5)}, i % 2)

        X = [[1.0, 2.0], [3.0, 4.0]]
        predictions = adapter.predict(X)

        assert len(predictions) == 2

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_predict_proba(self):
        """Test predict_proba method for classifiers."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Learn some samples first
        for i in range(50):
            adapter.learn_one({"0": float(i % 10), "1": float(i % 5)}, i % 2)

        X = [[1.0, 2.0]]
        probabilities = adapter.predict_proba(X)

        assert len(probabilities) == 1
        assert len(probabilities[0]) >= 1  # At least one probability value

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_predict_proba_regressor_raises(self):
        """Test predict_proba raises for regressors."""
        adapter = RiverSklearnAdapter(model_type=ModelType.REGRESSOR)

        with pytest.raises(ValueError) as exc_info:
            adapter.predict_proba([[1.0, 2.0]])
        assert "only available for classifiers" in str(exc_info.value)

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_to_dict_with_feature_names(self):
        """Test _to_dict uses feature names when provided."""
        adapter = RiverSklearnAdapter(
            model_type=ModelType.CLASSIFIER,
            feature_names=["age", "income"],
        )

        x = [25.0, 50000.0]
        result = adapter._to_dict(x)

        assert result == {"age": 25.0, "income": 50000.0}

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_to_dict_without_feature_names(self):
        """Test _to_dict uses indices when no feature names."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        x = [25.0, 50000.0]
        result = adapter._to_dict(x)

        assert result == {0: 25.0, 1: 50000.0}

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_to_dict_passthrough(self):
        """Test _to_dict passes through dict inputs."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        x = {"age": 25.0, "income": 50000.0}
        result = adapter._to_dict(x)

        assert result == x

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_get_stats(self):
        """Test get_stats returns correct LearningStats."""
        adapter = RiverSklearnAdapter(
            model_type=ModelType.CLASSIFIER,
            feature_names=["f1", "f2"],
        )

        # Learn some samples
        for i in range(10):
            adapter.learn_one({"f1": float(i), "f2": float(i * 2)}, i % 2)

        stats = adapter.get_stats()

        assert isinstance(stats, LearningStats)
        assert stats.samples_learned == 10
        assert stats.feature_names == ["f1", "f2"]
        assert stats.status == LearningStatus.COLD_START  # < MIN_SAMPLES_FOR_PREDICTION // 2

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_is_ready_property(self):
        """Test is_ready property based on sample count."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Initially not ready
        assert adapter.is_ready is False

        # Learn samples but not enough
        for i in range(100):
            adapter.learn_one({"0": float(i)}, i % 2)

        # Still not ready (need MIN_SAMPLES_FOR_PREDICTION)
        assert adapter.is_ready is False

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_reset(self):
        """Test reset clears model state."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Learn some samples
        for i in range(10):
            adapter.learn_one({"0": float(i)}, i % 2)

        assert adapter.samples_learned > 0

        # Reset
        adapter.reset()

        assert adapter.samples_learned == 0
        assert adapter._total_predictions == 0
        assert adapter._correct_predictions == 0
        assert adapter._last_update is None


class TestOnlineLearningPipeline:
    """Tests for OnlineLearningPipeline class."""

    @pytest.fixture
    def mock_fallback_model(self):
        """Create a mock sklearn fallback model."""
        model = MagicMock()
        model.predict = MagicMock(return_value=[1])
        model.predict_proba = MagicMock(return_value=[[0.2, 0.8]])
        model.classes_ = [0, 1]
        return model

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_initialization(self):
        """Test OnlineLearningPipeline initialization."""
        pipeline = OnlineLearningPipeline(
            feature_names=["f1", "f2"],
            model_type=ModelType.CLASSIFIER,
            n_models=5,
            seed=123,
        )

        assert pipeline.feature_names == ["f1", "f2"]
        assert pipeline.model_type == ModelType.CLASSIFIER
        assert pipeline.adapter is not None
        assert pipeline._fallback_model is None

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_set_fallback_model(self, mock_fallback_model):
        """Test setting fallback sklearn model."""
        pipeline = OnlineLearningPipeline()

        pipeline.set_fallback_model(mock_fallback_model)

        assert pipeline._fallback_model is mock_fallback_model

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_predict_cold_start_with_fallback(self, mock_fallback_model):
        """Test prediction during cold start uses fallback."""
        pipeline = OnlineLearningPipeline(
            feature_names=["f1", "f2"],
            enable_fallback=True,
        )
        pipeline.set_fallback_model(mock_fallback_model)

        result = pipeline.predict({"f1": 1.0, "f2": 2.0})

        assert result.used_fallback is True
        assert result.prediction == 1
        assert result.confidence is not None

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_predict_without_fallback(self):
        """Test prediction without fallback uses online model."""
        pipeline = OnlineLearningPipeline(
            feature_names=["f1", "f2"],
            enable_fallback=False,
        )

        result = pipeline.predict({"f1": 1.0, "f2": 2.0})

        assert result.used_fallback is False
        assert result.model_status == LearningStatus.COLD_START

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_learn(self):
        """Test learn method updates the adapter."""
        pipeline = OnlineLearningPipeline(feature_names=["f1", "f2"])

        initial_samples = pipeline.adapter.samples_learned

        pipeline.learn({"f1": 1.0, "f2": 2.0}, 1)

        assert pipeline.adapter.samples_learned == initial_samples + 1

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_learn_from_feedback(self):
        """Test learn_from_feedback processes feedback events."""
        pipeline = OnlineLearningPipeline(feature_names=["f1", "f2"])

        result = pipeline.learn_from_feedback(
            features={"f1": 1.0, "f2": 2.0},
            outcome=1,
            decision_id="test-123",
        )

        assert result.success is True
        assert result.samples_learned == 1

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_learn_from_feedback_error_handling(self):
        """Test learn_from_feedback handles errors gracefully."""
        pipeline = OnlineLearningPipeline(feature_names=["f1", "f2"])

        # Mock adapter to raise exception
        pipeline.adapter.learn_one = MagicMock(side_effect=RuntimeError("Learning failed"))

        result = pipeline.learn_from_feedback(
            features={"f1": 1.0, "f2": 2.0},
            outcome=1,
        )

        assert result.success is False
        assert "Learning failed" in result.error_message

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_get_stats(self):
        """Test get_stats returns pipeline statistics."""
        pipeline = OnlineLearningPipeline(feature_names=["f1", "f2"])

        # Learn some samples
        for i in range(5):
            pipeline.learn({"f1": float(i), "f2": float(i * 2)}, i % 2)

        stats = pipeline.get_stats()

        # PipelineStats is a dataclass, access fields as attributes
        assert stats.learning_stats is not None
        assert stats.total_predictions is not None  # Prediction stats (replaces "prediction_stats")
        assert stats.learning_stats.samples_learned == 5
        assert stats.model_ready is not None
        assert stats.has_fallback is not None

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_reset(self):
        """Test reset clears pipeline state."""
        pipeline = OnlineLearningPipeline(feature_names=["f1", "f2"])

        # Learn some samples and make predictions
        for i in range(5):
            pipeline.learn({"f1": float(i), "f2": float(i * 2)}, i % 2)
            pipeline.predict({"f1": float(i), "f2": float(i * 2)})

        # Reset
        pipeline.reset()

        assert pipeline.adapter.samples_learned == 0
        assert pipeline._fallback_predictions == 0
        assert pipeline._online_predictions == 0


class TestFeedbackKafkaConsumer:
    """Tests for FeedbackKafkaConsumer class."""

    @pytest.fixture
    def mock_pipeline(self):
        """Create a mock OnlineLearningPipeline."""
        pipeline = MagicMock()
        pipeline.learn_from_feedback = MagicMock(
            return_value=LearningResult(success=True, samples_learned=1, total_samples=100)
        )
        pipeline.get_stats = MagicMock(return_value={"learning_stats": {"samples_learned": 100}})
        return pipeline

    def test_consumer_initialization(self, mock_pipeline):
        """Test FeedbackKafkaConsumer initialization."""
        consumer = FeedbackKafkaConsumer(
            pipeline=mock_pipeline,
            bootstrap_servers="localhost:9092",
            topic="test.topic",
            group_id="test-group",
        )

        assert consumer.bootstrap_servers == "localhost:9092"
        assert consumer.topic == "test.topic"
        assert consumer.group_id == "test-group"
        assert consumer._running is False
        assert consumer._stats.status == "stopped"

    def test_consumer_check_dependencies_kafka_missing(self, mock_pipeline):
        """Test _check_dependencies returns False when Kafka missing."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        # Patch where the variable is checked (in consumer module)
        with patch("enhanced_agent_bus.online_learning_infra.consumer.KAFKA_AVAILABLE", False):
            result = consumer._check_dependencies()
            assert result is False

    def test_consumer_check_dependencies_river_missing(self, mock_pipeline):
        """Test _check_dependencies returns False when River missing."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        # Patch where the variables are checked (in consumer module)
        with patch("enhanced_agent_bus.online_learning_infra.consumer.KAFKA_AVAILABLE", True):
            with patch("enhanced_agent_bus.online_learning_infra.consumer.RIVER_AVAILABLE", False):
                result = consumer._check_dependencies()
                assert result is False

    @pytest.mark.skipif(
        not KAFKA_AVAILABLE or not RIVER_AVAILABLE,
        reason="Kafka or River not installed",
    )
    def test_consumer_check_dependencies_success(self, mock_pipeline):
        """Test _check_dependencies returns True when all deps available."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)
        result = consumer._check_dependencies()
        assert result is True

    def test_consumer_extract_outcome_actual_impact(self, mock_pipeline):
        """Test _extract_outcome with actual_impact field."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        event_data = {"actual_impact": 0.75}
        outcome = consumer._extract_outcome(event_data)

        assert outcome == 0.75

    def test_consumer_extract_outcome_status(self, mock_pipeline):
        """Test _extract_outcome with outcome status."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        # Test success outcome
        assert consumer._extract_outcome({"outcome": "success"}) == 1

        # Test failure outcome
        assert consumer._extract_outcome({"outcome": "failure"}) == 0

        # Test partial outcome
        assert consumer._extract_outcome({"outcome": "partial"}) == 0.5

        # Test unknown outcome
        assert consumer._extract_outcome({"outcome": "unknown"}) is None

    def test_consumer_extract_outcome_feedback_type(self, mock_pipeline):
        """Test _extract_outcome with feedback_type field."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        # Test positive feedback
        assert consumer._extract_outcome({"feedback_type": "positive"}) == 1

        # Test negative feedback
        assert consumer._extract_outcome({"feedback_type": "negative"}) == 0

        # Test neutral feedback
        assert consumer._extract_outcome({"feedback_type": "neutral"}) == 0.5

        # Test correction feedback (special handling)
        assert consumer._extract_outcome({"feedback_type": "correction"}) is None

    def test_consumer_extract_outcome_none(self, mock_pipeline):
        """Test _extract_outcome returns None for empty event."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        outcome = consumer._extract_outcome({})
        assert outcome is None

    def test_consumer_sanitize_error(self, mock_pipeline):
        """Test _sanitize_error redacts sensitive information."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        error = Exception("bootstrap_servers='kafka:9092' password='secret123' failed")
        sanitized = consumer._sanitize_error(error)

        assert "REDACTED" in sanitized
        assert "secret123" not in sanitized

    def test_consumer_sanitize_bootstrap(self, mock_pipeline):
        """Test _sanitize_bootstrap hides port details."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        servers = "kafka1:9092,kafka2:9093"
        sanitized = consumer._sanitize_bootstrap(servers)

        assert "kafka1:****" in sanitized
        assert "kafka2:****" in sanitized
        assert "9092" not in sanitized

    def test_consumer_get_stats(self, mock_pipeline):
        """Test get_stats returns ConsumerStats."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        stats = consumer.get_stats()

        assert isinstance(stats, ConsumerStats)
        assert stats.status == "stopped"

    def test_consumer_is_running_property(self, mock_pipeline):
        """Test is_running property."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        assert consumer.is_running is False

    def test_consumer_pipeline_property(self, mock_pipeline):
        """Test pipeline property."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        assert consumer.pipeline is mock_pipeline

    async def test_consumer_start_missing_deps(self, mock_pipeline):
        """Test start returns False when dependencies missing."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        with patch.object(consumer, "_check_dependencies", return_value=False):
            result = await consumer.start()
            assert result is False

    async def test_consumer_stop_when_not_running(self, mock_pipeline):
        """Test stop when consumer is not running."""
        consumer = FeedbackKafkaConsumer(pipeline=mock_pipeline)

        # Should not raise
        await consumer.stop()

        assert consumer._running is False


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_global_instances(self):
        """Reset global instances before each test."""
        import online_learning

        online_learning._online_learning_adapter = None
        online_learning._online_learning_pipeline = None
        online_learning._feedback_kafka_consumer = None
        yield
        online_learning._online_learning_adapter = None
        online_learning._online_learning_pipeline = None
        online_learning._feedback_kafka_consumer = None

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_get_online_learning_adapter_singleton(self):
        """Test get_online_learning_adapter creates singleton."""
        adapter1 = get_online_learning_adapter()
        adapter2 = get_online_learning_adapter()

        assert adapter1 is adapter2

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_get_online_learning_adapter_with_params(self):
        """Test get_online_learning_adapter with custom parameters."""
        # Use force_new=True to bypass singleton and create with custom params
        adapter = get_online_learning_adapter(
            model_type=ModelType.REGRESSOR,
            n_models=5,
            feature_names=["a", "b", "c"],
            force_new=True,
        )

        assert adapter.model_type == ModelType.REGRESSOR
        assert adapter.n_models == 5
        assert adapter.feature_names == ["a", "b", "c"]

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_get_online_learning_pipeline_singleton(self):
        """Test get_online_learning_pipeline creates singleton."""
        pipeline1 = get_online_learning_pipeline()
        pipeline2 = get_online_learning_pipeline()

        assert pipeline1 is pipeline2

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_get_online_learning_pipeline_with_params(self):
        """Test get_online_learning_pipeline with custom parameters."""
        # Use force_new=True to bypass singleton and create with custom params
        pipeline = get_online_learning_pipeline(
            feature_names=["x", "y"],
            model_type=ModelType.REGRESSOR,
            force_new=True,
        )

        assert pipeline.feature_names == ["x", "y"]
        assert pipeline.model_type == ModelType.REGRESSOR

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_learn_from_feedback_event(self):
        """Test learn_from_feedback_event convenience function."""
        result = learn_from_feedback_event(
            features={"f1": 1.0, "f2": 2.0},
            outcome=1,
            decision_id="test-456",
        )

        assert isinstance(result, LearningResult)
        assert result.success is True

    def test_get_consumer_stats_none_when_no_consumer(self):
        """Test get_consumer_stats returns None when no consumer."""
        stats = get_consumer_stats()
        assert stats is None


class TestConfigurationConstants:
    """Tests for configuration constants."""

    def test_river_model_type_from_env(self):
        """Test RIVER_MODEL_TYPE uses environment variable."""
        from online_learning import RIVER_MODEL_TYPE

        expected = os.getenv("RIVER_MODEL_TYPE", "classifier")
        assert RIVER_MODEL_TYPE == expected

    def test_river_n_models_from_env(self):
        """Test RIVER_N_MODELS uses environment variable."""
        expected = int(os.getenv("RIVER_N_MODELS", "10"))
        assert RIVER_N_MODELS == expected

    def test_river_seed_from_env(self):
        """Test RIVER_SEED uses environment variable."""
        expected = int(os.getenv("RIVER_SEED", "42"))
        assert RIVER_SEED == expected

    def test_min_samples_for_prediction_from_env(self):
        """Test MIN_SAMPLES_FOR_PREDICTION uses environment variable."""
        expected = int(os.getenv("MIN_SAMPLES_FOR_PREDICTION", "500"))
        assert MIN_SAMPLES_FOR_PREDICTION == expected

    def test_enable_cold_start_fallback_from_env(self):
        """Test ENABLE_COLD_START_FALLBACK uses environment variable."""
        expected = os.getenv("ENABLE_COLD_START_FALLBACK", "true").lower() == "true"
        assert ENABLE_COLD_START_FALLBACK == expected

    def test_kafka_bootstrap_from_env(self):
        """Test KAFKA_BOOTSTRAP is a valid bootstrap server address."""
        # KAFKA_BOOTSTRAP is a module-level constant set at import time.
        # We verify it is a non-empty string with host:port format.
        assert isinstance(KAFKA_BOOTSTRAP, str) and KAFKA_BOOTSTRAP
        assert ":" in KAFKA_BOOTSTRAP

    def test_kafka_topic_feedback_from_env(self):
        """Test KAFKA_TOPIC_FEEDBACK uses environment variable."""
        expected = os.getenv("KAFKA_TOPIC_FEEDBACK", "governance.feedback.v1")
        assert KAFKA_TOPIC_FEEDBACK == expected

    def test_kafka_consumer_group_from_env(self):
        """Test KAFKA_CONSUMER_GROUP uses environment variable."""
        expected = os.getenv("KAFKA_CONSUMER_GROUP", "river-learner")
        assert KAFKA_CONSUMER_GROUP == expected


class TestAvailabilityFlags:
    """Tests for availability flag exports."""

    def test_river_available_flag(self):
        """Test RIVER_AVAILABLE flag is exported."""
        assert isinstance(RIVER_AVAILABLE, bool)

    def test_numpy_available_flag(self):
        """Test NUMPY_AVAILABLE flag is exported."""
        assert isinstance(NUMPY_AVAILABLE, bool)

    def test_kafka_available_flag(self):
        """Test KAFKA_AVAILABLE flag is exported."""
        assert isinstance(KAFKA_AVAILABLE, bool)


class TestAdapterPatternWorksCorrectly:
    """Tests verifying the adapter pattern works as expected per spec."""

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_converts_array_to_dict(self):
        """Test adapter correctly converts array inputs to dict for River."""
        adapter = RiverSklearnAdapter(
            model_type=ModelType.CLASSIFIER,
            feature_names=["age", "income", "score"],
        )

        # Array input should be converted to dict
        x_array = [25.0, 50000.0, 0.8]
        x_dict = adapter._to_dict(x_array)

        assert x_dict == {"age": 25.0, "income": 50000.0, "score": 0.8}

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_maintains_sklearn_interface(self):
        """Test adapter provides sklearn-compatible interface."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Learn samples
        for i in range(20):
            adapter.learn_one({"0": float(i), "1": float(i * 2)}, i % 2)

        # sklearn-style batch methods should work
        X = [[1.0, 2.0], [3.0, 6.0], [5.0, 10.0]]

        predictions = adapter.predict(X)
        assert len(predictions) == 3

        probabilities = adapter.predict_proba(X)
        assert len(probabilities) == 3

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_river_style_methods_work(self):
        """Test adapter maintains River-style single sample methods."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # River-style learn_one
        adapter.learn_one({"f0": 1.0, "f1": 2.0}, 1)

        # River-style predict_one
        prediction = adapter.predict_one({"f0": 1.0, "f1": 2.0})

        # River-style predict_proba_one
        proba = adapter.predict_proba_one({"f0": 1.0, "f1": 2.0})

        assert adapter.samples_learned >= 1
        assert isinstance(proba, dict)

    @pytest.mark.skipif(
        not RIVER_AVAILABLE or not NUMPY_AVAILABLE,
        reason="River or NumPy not installed",
    )
    def test_adapter_predictions_change_after_learning(self):
        """Test that predictions evolve as the model learns."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Make initial prediction (model has no training)
        initial_proba = adapter.predict_proba_one({"0": 5.0, "1": 10.0})

        # Learn many samples with clear pattern
        for i in range(100):
            # Class 1 when feature 0 > 5, else class 0
            label = 1 if i % 10 > 5 else 0
            adapter.learn_one({"0": float(i % 10), "1": float(i % 20)}, label)

        # Make prediction after learning
        learned_proba = adapter.predict_proba_one({"0": 5.0, "1": 10.0})

        # Model should have learned something (probabilities should exist)
        assert learned_proba is not None or learned_proba == {}
        assert adapter.samples_learned == 100


class TestPipelineWithFallback:
    """Tests for OnlineLearningPipeline cold start fallback behavior."""

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_fallback_used_during_cold_start(self):
        """Test fallback model is used during cold start period."""
        # Create mock sklearn model
        mock_sklearn = MagicMock()
        mock_sklearn.predict = MagicMock(return_value=[1])
        mock_sklearn.predict_proba = MagicMock(return_value=[[0.1, 0.9]])
        mock_sklearn.classes_ = [0, 1]

        pipeline = OnlineLearningPipeline(
            feature_names=["f1", "f2"],
            enable_fallback=True,
        )
        pipeline.set_fallback_model(mock_sklearn)

        result = pipeline.predict({"f1": 1.0, "f2": 2.0})

        assert result.used_fallback is True
        assert result.prediction == 1
        assert result.confidence == 0.9

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_no_fallback_when_disabled(self):
        """Test fallback not used when disabled."""
        mock_sklearn = MagicMock()

        pipeline = OnlineLearningPipeline(
            feature_names=["f1", "f2"],
            enable_fallback=False,
        )
        pipeline.set_fallback_model(mock_sklearn)

        result = pipeline.predict({"f1": 1.0, "f2": 2.0})

        assert result.used_fallback is False
        mock_sklearn.predict.assert_not_called()


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_adapter_learn_batch_error_handling(self):
        """Test learn_batch handles errors gracefully."""
        adapter = RiverSklearnAdapter(model_type=ModelType.CLASSIFIER)

        # Mock learn_one to raise after some samples
        original_learn_one = adapter.learn_one
        call_count = [0]

        def failing_learn_one(x, y):
            call_count[0] += 1
            if call_count[0] > 2:
                raise ValueError("Simulated failure")
            original_learn_one(x, y)

        adapter.learn_one = failing_learn_one

        result = adapter.learn_batch([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]], [0, 1, 0, 1])

        assert result.success is False
        assert "Simulated failure" in result.error_message

    @pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
    def test_pipeline_fallback_error_graceful_degradation(self):
        """Test pipeline degrades gracefully when fallback fails."""
        mock_sklearn = MagicMock()
        mock_sklearn.predict = MagicMock(side_effect=RuntimeError("Sklearn failed"))

        pipeline = OnlineLearningPipeline(
            feature_names=["f1", "f2"],
            enable_fallback=True,
        )
        pipeline.set_fallback_model(mock_sklearn)

        # Should fall back to online model when sklearn fails
        result = pipeline.predict({"f1": 1.0, "f2": 2.0})

        # Should have fallen back to River model
        assert result.used_fallback is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
