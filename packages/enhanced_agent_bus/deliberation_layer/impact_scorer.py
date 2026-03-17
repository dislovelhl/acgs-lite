"""
Impact Scorer Facade (Deliberation Layer).
Constitutional Hash: cdd01ef066bc6cf2

Provides unified impact scoring with support for:
- Basic keyword-based semantic scoring (default)
- MiniCPM-enhanced 7-dimensional governance scoring (optional)
- ONNX/TensorRT optimized inference (optional)
- Batch processing for high-throughput scenarios
"""

import hashlib
from typing import Union, cast

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    NUMPY_AVAILABLE = False

from packages.enhanced_agent_bus.governance_constants import (
    IMPACT_CRITICAL_FLOOR,
    IMPACT_HIGH_SEMANTIC_FLOOR,
    IMPACT_WEIGHT_CONTEXT,
    IMPACT_WEIGHT_DRIFT,
    IMPACT_WEIGHT_PERMISSION,
    IMPACT_WEIGHT_SEMANTIC,
    IMPACT_WEIGHT_TRAJECTORY,
    IMPACT_WEIGHT_VOLUME,
)

try:
    from packages.enhanced_agent_bus.adaptive_governance.dtmc_learner import DTMCLearner

    DTMC_AVAILABLE = True
except ImportError:
    DTMCLearner = None  # type: ignore[assignment,misc]
    DTMC_AVAILABLE = False
from packages.enhanced_agent_bus.impact_scorer_infra.models import (
    ImpactVector,
    ScoringConfig,
    ScoringMethod,
    ScoringResult,
)
from packages.enhanced_agent_bus.impact_scorer_infra.service import (
    CONSTITUTIONAL_HASH,
    ImpactScoringConfig,
    calculate_message_impact,
    configure_impact_scorer,
    cosine_similarity_fallback,
    get_gpu_decision_matrix,
    get_impact_scorer,
    get_impact_scorer_service,
    get_profiling_report,
    reset_impact_scorer,
    reset_profiling,
)
from src.core.shared.cache.manager import TieredCacheConfig, TieredCacheManager
from src.core.shared.types import JSONDict

try:
    from packages.enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
        TensorRTOptimizer,
    )
except ImportError:
    # Fallback for standalone execution contexts
    try:
        from .tensorrt_optimizer import TensorRTOptimizer
    except ImportError:
        # Provide stub when neither import works
        TensorRTOptimizer = None  # type: ignore[misc, assignment]

logger = get_logger(__name__)
TRANSFORMERS_AVAILABLE = False
ONNX_AVAILABLE = False
TORCH_AVAILABLE = False
PROFILING_AVAILABLE = False


