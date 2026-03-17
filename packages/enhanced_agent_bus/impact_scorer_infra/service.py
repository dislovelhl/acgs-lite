"""
Impact Scoring Service for ACGS-2.

Constitutional Hash: cdd01ef066bc6cf2

Provides configurable impact scoring with support for:
- Basic semantic scoring (keyword-based)
- MiniCPM-enhanced semantic scoring (7-dimensional governance vectors)
- Statistical scoring
- Ensemble combination
"""

from dataclasses import dataclass

import numpy as np
from packages.enhanced_agent_bus.impact_scorer_infra.models import ScoringMethod, ScoringResult
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

from .algorithms.base import WeightedEnsemble
from .algorithms.semantic import SemanticScorer
from .algorithms.statistical import StatisticalScorer

logger = get_logger(__name__)
# Constitutional hash for governance validation

from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402

MINICPM_INIT_ERRORS = (AttributeError, OSError, RuntimeError, ValueError, TypeError)


@dataclass
class ImpactScoringConfig:
    """Configuration for impact scoring service."""

    enable_minicpm: bool = False
    minicpm_model_name: str = "MiniCPM4-0.5B"
    minicpm_fallback_to_keywords: bool = True
    minicpm_use_fp16: bool = True
    prefer_minicpm_semantic: bool = True  # Use MiniCPM over basic semantic when available


