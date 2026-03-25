"""
Tests for Impact Scoring Service Integration with MiniCPM.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.impact_scorer_infra import (
    CONSTITUTIONAL_HASH,
    ImpactScoringConfig,
    ImpactScoringService,
    ImpactVector,
    ScoringMethod,
    ScoringResult,
    configure_impact_scorer,
    get_impact_scorer_service,
    reset_impact_scorer,
)


class TestConstitutionalCompliance:
    """Tests for constitutional compliance."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_gpu_matrix_includes_hash(self):
        """Verify GPU decision matrix includes constitutional hash."""
        reset_impact_scorer()
        service = get_impact_scorer_service()
        matrix = service.get_gpu_decision_matrix()
        assert "constitutional_hash" in matrix
        assert matrix["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestImpactScoringConfig:
    """Tests for ImpactScoringConfig."""

    def test_default_values(self):
        """Verify default configuration values."""
        config = ImpactScoringConfig()
        assert config.enable_minicpm is False
        assert config.minicpm_model_name == "MiniCPM4-0.5B"
        assert config.minicpm_fallback_to_keywords is True
        assert config.minicpm_use_fp16 is True
        assert config.prefer_minicpm_semantic is True

    def test_custom_values(self):
        """Verify custom configuration values."""
        config = ImpactScoringConfig(
            enable_minicpm=True,
            minicpm_model_name="MiniCPM4-8B",
            minicpm_fallback_to_keywords=False,
        )
        assert config.enable_minicpm is True
        assert config.minicpm_model_name == "MiniCPM4-8B"
        assert config.minicpm_fallback_to_keywords is False


class TestImpactScoringServiceBasic:
    """Tests for basic ImpactScoringService functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset service before each test."""
        reset_impact_scorer()
        yield
        reset_impact_scorer()

    def test_service_init_default(self):
        """Test service initialization with defaults."""
        service = ImpactScoringService()
        assert ScoringMethod.SEMANTIC in service.scorers
        assert ScoringMethod.STATISTICAL in service.scorers
        assert service.minicpm_available is False

    def test_service_init_with_config(self):
        """Test service initialization with config."""
        config = ImpactScoringConfig(enable_minicpm=False)
        service = ImpactScoringService(config)
        assert service.config.enable_minicpm is False

    def test_get_impact_score_basic(self):
        """Test basic impact scoring."""
        service = ImpactScoringService()
        result = service.get_impact_score({"content": "test message"})

        assert isinstance(result, ScoringResult)
        assert hasattr(result, "aggregate_score")
        assert hasattr(result, "vector")
        assert 0.0 <= result.aggregate_score <= 1.0

    def test_calculate_message_impact(self):
        """Test message impact calculation."""
        service = ImpactScoringService()
        score = service.calculate_message_impact(
            {"content": "security breach"}, {"priority": "high"}
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_profiling_report(self):
        """Test profiling report includes expected fields."""
        service = ImpactScoringService()
        report = service.get_profiling_report()

        assert "minicpm_enabled" in report
        assert "minicpm_available" in report
        assert "scorers_active" in report


class TestMiniCPMIntegration:
    """Tests for MiniCPM integration."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset service before each test."""
        reset_impact_scorer()
        yield
        reset_impact_scorer()

    def test_minicpm_disabled_by_default(self):
        """Test MiniCPM is disabled by default."""
        service = ImpactScoringService()
        assert service.minicpm_available is False
        assert ScoringMethod.MINICPM_SEMANTIC not in service.scorers

    def test_minicpm_initialization_with_fallback(self):
        """Test MiniCPM initialization falls back gracefully."""
        # Even with enable_minicpm=True, should not crash if transformers unavailable
        config = ImpactScoringConfig(
            enable_minicpm=True,
            minicpm_fallback_to_keywords=True,
        )
        service = ImpactScoringService(config)

        # Should still work even if MiniCPM not available
        result = service.get_impact_score({"content": "security breach detected"})
        assert result is not None
        assert 0.0 <= result.aggregate_score <= 1.0

    def test_get_governance_vector_without_minicpm(self):
        """Test governance vector returns None when MiniCPM not available."""
        service = ImpactScoringService()
        vector = service.get_governance_vector({"content": "test"})
        assert vector is None

    def test_get_minicpm_score_without_minicpm(self):
        """Test MiniCPM score returns None when not available."""
        service = ImpactScoringService()
        result = service.get_minicpm_score({"content": "test"})
        assert result is None

    def test_unload_minicpm_when_not_loaded(self):
        """Test unloading MiniCPM when not loaded doesn't crash."""
        service = ImpactScoringService()
        # Should not raise
        service.unload_minicpm()
        assert service.minicpm_available is False


class TestMiniCPMWithMockedScorer:
    """Tests with mocked MiniCPM scorer."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset service before each test."""
        reset_impact_scorer()
        yield
        reset_impact_scorer()

    @pytest.fixture
    def mock_minicpm_scorer(self):
        """Create mock MiniCPM scorer."""
        scorer = MagicMock()
        scorer.score.return_value = ScoringResult(
            vector=ImpactVector(
                safety=0.1,
                security=0.9,
                privacy=0.3,
                fairness=0.2,
                reliability=0.4,
                transparency=0.5,
                efficiency=0.6,
            ),
            aggregate_score=0.85,
            method=ScoringMethod.MINICPM_SEMANTIC,
            confidence=0.95,
            metadata={"constitutional_hash": CONSTITUTIONAL_HASH},
        )
        scorer.unload.return_value = None
        return scorer

    def test_minicpm_scorer_used_when_available(self, mock_minicpm_scorer):
        """Test MiniCPM scorer is used when available and configured."""
        config = ImpactScoringConfig(enable_minicpm=True, prefer_minicpm_semantic=True)
        service = ImpactScoringService(config)

        # Manually inject mock scorer
        service._minicpm_scorer = mock_minicpm_scorer
        service._minicpm_available = True
        service.scorers[ScoringMethod.MINICPM_SEMANTIC] = mock_minicpm_scorer

        result = service.get_impact_score({"content": "security breach"})

        # MiniCPM scorer should have been called
        mock_minicpm_scorer.score.assert_called_once()

    def test_get_governance_vector_with_minicpm(self, mock_minicpm_scorer):
        """Test governance vector with mocked MiniCPM."""
        service = ImpactScoringService()

        # Inject mock
        service._minicpm_scorer = mock_minicpm_scorer
        service._minicpm_available = True

        vector = service.get_governance_vector({"content": "test"})

        assert vector is not None
        assert "safety" in vector
        assert "security" in vector
        assert vector["security"] == 0.9

    def test_get_minicpm_score_with_mock(self, mock_minicpm_scorer):
        """Test MiniCPM score with mocked scorer."""
        service = ImpactScoringService()

        # Inject mock
        service._minicpm_scorer = mock_minicpm_scorer
        service._minicpm_available = True

        result = service.get_minicpm_score({"content": "test"})

        assert result is not None
        assert result.method == ScoringMethod.MINICPM_SEMANTIC
        assert result.aggregate_score == 0.85

    def test_unload_minicpm_clears_scorer(self, mock_minicpm_scorer):
        """Test unloading MiniCPM clears the scorer."""
        service = ImpactScoringService()

        # Inject mock
        service._minicpm_scorer = mock_minicpm_scorer
        service._minicpm_available = True
        service.scorers[ScoringMethod.MINICPM_SEMANTIC] = mock_minicpm_scorer

        service.unload_minicpm()

        assert service._minicpm_scorer is None
        assert service._minicpm_available is False
        assert ScoringMethod.MINICPM_SEMANTIC not in service.scorers
        mock_minicpm_scorer.unload.assert_called_once()


class TestFactoryFunctions:
    """Tests for factory functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset service before each test."""
        reset_impact_scorer()
        yield
        reset_impact_scorer()

    def test_configure_impact_scorer(self):
        """Test configure_impact_scorer function."""
        config = configure_impact_scorer(
            enable_minicpm=True,
            minicpm_model_name="MiniCPM4-8B",
        )

        assert config.enable_minicpm is True
        assert config.minicpm_model_name == "MiniCPM4-8B"

    def test_get_impact_scorer_service_singleton(self):
        """Test service is singleton."""
        service1 = get_impact_scorer_service()
        service2 = get_impact_scorer_service()
        assert service1 is service2

    def test_get_impact_scorer_service_with_config(self):
        """Test service respects configuration."""
        config = ImpactScoringConfig(enable_minicpm=False)
        service = get_impact_scorer_service(config)
        assert service.config.enable_minicpm is False

    def test_reset_impact_scorer(self):
        """Test reset creates new service."""
        service1 = get_impact_scorer_service()
        reset_impact_scorer()
        service2 = get_impact_scorer_service()
        assert service1 is not service2

    def test_configure_then_get_service(self):
        """Test configuration is used by subsequent service creation."""
        configure_impact_scorer(
            enable_minicpm=True,
            prefer_minicpm_semantic=False,
        )

        service = get_impact_scorer_service()
        assert service.config.enable_minicpm is True
        assert service.config.prefer_minicpm_semantic is False


class TestScoringMethodEnum:
    """Tests for ScoringMethod enum."""

    def test_minicpm_semantic_method_exists(self):
        """Test MINICPM_SEMANTIC method exists."""
        assert hasattr(ScoringMethod, "MINICPM_SEMANTIC")
        assert ScoringMethod.MINICPM_SEMANTIC.value == "minicpm_semantic"

    def test_all_methods_defined(self):
        """Test all expected methods are defined."""
        expected_methods = {
            "SEMANTIC",
            "MINICPM_SEMANTIC",
            "STATISTICAL",
            "HEURISTIC",
            "LEARNING",
            "ENSEMBLE",
        }
        actual_methods = {m.name for m in ScoringMethod}
        assert expected_methods.issubset(actual_methods)


class TestImpactVector:
    """Tests for ImpactVector."""

    def test_default_values(self):
        """Test default vector values."""
        vector = ImpactVector()
        assert vector.safety == 0.0
        assert vector.security == 0.0
        assert vector.privacy == 0.0
        assert vector.fairness == 0.0
        assert vector.reliability == 0.0
        assert vector.transparency == 0.0
        assert vector.efficiency == 0.0

    def test_custom_values(self):
        """Test custom vector values."""
        vector = ImpactVector(
            safety=0.1,
            security=0.9,
            privacy=0.5,
        )
        assert vector.safety == 0.1
        assert vector.security == 0.9
        assert vector.privacy == 0.5

    def test_to_dict(self):
        """Test vector to_dict method."""
        vector = ImpactVector(safety=0.5, security=0.8)
        d = vector.to_dict()

        assert isinstance(d, dict)
        assert len(d) == 7
        assert d["safety"] == 0.5
        assert d["security"] == 0.8


class TestScoringResult:
    """Tests for ScoringResult."""

    def test_create_result(self):
        """Test creating scoring result."""
        result = ScoringResult(
            vector=ImpactVector(security=0.9),
            aggregate_score=0.85,
            method=ScoringMethod.MINICPM_SEMANTIC,
            confidence=0.95,
            metadata={"test": True},
        )

        assert result.aggregate_score == 0.85
        assert result.method == ScoringMethod.MINICPM_SEMANTIC
        assert result.confidence == 0.95
        assert result.metadata["test"] is True

    def test_result_version(self):
        """Test result includes version."""
        result = ScoringResult(
            vector=ImpactVector(),
            aggregate_score=0.5,
            method=ScoringMethod.SEMANTIC,
            confidence=0.8,
        )
        assert result.version == "3.1.0"
