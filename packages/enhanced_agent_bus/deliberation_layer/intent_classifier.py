"""
ACGS-2 SDPC - Intent Classifier
Constitutional Hash: cdd01ef066bc6cf2

Categorizes user intent for dynamic routing and prompt compilation.
Implements hybrid classification with LLM fallback for ambiguous cases.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

try:
    from src.core.shared.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.observability.structured_logging import get_logger


class IntentType(Enum):
    FACTUAL = "factual"  # High precision, requires GraphCheck & ASC
    CREATIVE = "creative"  # High fluency, relaxed factual constraints
    REASONING = "reasoning"  # Complex logic, triggers AMPO branching
    GENERAL = "general"  # Default/conversational intent


class RoutingPath(Enum):
    """Enumeration of classification routing paths for hybrid classification."""

    RULE_BASED = "rule_based"  # Fast path using keyword heuristics
    LLM = "llm"  # Slow path using LLM for ambiguous cases
    LLM_FALLBACK = "llm_fallback"  # LLM failed, fell back to rule-based
    EMPTY_INPUT = "empty_input"  # Empty/whitespace input, returned GENERAL


@dataclass
class ClassificationResult:
    """Result of intent classification with routing metadata.

    Provides detailed information about the classification decision,
    including which routing path was used and timing information.
    """

    intent: IntentType
    confidence: float
    routing_path: RoutingPath
    latency_ms: float
    rule_based_intent: IntentType | None = None
    rule_based_confidence: float | None = None
    llm_intent: IntentType | None = None
    llm_confidence: float | None = None
    llm_reasoning: str | None = None
    cached: bool = False

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for logging/serialization."""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "routing_path": self.routing_path.value,
            "latency_ms": round(self.latency_ms, 3),
            "rule_based_intent": self.rule_based_intent.value if self.rule_based_intent else None,
            "rule_based_confidence": self.rule_based_confidence,
            "llm_intent": self.llm_intent.value if self.llm_intent else None,
            "llm_confidence": self.llm_confidence,
            "llm_reasoning": self.llm_reasoning,
            "cached": self.cached,
        }


logger = get_logger(__name__)
LLM_CLASSIFICATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)

# LiteLLM availability flag
LITELLM_AVAILABLE = False


# Mock classes for test friendliness when LiteLLM is missing
class MockLiteLLMCache:
    """Mock cache class for when LiteLLM is not available."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


class MockLiteLLM:
    """Mock LiteLLM module for when it's not available."""

    cache: object | None = None

    @staticmethod
    async def acompletion(*args: object, **kwargs: object) -> JSONDict:
        """Mock async completion that returns empty response."""
        return {"choices": [{"message": {"content": "{}"}}]}


# Attempt to import LiteLLM
try:
    import litellm
    from litellm import Cache

    LITELLM_AVAILABLE = True
except ImportError:
    litellm = MockLiteLLM()  # type: ignore[assignment]
    Cache = MockLiteLLMCache  # type: ignore[assignment, misc]
    LITELLM_AVAILABLE = False


