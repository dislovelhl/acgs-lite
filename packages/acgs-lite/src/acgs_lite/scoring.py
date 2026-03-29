"""Constitutional impact scorer — semantic risk assessment for agent actions.

Extracted from acgs2 for standalone use in acgs-lite and constitutional_swarm.
Provides layered scoring: rule-based (fast) → transformer (accurate) → Rust (fastest).

Usage::

    from acgs_lite.scoring import ConstitutionalImpactScorer

    scorer = ConstitutionalImpactScorer()
    result = scorer.score("delete all user records")
    # {"score": 0.82, "risk_level": "critical", ...}
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, ClassVar

try:
    from transformers import pipeline

    TRANSFORMERS_AVAILABLE = True
except Exception:
    TRANSFORMERS_AVAILABLE = False

try:
    from acgs_lite_rust import ImpactScorer as _RustImpactScorer  # type: ignore[import]

    RUST_SCORER_AVAILABLE = True
except ImportError:
    RUST_SCORER_AVAILABLE = False

_log = logging.getLogger(__name__)

# Feature flag: "python" | "rust" | "shadow"
# shadow = run both, log divergences, use python result
_IMPACT_SCORER_BACKEND = os.environ.get("IMPACT_SCORER_BACKEND", "python").lower()
_IMPACT_SCORER_MODEL_DIR = os.environ.get("IMPACT_SCORER_MODEL_DIR", "")
_SHADOW_DIVERGENCE_THRESHOLD = float(os.environ.get("IMPACT_SCORER_SHADOW_THRESHOLD", "0.02"))


class RuleBasedScorer:
    """Rule-based impact scorer — fallback when ML models are unavailable.

    Uses keyword matching and pattern analysis for risk assessment.
    No external dependencies. Always available.
    """

    RISK_CATEGORIES: ClassVar[dict[str, Any]] = {
        "data_destruction": {
            "keywords": ["delete", "remove", "drop", "truncate", "destroy", "erase", "wipe"],
            "weight": 0.3,
        },
        "code_execution": {
            "keywords": ["execute", "run", "eval", "exec", "spawn", "subprocess", "shell"],
            "weight": 0.25,
        },
        "system_access": {
            "keywords": ["admin", "root", "sudo", "chmod", "chown", "system", "kernel"],
            "weight": 0.25,
        },
        "production_impact": {
            "keywords": ["production", "prod", "deploy", "publish", "release", "live"],
            "weight": 0.2,
        },
        "database_operations": {
            "keywords": ["database", "sql", "query", "insert", "update", "migration"],
            "weight": 0.15,
        },
        "network_operations": {
            "keywords": ["api", "http", "request", "download", "upload", "fetch"],
            "weight": 0.1,
        },
        "authentication": {
            "keywords": ["password", "token", "secret", "credential", "auth", "key"],
            "weight": 0.2,
        },
        "financial": {
            "keywords": ["payment", "transaction", "money", "transfer", "billing", "invoice"],
            "weight": 0.25,
        },
    }

    RISK_PATTERNS: ClassVar[list[tuple[str, float]]] = [
        (r"\b(DELETE|DROP|TRUNCATE)\s+", 0.3),
        (r"rm\s+-rf?\s+", 0.4),
        (r"sudo\s+", 0.2),
        (r"https?://[^\s]+", 0.05),
        (r"```(python|bash|sh|javascript|sql)", 0.1),
        (r"API[_-]?KEY|SECRET|TOKEN", 0.15),
    ]

    def score(self, content: str) -> float:
        """Return impact score in [0.0, 1.0] based on keyword and pattern matching."""
        if not content:
            return 0.0

        content_lower = content.lower()
        result = 0.0

        for _category, config in self.RISK_CATEGORIES.items():
            for keyword in config["keywords"]:
                if keyword in content_lower:
                    result += config["weight"]
                    break

        for pattern, weight in self.RISK_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                result += weight

        return min(result, 1.0)


class TransformerScorer:
    """ML-based impact scorer using DistilBERT for semantic analysis.

    Requires: pip install transformers torch
    Falls back to RuleBasedScorer on any error.
    """

    def __init__(self, model_name: str = "distilbert-base-uncased") -> None:
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "transformers and torch are required for TransformerScorer. "
                "Install with: pip install transformers torch"
            )
        self.model_name = model_name
        self._classifier = None

    @property
    def classifier(self):
        if self._classifier is None:
            self._classifier = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                device=-1,
            )
        return self._classifier

    def score(self, content: str) -> float:
        """Return impact score in [0.0, 1.0] using transformer model."""
        if not content:
            return 0.0

        if len(content) > 512:
            content = content[:512]

        try:
            result = self.classifier(content)[0]
            base_score = result["score"] if result["label"] == "NEGATIVE" else 1 - result["score"]
            rule_score = RuleBasedScorer().score(content)
            return min(0.6 * base_score + 0.4 * rule_score, 1.0)
        except (RuntimeError, ValueError, TypeError):
            return RuleBasedScorer().score(content)


class RustScorer:
    """Thin wrapper around the Rust/Candle ImpactScorer PyO3 extension.

    Requires:
      - acgs_lite_rust built: cd packages/acgs-lite/rust && maturin develop --release
      - IMPACT_SCORER_MODEL_DIR pointing to a fine-tuned DistilBERT model directory
    """

    def __init__(
        self,
        model_dir: str = _IMPACT_SCORER_MODEL_DIR,
        device: str = "cpu",
    ) -> None:
        if not RUST_SCORER_AVAILABLE:
            raise ImportError(
                "acgs_lite_rust not installed. "
                "Run: cd packages/acgs-lite/rust && maturin develop --release"
            )
        if not model_dir:
            raise ValueError(
                "IMPACT_SCORER_MODEL_DIR must point to a fine-tuned DistilBERT model directory"
            )
        self._scorer = _RustImpactScorer(model_dir=model_dir, device=device)

    def score(self, content: str) -> float:
        """Return impact score in [0.0, 1.0]."""
        return self._scorer.score(content)

    def score_batch(self, contents: list[str]) -> list[float]:
        """Return batch of impact scores."""
        return self._scorer.score_batch(contents)

    def needs_deliberation(self, content: str) -> bool:
        """Return True if score >= 0.8 (deliberation gate)."""
        return self._scorer.needs_deliberation(content)


class ConstitutionalImpactScorer:
    """ACGS-compliant impact scorer combining multiple scoring strategies.

    Layered routing:
      python  → RuleBasedScorer (default, no deps)
      ml      → TransformerScorer (requires transformers)
      rust    → RustScorer (requires acgs_lite_rust + model)
      shadow  → run both python and rust, log divergence, use python result

    Environment variables:
      IMPACT_SCORER_BACKEND   python | rust | shadow  (default: python)
      IMPACT_SCORER_MODEL_DIR path to fine-tuned DistilBERT model dir
      IMPACT_SCORER_SHADOW_THRESHOLD  divergence threshold (default: 0.02)
    """

    CONSTITUTIONAL_PRINCIPLES: ClassVar[list[str]] = [
        "data_privacy",
        "user_consent",
        "transparency",
        "non_maleficence",
        "accountability",
        "fairness",
    ]

    def __init__(self, use_ml: bool = False) -> None:
        self.use_ml = use_ml and TRANSFORMERS_AVAILABLE
        self.rule_scorer = RuleBasedScorer()
        self._ml_scorer: TransformerScorer | None = None
        self._rust_scorer: RustScorer | None = None
        self._backend = _IMPACT_SCORER_BACKEND

    def _get_rust_scorer(self) -> RustScorer | None:
        if self._rust_scorer is not None:
            return self._rust_scorer
        if not RUST_SCORER_AVAILABLE or not _IMPACT_SCORER_MODEL_DIR:
            return None
        try:
            self._rust_scorer = RustScorer()
            _log.info("RustScorer loaded from %s", _IMPACT_SCORER_MODEL_DIR)
        except Exception as exc:
            _log.warning("RustScorer unavailable: %s", type(exc).__name__)
        return self._rust_scorer

    @property
    def ml_scorer(self) -> TransformerScorer | None:
        if self.use_ml and self._ml_scorer is None:
            try:
                self._ml_scorer = TransformerScorer()
            except (RuntimeError, ValueError, TypeError, ImportError):
                self.use_ml = False
        return self._ml_scorer

    def score(
        self,
        content: str,
        context: dict[str, Any] | None = None,
        agent_type: str | None = None,
    ) -> dict[str, Any]:
        """Return comprehensive impact assessment dict.

        Keys: score, base_score, agent_modifier, scoring_method,
              constitutional_alignment, risk_level
        """
        rust = self._get_rust_scorer()
        if self._backend == "rust" and rust is not None:
            base_score = rust.score(content)
            scoring_method = "rust"
        elif self._backend == "shadow" and rust is not None:
            py_score = (
                self.ml_scorer.score(content)
                if (self.use_ml and self.ml_scorer)
                else self.rule_scorer.score(content)
            )
            rust_score = rust.score(content)
            diff = abs(py_score - rust_score)
            if diff > _SHADOW_DIVERGENCE_THRESHOLD:
                _log.warning(
                    "impact_scorer shadow divergence diff=%.4f py=%.4f rust=%.4f action=%r",
                    diff,
                    py_score,
                    rust_score,
                    content[:120],
                )
            py_gate = py_score >= 0.8
            rust_gate = rust_score >= 0.8
            if py_gate != rust_gate:
                _log.error(
                    "impact_scorer GATE FLIP py=%s rust=%s py_score=%.4f rust_score=%.4f action=%r",
                    "deliberate" if py_gate else "fast-lane",
                    "deliberate" if rust_gate else "fast-lane",
                    py_score,
                    rust_score,
                    content[:120],
                )
            base_score = py_score
            scoring_method = "shadow-python"
        elif self.use_ml and self.ml_scorer:
            base_score = self.ml_scorer.score(content)
            scoring_method = "ml"
        else:
            base_score = self.rule_scorer.score(content)
            scoring_method = "rule"

        agent_modifier = self._get_agent_modifier(agent_type)
        adjusted_score = min(base_score * agent_modifier, 1.0)

        if context:
            context_modifier = self._get_context_modifier(context)
            adjusted_score = min(adjusted_score * context_modifier, 1.0)

        return {
            "score": adjusted_score,
            "base_score": base_score,
            "agent_modifier": agent_modifier,
            "scoring_method": scoring_method,
            "constitutional_alignment": self._assess_constitutional_alignment(content),
            "risk_level": _risk_level(adjusted_score),
        }

    def _get_agent_modifier(self, agent_type: str | None) -> float:
        modifiers = {
            "supervisor": 0.8,
            "researcher": 0.9,
            "coder": 1.2,
            "analyst": 0.9,
            "writer": 0.7,
        }
        return modifiers.get(agent_type or "", 1.0)

    def _get_context_modifier(self, context: dict[str, Any]) -> float:
        modifier = 1.0
        if context.get("environment") == "production":
            modifier *= 1.3
        if context.get("authenticated"):
            modifier *= 0.9
        success_rate = context.get("success_rate", 0.5)
        modifier *= 1.2 - success_rate * 0.4
        return modifier

    def _assess_constitutional_alignment(self, content: str) -> dict[str, Any]:
        content_lower = content.lower()
        assessments = {
            "data_privacy": (
                not any(p in content_lower for p in ["personal data", "pii", "private"])
                or "anonymize" in content_lower
            ),
            "user_consent": "consent" in content_lower or "permission" in content_lower,
            "transparency": "explain" in content_lower or "reason" in content_lower,
            "non_maleficence": not any(
                p in content_lower for p in ["harm", "damage", "destroy", "attack"]
            ),
            "accountability": "log" in content_lower or "audit" in content_lower,
            "fairness": not any(
                p in content_lower for p in ["discriminate", "bias", "unfair"]
            ),
        }
        alignment_score = sum(assessments.values()) / len(assessments)
        return {
            "principles": assessments,
            "overall_score": alignment_score,
            "compliant": alignment_score >= 0.7,
        }


def _risk_level(score: float) -> str:
    """Convert numeric score to risk level string."""
    if score < 0.3:
        return "low"
    if score < 0.5:
        return "medium"
    if score < 0.8:
        return "high"
    return "critical"


def score_impact(content: str, **kwargs: Any) -> float:
    """Convenience function — return a single impact score in [0.0, 1.0]."""
    return ConstitutionalImpactScorer().score(content, **kwargs)["score"]