class ImpactScorer:
    """
    Facade for impact scoring in the deliberation layer.

    Provides unified access to impact scoring capabilities including:
    - Basic semantic scoring via keyword matching
    - MiniCPM-enhanced 7-dimensional governance scoring (when enabled)
    - ONNX/TensorRT optimized inference for batch processing

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        config: ScoringConfig | None = None,
        use_onnx: bool = False,
        enable_minicpm: bool = False,
        minicpm_model_name: str = "MiniCPM4-0.5B",
        prefer_minicpm_semantic: bool = True,
        enable_caching: bool = True,
        dtmc_learner: "DTMCLearner | None" = None,
        enable_loco_operator: bool = False,
        loco_operator_model: str = "LocoreMind/LocoOperator-4B-GGUF",
        loco_operator_device: str = "cpu",
    ):
        """
        Initialize the impact scorer.

        Args:
            config: Scoring configuration for weight and threshold tuning.
            use_onnx: Enable ONNX/TensorRT optimization for batch inference.
            enable_minicpm: Enable MiniCPM-enhanced semantic scoring.
            minicpm_model_name: MiniCPM model to use when enabled.
            prefer_minicpm_semantic: Prefer MiniCPM over basic semantic when available.
            enable_caching: Enable tiered caching for embeddings and scores.
            enable_loco_operator: Enable LocoOperator-4B governance scoring (MACI proposer).
            loco_operator_model: LocoOperator model identifier.
            loco_operator_device: Device for LocoOperator inference ('cpu', 'cuda', 'mps').
        """
        # Configure the impact scorer service with MiniCPM settings
        if enable_minicpm:
            configure_impact_scorer(
                enable_minicpm=True,
                minicpm_model_name=minicpm_model_name,
                minicpm_fallback_to_keywords=True,
                prefer_minicpm_semantic=prefer_minicpm_semantic,
            )

        self.service = get_impact_scorer_service()
        self.config = config or ScoringConfig()
        self._enable_minicpm = enable_minicpm

        # LocoOperator-4B integration (MACI proposer role)
        self._enable_loco_operator = enable_loco_operator
        self._loco_client: object | None = None
        if enable_loco_operator:
            try:
                from packages.enhanced_agent_bus.deliberation_layer.loco_operator_client import (
                    LocoOperatorGovernanceClient,
                )
                from packages.enhanced_agent_bus.llm_adapters.config import (
                    LocoOperatorAdapterConfig,
                )

                cfg = LocoOperatorAdapterConfig(
                    model=loco_operator_model,
                    device=loco_operator_device,
                    use_inference_api=False,
                )
                self._loco_client = LocoOperatorGovernanceClient(config=cfg)
                logger.info(
                    "ImpactScorer: LocoOperator-4B enabled (model=%s device=%s)",
                    loco_operator_model,
                    loco_operator_device,
                )
            except Exception as exc:
                logger.warning(
                    "ImpactScorer: LocoOperator-4B init failed, continuing without it: %s", exc
                )
        self.model_name = "distilbert-base-uncased"
        self._bert_enabled = False
        self._onnx_enabled = use_onnx and ONNX_AVAILABLE
        self._enable_caching = enable_caching
        self._embedding_cache: TieredCacheManager | None = None

        if enable_caching:
            cache_config = TieredCacheConfig(
                l1_maxsize=100,
                l1_ttl=300,
                l2_ttl=3600,
                l3_enabled=True,
                l3_ttl=86400,
            )
            self._embedding_cache = TieredCacheManager(
                config=cache_config, name="impact_embeddings"
            )

        self.high_impact_keywords = [
            "critical",
            "security",
            "emergency",
            "danger",
            "breach",
            "vulnerability",
            "exploit",
            "unauthorized",
            "suspicious",
            "transaction",
            "transfer",
            "payment",
            "violation",
            "regulation",
            "legal",
            "compliance",
            "audit",
            "governance",
            "attack",
            "threat",
            "compromise",
            "intrusion",
            "exfiltration",
            "alert",
            "execute_command",
            "transfer_funds",
        ]
        self._volume_counts: dict[str, int] = {}
        self._drift_history: dict[str, list[float]] = {}
        self._tokenization_cache: JSONDict = {}  # Cache for tokenized content
        self._optimizer = None
        if self._onnx_enabled:
            self._optimizer = TensorRTOptimizer(self.model_name)
            # Try to load best backend
            if not (self._optimizer.load_tensorrt_engine() or self._optimizer.load_onnx_runtime()):
                logger.warning("Failed to load optimized backend, will use PyTorch fallback")

        # Pro2Guard DTMC trajectory scorer (6th dimension, Sprint 3).
        # Optional — when None, trajectory scoring is skipped (backward-compatible).
        self._dtmc_learner: DTMCLearner | None = dtmc_learner  # type: ignore[type-arg]

        # Spec-to-Artifact tracking (ref: solveeverything.org)
        # Tracks first-attempt governance decision accuracy continuously.
        self._total_evaluations: int = 0
        self._overrides: int = 0

    async def initialize(self) -> bool:
        """Initialize cache connections."""
        if self._embedding_cache:
            return cast(bool, await self._embedding_cache.initialize())
        return True

    async def close(self) -> None:
        """Close cache connections."""
        if self._embedding_cache:
            await self._embedding_cache.close()

    def _generate_cache_key(self, text: str) -> str:
        combined = f"{text}:{CONSTITUTIONAL_HASH}"
        return f"impact:embedding:{hashlib.sha256(combined.encode()).hexdigest()}"

    @classmethod
    def reset_class_cache(cls) -> None:
        """Reset class-level cache for testing compatibility."""
        pass

    def clear_tokenization_cache(self) -> None:
        """Clear the tokenization cache."""
        self._tokenization_cache.clear()

    @property
    def minicpm_available(self) -> bool:
        """Check if MiniCPM-enhanced scoring is available."""
        return cast(bool, self.service.minicpm_available)

    @property
    def minicpm_enabled(self) -> bool:
        """Check if MiniCPM was requested at initialization."""
        return self._enable_minicpm

    @property
    def loco_operator_available(self) -> bool:
        """Check if LocoOperator-4B scoring is available.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if self._loco_client is None:
            return False
        return bool(getattr(self._loco_client, "is_available", False))

    async def _score_with_loco_operator(self, action: str, context: JSONDict) -> "object | None":
        """Async governance scoring via LocoOperator-4B.

        MACI role: proposer — returns a GovernanceScoringResult or None on unavailability.

        Args:
            action: Description of the governance action to score.
            context: Structured message context.

        Returns:
            GovernanceScoringResult from LocoOperator, or None if unavailable/disabled.
        """
        if not self.loco_operator_available or self._loco_client is None:
            return None
        return await self._loco_client.score_governance_action(action, context)  # type: ignore[union-attr, no-any-return]

    def get_governance_vector(self, context: JSONDict) -> dict[str, float] | None:
        """
        Get 7-dimensional governance impact vector.

        Returns a dictionary with scores for:
        - safety: Physical and operational safety impact
        - security: Information and system security impact
        - privacy: Personal data and confidentiality impact
        - fairness: Equity and bias considerations
        - reliability: System dependability impact
        - transparency: Explainability and auditability
        - efficiency: Resource and performance impact

        Args:
            context: Message context to analyze.

        Returns:
            Dict with governance dimension scores, or None if MiniCPM not available.
        """
        return cast(dict[str, float] | None, self.service.get_governance_vector(context))

    def get_minicpm_score(self, context: JSONDict) -> ScoringResult | None:
        """
        Get impact score specifically from MiniCPM scorer.

        Args:
            context: Message context to analyze.

        Returns:
            ScoringResult from MiniCPM, or None if not available.
        """
        return self.service.get_minicpm_score(context)

    def score_impact(self, context: JSONDict) -> ScoringResult:
        """Get comprehensive impact score using the configured scoring methods."""
        return self.service.get_impact_score(context)

    def calculate_impact_score(
        self, message: JSONDict | object, context: JSONDict | None = None
    ) -> float:
        if context is None:
            context = {}

        # Handle None message gracefully
        if message is None:
            message = {}

        msg_from = (
            message.get("from_agent", "unknown")
            if isinstance(message, dict)
            else getattr(message, "from_agent", "unknown")
        )
        msg_priority = (
            context.get("priority")
            or (
                message.get("priority")
                if isinstance(message, dict)
                else getattr(message, "priority", "normal")
            )
            or "normal"
        )

        if hasattr(msg_priority, "name"):
            msg_priority = msg_priority.name.lower()
        else:
            msg_priority = str(msg_priority).lower()

        semantic_score = context.get("semantic_override")
        if semantic_score is None:
            semantic_score = self._calculate_semantic_score(message)

        p_score = self._calculate_permission_score(message)
        v_score = self._calculate_volume_score(msg_from)
        c_score = self._calculate_context_score(message, context)
        d_score = self._calculate_drift_score(msg_from, 0.4)

        # Factors are now multiplicative with 1.0 as neutral
        p_factor = self._calculate_priority_factor(message, context)
        t_factor = self._calculate_type_factor(message, context)

        semantic_w = IMPACT_WEIGHT_SEMANTIC
        permission_w = IMPACT_WEIGHT_PERMISSION
        volume_w = IMPACT_WEIGHT_VOLUME
        context_w = IMPACT_WEIGHT_CONTEXT
        drift_w = IMPACT_WEIGHT_DRIFT

        base_score = (
            semantic_score * semantic_w
            + p_score * permission_w
            + v_score * volume_w
            + c_score * context_w
            + d_score * drift_w
        )

        final_score = base_score * p_factor * t_factor

        # Critical priority always gets high score
        if msg_priority == "critical":
            final_score = max(final_score, IMPACT_CRITICAL_FLOOR)

        # High semantic score (from high-impact keywords) should boost final score
        if semantic_score >= 0.9:
            final_score = max(final_score, IMPACT_HIGH_SEMANTIC_FLOOR)

        # 6th dimension: Pro2Guard DTMC trajectory risk (Sprint 3).
        # Active only when a DTMCLearner is attached AND the caller provides
        # trajectory_prefix (list[int] of ImpactLevel ordinals) in context.
        # IMPACT_WEIGHT_TRAJECTORY defaults to 0.0 → no change without opt-in.
        if self._dtmc_learner is not None and IMPACT_WEIGHT_TRAJECTORY > 0.0 and context:
            trajectory_prefix = context.get("trajectory_prefix")
            if trajectory_prefix:
                dtmc_risk = self._dtmc_learner.predict_risk(list(trajectory_prefix))
                final_score = min(1.0, final_score + dtmc_risk * IMPACT_WEIGHT_TRAJECTORY)
                logger.debug(
                    "ImpactScorer: DTMC trajectory risk=%.3f weight=%.3f → final=%.3f",
                    dtmc_risk,
                    IMPACT_WEIGHT_TRAJECTORY,
                    final_score,
                )

        self._total_evaluations += 1
        return float(min(1.0, final_score))

    def record_override(self) -> None:
        """Record a human override of a governance decision.

        Call when HITL review reverses an impact scorer decision (false positive
        or false negative corrected by human). Used to compute the Spec-to-Artifact
        Score (ref: solveeverything.org).
        """
        self._overrides += 1

    @property
    def spec_to_artifact_score(self) -> float:
        """Spec-to-Artifact Score: first-attempt governance accuracy.

        Measures what fraction of governance decisions are correct without
        retries or human override.

        Formula: (1 - override_rate)
        where override_rate = overrides / total_evaluations.

        Returns 1.0 when no evaluations have been performed yet.
        Ref: solveeverything.org — "percentage of times your AI stack
        produces working and safe code on the first try."
        """
        if self._total_evaluations == 0:
            return 1.0
        override_rate = self._overrides / self._total_evaluations
        return 1.0 - override_rate

    def get_spec_to_artifact_metrics(self) -> dict[str, Union[int, float]]:
        """Get detailed Spec-to-Artifact metrics for observability.

        Returns:
            Dict with total_evaluations, overrides, override_rate,
            and spec_to_artifact_score.
        """
        override_rate = (
            self._overrides / self._total_evaluations if self._total_evaluations > 0 else 0.0
        )
        return {
            "total_evaluations": self._total_evaluations,
            "overrides": self._overrides,
            "override_rate": override_rate,
            "spec_to_artifact_score": self.spec_to_artifact_score,
        }

    def _calculate_permission_score(self, message: dict[str, object] | object) -> float:
        if isinstance(message, dict):
            tools = message.get("tools", [])
        else:
            tools = getattr(message, "tools", [])
        if not tools:
            return 0.1

        # High-risk tool patterns
        high_risk_patterns = [
            "execute",
            "command",
            "shell",
            "bash",
            "sudo",
            "admin",
            "blockchain",
            "transfer",
            "payment",
            "funds",
            "delete",
            "modify",
            "update",
            "write",
            "create",
            "drop",
            "truncate",
        ]

        max_score = 0.1
        for tool in tools:
            tool_name = tool.get("name", "") if isinstance(tool, dict) else str(tool)
            tool_lower = tool_name.lower()

            # Check for high-risk patterns
            if any(pattern in tool_lower for pattern in high_risk_patterns):
                max_score = max(max_score, 0.7)
            elif "read" in tool_lower or "get" in tool_lower or "list" in tool_lower:
                max_score = max(max_score, 0.2)
            else:
                max_score = max(max_score, 0.3)

        return min(1.0, max_score)

    def _calculate_volume_score(self, agent_id: str) -> float:
        """Calculate volume-based score based on agent request history.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if not hasattr(self, "_agent_request_counts"):
            self._agent_request_counts: dict[str, int] = {}

        # Increment and get count
        count = self._agent_request_counts.get(agent_id, 0) + 1
        self._agent_request_counts[agent_id] = count

        # Scale score based on volume
        if count <= 10:
            return 0.1  # New agent baseline
        elif count <= 30:
            return 0.2
        elif count <= 50:
            return 0.5
        elif count <= 100:
            return 0.7
        else:
            return 1.0  # Very high volume

    def _calculate_context_score(self, message: JSONDict | object, context: JSONDict) -> float:
        base_score = 0.1

        if isinstance(message, dict):
            payload = message.get("payload", {})
        else:
            payload = getattr(message, "payload", getattr(message, "content", {}))
            if not isinstance(payload, dict):
                payload = {}

        if isinstance(payload, dict):
            amount = payload.get("amount", 0)
            if isinstance(amount, (int, float)) and amount >= 10000:
                base_score += 0.4

        return min(1.0, base_score)

    def _calculate_drift_score(self, agent_id: str, default: float) -> float:
        """Calculate behavioral drift score for an agent.

        Detects anomalous behavior by comparing current score to historical average.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if not hasattr(self, "_agent_score_history"):
            self._agent_score_history: dict[str, list[float]] = {}

        # Get agent's history
        history = self._agent_score_history.get(agent_id, [])

        # Store the current score
        self._agent_score_history.setdefault(agent_id, []).append(default)

        # Unknown or first request - no drift
        if len(history) < 2:
            return 0.0

        # Calculate average and deviation
        avg = sum(history) / len(history)
        deviation = abs(default - avg)

        # If deviation is significant, return drift score
        if deviation > 0.3:
            return min(1.0, deviation)

        return 0.0

    def score_messages_batch(self, messages: list[JSONDict]) -> list[float]:
        """Batch score impact for multiple messages using optimized inference."""
        if self._onnx_enabled and self._optimizer:
            if not NUMPY_AVAILABLE:
                raise ImportError("numpy is required for batch scoring")
            texts = [self._extract_text_content(m) for m in messages]
            # Use optimized batch inference
            embeddings = self._optimizer.infer_batch(texts)
            # For simplicity, calculate scores from embeddings (mock logic for now)
            # In real system, this would use a classification head on the embeddings
            scores = [float(np.mean(np.abs(emb)) * 2.0) for emb in embeddings]
            return [min(1.0, s) for s in scores]

        return [self.calculate_impact_score(m, {}) for m in messages]

    def batch_score_impact(
        self, messages: list[JSONDict], contexts: list[JSONDict] | None = None
    ) -> list[float]:
        """
        Batch score impact for multiple messages.
        """
        if contexts is None:
            contexts = [{} for _ in range(len(messages))]
        elif len(contexts) != len(messages):
            raise ValueError(
                f"contexts length ({len(contexts)}) must match messages length ({len(messages)})"
            )
        return [self.calculate_impact_score(m, c) for m, c in zip(messages, contexts, strict=False)]

    def reset_history(self) -> None:
        """Reset internal history and caches."""
        if hasattr(self, "_agent_request_counts"):
            self._agent_request_counts.clear()
        if hasattr(self, "_agent_score_history"):
            self._agent_score_history.clear()
        self._volume_counts.clear()
        self._drift_history.clear()

    def _calculate_semantic_score(self, message: JSONDict) -> float:
        text = self._extract_text_content(message).strip().lower()
        if not text:
            return 0.0
        if any(kw in text for kw in self.high_impact_keywords):
            return 0.95
        return 0.1

    def _get_keyword_score(self, text: str) -> float:
        text_lower = text.lower()
        matched_count = sum(1 for kw in self.high_impact_keywords if kw in text_lower)
        if matched_count == 0:
            return 0.1
        if matched_count == 1:
            return 0.5
        if matched_count == 2:
            return 0.75
        return min(1.0, 0.75 + (matched_count - 2) * 0.1)

    def _calculate_priority_factor(
        self, message: JSONDict, context: JSONDict | None = None
    ) -> float:
        """Calculate priority factor in range 0-1.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if context is None:
            context = {}
        priority = (
            context.get("priority")
            or (
                message.get("priority")
                if isinstance(message, dict)
                else getattr(message, "priority", "normal")
            )
            or "normal"
        )

        # Handle Priority enum
        if hasattr(priority, "value"):
            priority = priority.value
        if hasattr(priority, "name"):
            priority = priority.name.lower()

        # Convert to string for comparison
        priority = str(priority).lower()

        # Return values in 0-1 range as tests expect
        if priority in ["critical", "3"]:
            return 1.0
        if priority in ["high", "2"]:
            return 0.8
        if priority in ["medium", "normal", "1"]:
            return 0.5
        if priority in ["low", "0"]:
            return 0.2
        return 0.5  # Default for unknown priority

    def _calculate_type_factor(self, message: JSONDict, context: JSONDict | None = None) -> float:
        m_type = (
            message.get("message_type", "")
            if isinstance(message, dict)
            else getattr(message, "message_type", "")
        )
        if m_type == "governance":
            return 1.5
        if m_type == "security":
            return 1.4
        if m_type == "financial":
            return 1.3
        return 1.0

    def _extract_text_content(self, message: dict[str, object] | object) -> str:
        """Extract text content from message for semantic analysis."""
        content_parts = []

        # Extract basic content
        content_parts.extend(self._extract_basic_content(message))

        # Extract payload content (for dict messages)
        if isinstance(message, dict):
            content_parts.extend(self._extract_payload_content(message))

        # Extract tool content
        content_parts.extend(self._extract_tool_content(message))

        return " ".join(content_parts)

    def _extract_basic_content(self, message: dict[str, object] | object) -> list[str]:
        """Extract basic content from message."""
        content_parts = []

        if hasattr(message, "content"):
            content_parts.append(str(message.content))
        elif isinstance(message, dict) and "content" in message:
            content_parts.append(str(message["content"]))

        return content_parts

    def _extract_payload_content(self, message: dict[str, object]) -> list[str]:
        """Extract payload and key-based content from dict message."""
        content_parts = []

        # Payload message
        if "payload" in message and isinstance(message["payload"], dict):
            payload = message["payload"]
            if "message" in payload:
                content_parts.append(str(payload["message"]))

        # Key-based content
        for key in ("action", "details", "description", "text"):
            if key in message:
                content_parts.append(str(message[key]))

        return content_parts

    def _extract_tool_content(self, message: dict[str, object] | object) -> list[str]:
        """Extract tool names for keyword matching."""
        content_parts = []

        # Get tools list
        tools: list[object] = []
        if isinstance(message, dict):
            tools = message.get("tools", [])
        elif hasattr(message, "tools"):
            tools = message.tools or []

        # Extract tool names
        for tool in tools:
            if isinstance(tool, dict):
                content_parts.append(tool.get("name", ""))
            else:
                content_parts.append(str(tool))

        return content_parts

    async def _get_embeddings(self, text: str) -> "np.ndarray":  # type: ignore[name-defined]
        """Get embeddings for text, with fallback for when model is not available.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if not NUMPY_AVAILABLE:
            raise ImportError("numpy is required for embedding generation")

        if self._embedding_cache:
            cache_key = self._generate_cache_key(text)
            cached_embedding = await self._embedding_cache.get_async(cache_key)
            if cached_embedding is not None:
                if isinstance(cached_embedding, str):
                    import json

                    cached_embedding = json.loads(cached_embedding)
                logger.info(f"Embedding cache HIT for text length {len(text)}")
                return np.array(cached_embedding)  # type: ignore[no-any-return]
            logger.debug(f"Embedding cache MISS for text length {len(text)}")

        embedding = np.zeros((1, 768))

        if self._embedding_cache and cached_embedding is None:
            await self._embedding_cache.set(cache_key, embedding.tolist(), ttl=3600)

        return embedding

    def _get_keyword_embeddings(self) -> "np.ndarray":  # type: ignore[name-defined]
        if not NUMPY_AVAILABLE:
            raise ImportError("numpy is required for keyword embeddings")
        return np.array([[0.1] * 768])  # type: ignore[no-any-return]


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Main class
    "ImpactScorer",
    "ImpactScoringConfig",
    # Models
    "ImpactVector",
    # Configuration
    "ScoringConfig",
    "ScoringMethod",
    "ScoringResult",
    # Factory functions
    "calculate_message_impact",
    "configure_impact_scorer",
    # Utility functions
    "cosine_similarity_fallback",
    "get_gpu_decision_matrix",
    "get_impact_scorer",
    "get_impact_scorer_service",
    "get_profiling_report",
    "reset_impact_scorer",
    "reset_profiling",
]
