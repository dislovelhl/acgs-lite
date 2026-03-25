"""
MiniCPM-Enhanced Semantic Impact Scoring.

Constitutional Hash: 608508a9bd224290

Uses MiniCPM embeddings for true semantic understanding of message content,
providing dimension-specific impact scores for governance domains.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from enhanced_agent_bus.impact_scorer_infra.models import (
    ImpactVector,
    ScoringMethod,
    ScoringResult,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import BaseScoringAlgorithm

if TYPE_CHECKING:
    from enhanced_agent_bus.embeddings.provider import BaseEmbeddingProvider

logger = get_logger(__name__)
_MINICPM_SCORER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

# Constitutional Hash for governance compliance
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class GovernanceDomain(Enum):
    """Constitutional governance domains for impact scoring."""

    SAFETY = "safety"
    SECURITY = "security"
    PRIVACY = "privacy"
    FAIRNESS = "fairness"
    RELIABILITY = "reliability"
    TRANSPARENCY = "transparency"
    EFFICIENCY = "efficiency"


# Reference texts for each governance domain - used to compute domain embeddings
DOMAIN_REFERENCE_TEXTS = {
    GovernanceDomain.SAFETY: [
        "This action could harm users or cause physical damage to systems.",
        "Safety critical operation that affects human wellbeing.",
        "Dangerous action that violates safety protocols.",
        "Emergency situation requiring immediate safety intervention.",
        "Risk of injury, harm, or catastrophic failure.",
        "Safety guardrails and protective measures required.",
    ],
    GovernanceDomain.SECURITY: [
        "Unauthorized access attempt detected in the system.",
        "Security vulnerability or exploit in the codebase.",
        "Potential breach of security perimeter and defenses.",
        "Malicious activity or attack vector identified.",
        "Credential compromise or authentication bypass.",
        "Security audit finding requiring immediate remediation.",
    ],
    GovernanceDomain.PRIVACY: [
        "Personal data processing without user consent.",
        "PII exposure or data leakage incident.",
        "Privacy violation affecting user data rights.",
        "Unauthorized collection of sensitive information.",
        "Data retention policy violation detected.",
        "GDPR or privacy regulation non-compliance.",
    ],
    GovernanceDomain.FAIRNESS: [
        "Algorithmic bias detected in decision making.",
        "Discriminatory treatment based on protected attributes.",
        "Unfair outcome affecting specific user groups.",
        "Equitable access violation in resource allocation.",
        "Bias in AI model predictions or recommendations.",
        "Fair treatment and equal opportunity concerns.",
    ],
    GovernanceDomain.RELIABILITY: [
        "System availability and uptime affected.",
        "Service degradation or outage detected.",
        "Data integrity and consistency issues.",
        "Fault tolerance and recovery concerns.",
        "Performance regression impacting reliability.",
        "System stability and operational resilience.",
    ],
    GovernanceDomain.TRANSPARENCY: [
        "Decision explanation required for audit trail.",
        "Explainability of AI system reasoning.",
        "Audit logging and traceability requirements.",
        "Regulatory disclosure and reporting obligations.",
        "Governance decision documentation needed.",
        "Constitutional compliance verification required.",
    ],
    GovernanceDomain.EFFICIENCY: [
        "Resource utilization and cost optimization.",
        "Performance optimization and latency reduction.",
        "Computational efficiency and throughput.",
        "Energy consumption and sustainability.",
        "Operational cost and resource allocation.",
        "System scalability and capacity planning.",
    ],
}

# High-impact indicator keywords for quick classification boost
HIGH_IMPACT_INDICATORS = {
    GovernanceDomain.SAFETY: [
        "danger",
        "harm",
        "injury",
        "emergency",
        "critical",
        "fatal",
        "hazard",
    ],
    GovernanceDomain.SECURITY: [
        "breach",
        "attack",
        "exploit",
        "vulnerability",
        "unauthorized",
        "malicious",
        "compromise",
    ],
    GovernanceDomain.PRIVACY: [
        "pii",
        "personal",
        "gdpr",
        "consent",
        "data leak",
        "exposure",
        "sensitive",
    ],
    GovernanceDomain.FAIRNESS: [
        "bias",
        "discrimination",
        "unfair",
        "prejudice",
        "inequitable",
        "disparity",
    ],
    GovernanceDomain.RELIABILITY: [
        "outage",
        "downtime",
        "failure",
        "unavailable",
        "degradation",
        "crash",
    ],
    GovernanceDomain.TRANSPARENCY: [
        "audit",
        "compliance",
        "regulation",
        "disclosure",
        "explain",
        "justify",
    ],
    GovernanceDomain.EFFICIENCY: [
        "slow",
        "latency",
        "timeout",
        "bottleneck",
        "resource",
        "cost",
    ],
}


@dataclass
class MiniCPMScorerConfig:
    """Configuration for MiniCPM semantic scorer."""

    model_name: str = "MiniCPM4-0.5B"
    pooling_strategy: str = "mean"
    use_fp16: bool = True
    cache_embeddings: bool = True
    normalize: bool = True
    keyword_boost: float = 0.15  # Boost for keyword matches
    similarity_threshold: float = 0.3  # Minimum similarity to consider relevant
    high_impact_threshold: float = 0.7  # Threshold for high-impact classification
    batch_size: int = 16
    fallback_to_keywords: bool = True  # Use keyword fallback if embeddings unavailable


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class MiniCPMSemanticScorer(BaseScoringAlgorithm):
    """
    MiniCPM-enhanced semantic impact scorer.

    Constitutional Hash: 608508a9bd224290

    Uses MiniCPM embeddings for true semantic understanding of message content,
    providing dimension-specific impact scores across 7 governance domains.
    """

    def __init__(self, config: MiniCPMScorerConfig | None = None):
        self.config = config or MiniCPMScorerConfig()
        self._provider: BaseEmbeddingProvider | None = None
        self._domain_embeddings: dict[GovernanceDomain, list[float]] | None = None
        self._embedding_cache: dict[str, list[float]] = {}
        self._provider_available = False
        self._initialization_attempted = False  # Track if we've tried to initialize

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    def _initialize_provider(self) -> bool:
        """
        Lazy-initialize the MiniCPM embedding provider.

        Returns:
            True if provider initialized successfully, False otherwise.
        """
        # If initialization was already attempted, return cached result
        if self._initialization_attempted:
            return self._provider_available

        if self._provider is not None:
            return self._provider_available

        self._initialization_attempted = True

        try:
            from enhanced_agent_bus.embeddings.provider import (
                EmbeddingConfig,
                EmbeddingProviderType,
                create_embedding_provider,
            )

            config = EmbeddingConfig(
                provider_type=EmbeddingProviderType.MINICPM,
                model_name=self.config.model_name,
                cache_embeddings=self.config.cache_embeddings,
                normalize=self.config.normalize,
                extra_params={
                    "pooling": self.config.pooling_strategy,
                    "use_fp16": self.config.use_fp16,
                },
            )

            self._provider = create_embedding_provider(config)

            # Verify the provider actually works by trying a simple embedding
            # This triggers lazy loading of transformers and will fail if not installed
            try:
                _ = self._provider.embed("test")
                self._provider_available = True
                logger.info(f"MiniCPM semantic scorer initialized with {self.config.model_name}")
                return True
            except ImportError as e:
                logger.warning(f"MiniCPM provider not functional (missing dependencies): {e}")
                self._provider = None
                self._provider_available = False
                return False
            except _MINICPM_SCORER_ERRORS as e:
                logger.warning(f"MiniCPM provider verification failed: {e}")
                self._provider = None
                self._provider_available = False
                return False

        except ImportError as e:
            logger.warning(f"MiniCPM provider not available: {e}")
            self._provider_available = False
            return False
        except _MINICPM_SCORER_ERRORS as e:
            logger.warning(f"Failed to initialize MiniCPM provider: {e}")
            self._provider_available = False
            return False

    def _compute_domain_embeddings(self) -> None:
        """Pre-compute reference embeddings for each governance domain."""
        if self._domain_embeddings is not None:
            return

        if not self._initialize_provider():
            return

        try:
            self._domain_embeddings = {}

            for domain in GovernanceDomain:
                reference_texts = DOMAIN_REFERENCE_TEXTS[domain]
                # Compute embeddings for all reference texts
                embeddings = self._provider.embed_batch(reference_texts)
                # Average to get domain centroid
                centroid = [
                    sum(emb[i] for emb in embeddings) / len(embeddings)
                    for i in range(len(embeddings[0]))
                ]
                self._domain_embeddings[domain] = centroid

            logger.info(f"Computed domain embeddings for {len(self._domain_embeddings)} domains")
        except _MINICPM_SCORER_ERRORS as e:
            logger.warning(f"Failed to compute domain embeddings: {e}")
            self._domain_embeddings = None
            self._provider_available = False

    def _get_embedding(self, text: str) -> list[float] | None:
        """Get embedding for text, using cache if available."""
        if not self._provider_available:
            return None

        cache_key = self._get_cache_key(text)
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        try:
            embedding = self._provider.embed(text)
            self._embedding_cache[cache_key] = embedding
            return embedding
        except _MINICPM_SCORER_ERRORS as e:
            logger.warning(f"Failed to compute embedding: {e}")
            return None

    def _calculate_keyword_score(self, text: str, domain: GovernanceDomain) -> float:
        """Calculate keyword-based score for a domain."""
        text_lower = text.lower()
        indicators = HIGH_IMPACT_INDICATORS[domain]

        matches = sum(1 for kw in indicators if kw in text_lower)
        if matches == 0:
            return 0.0

        # Normalize by number of indicators
        return min(1.0, matches * 0.3)

    def _calculate_semantic_similarity(
        self, text_embedding: list[float], domain: GovernanceDomain
    ) -> float:
        """Calculate semantic similarity between text and domain centroid."""
        if self._domain_embeddings is None or domain not in self._domain_embeddings:
            return 0.0

        domain_embedding = self._domain_embeddings[domain]
        similarity = cosine_similarity(text_embedding, domain_embedding)

        # Normalize from [-1, 1] to [0, 1]
        return (similarity + 1.0) / 2.0

    def _extract_text_content(self, context: dict) -> str:
        """Extract text content from context dictionary."""
        parts = []

        # Extract direct content
        parts.extend(self._extract_direct_content(context))

        # Extract message content
        parts.extend(self._extract_message_content(context))

        # Extract action and reasoning
        parts.extend(self._extract_action_reasoning(context))

        # Extract tools content
        parts.extend(self._extract_tools_content(context))

        return " ".join(parts).strip()

    def _extract_direct_content(self, context: dict) -> list[str]:
        """Extract direct content from context."""
        parts = []
        if "content" in context:
            parts.append(str(context["content"]))
        return parts

    def _extract_message_content(self, context: dict) -> list[str]:
        """Extract message content from context."""
        parts = []
        if "message" not in context:
            return parts

        msg = context["message"]
        if isinstance(msg, dict):
            if "content" in msg:
                parts.append(str(msg["content"]))
            if "payload" in msg and isinstance(msg["payload"], dict):
                if "message" in msg["payload"]:
                    parts.append(str(msg["payload"]["message"]))
        else:
            parts.append(str(msg))

        return parts

    def _extract_action_reasoning(self, context: dict) -> list[str]:
        """Extract action and reasoning from context."""
        parts = []
        if "action" in context:
            parts.append(str(context["action"]))
        if "reasoning" in context:
            parts.append(str(context["reasoning"]))
        return parts

    def _extract_tools_content(self, context: dict) -> list[str]:
        """Extract tools content from context."""
        parts = []
        if "tools" not in context:
            return parts

        tools = context["tools"]
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict):
                    parts.append(tool.get("name", ""))
                else:
                    parts.append(str(tool))

        return parts

    def score(self, context: dict) -> ScoringResult:
        """
        Compute impact score using MiniCPM semantic understanding.

        Args:
            context: Dictionary containing message content and metadata.

        Returns:
            ScoringResult with 7-dimensional ImpactVector and aggregate score.
        """
        text = self._extract_text_content(context)

        if not text:
            # Empty content - return neutral scores
            return ScoringResult(
                vector=ImpactVector(),
                aggregate_score=0.0,
                method=ScoringMethod.SEMANTIC,
                confidence=0.0,
                metadata={"error": "empty_content", "constitutional_hash": CONSTITUTIONAL_HASH},
            )

        # Initialize provider and compute domain embeddings
        self._initialize_provider()
        self._compute_domain_embeddings()

        # Get text embedding
        text_embedding = self._get_embedding(text)

        # Calculate scores for each domain
        domain_scores = {}
        use_semantic = text_embedding is not None and self._domain_embeddings is not None

        for domain in GovernanceDomain:
            if use_semantic:
                # Semantic similarity score
                semantic_score = self._calculate_semantic_similarity(text_embedding, domain)
            else:
                semantic_score = 0.0

            # Keyword boost
            keyword_score = self._calculate_keyword_score(text, domain)

            # Combine scores
            if use_semantic:
                # Weight semantic higher when available
                combined = semantic_score * 0.8 + keyword_score * 0.2
            elif self.config.fallback_to_keywords:
                # Use only keywords as fallback
                combined = keyword_score
            else:
                combined = 0.0

            # Apply threshold
            if combined < self.config.similarity_threshold:
                combined = 0.0

            domain_scores[domain] = min(1.0, combined)

        # Create impact vector
        vector = ImpactVector(
            safety=domain_scores[GovernanceDomain.SAFETY],
            security=domain_scores[GovernanceDomain.SECURITY],
            privacy=domain_scores[GovernanceDomain.PRIVACY],
            fairness=domain_scores[GovernanceDomain.FAIRNESS],
            reliability=domain_scores[GovernanceDomain.RELIABILITY],
            transparency=domain_scores[GovernanceDomain.TRANSPARENCY],
            efficiency=domain_scores[GovernanceDomain.EFFICIENCY],
        )

        # Calculate aggregate score (weighted average)
        weights = {
            GovernanceDomain.SAFETY: 0.20,
            GovernanceDomain.SECURITY: 0.20,
            GovernanceDomain.PRIVACY: 0.15,
            GovernanceDomain.FAIRNESS: 0.15,
            GovernanceDomain.RELIABILITY: 0.10,
            GovernanceDomain.TRANSPARENCY: 0.10,
            GovernanceDomain.EFFICIENCY: 0.10,
        }

        aggregate = sum(domain_scores[d] * weights[d] for d in GovernanceDomain)

        # Confidence based on method used
        confidence = 0.95 if use_semantic else 0.6

        # Check for high-impact indicators
        max_domain_score = max(domain_scores.values())
        is_high_impact = max_domain_score >= self.config.high_impact_threshold

        return ScoringResult(
            vector=vector,
            aggregate_score=min(1.0, aggregate),
            method=ScoringMethod.SEMANTIC,
            confidence=confidence,
            metadata={
                "model": self.config.model_name if use_semantic else "keyword_fallback",
                "semantic_enabled": use_semantic,
                "is_high_impact": is_high_impact,
                "max_domain": max(domain_scores.items(), key=lambda x: x[1])[0].value,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def score_batch(self, contexts: list[dict]) -> list[ScoringResult]:
        """
        Batch score multiple contexts efficiently.

        Args:
            contexts: List of context dictionaries.

        Returns:
            List of ScoringResult for each context.
        """
        if not contexts:
            return []

        # Initialize provider
        self._initialize_provider()
        self._compute_domain_embeddings()

        # Extract texts
        texts = [self._extract_text_content(ctx) for ctx in contexts]

        # Batch embed if provider available
        if self._provider_available and self._provider is not None:
            try:
                non_empty_texts = [(i, t) for i, t in enumerate(texts) if t]
                if non_empty_texts:
                    indices, batch_texts = zip(*non_empty_texts, strict=False)
                    embeddings = self._provider.embed_batch(list(batch_texts))

                    # Cache embeddings
                    for _idx, text, emb in zip(indices, batch_texts, embeddings, strict=False):
                        cache_key = self._get_cache_key(text)
                        self._embedding_cache[cache_key] = emb
            except _MINICPM_SCORER_ERRORS as e:
                logger.warning(f"Batch embedding failed: {e}")

        # Score each context
        return [self.score(ctx) for ctx in contexts]

    def unload(self) -> None:
        """Unload model to free memory."""
        if self._provider is not None and hasattr(self._provider, "unload"):
            self._provider.unload()
        self._provider = None
        self._provider_available = False
        self._domain_embeddings = None
        self._embedding_cache.clear()
        logger.info("MiniCPM semantic scorer unloaded")

    def get_info(self) -> dict:
        """Get scorer information."""
        return {
            "scorer_type": "MiniCPMSemanticScorer",
            "model_name": self.config.model_name,
            "provider_available": self._provider_available,
            "domains_loaded": self._domain_embeddings is not None,
            "cache_size": len(self._embedding_cache),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# Factory function for easy instantiation
def create_minicpm_scorer(
    model_name: str = "MiniCPM4-0.5B",
    use_fp16: bool = True,
    fallback_to_keywords: bool = True,
) -> MiniCPMSemanticScorer:
    """
    Create a MiniCPM semantic scorer with the specified configuration.

    Args:
        model_name: MiniCPM model to use (MiniCPM4-0.5B, MiniCPM4-8B, MiniCPM3-4B)
        use_fp16: Whether to use FP16 precision
        fallback_to_keywords: Whether to fallback to keywords if embeddings unavailable

    Returns:
        Configured MiniCPMSemanticScorer instance.
    """
    config = MiniCPMScorerConfig(
        model_name=model_name,
        use_fp16=use_fp16,
        fallback_to_keywords=fallback_to_keywords,
    )
    return MiniCPMSemanticScorer(config)


__all__ = [
    "DOMAIN_REFERENCE_TEXTS",
    "HIGH_IMPACT_INDICATORS",
    "GovernanceDomain",
    "MiniCPMScorerConfig",
    "MiniCPMSemanticScorer",
    "create_minicpm_scorer",
]
