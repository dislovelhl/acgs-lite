"""
ACGS-2 Enhanced Agent Bus - LocoOperator-4B Governance Client
Constitutional Hash: cdd01ef066bc6cf2

Async governance client wrapping HuggingFaceAdapter for LocoOperator-4B.

MACI Role: PROPOSER ONLY
- Generates governance scoring signals and action recommendations.
- Output is never self-validated; it must pass the independent MessageProcessor
  7-stage pipeline and OPA client before any downstream execution.
- Every response is stamped with maci_role="proposer" and the constitutional hash.

Usage:
    client = LocoOperatorGovernanceClient()
    if client.is_available:
        result = await client.score_governance_action("deploy_policy", context)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from packages.enhanced_agent_bus.exceptions.operations import GovernanceError

# ---- Local imports ----------------------------------------------------------------
from packages.enhanced_agent_bus.llm_adapters.config import LocoOperatorAdapterConfig
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Optional heavy imports -- guarded so unit tests don't require a GPU
_HUGGINGFACE_ADAPTER_AVAILABLE = False
try:
    from packages.enhanced_agent_bus.llm_adapters import HuggingFaceAdapter, LLMMessage

    _HUGGINGFACE_ADAPTER_AVAILABLE = True
except ImportError:
    HuggingFaceAdapter = None  # type: ignore[assignment,misc]
    LLMMessage = None  # type: ignore[assignment]


# ---- Result data-classes ----------------------------------------------------------


@dataclass
class GovernanceScoringResult:
    """Result from a LocoOperator governance action scoring request.

    Constitutional Hash: cdd01ef066bc6cf2
    MACI role is always 'proposer' -- never 'validator' or 'executor'.
    """

    score: float  # 0.0-1.0 governance risk/impact score
    rationale: str
    maci_role: str  # always "proposer"
    constitutional_hash: str
    model_id: str
    latency_ms: float
    raw_response: str = field(default="")

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ACGSValidationError(
                f"score must be in [0.0, 1.0], got {self.score}",
                error_code="LOCO_SCORE_OUT_OF_RANGE",
            )
        if self.maci_role != "proposer":
            raise ACGSValidationError(
                f"MACI violation: maci_role must be 'proposer', got {self.maci_role!r}",
                error_code="LOCO_MACI_ROLE_INVALID",
            )
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ACGSValidationError(
                f"Constitutional hash mismatch: expected {CONSTITUTIONAL_HASH!r}, "
                f"got {self.constitutional_hash!r}",
                error_code="LOCO_HASH_MISMATCH",
            )


@dataclass
class PolicyEvaluationResult:
    """Result from a LocoOperator policy fragment evaluation.

    Constitutional Hash: cdd01ef066bc6cf2
    MACI role is always 'proposer' -- evaluation is a recommendation, not a decision.
    """

    is_compliant: bool | None  # None means model is uncertain
    confidence: float  # 0.0-1.0
    explanation: str
    maci_role: str  # always "proposer"
    constitutional_hash: str

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ACGSValidationError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}",
                error_code="LOCO_CONFIDENCE_OUT_OF_RANGE",
            )
        if self.maci_role != "proposer":
            raise ACGSValidationError(
                f"MACI violation: maci_role must be 'proposer', got {self.maci_role!r}",
                error_code="LOCO_MACI_ROLE_INVALID",
            )
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ACGSValidationError(
                f"Constitutional hash mismatch: expected "
                f"{CONSTITUTIONAL_HASH!r}, "
                f"got {self.constitutional_hash!r}",
                error_code="LOCO_HASH_MISMATCH",
            )


@dataclass
class HealthCheckResult:
    """Health status for the LocoOperator governance client.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    is_healthy: bool
    model_id: str
    latency_ms: float
    error: str | None = None


# ---- Prompts -----------------------------------------------------------------------

_SCORING_SYSTEM_PROMPT = """You are a MACI Proposer agent for the ACGS-2 governance platform.
Constitutional Hash: cdd01ef066bc6cf2

Your role is to PROPOSE governance risk scores for actions. You are NEVER a validator.
Respond with a JSON object containing:
- "score": float 0.0-1.0 (0=safe, 1=critical risk)
- "rationale": string (brief explanation, max 200 chars)
Do not include any other text."""

