from enhanced_agent_bus._compat.config.governance_constants import IMPACT_SCORER_CONFIG
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

"""
Tests for ImpactScorer — targets ≥90% coverage.
Constitutional Hash: 608508a9bd224290
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Force-import the module under test at collection time so coverage sees it.
# Use patch to suppress MLflow I/O during import-time initialisation.
with patch(
    "enhanced_agent_bus.adaptive_governance.impact_scorer.ImpactScorer._initialize_mlflow",
    return_value=None,
):
    import enhanced_agent_bus.adaptive_governance.impact_scorer as _IMPACT_MODULE

_IMPACT_MODULE_DEFAULTS = {
    "SKLEARN_AVAILABLE": _IMPACT_MODULE.SKLEARN_AVAILABLE,
    "RandomForestRegressor": _IMPACT_MODULE.RandomForestRegressor,
    "NUMPY_AVAILABLE": _IMPACT_MODULE.NUMPY_AVAILABLE,
    "np": _IMPACT_MODULE.np,
    "MLFLOW_AVAILABLE": _IMPACT_MODULE.MLFLOW_AVAILABLE,
    "mlflow": _IMPACT_MODULE.mlflow,
    "TORCH_AVAILABLE": _IMPACT_MODULE.TORCH_AVAILABLE,
    "torch": _IMPACT_MODULE.torch,
    "sinkhorn_projection": _IMPACT_MODULE.sinkhorn_projection,
}


@pytest.fixture(autouse=True)
def _restore_impact_module_state():
    for name, value in _IMPACT_MODULE_DEFAULTS.items():
        setattr(_IMPACT_MODULE, name, value)
    yield
    for name, value in _IMPACT_MODULE_DEFAULTS.items():
        setattr(_IMPACT_MODULE, name, value)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scorer(constitutional_hash: str = CONSTITUTIONAL_HASH, **kwargs):
    """Return an ImpactScorer with MLflow initialisation suppressed."""
    with patch.object(_IMPACT_MODULE.ImpactScorer, "_initialize_mlflow", return_value=None):
        scorer = _IMPACT_MODULE.ImpactScorer(constitutional_hash=constitutional_hash, **kwargs)
    return scorer


def _make_features(
    message_length: int = 100,
    agent_count: int = 2,
    tenant_complexity: float = 0.5,
    temporal_patterns: list | None = None,
    semantic_similarity: float = 0.3,
    historical_precedence: int = 1,
    resource_utilization: float = 0.2,
    network_isolation: float = 0.9,
    risk_score: float = 0.0,
    confidence_level: float = 0.0,
):
    from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

    return ImpactFeatures(
        message_length=message_length,
        agent_count=agent_count,
        tenant_complexity=tenant_complexity,
        temporal_patterns=temporal_patterns if temporal_patterns is not None else [0.1, 0.2],
        semantic_similarity=semantic_similarity,
        historical_precedence=historical_precedence,
        resource_utilization=resource_utilization,
        network_isolation=network_isolation,
        risk_score=risk_score,
        confidence_level=confidence_level,
    )


# ---------------------------------------------------------------------------
# __init__ / construction
# ---------------------------------------------------------------------------


class TestImpactScorerInit:
    def test_init_stores_constitutional_hash(self):
        scorer = _make_scorer()
        assert scorer.constitutional_hash == CONSTITUTIONAL_HASH

    def test_init_with_sklearn_available(self):
        """When sklearn is available the classifier is set."""
        scorer = _make_scorer()
        # sklearn is available in this environment — classifier should not be None
        from enhanced_agent_bus.adaptive_governance import impact_scorer as _mod

        if _mod.SKLEARN_AVAILABLE:
            assert scorer.impact_classifier is not None
        else:
            assert scorer.impact_classifier is None

    def test_init_without_sklearn(self):
        """Without sklearn, impact_classifier is None."""
        orig = _IMPACT_MODULE.SKLEARN_AVAILABLE
        orig_cls = _IMPACT_MODULE.RandomForestRegressor
        try:
            _IMPACT_MODULE.SKLEARN_AVAILABLE = False
            _IMPACT_MODULE.RandomForestRegressor = None
            scorer = _make_scorer()
            assert scorer.impact_classifier is None
        finally:
            _IMPACT_MODULE.SKLEARN_AVAILABLE = orig
            _IMPACT_MODULE.RandomForestRegressor = orig_cls

    def test_init_feature_weights_sum_to_one(self):
        scorer = _make_scorer()
        total = sum(scorer.feature_weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_init_model_not_trained(self):
        scorer = _make_scorer()
        assert scorer.model_trained is False

    def test_init_mlflow_not_initialized_in_pytest(self):
        """_initialize_mlflow should set _mlflow_initialized=False when pytest is in sys.modules."""
        # pytest IS already in sys.modules here; call real _initialize_mlflow
        scorer = _IMPACT_MODULE.ImpactScorer.__new__(_IMPACT_MODULE.ImpactScorer)
        scorer.constitutional_hash = CONSTITUTIONAL_HASH
        scorer._mlflow_initialized = False
        scorer._mlflow_experiment_id = None
        scorer.model_version = None
        # Patch MLFLOW_AVAILABLE so we reach the pytest check
        orig = _IMPACT_MODULE.MLFLOW_AVAILABLE
        orig_mlflow = _IMPACT_MODULE.mlflow
        try:
            _IMPACT_MODULE.MLFLOW_AVAILABLE = True
            _IMPACT_MODULE.mlflow = MagicMock()
            scorer._initialize_mlflow()
            # Should return early without setting _mlflow_initialized=True
            assert scorer._mlflow_initialized is False
        finally:
            _IMPACT_MODULE.MLFLOW_AVAILABLE = orig
            _IMPACT_MODULE.mlflow = orig_mlflow

    def test_init_mlflow_not_available(self):
        """When MLflow is not available _initialize_mlflow logs a warning and returns."""
        orig = _IMPACT_MODULE.MLFLOW_AVAILABLE
        try:
            _IMPACT_MODULE.MLFLOW_AVAILABLE = False
            scorer = _IMPACT_MODULE.ImpactScorer.__new__(_IMPACT_MODULE.ImpactScorer)
            scorer.constitutional_hash = "abc"
            scorer._mlflow_initialized = False
            scorer._mlflow_experiment_id = None
            scorer.model_version = None
            scorer._initialize_mlflow()
            assert scorer._mlflow_initialized is False
        finally:
            _IMPACT_MODULE.MLFLOW_AVAILABLE = orig

    def test_init_mlflow_available_not_in_pytest(self):
        """When mlflow is available and we are NOT in pytest, _initialize_mlflow runs."""
        orig_avail = _IMPACT_MODULE.MLFLOW_AVAILABLE
        orig_mlflow = _IMPACT_MODULE.mlflow
        try:
            mock_mlflow = MagicMock()
            mock_mlflow.get_experiment_by_name.return_value = None
            mock_mlflow.create_experiment.return_value = "exp-001"
            _IMPACT_MODULE.MLFLOW_AVAILABLE = True
            _IMPACT_MODULE.mlflow = mock_mlflow

            scorer = _IMPACT_MODULE.ImpactScorer.__new__(_IMPACT_MODULE.ImpactScorer)
            scorer.constitutional_hash = CONSTITUTIONAL_HASH
            scorer._mlflow_initialized = False
            scorer._mlflow_experiment_id = None
            scorer.model_version = None

            # Temporarily remove pytest from sys.modules to trigger the real init branch
            saved = sys.modules.pop("pytest", None)
            try:
                scorer._initialize_mlflow()
            finally:
                if saved is not None:
                    sys.modules["pytest"] = saved

            assert scorer._mlflow_initialized is True
            assert scorer._mlflow_experiment_id == "exp-001"
        finally:
            _IMPACT_MODULE.MLFLOW_AVAILABLE = orig_avail
            _IMPACT_MODULE.mlflow = orig_mlflow

    def test_init_mlflow_experiment_exists(self):
        """Branch: experiment already exists (get_experiment_by_name returns non-None)."""
        orig_avail = _IMPACT_MODULE.MLFLOW_AVAILABLE
        orig_mlflow = _IMPACT_MODULE.mlflow
        try:
            mock_exp = MagicMock()
            mock_exp.experiment_id = "existing-001"
            mock_mlflow = MagicMock()
            mock_mlflow.get_experiment_by_name.return_value = mock_exp
            _IMPACT_MODULE.MLFLOW_AVAILABLE = True
            _IMPACT_MODULE.mlflow = mock_mlflow

            scorer = _IMPACT_MODULE.ImpactScorer.__new__(_IMPACT_MODULE.ImpactScorer)
            scorer.constitutional_hash = CONSTITUTIONAL_HASH
            scorer._mlflow_initialized = False
            scorer._mlflow_experiment_id = None
            scorer.model_version = None

            saved = sys.modules.pop("pytest", None)
            try:
                scorer._initialize_mlflow()
            finally:
                if saved is not None:
                    sys.modules["pytest"] = saved

            assert scorer._mlflow_experiment_id == "existing-001"
        finally:
            _IMPACT_MODULE.MLFLOW_AVAILABLE = orig_avail
            _IMPACT_MODULE.mlflow = orig_mlflow

    def test_init_mlflow_error_is_caught(self):
        """RuntimeError during mlflow init is caught and _mlflow_initialized stays False."""
        orig_avail = _IMPACT_MODULE.MLFLOW_AVAILABLE
        orig_mlflow = _IMPACT_MODULE.mlflow
        try:
            mock_mlflow = MagicMock()
            mock_mlflow.set_tracking_uri.side_effect = RuntimeError("conn refused")
            _IMPACT_MODULE.MLFLOW_AVAILABLE = True
            _IMPACT_MODULE.mlflow = mock_mlflow

            scorer = _IMPACT_MODULE.ImpactScorer.__new__(_IMPACT_MODULE.ImpactScorer)
            scorer.constitutional_hash = CONSTITUTIONAL_HASH
            scorer._mlflow_initialized = False
            scorer._mlflow_experiment_id = None
            scorer.model_version = None

            saved = sys.modules.pop("pytest", None)
            try:
                scorer._initialize_mlflow()
            finally:
                if saved is not None:
                    sys.modules["pytest"] = saved

            assert scorer._mlflow_initialized is False
        finally:
            _IMPACT_MODULE.MLFLOW_AVAILABLE = orig_avail
            _IMPACT_MODULE.mlflow = orig_mlflow

    def test_use_mhc_stability_false_when_torch_unavailable(self):
        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        orig = _mod.TORCH_AVAILABLE
        try:
            _mod.TORCH_AVAILABLE = False
            scorer = _make_scorer()
            assert scorer.use_mhc_stability is False
        finally:
            _mod.TORCH_AVAILABLE = orig

    def test_use_mhc_stability_false_when_sinkhorn_none(self):
        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        orig_sink = _mod.sinkhorn_projection
        orig_torch = _mod.TORCH_AVAILABLE
        try:
            _mod.sinkhorn_projection = None
            _mod.TORCH_AVAILABLE = True
            scorer = _make_scorer()
            assert scorer.use_mhc_stability is False
        finally:
            _mod.sinkhorn_projection = orig_sink
            _mod.TORCH_AVAILABLE = orig_torch


# ---------------------------------------------------------------------------
# assess_impact
# ---------------------------------------------------------------------------


class TestAssessImpact:
    async def test_assess_impact_untrained_returns_rule_based(self):
        scorer = _make_scorer()
        message = {"content": "hello world", "tenant_id": "t1"}
        context: dict = {"active_agents": ["a1", "a2"]}
        features = await scorer.assess_impact(message, context)
        assert 0.0 <= features.risk_score <= 1.0
        assert features.confidence_level == pytest.approx(0.7)  # fallback value

    async def test_assess_impact_trained_uses_ml_prediction(self):
        scorer = _make_scorer()
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.return_value = [0.42]
        scorer.impact_classifier = mock_clf

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        orig = _mod.NUMPY_AVAILABLE
        orig_np = _mod.np
        try:
            import numpy as np

            _mod.NUMPY_AVAILABLE = True
            _mod.np = np
            message = {"content": "test", "tenant_id": "t1"}
            context: dict = {"active_agents": []}
            features = await scorer.assess_impact(message, context)
            assert features.risk_score == pytest.approx(0.42)
        finally:
            _mod.NUMPY_AVAILABLE = orig
            _mod.np = orig_np

    async def test_assess_impact_exception_returns_safe_defaults(self):
        scorer = _make_scorer()

        async def bad_extract(*a, **kw):
            raise RuntimeError("extraction failed")

        scorer._extract_features = bad_extract
        message = {"content": "test", "tenant_id": "t1"}
        context: dict = {}
        features = await scorer.assess_impact(message, context)
        assert features.risk_score == pytest.approx(0.1)  # conservative_default_score
        assert features.confidence_level == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# _extract_features
# ---------------------------------------------------------------------------


class TestExtractFeatures:
    async def test_extract_features_basic(self):
        scorer = _make_scorer()
        message = {"content": "Hello", "tenant_id": "tenant-A"}
        context: dict = {"active_agents": ["x", "y", "z"]}
        features = await scorer._extract_features(message, context)
        assert features.message_length == 5
        assert features.agent_count == 3

    async def test_extract_features_no_active_agents(self):
        scorer = _make_scorer()
        message = {"content": "abc", "tenant_id": "t"}
        context: dict = {}
        features = await scorer._extract_features(message, context)
        assert features.agent_count == 0

    async def test_extract_features_active_agents_not_list(self):
        scorer = _make_scorer()
        message = {"content": "abc", "tenant_id": "t"}
        context: dict = {"active_agents": 5}
        features = await scorer._extract_features(message, context)
        assert features.agent_count == 0

    async def test_extract_features_missing_content(self):
        scorer = _make_scorer()
        message: dict = {}
        context: dict = {}
        features = await scorer._extract_features(message, context)
        assert features.message_length == 0

    async def test_extract_features_tuple_active_agents(self):
        scorer = _make_scorer()
        message = {"content": "x", "tenant_id": "t"}
        context: dict = {"active_agents": ("a", "b")}
        features = await scorer._extract_features(message, context)
        assert features.agent_count == 2


# ---------------------------------------------------------------------------
# _rule_based_risk_score
# ---------------------------------------------------------------------------


class TestRuleBasedRiskScore:
    def test_short_message_no_extra_risk(self):
        scorer = _make_scorer()
        f = _make_features(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(f)
        assert score == pytest.approx(0.0)

    def test_long_message_high_threshold_adds_0_3(self):
        scorer = _make_scorer()
        f = _make_features(
            message_length=15000,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(f)
        assert score == pytest.approx(0.3)

    def test_medium_message_low_threshold_adds_0_1(self):
        scorer = _make_scorer()
        f = _make_features(
            message_length=5000,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(f)
        assert score == pytest.approx(0.1)

    def test_high_agent_count_adds_0_2(self):
        scorer = _make_scorer()
        f = _make_features(
            message_length=0,
            agent_count=15,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(f)
        assert score == pytest.approx(0.2)

    def test_medium_agent_count_adds_0_1(self):
        scorer = _make_scorer()
        f = _make_features(
            message_length=0,
            agent_count=7,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(f)
        assert score == pytest.approx(0.1)

    def test_score_capped_at_1(self):
        scorer = _make_scorer()
        f = _make_features(
            message_length=20000,
            agent_count=20,
            tenant_complexity=1.0,
            resource_utilization=1.0,
            semantic_similarity=1.0,
        )
        score = scorer._rule_based_risk_score(f)
        assert score == pytest.approx(1.0)

    def test_combined_factors(self):
        scorer = _make_scorer()
        # length>10000 (+0.3) + agents>5 (+0.1) + complexity*0.2 + resource*0.3 + semantic*0.2
        f = _make_features(
            message_length=15000,
            agent_count=7,
            tenant_complexity=0.5,
            resource_utilization=0.5,
            semantic_similarity=0.5,
        )
        expected = min(1.0, 0.3 + 0.1 + 0.5 * 0.2 + 0.5 * 0.3 + 0.5 * 0.2)
        score = scorer._rule_based_risk_score(f)
        assert score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# _calculate_confidence
# ---------------------------------------------------------------------------


class TestCalculateConfidence:
    def test_base_confidence_no_extras(self):
        scorer = _make_scorer()
        f = _make_features(historical_precedence=0, temporal_patterns=[], semantic_similarity=0.0)
        c = scorer._calculate_confidence(f)
        assert c == pytest.approx(0.5)

    def test_historical_precedence_boosts_confidence(self):
        scorer = _make_scorer()
        f = _make_features(historical_precedence=1, temporal_patterns=[], semantic_similarity=0.0)
        c = scorer._calculate_confidence(f)
        assert c == pytest.approx(0.6)

    def test_temporal_patterns_boost_confidence(self):
        scorer = _make_scorer()
        f = _make_features(
            historical_precedence=0, temporal_patterns=[0.1], semantic_similarity=0.0
        )
        c = scorer._calculate_confidence(f)
        assert c == pytest.approx(0.6)

    def test_semantic_similarity_boosts_confidence(self):
        scorer = _make_scorer()
        f = _make_features(historical_precedence=0, temporal_patterns=[], semantic_similarity=0.5)
        c = scorer._calculate_confidence(f)
        assert c == pytest.approx(0.7)

    def test_all_factors_capped_at_1(self):
        scorer = _make_scorer()
        # 0.5 base + 0.1 (precedence>0) + 0.1 (temporal) + 0.2 (semantic>0) = 0.9
        # min(1.0, 0.9) = 0.9
        f = _make_features(
            historical_precedence=5, temporal_patterns=[0.1, 0.2], semantic_similarity=1.0
        )
        c = scorer._calculate_confidence(f)
        assert c == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# _predict_risk_score
# ---------------------------------------------------------------------------


class TestPredictRiskScore:
    def test_not_trained_falls_back_to_rule_based(self):
        scorer = _make_scorer()
        scorer.model_trained = False
        f = _make_features()
        score = scorer._predict_risk_score(f)
        # Should return rule-based score
        assert 0.0 <= score <= 1.0

    def test_no_classifier_falls_back(self):
        scorer = _make_scorer()
        scorer.model_trained = True
        scorer.impact_classifier = None
        f = _make_features()
        score = scorer._predict_risk_score(f)
        assert 0.0 <= score <= 1.0

    def test_numpy_not_available_falls_back(self):
        scorer = _make_scorer()
        scorer.model_trained = True
        scorer.impact_classifier = MagicMock()
        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        orig = _mod.NUMPY_AVAILABLE
        try:
            _mod.NUMPY_AVAILABLE = False
            f = _make_features()
            score = scorer._predict_risk_score(f)
            assert 0.0 <= score <= 1.0
        finally:
            _mod.NUMPY_AVAILABLE = orig

    def test_successful_prediction_clipped(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.return_value = [1.5]  # should be clipped to 1.0
        scorer.impact_classifier = mock_clf

        orig_np = _mod.np
        orig_avail = _mod.NUMPY_AVAILABLE
        try:
            _mod.np = np
            _mod.NUMPY_AVAILABLE = True
            f = _make_features(temporal_patterns=[0.1, 0.2])
            score = scorer._predict_risk_score(f)
            assert score == pytest.approx(1.0)
        finally:
            _mod.np = orig_np
            _mod.NUMPY_AVAILABLE = orig_avail

    def test_prediction_with_no_temporal_patterns(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.return_value = [0.55]
        scorer.impact_classifier = mock_clf

        orig_np = _mod.np
        orig_avail = _mod.NUMPY_AVAILABLE
        try:
            _mod.np = np
            _mod.NUMPY_AVAILABLE = True
            f = _make_features(temporal_patterns=[])
            score = scorer._predict_risk_score(f)
            assert score == pytest.approx(0.55)
        finally:
            _mod.np = orig_np
            _mod.NUMPY_AVAILABLE = orig_avail

    def test_prediction_error_falls_back_to_rule_based(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.side_effect = RuntimeError("predict failed")
        scorer.impact_classifier = mock_clf

        orig_np = _mod.np
        orig_avail = _mod.NUMPY_AVAILABLE
        try:
            _mod.np = np
            _mod.NUMPY_AVAILABLE = True
            f = _make_features()
            score = scorer._predict_risk_score(f)
            assert 0.0 <= score <= 1.0
        finally:
            _mod.np = orig_np
            _mod.NUMPY_AVAILABLE = orig_avail


# ---------------------------------------------------------------------------
# _apply_mhc_stability
# ---------------------------------------------------------------------------


class TestApplyMhcStability:
    def test_no_op_when_mhc_disabled(self):
        scorer = _make_scorer()
        scorer.use_mhc_stability = False
        original_weights = dict(scorer.feature_weights)
        scorer._apply_mhc_stability()
        assert scorer.feature_weights == original_weights

    def test_applies_softmax_when_torch_available(self):
        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer.use_mhc_stability = True

        mock_torch = MagicMock()
        tensor_mock = MagicMock()
        # Build a fake softmax output that maps to the weights dict keys
        weight_list = list(scorer.feature_weights.values())
        import math

        total = sum(math.exp(v) for v in weight_list)
        softmax_vals = [math.exp(v) / total for v in weight_list]
        w_normalized = MagicMock()
        # Make indexing return floats
        w_normalized.__getitem__ = MagicMock(side_effect=lambda i: softmax_vals[i])
        mock_torch.tensor.return_value = tensor_mock
        mock_torch.nn.functional.softmax.return_value = w_normalized

        orig_torch = _mod.torch
        orig_avail = _mod.TORCH_AVAILABLE
        try:
            _mod.torch = mock_torch
            _mod.TORCH_AVAILABLE = True
            scorer._apply_mhc_stability()
            # All weights should now be the softmax values
            for i, key in enumerate(scorer.feature_weights.keys()):
                assert scorer.feature_weights[key] == pytest.approx(softmax_vals[i])
        finally:
            _mod.torch = orig_torch
            _mod.TORCH_AVAILABLE = orig_avail

    def test_error_in_mhc_is_caught(self):
        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer.use_mhc_stability = True

        mock_torch = MagicMock()
        mock_torch.tensor.side_effect = RuntimeError("tensor error")

        orig_torch = _mod.torch
        try:
            _mod.torch = mock_torch
            scorer._apply_mhc_stability()  # Should not raise
        finally:
            _mod.torch = orig_torch


# ---------------------------------------------------------------------------
# update_model
# ---------------------------------------------------------------------------


class TestUpdateModel:
    def test_adds_training_sample(self):
        scorer = _make_scorer()
        f = _make_features()
        scorer.update_model(f, 0.8)
        assert len(scorer.training_samples) == 1

    def test_does_not_retrain_before_threshold(self):
        scorer = _make_scorer()
        retrain_calls = []

        def mock_retrain():
            retrain_calls.append(True)

        scorer._retrain_model = mock_retrain
        for _i in range(IMPACT_SCORER_CONFIG.min_training_samples - 1):
            scorer.update_model(_make_features(), 0.5)
        assert len(retrain_calls) == 0

    def test_retrains_at_threshold(self):
        scorer = _make_scorer()
        retrain_calls = []

        def mock_retrain():
            retrain_calls.append(True)

        scorer._retrain_model = mock_retrain
        scorer._apply_mhc_stability = MagicMock()
        trigger_count = IMPACT_SCORER_CONFIG.retrain_frequency
        for _i in range(trigger_count):
            scorer.update_model(_make_features(), 0.5)
        assert len(retrain_calls) == 1
        scorer._apply_mhc_stability.assert_called_once()

    def test_error_in_update_is_caught(self):
        scorer = _make_scorer()
        # Pass something that causes an error when appended to training_samples
        # by monkey-patching the list's append
        scorer.training_samples = MagicMock()
        scorer.training_samples.append.side_effect = RuntimeError("append failed")
        # Should not raise
        scorer.update_model(_make_features(), 0.5)


# ---------------------------------------------------------------------------
# _retrain_model
# ---------------------------------------------------------------------------


class TestRetrainModel:
    def test_no_op_when_numpy_not_available(self):
        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        orig = _mod.NUMPY_AVAILABLE
        try:
            _mod.NUMPY_AVAILABLE = False
            scorer._retrain_model()
            assert scorer.model_trained is False
        finally:
            _mod.NUMPY_AVAILABLE = orig

    def test_no_op_when_classifier_is_none(self):
        scorer = _make_scorer()
        scorer.impact_classifier = None
        scorer._retrain_model()
        assert scorer.model_trained is False

    def test_no_op_when_too_few_samples(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        # Provide classifier but no samples
        orig_np = _mod.np
        orig_avail = _mod.NUMPY_AVAILABLE
        try:
            _mod.np = np
            _mod.NUMPY_AVAILABLE = True
            scorer._retrain_model()
            assert scorer.model_trained is False
        finally:
            _mod.np = orig_np
            _mod.NUMPY_AVAILABLE = orig_avail

    def test_retrains_without_mlflow(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer._mlflow_initialized = False
        mock_clf = MagicMock()
        scorer.impact_classifier = mock_clf

        for _i in range(IMPACT_SCORER_CONFIG.min_training_samples):
            scorer.training_samples.append((_make_features(temporal_patterns=[0.1]), 0.5))

        orig_np = _mod.np
        orig_avail = _mod.NUMPY_AVAILABLE
        orig_mlflow_avail = _mod.MLFLOW_AVAILABLE
        try:
            _mod.np = np
            _mod.NUMPY_AVAILABLE = True
            _mod.MLFLOW_AVAILABLE = False
            scorer._retrain_model()
            assert scorer.model_trained is True
            mock_clf.fit.assert_called_once()
        finally:
            _mod.np = orig_np
            _mod.NUMPY_AVAILABLE = orig_avail
            _mod.MLFLOW_AVAILABLE = orig_mlflow_avail

    def test_retrains_with_mlflow(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer._mlflow_initialized = True
        mock_clf = MagicMock()
        scorer.impact_classifier = mock_clf

        for _i in range(IMPACT_SCORER_CONFIG.min_training_samples):
            scorer.training_samples.append((_make_features(temporal_patterns=[0.1]), 0.5))

        log_mock = MagicMock()
        scorer._log_training_run_to_mlflow = log_mock

        orig_np = _mod.np
        orig_avail = _mod.NUMPY_AVAILABLE
        orig_mlflow_avail = _mod.MLFLOW_AVAILABLE
        try:
            _mod.np = np
            _mod.NUMPY_AVAILABLE = True
            _mod.MLFLOW_AVAILABLE = True
            scorer._retrain_model()
            assert scorer.model_trained is True
            log_mock.assert_called_once()
        finally:
            _mod.np = orig_np
            _mod.NUMPY_AVAILABLE = orig_avail
            _mod.MLFLOW_AVAILABLE = orig_mlflow_avail

    def test_error_in_retrain_is_caught(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer._mlflow_initialized = False
        mock_clf = MagicMock()
        mock_clf.fit.side_effect = RuntimeError("fit failed")
        scorer.impact_classifier = mock_clf

        for _i in range(IMPACT_SCORER_CONFIG.min_training_samples):
            scorer.training_samples.append((_make_features(), 0.5))

        orig_np = _mod.np
        orig_avail = _mod.NUMPY_AVAILABLE
        orig_mlflow_avail = _mod.MLFLOW_AVAILABLE
        try:
            _mod.np = np
            _mod.NUMPY_AVAILABLE = True
            _mod.MLFLOW_AVAILABLE = False
            scorer._retrain_model()  # Should not raise
        finally:
            _mod.np = orig_np
            _mod.NUMPY_AVAILABLE = orig_avail
            _mod.MLFLOW_AVAILABLE = orig_mlflow_avail


# ---------------------------------------------------------------------------
# _log_training_run_to_mlflow
# ---------------------------------------------------------------------------


class TestLogTrainingRunToMlflow:
    def _build_scorer_with_mock_mlflow(self):
        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer = _make_scorer()
        scorer._mlflow_initialized = True
        scorer._mlflow_experiment_id = "exp-001"
        mock_clf = MagicMock()
        mock_clf.n_estimators = 50
        mock_clf.max_depth = 10
        mock_clf.random_state = 42
        mock_clf.predict.return_value = [0.5] * 50
        mock_clf.feature_importances_ = [0.125] * 8
        scorer.impact_classifier = mock_clf
        return scorer, _mod

    def test_logs_run_successfully(self):
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer, mod = self._build_scorer_with_mock_mlflow()

        orig_mlflow = mod.mlflow
        orig_np = mod.np
        orig_avail = mod.NUMPY_AVAILABLE
        try:
            mock_mlflow = MagicMock()
            mock_run = MagicMock()
            mock_run.info.run_id = "run-abc"
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=mock_run)
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)
            mod.mlflow = mock_mlflow
            mod.np = np
            mod.NUMPY_AVAILABLE = True

            samples = [(_make_features(), float(i) / 50) for i in range(50)]
            X = np.zeros((50, 8))
            y = np.array([float(i) / 50 for i in range(50)])
            scorer._log_training_run_to_mlflow(X, y, samples)

            assert scorer.model_version == "run-abc"
            mock_mlflow.log_params.assert_called_once()
            mock_mlflow.log_metrics.assert_called_once()
        finally:
            mod.mlflow = orig_mlflow
            mod.np = orig_np
            mod.NUMPY_AVAILABLE = orig_avail

    def test_logs_run_r2_zero_when_ss_tot_zero(self):
        """Branch: ss_tot == 0 -> r2_score = 0.0."""
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer, mod = self._build_scorer_with_mock_mlflow()
        scorer.impact_classifier.predict.return_value = [0.5] * 50

        orig_mlflow = mod.mlflow
        orig_np = mod.np
        orig_avail = mod.NUMPY_AVAILABLE
        try:
            mock_mlflow = MagicMock()
            mock_run = MagicMock()
            mock_run.info.run_id = "run-xyz"
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=mock_run)
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)
            mod.mlflow = mock_mlflow
            mod.np = np
            mod.NUMPY_AVAILABLE = True

            # All y values identical → ss_tot == 0
            samples = [(_make_features(), 0.5) for _ in range(50)]
            X = np.zeros((50, 8))
            y = np.full(50, 0.5)
            scorer._log_training_run_to_mlflow(X, y, samples)
            # Verify it completed without error
            assert scorer.model_version == "run-xyz"
        finally:
            mod.mlflow = orig_mlflow
            mod.np = orig_np
            mod.NUMPY_AVAILABLE = orig_avail

    def test_no_feature_importances_attr(self):
        """Branch: classifier has no feature_importances_ attribute."""
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer, mod = self._build_scorer_with_mock_mlflow()
        # Remove feature_importances_
        del scorer.impact_classifier.feature_importances_

        orig_mlflow = mod.mlflow
        orig_np = mod.np
        orig_avail = mod.NUMPY_AVAILABLE
        try:
            mock_mlflow = MagicMock()
            mock_run = MagicMock()
            mock_run.info.run_id = "run-no-fi"
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=mock_run)
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)
            mod.mlflow = mock_mlflow
            mod.np = np
            mod.NUMPY_AVAILABLE = True

            samples = [(_make_features(), 0.5) for _ in range(50)]
            X = np.zeros((50, 8))
            y = np.full(50, 0.5)
            scorer._log_training_run_to_mlflow(X, y, samples)
            mock_mlflow.log_metric.assert_not_called()
        finally:
            mod.mlflow = orig_mlflow
            mod.np = orig_np
            mod.NUMPY_AVAILABLE = orig_avail

    def test_error_falls_back_to_direct_fit(self):
        """RuntimeError during mlflow run causes fallback fit."""
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer, mod = self._build_scorer_with_mock_mlflow()

        orig_mlflow = mod.mlflow
        orig_np = mod.np
        orig_avail = mod.NUMPY_AVAILABLE
        try:
            mock_mlflow = MagicMock()
            mock_mlflow.start_run.side_effect = RuntimeError("mlflow unavailable")
            mod.mlflow = mock_mlflow
            mod.np = np
            mod.NUMPY_AVAILABLE = True

            samples = [(_make_features(), 0.5) for _ in range(50)]
            X = np.zeros((50, 8))
            y = np.full(50, 0.5)
            scorer._log_training_run_to_mlflow(X, y, samples)
            # Fallback fit should have been called
            scorer.impact_classifier.fit.assert_called_once_with(X, y)
        finally:
            mod.mlflow = orig_mlflow
            mod.np = orig_np
            mod.NUMPY_AVAILABLE = orig_avail

    def test_feature_importance_uses_fallback_name_beyond_known_list(self):
        """Branch: idx >= len(feature_names) -> uses f'feature_{idx}'."""
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer, mod = self._build_scorer_with_mock_mlflow()
        # 9 importances — 9th index is beyond the 8-name list
        scorer.impact_classifier.feature_importances_ = [0.1] * 9

        orig_mlflow = mod.mlflow
        orig_np = mod.np
        orig_avail = mod.NUMPY_AVAILABLE
        try:
            mock_mlflow = MagicMock()
            mock_run = MagicMock()
            mock_run.info.run_id = "run-fi"
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=mock_run)
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)
            mod.mlflow = mock_mlflow
            mod.np = np
            mod.NUMPY_AVAILABLE = True

            samples = [(_make_features(), 0.5) for _ in range(50)]
            X = np.zeros((50, 8))
            y = np.full(50, 0.5)
            scorer._log_training_run_to_mlflow(X, y, samples)

            # The 9th call (idx=8) should use "feature_8"
            calls = [str(c) for c in mock_mlflow.log_metric.call_args_list]
            assert any("feature_8" in c for c in calls)
        finally:
            mod.mlflow = orig_mlflow
            mod.np = orig_np
            mod.NUMPY_AVAILABLE = orig_avail

    def test_impact_distribution_buckets(self):
        """Cover all three impact bucket branches (high/medium/low)."""
        import numpy as np

        import enhanced_agent_bus.adaptive_governance.impact_scorer as _mod

        scorer, mod = self._build_scorer_with_mock_mlflow()
        scorer.impact_classifier.predict = MagicMock(return_value=[0.5] * 50)

        orig_mlflow = mod.mlflow
        orig_np = mod.np
        orig_avail = mod.NUMPY_AVAILABLE
        try:
            mock_mlflow = MagicMock()
            mock_run = MagicMock()
            mock_run.info.run_id = "run-dist"
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=mock_run)
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)
            mod.mlflow = mock_mlflow
            mod.np = np
            mod.NUMPY_AVAILABLE = True

            # Mix: 17 high (>=0.7), 17 medium (0.3-0.7), 16 low (<0.3)
            samples = (
                [(_make_features(), 0.8) for _ in range(17)]
                + [(_make_features(), 0.5) for _ in range(17)]
                + [(_make_features(), 0.1) for _ in range(16)]
            )
            X = np.zeros((50, 8))
            y = np.array([s[1] for s in samples])
            scorer._log_training_run_to_mlflow(X, y, samples)
            # Just verify no exception was raised and model_version set
            assert scorer.model_version == "run-dist"
        finally:
            mod.mlflow = orig_mlflow
            mod.np = orig_np
            mod.NUMPY_AVAILABLE = orig_avail


# ---------------------------------------------------------------------------
# Placeholder helper methods
# ---------------------------------------------------------------------------


class TestHelperMethods:
    async def test_calculate_tenant_complexity(self):
        scorer = _make_scorer()
        result = await scorer._calculate_tenant_complexity("t1", {})
        assert result == pytest.approx(0.5)

    async def test_analyze_temporal_patterns(self):
        scorer = _make_scorer()
        result = await scorer._analyze_temporal_patterns({"content": "x"}, {})
        assert result == [0.1, 0.2, 0.15]

    async def test_analyze_semantic_similarity(self):
        scorer = _make_scorer()
        result = await scorer._analyze_semantic_similarity("hello", {})
        assert result == pytest.approx(0.3)

    async def test_check_historical_precedence(self):
        scorer = _make_scorer()
        result = await scorer._check_historical_precedence({}, {})
        assert result == 1

    async def test_assess_resource_impact(self):
        scorer = _make_scorer()
        result = await scorer._assess_resource_impact({}, {})
        assert result == pytest.approx(0.2)

    async def test_measure_isolation_strength(self):
        scorer = _make_scorer()
        result = await scorer._measure_isolation_strength("t1", {})
        assert result == pytest.approx(0.9)