class ImpactScoringService:
    """
    Service for computing impact scores on agent messages.

    Supports multiple scoring algorithms:
    - Semantic: Basic keyword-based semantic analysis
    - MiniCPM Semantic: Advanced 7-dimensional governance scoring
    - Statistical: Statistical pattern analysis

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(self, config: ImpactScoringConfig | None = None):
        self.config = config or ImpactScoringConfig()
        self._minicpm_scorer: object | None = None
        self._minicpm_available = False

        # Initialize base scorers
        self.scorers = {
            ScoringMethod.SEMANTIC: SemanticScorer(),
            ScoringMethod.STATISTICAL: StatisticalScorer(),
        }

        # Optionally initialize MiniCPM scorer
        if self.config.enable_minicpm:
            self._initialize_minicpm_scorer()

        self.ensemble = WeightedEnsemble()
        self._profiling_data: JSONDict = {}

    def _initialize_minicpm_scorer(self) -> bool:
        """
        Initialize the MiniCPM semantic scorer.

        Returns:
            True if MiniCPM scorer initialized successfully.
        """
        try:
            from .algorithms.minicpm_semantic import (
                MiniCPMScorerConfig,
                MiniCPMSemanticScorer,
            )

            minicpm_config = MiniCPMScorerConfig(
                model_name=self.config.minicpm_model_name,
                fallback_to_keywords=self.config.minicpm_fallback_to_keywords,
                use_fp16=self.config.minicpm_use_fp16,
            )

            self._minicpm_scorer = MiniCPMSemanticScorer(minicpm_config)
            self._minicpm_available = True
            self.scorers[ScoringMethod.MINICPM_SEMANTIC] = self._minicpm_scorer

            logger.info(f"MiniCPM semantic scorer initialized: {self.config.minicpm_model_name}")
            return True

        except ImportError as e:
            logger.warning(f"MiniCPM scorer not available: {e}")
            self._minicpm_available = False
            return False
        except MINICPM_INIT_ERRORS as e:
            logger.error(f"Failed to initialize MiniCPM scorer: {e}")
            self._minicpm_available = False
            return False

    @property
    def minicpm_available(self) -> bool:
        """Check if MiniCPM scorer is available."""
        return self._minicpm_available

    def get_impact_score(self, context: JSONDict) -> ScoringResult:
        """
        Calculate impact score for the given context.

        If MiniCPM is enabled and available, uses the 7-dimensional governance
        scoring. Otherwise falls back to basic semantic + statistical scoring.

        Args:
            context: Message context to score.

        Returns:
            ScoringResult with aggregate score and impact vector.
        """
        results = []

        # Determine which semantic scorer to use
        if (
            self._minicpm_available
            and self.config.prefer_minicpm_semantic
            and ScoringMethod.MINICPM_SEMANTIC in self.scorers
        ):
            # Use MiniCPM semantic scorer (skip basic semantic)
            results.append(self.scorers[ScoringMethod.MINICPM_SEMANTIC].score(context))
        elif ScoringMethod.SEMANTIC in self.scorers:
            # Use basic semantic scorer
            results.append(self.scorers[ScoringMethod.SEMANTIC].score(context))

        # Always include statistical scorer
        if ScoringMethod.STATISTICAL in self.scorers:
            results.append(self.scorers[ScoringMethod.STATISTICAL].score(context))

        return self.ensemble.combine(results)

    def get_minicpm_score(self, context: JSONDict) -> ScoringResult | None:
        """
        Get impact score specifically from MiniCPM scorer.

        Returns:
            ScoringResult from MiniCPM scorer, or None if not available.
        """
        if not self._minicpm_available or self._minicpm_scorer is None:
            return None
        return self._minicpm_scorer.score(context)  # type: ignore[no-any-return]

    def get_governance_vector(self, context: JSONDict) -> dict[str, float] | None:
        """
        Get the 7-dimensional governance impact vector.

        Returns:
            Dict with safety, security, privacy, fairness, reliability,
            transparency, efficiency scores, or None if MiniCPM not available.
        """
        result = self.get_minicpm_score(context)
        if result is None:
            return None
        return result.vector.to_dict()

    def calculate_message_impact(self, message: JSONDict, context: JSONDict) -> float:
        merged_context = {**context}
        if isinstance(message, dict):
            for key in ("action", "details", "description", "content", "text"):
                if key in message:
                    merged_context[key] = message[key]
        res = self.get_impact_score(merged_context)
        return res.aggregate_score

    def calculate_impact_score(self, message: JSONDict, context: JSONDict | None = None) -> float:
        """Calculate impact score for a message (alias for calculate_message_impact).

        This method provides compatibility with code expecting calculate_impact_score API.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if context is None:
            context = {}
        # Merge message content into context for scoring
        merged_context = {**context}
        if isinstance(message, dict):
            merged_context["content"] = message.get("content", message)
        return self.calculate_message_impact(message, merged_context)

    async def calculate_impact_score_async(
        self, message: JSONDict, context: JSONDict | None = None
    ) -> float:
        return self.calculate_impact_score(message, context)

    def get_gpu_decision_matrix(self) -> JSONDict:
        """Get GPU optimization status."""
        return {
            "status": "optimized",
            "backend": "tensorrt",
            "minicpm_available": self._minicpm_available,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def get_profiling_report(self) -> JSONDict:
        """Get profiling data."""
        return {
            **self._profiling_data,
            "minicpm_enabled": self.config.enable_minicpm,
            "minicpm_available": self._minicpm_available,
            "scorers_active": [m.value for m in self.scorers.keys()],
        }

    def reset_profiling(self) -> None:
        """Reset profiling data."""
        self._profiling_data = {}

    def unload_minicpm(self) -> None:
        """Unload MiniCPM scorer to free resources."""
        if self._minicpm_scorer is not None:
            self._minicpm_scorer.unload()
            self._minicpm_scorer = None
            self._minicpm_available = False
            if ScoringMethod.MINICPM_SEMANTIC in self.scorers:
                del self.scorers[ScoringMethod.MINICPM_SEMANTIC]
            logger.info("MiniCPM scorer unloaded")


_impact_service: ImpactScoringService | None = None
_impact_service_config: ImpactScoringConfig | None = None


def configure_impact_scorer(
    enable_minicpm: bool = False,
    minicpm_model_name: str = "MiniCPM4-0.5B",
    minicpm_fallback_to_keywords: bool = True,
    prefer_minicpm_semantic: bool = True,
) -> ImpactScoringConfig:
    """
    Configure the impact scorer service.

    Call this before get_impact_scorer_service() to customize behavior.
    Must be called before first use or after reset_impact_scorer().

    Args:
        enable_minicpm: Enable MiniCPM-enhanced semantic scoring.
        minicpm_model_name: MiniCPM model to use.
        minicpm_fallback_to_keywords: Fall back to keywords when model unavailable.
        prefer_minicpm_semantic: Prefer MiniCPM over basic semantic.

    Returns:
        The configuration object.
    """
    global _impact_service_config
    _impact_service_config = ImpactScoringConfig(
        enable_minicpm=enable_minicpm,
        minicpm_model_name=minicpm_model_name,
        minicpm_fallback_to_keywords=minicpm_fallback_to_keywords,
        prefer_minicpm_semantic=prefer_minicpm_semantic,
    )
    return _impact_service_config


def get_impact_scorer_service(
    config: ImpactScoringConfig | None = None,
) -> ImpactScoringService:
    """
    Get the impact scorer service singleton.

    Args:
        config: Optional configuration. If provided and service doesn't exist,
                uses this config. Otherwise uses global config or defaults.

    Returns:
        The ImpactScoringService instance.
    """
    global _impact_service, _impact_service_config

    if _impact_service is None:
        effective_config = config or _impact_service_config
        _impact_service = ImpactScoringService(effective_config)

    return _impact_service


def get_impact_scorer() -> ImpactScoringService:
    """Get the impact scorer service (alias for get_impact_scorer_service)."""
    return get_impact_scorer_service()


def calculate_message_impact(message: JSONDict, context: JSONDict | None = None) -> float:
    return get_impact_scorer().calculate_message_impact(message, context or {})


def cosine_similarity_fallback(
    v1: list[float] | list[list[float]], v2: list[float] | list[list[float]]
) -> float:
    if isinstance(v1, list) and v1 and isinstance(v1[0], list):
        v1 = v1[0]
    if isinstance(v2, list) and v2 and isinstance(v2[0], list):
        v2 = v2[0]

    v1_arr = np.array(v1)
    v2_arr = np.array(v2)
    norm1 = np.linalg.norm(v1_arr)
    norm2 = np.linalg.norm(v2_arr)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1_arr, v2_arr) / (norm1 * norm2))


def get_gpu_decision_matrix() -> JSONDict:
    return get_impact_scorer().get_gpu_decision_matrix()


def get_profiling_report() -> JSONDict:
    return get_impact_scorer().get_profiling_report()


def reset_profiling() -> None:
    get_impact_scorer().reset_profiling()


def reset_impact_scorer() -> None:
    """Reset the impact scorer singleton for testing."""
    global _impact_service, _impact_service_config
    if _impact_service is not None:
        _impact_service.unload_minicpm()
    _impact_service = None
    _impact_service_config = None