_POLICY_SYSTEM_PROMPT = """You are a MACI Proposer agent for the ACGS-2 governance platform.
Constitutional Hash: cdd01ef066bc6cf2

Your role is to PROPOSE compliance assessments for policy fragments. You are NEVER a validator.
Respond with a JSON object containing:
- "is_compliant": boolean or null (null if uncertain)
- "confidence": float 0.0-1.0
- "explanation": string (brief, max 300 chars)
Do not include any other text."""


# ---- Client -----------------------------------------------------------------------


class LocoOperatorGovernanceClient:
    """Async governance client wrapping HuggingFaceAdapter for LocoOperator-4B.

    Constitutional Hash: cdd01ef066bc6cf2

    MACI Role: PROPOSER ONLY. All outputs are tagged maci_role="proposer" and
    must be independently validated before any executor acts on them.

    Gracefully degrades (is_available=False) when:
    - transformers/torch packages are not installed
    - The underlying adapter fails its health check
    """

    def __init__(
        self,
        config: LocoOperatorAdapterConfig | None = None,
        *,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """Initialise the LocoOperator governance client.

        Args:
            config: LocoOperator adapter config. Defaults to LocoOperatorAdapterConfig().
            constitutional_hash: Constitutional hash for compliance stamping.
        """
        self._constitutional_hash = constitutional_hash
        self._config = config or LocoOperatorAdapterConfig()
        self._adapter: object | None = None
        self._available: bool = False

        if _HUGGINGFACE_ADAPTER_AVAILABLE and HuggingFaceAdapter is not None:
            try:
                self._adapter = HuggingFaceAdapter(config=self._config)
                self._available = True
                logger.info(
                    "LocoOperatorGovernanceClient initialised with model=%s device=%s",
                    self._config.model,
                    self._config.device,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "LocoOperatorGovernanceClient: adapter init failed -- "
                    "falling back to unavailable mode: %s",
                    exc,
                )
                self._available = False
        else:
            logger.info(
                "LocoOperatorGovernanceClient: HuggingFaceAdapter not available "
                "(transformers/torch may not be installed). is_available=False."
            )

    # ---- Properties ---------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """True when the underlying adapter is ready for inference."""
        return self._available and self._adapter is not None

    @property
    def model_id(self) -> str:
        """Return the configured model identifier."""
        return self._config.model

    # ---- Public async API ---------------------------------------------------------

    async def score_governance_action(
        self,
        action: str,
        context: JSONDict,
    ) -> GovernanceScoringResult | None:
        """Score a governance action and return a structured result.

        MACI role: proposer -- the result must be independently validated.

        Args:
            action: Human-readable description of the governance action.
            context: Structured context for the action (payload, metadata, etc.).

        Returns:
            GovernanceScoringResult with score in [0.0, 1.0], or None if unavailable.

        Raises:
            GovernanceError: On transport/parsing failures when the client is available.
        """
        if not self.is_available:
            logger.debug("LocoOperatorGovernanceClient.score_governance_action: unavailable")
            return None

        user_prompt = (
            f"Action: {action}\n"
            f"Context: {_truncate_json(context, max_chars=800)}\n"
            "Provide a governance risk score as JSON."
        )

        t_start = time.monotonic()
        try:
            raw = await self._call_adapter(_SCORING_SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            raise GovernanceError(
                f"LocoOperator transport failure during score_governance_action: {exc}"
            ) from exc
        latency_ms = (time.monotonic() - t_start) * 1000.0

        try:
            parsed = _parse_json_response(raw)
            score = float(parsed.get("score", 0.5))
            score = max(0.0, min(1.0, score))
            rationale = str(parsed.get("rationale", ""))[:400]
        except (json.JSONDecodeError, ValueError) as exc:
            raise GovernanceError(
                f"LocoOperator response parse failure in score_governance_action: {exc}"
            ) from exc

        result = GovernanceScoringResult(
            score=score,
            rationale=rationale,
            maci_role="proposer",
            constitutional_hash=self._constitutional_hash,
            model_id=self._config.model,
            latency_ms=latency_ms,
            raw_response=raw[:500],
        )
        logger.debug(
            "LocoOperator scored action=%r score=%.3f latency=%.1fms",
            action[:60],
            score,
            latency_ms,
        )
        return result

    async def evaluate_policy_fragment(
        self,
        fragment: str,
    ) -> PolicyEvaluationResult | None:
        """Evaluate a policy fragment for constitutional compliance.

        MACI role: proposer -- the result is a recommendation, not a decision.

        Args:
            fragment: Policy text or rule fragment to evaluate.

        Returns:
            PolicyEvaluationResult, or None if unavailable.

        Raises:
            GovernanceError: On transport/parsing failures when the client is available.
        """
        if not self.is_available:
            logger.debug("LocoOperatorGovernanceClient.evaluate_policy_fragment: unavailable")
            return None

        user_prompt = (
            f"Policy fragment:\n{fragment[:2000]}\n\nEvaluate constitutional compliance as JSON."
        )

        try:
            raw = await self._call_adapter(_POLICY_SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            raise GovernanceError(
                f"LocoOperator transport failure during evaluate_policy_fragment: {exc}"
            ) from exc

        try:
            parsed = _parse_json_response(raw)
            is_compliant_raw = parsed.get("is_compliant")
            if is_compliant_raw is None:
                is_compliant: bool | None = None
            else:
                is_compliant = bool(is_compliant_raw)
            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            explanation = str(parsed.get("explanation", ""))[:500]
        except (json.JSONDecodeError, ValueError) as exc:
            raise GovernanceError(
                f"LocoOperator response parse failure in evaluate_policy_fragment: {exc}"
            ) from exc

        result = PolicyEvaluationResult(
            is_compliant=is_compliant,
            confidence=confidence,
            explanation=explanation,
            maci_role="proposer",
            constitutional_hash=self._constitutional_hash,
        )
        logger.debug(
            "LocoOperator evaluated policy fragment: is_compliant=%s confidence=%.3f",
            is_compliant,
            confidence,
        )
        return result

    async def health_check(self) -> HealthCheckResult:
        """Perform a lightweight health check against the adapter.

        Returns:
            HealthCheckResult indicating availability and latency.
        """
        if not self.is_available:
            return HealthCheckResult(
                is_healthy=False,
                model_id=self._config.model,
                latency_ms=0.0,
                error="Adapter not available (transformers/torch missing or init failed)",
            )

        t_start = time.monotonic()
        try:
            adapter = self._adapter
            if hasattr(adapter, "health_check"):
                await adapter.health_check()  # type: ignore[union-attr]
            latency_ms = (time.monotonic() - t_start) * 1000.0
            return HealthCheckResult(
                is_healthy=True,
                model_id=self._config.model,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t_start) * 1000.0
            logger.warning("LocoOperator health_check failed: %s", exc)
            return HealthCheckResult(
                is_healthy=False,
                model_id=self._config.model,
                latency_ms=latency_ms,
                error=str(exc),
            )

    # ---- Internal helpers ---------------------------------------------------------

    async def _call_adapter(self, system: str, user: str) -> str:
        """Call the underlying HuggingFace adapter and return the response text.

        Args:
            system: System prompt.
            user: User message.

        Returns:
            Raw response string from the model.

        Raises:
            GovernanceError: If the adapter call fails.
        """
        if self._adapter is None or LLMMessage is None:
            raise GovernanceError("LocoOperator adapter is not initialised")

        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user),
        ]

        try:
            response = await self._adapter.acomplete(messages=messages)  # type: ignore[union-attr]
            return str(response.content) if hasattr(response, "content") else str(response)
        except Exception as exc:
            raise GovernanceError(f"LocoOperator adapter call failed: {exc}") from exc


# ---- Utility helpers ---------------------------------------------------------------


def _truncate_json(data: JSONDict, max_chars: int = 800) -> str:
    """Safely convert a JSONDict to a string, truncated to max_chars."""
    import json

    try:
        text = json.dumps(data, default=str)
    except Exception:
        text = str(data)
    return text[:max_chars]


def _parse_json_response(raw: str) -> dict[str, object]:
    """Extract a JSON object from a model response string.

    Handles cases where the model wraps JSON in markdown code fences.
    """
    import json
    import re

    text = raw.strip()

    # Strip markdown fences if present
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Find first {...} block
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        text = brace_match.group(0)

    return dict(json.loads(text))  # type: ignore[arg-type]


__all__ = [
    "GovernanceScoringResult",
    "HealthCheckResult",
    "LocoOperatorGovernanceClient",
    "PolicyEvaluationResult",
]