class IntentClassifier:
    """Classifies user intent to determine optimal processing strategies."""

    DEFAULT_CONFIDENCE = 0.5
    BASE_CONFIDENCE = 0.7
    MAX_RULE_CONFIDENCE = 1.0
    CONFIDENCE_BOOST_PER_MATCH = 0.1

    REASONING_KEYWORDS: ClassVar[list[str]] = [
        "calculate",
        "prove",
        "reason",
        "step by step",
        "analyze",
    ]
    FACTUAL_KEYWORDS: ClassVar[list[str]] = [
        "tell me about",
        "who is",
        "what is",
        "where is",
        "what happened in",
        "date of",
        "historical",
        "how many",
    ]
    CREATIVE_KEYWORDS: ClassVar[list[str]] = [
        "write a story",
        "poem",
        "joke",
        "creative",
        "imagine",
        "song",
    ]

    def __init__(
        self,
        model_name: str = "distilbert-base-uncased",
        config: BusConfiguration | None = None,
        llm_enabled: bool = False,
        llm_confidence_threshold: float = 0.8,
    ):
        self.model_name = model_name
        self.config = config or BusConfiguration()
        self.llm_enabled = llm_enabled
        self.llm_confidence_threshold = llm_confidence_threshold

        # Override config if args provided
        if llm_enabled:
            self.config.llm_enabled = True
        if llm_confidence_threshold:
            self.config.llm_confidence_threshold = llm_confidence_threshold

        # Ensure defaults if not in config
        if not hasattr(self.config, "llm_enabled"):
            self.config.llm_enabled = llm_enabled
        if not hasattr(self.config, "llm_confidence_threshold"):
            self.config.llm_confidence_threshold = llm_confidence_threshold

        # For Phase 1, we use dynamic heuristic pattern matching with an LLM fallback hook.
        logger.info(f"IntentClassifier initialized with model: {model_name}")
        self._llm_client_initialized = False  # Used by tests

    def classify(self, content: str) -> IntentType:
        """Determines the intent type of the provided content."""
        content_lower = content.lower()

        # Heuristic Pattern Matching (Fast Path)
        if any(
            word in content_lower
            for word in ["calculate", "prove", "reason", "step by step", "analyze"]
        ):
            return IntentType.REASONING

        if any(
            word in content_lower
            for word in [
                "tell me about",
                "who is",
                "what is",
                "where is",
                "what happened in",
                "date of",
                "historical",
                "how many",
            ]
        ):
            return IntentType.FACTUAL

        if any(
            word in content_lower
            for word in ["write a story", "poem", "joke", "creative", "imagine", "song"]
        ):
            return IntentType.CREATIVE

        # Default to general intent
        return IntentType.GENERAL

    def _count_keyword_matches(self, content_lower: str, keywords: list[str]) -> int:
        """Count how many keywords from the list appear in the content."""
        return sum(1 for keyword in keywords if keyword in content_lower)

    def _calculate_confidence(self, match_count: int, is_default: bool = False) -> float:
        """Calculate confidence score based on keyword match count."""
        if is_default:
            return self.DEFAULT_CONFIDENCE
        if match_count == 0:
            return self.DEFAULT_CONFIDENCE
        # Base confidence + boost for each additional match beyond the first
        confidence = self.BASE_CONFIDENCE + (match_count - 1) * self.CONFIDENCE_BOOST_PER_MATCH
        return min(confidence, self.MAX_RULE_CONFIDENCE)

    def classify_with_confidence(self, content: str) -> tuple[IntentType, float]:
        """
        Determines the intent type and confidence score of the provided content.

        Returns:
            tuple of (IntentType, confidence) where confidence is a float between 0 and 1.
            Higher confidence indicates stronger keyword matches.
        """
        content_lower = content.lower()

        # Count matches for each intent type
        reasoning_matches = self._count_keyword_matches(content_lower, self.REASONING_KEYWORDS)
        factual_matches = self._count_keyword_matches(content_lower, self.FACTUAL_KEYWORDS)
        creative_matches = self._count_keyword_matches(content_lower, self.CREATIVE_KEYWORDS)

        # Determine intent based on highest match count, with priority order for ties
        match_counts = [
            (IntentType.REASONING, reasoning_matches),
            (IntentType.FACTUAL, factual_matches),
            (IntentType.CREATIVE, creative_matches),
        ]

        # Find the intent with the most matches
        best_intent = IntentType.GENERAL
        best_count = 0

        for intent_type, count in match_counts:
            if count > best_count:
                best_intent = intent_type
                best_count = count

        # Calculate confidence based on match strength
        if best_count > 0:
            confidence = self._calculate_confidence(best_count)
            return best_intent, confidence

        # Default to general with lower confidence
        return IntentType.GENERAL, self._calculate_confidence(0, is_default=True)

    # LLM prompt template for intent classification
    LLM_CLASSIFICATION_PROMPT: str = """You are an intent classifier for a governance system. Classify the user's input into exactly one of these categories:

- FACTUAL: Questions seeking specific facts, data, historical information, or verifiable answers.
  Examples: "What is the capital of France?", "When did World War 2 end?", "How many users are in the system?"

- CREATIVE: Requests for creative content, storytelling, imagination, or artistic output.
  Examples: "Write a poem about spring", "Tell me a joke", "Create a story about a robot"

- REASONING: Complex analytical tasks requiring step-by-step logic, calculations, or problem-solving.
  Examples: "Calculate the derivative of x^2", "Explain why the sky is blue step by step", "Analyze this data"

- GENERAL: Conversational inputs, greetings, or anything that doesn't fit the above categories.
  Examples: "Hello", "How are you?", "Thanks for your help"

User input: {content}

Respond with ONLY a JSON object in this exact format:
{{"intent": "FACTUAL|CREATIVE|REASONING|GENERAL", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""

    # Maximum content length to send to LLM (to control costs)
    MAX_CONTENT_LENGTH: int = 2000

    def _get_llm_params(self) -> JSONDict:
        """Get LLM parameters for classification."""
        return {
            "model": getattr(self.config, "llm_model", "gpt-5-mini"),
            "temperature": 0.0,
            "max_tokens": 100,
        }

    async def _invoke_llm_classification(self, content: str) -> JSONDict | None:
        """Invoke LLM for intent classification.

        Args:
            content: The user input to classify.

        Returns:
            dict with intent, confidence, and reasoning, or None on failure.
        """
        # Fallback to simple keyword matching if litellm fails
        if not LITELLM_AVAILABLE:
            return None

        # Truncate content if too long
        truncated_content = (
            content[: self.MAX_CONTENT_LENGTH]
            if len(content) > self.MAX_CONTENT_LENGTH
            else content
        )

        try:
            # Prepare the prompt
            prompt = self.LLM_CLASSIFICATION_PROMPT.format(content=truncated_content)

            # Get LLM parameters
            params = self._get_llm_params()

            # Call LiteLLM acompletion
            response = await litellm.acompletion(
                messages=[{"role": "user", "content": prompt}],
                **params,
            )

            # Extract response content
            if not response or not response.get("choices"):
                logger.warning("Empty LLM response received")
                return None

            response_content = response["choices"][0]["message"]["content"]

            # Parse JSON response
            try:
                result = json.loads(response_content.strip())
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                # Try to extract intent from plain text response
                response_upper = response_content.upper()
                for intent_type in IntentType:
                    if intent_type.name in response_upper:
                        return {
                            "intent": intent_type.name,
                            "confidence": 0.7,
                            "reasoning": "Extracted from text",
                        }
                return None

        except LLM_CLASSIFICATION_ERRORS as e:
            logger.error(f"LLM classification failed: {e}")
            return None

    def _parse_llm_intent(self, llm_result: JSONDict) -> IntentType | None:
        """Parse LLM result to extract IntentType.

        Args:
            llm_result: dict containing intent classification from LLM.

        Returns:
            IntentType if valid intent found, None otherwise.
        """
        intent_str = llm_result.get("intent", "").upper()

        # Map string to IntentType enum
        intent_map = {
            "FACTUAL": IntentType.FACTUAL,
            "CREATIVE": IntentType.CREATIVE,
            "REASONING": IntentType.REASONING,
            "GENERAL": IntentType.GENERAL,
        }

        return intent_map.get(intent_str)

    async def classify_async_with_metadata(
        self, content: str, context: JSONDict | None = None
    ) -> ClassificationResult:
        """
        Classify intent asynchronously and return full metadata.

        Uses rule-based classification first, falling back to LLM if confidence is low
        and LLM is enabled.
        """
        # 1. Rule-based classification
        rule_intent, rule_confidence = self.classify_with_confidence(content)

        # Check if we should use LLM
        # We use LLM if:
        # a) LLM is enabled
        # b) Rule confidence is below threshold
        threshold = self.llm_confidence_threshold
        llm_enabled = self.llm_enabled

        if llm_enabled and rule_confidence < threshold:
            # Try LLM
            llm_result_dict = await self._invoke_llm_classification(content)

            if llm_result_dict:
                llm_intent = self._parse_llm_intent(llm_result_dict)
                if llm_intent:
                    return ClassificationResult(
                        intent=llm_intent,
                        confidence=float(llm_result_dict.get("confidence", 0.8)),
                        routing_path=RoutingPath.LLM,
                        latency_ms=0.0,
                        rule_based_intent=rule_intent,
                        rule_based_confidence=rule_confidence,
                        llm_intent=llm_intent,
                        llm_confidence=float(llm_result_dict.get("confidence", 0.8)),
                        llm_reasoning=llm_result_dict.get("reasoning"),
                    )

            # Fallback if LLM failed or returned no intent
            return ClassificationResult(
                intent=rule_intent,
                confidence=rule_confidence,
                routing_path=RoutingPath.LLM_FALLBACK,
                latency_ms=0.0,
                rule_based_intent=rule_intent,
                rule_based_confidence=rule_confidence,
            )

        # 2. Return rule-based result matching high confidence
        return ClassificationResult(
            intent=rule_intent,
            confidence=rule_confidence,
            routing_path=RoutingPath.RULE_BASED,
            latency_ms=0.0,
            rule_based_intent=rule_intent,
            rule_based_confidence=rule_confidence,
        )

    async def classify_async(self, content: str, context: JSONDict | None = None) -> IntentType:
        """Asynchronous classification with optional context/LLM fallback."""
        result = await self.classify_async_with_metadata(content, context)
        return result.intent
