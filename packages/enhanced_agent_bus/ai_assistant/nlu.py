"""
ACGS-2 AI Assistant - Natural Language Understanding
Constitutional Hash: 608508a9bd224290

Advanced NLU with intent classification, entity extraction,
and sentiment analysis. Integrates with constitutional governance.
"""

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

# Import centralized constitutional hash with fallback
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict, JSONValue
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class Sentiment(Enum):
    """Sentiment categories."""

    VERY_NEGATIVE = -2
    NEGATIVE = -1
    NEUTRAL = 0
    POSITIVE = 1
    VERY_POSITIVE = 2


@dataclass
class Intent:
    """Represents a detected intent."""

    name: str
    confidence: float
    parameters: JSONDict = field(default_factory=dict)
    is_primary: bool = True

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "confidence": self.confidence,
            "parameters": self.parameters,
            "is_primary": self.is_primary,
        }


@dataclass
class Entity:
    """Represents an extracted entity."""

    text: str
    type: str
    value: JSONValue
    start: int
    end: int
    confidence: float = 1.0
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "text": self.text,
            "type": self.type,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class NLUResult:
    """Complete NLU processing result."""

    original_text: str = ""
    processed_text: str = ""
    primary_intent: Intent | None = None
    secondary_intents: list[Intent] = field(default_factory=list)
    entities: list[Entity] | JSONDict = field(default_factory=list)
    sentiment: Sentiment = Sentiment.NEUTRAL
    sentiment_score: float = 0.5
    language: str = "en"
    confidence: float = 0.0
    requires_clarification: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH
    processing_time_ms: float = 0.0
    # Convenience parameter for simpler initialization
    intents: list[JSONDict] | None = field(default=None, repr=False)

    def __post_init__(self):
        """Process intents convenience parameter if provided."""
        if self.intents:
            # Convert dict-based intents to Intent objects
            intent_objects = []
            for intent_data in self.intents:
                if isinstance(intent_data, dict):
                    intent = Intent(
                        name=intent_data.get("intent", intent_data.get("name", "unknown")),
                        confidence=intent_data.get("confidence", 0.0),
                    )
                    intent_objects.append(intent)
                elif isinstance(intent_data, Intent):
                    intent_objects.append(intent_data)

            if intent_objects:
                self.primary_intent = intent_objects[0]
                self.secondary_intents = intent_objects[1:] if len(intent_objects) > 1 else []

            # Clear the convenience parameter
            self.intents = None

    def to_dict(self) -> JSONDict:
        return {
            "original_text": self.original_text,
            "processed_text": self.processed_text,
            "primary_intent": self.primary_intent.to_dict() if self.primary_intent else None,
            "secondary_intents": [i.to_dict() for i in self.secondary_intents],
            "entities": (
                self.entities
                if isinstance(self.entities, dict)
                else [e.to_dict() for e in self.entities]
            ),
            "sentiment": (
                self.sentiment.name if hasattr(self.sentiment, "name") else str(self.sentiment)
            ),
            "sentiment_score": self.sentiment_score,
            "language": self.language,
            "confidence": self.confidence,
            "requires_clarification": self.requires_clarification,
            "constitutional_hash": self.constitutional_hash,
            "processing_time_ms": self.processing_time_ms,
        }


class IntentClassifier(ABC):
    """Abstract base class for intent classification."""

    @abstractmethod
    async def classify(
        self,
        text: str,
        context: JSONDict | None = None,
    ) -> list[Intent]:
        """Classify text into intents."""
        pass


class EntityExtractor(ABC):
    """Abstract base class for entity extraction."""

    @abstractmethod
    async def extract(
        self,
        text: str,
        context: JSONDict | None = None,
    ) -> list[Entity]:
        """Extract entities from text."""
        pass


class RuleBasedIntentClassifier(IntentClassifier):
    """
    Rule-based intent classifier using pattern matching.

    Good for well-defined intents with clear patterns.
    Can be extended with ML-based classification.
    """

    def __init__(self, intent_patterns: dict[str, list[str]] | None = None):
        self.intent_patterns = intent_patterns or self._default_patterns()
        self._compiled_patterns = self._compile_patterns()

    def _default_patterns(self) -> dict[str, list[str]]:
        """Default intent patterns with expanded synonyms and variations."""
        return {
            "greeting": [
                r"\b(hi|hello|hey|greetings|good\s*(morning|afternoon|evening))\b",
                r"^(hi|hello|hey)$",
                r"howdy|salutations|ciao",
            ],
            "farewell": [
                r"\b(bye|goodbye|see\s*you|take\s*care|farewell|later|ttyl)\b",
                r"good night|catch you later",
            ],
            "help": [
                r"\b(help|assist|support|stuck|confused|problem|issue)\b",
                r"(can|could)\s+you\s+help",
                r"i\s+need\s+help",
                r"manual|guide|instructions",
            ],
            "question": [
                r"^(what|who|where|when|why|how|which|can|could|would|is|are|do|does)\b",
                r"\?$",
            ],
            "confirmation": [
                r"^(yes|yeah|yep|sure|ok|okay|correct|right|exactly|confirm|proceed|go\s*ahead)$",
                r"\b(that's\s*right|that's\s*correct|affirmative)\b",
            ],
            "denial": [
                r"^(no|nope|nah|wrong|incorrect|cancel|stop|halt|abort)$",
                r"\b(that's\s*wrong|not\s*correct|negative)\b",
            ],
            "order_status": [
                r"\b(order|delivery|shipment)\s*(status|update|tracking)\b",
                r"where\s*is\s*my\s*(order|package|delivery)",
                r"track\s*(my\s*)?(order|package)",
            ],
            "complaint": [
                r"\b(problem|issue|broken|not\s*working|disappointed|frustrated|angry|bad|awful|broken)\b",
                r"this\s+is\s+(terrible|awful|unacceptable)",
                r"complaint|dissatisfied",
            ],
            "request_info": [
                r"(tell|inform|let)\s+me\s+about",
                r"i\s+want\s+to\s+know",
                r"(can|could)\s+you\s+(tell|explain|describe)",
                r"info|details|more about",
            ],
            "feedback": [
                r"\b(feedback|suggestion|recommend|improve|rate|review)\b",
                r"i\s+(think|suggest|recommend)",
                r"my\s+thoughts",
            ],
        }

    def _compile_patterns(self) -> dict[str, list[re.Pattern]]:
        """Compile regex patterns for efficiency."""
        compiled = {}
        for intent, patterns in self.intent_patterns.items():
            compiled[intent] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        return compiled

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Simple word-based similarity ratio."""
        s1_words = set(s1.lower().split())
        s2_words = set(s2.lower().split())
        if not s1_words or not s2_words:
            return 0.0
        intersection = s1_words.intersection(s2_words)
        return len(intersection) / max(len(s1_words), len(s2_words))

    async def classify(
        self,
        text: str,
        context: JSONDict | None = None,
    ) -> list[Intent]:
        """Classify text into intents using pattern matching and similarity."""
        intents = []
        text_lower = text.lower().strip()

        for intent_name, patterns in self._compiled_patterns.items():
            max_intent_confidence, best_match = self._match_intent_patterns(
                text_lower, patterns, intent_name
            )

            if max_intent_confidence > 0.3:
                intents.append(
                    Intent(
                        name=intent_name,
                        confidence=max_intent_confidence,
                        parameters=best_match or {},
                    )
                )

        return self._finalize_intent_classification(intents)

    def _match_intent_patterns(
        self, text_lower: str, patterns: list[re.Pattern], intent_name: str
    ) -> tuple[float, dict | None]:
        """Match text against intent patterns and return best confidence and match."""
        max_intent_confidence = 0.0
        best_match = None

        for pattern in patterns:
            regex_conf, match_info = self._try_regex_match(text_lower, pattern)
            if regex_conf > max_intent_confidence:
                max_intent_confidence = regex_conf
                best_match = match_info

            # Try fuzzy similarity matching
            fuzzy_conf, fuzzy_match = self._try_fuzzy_match(text_lower, intent_name)
            if fuzzy_conf > max_intent_confidence:
                max_intent_confidence = fuzzy_conf
                best_match = fuzzy_match

        return max_intent_confidence, best_match

    def _try_regex_match(self, text_lower: str, pattern: re.Pattern) -> tuple[float, dict | None]:
        """Try regex pattern matching and return confidence and match info."""
        match = pattern.search(text_lower)
        if not match:
            return 0.0, None

        match_length = match.end() - match.start()
        regex_conf = min(0.95, 0.5 + (match_length / len(text_lower)) * 0.5)
        match_info = {
            "matched_pattern": pattern.pattern,
            "match_text": match.group(),
        }
        return regex_conf, match_info

    def _try_fuzzy_match(self, text_lower: str, intent_name: str) -> tuple[float, dict | None]:
        """Try fuzzy word-based similarity matching."""
        max_sim = 0.0
        best_keywords = None

        raw_patterns = self.intent_patterns[intent_name]
        for rp in raw_patterns:
            # Strip regex chars for keyword similarity
            keywords = re.sub(r"[\^\\\$\|\(\)\[\]\*?\+\.\b]", "", rp)
            sim = self._calculate_similarity(text_lower, keywords)
            if sim > max_sim:
                max_sim = sim
                best_keywords = keywords

        if max_sim > 0.0:
            fuzzy_conf = max_sim * 0.9  # Penalty for non-regex fuzzy match
            match_info = {
                "matched_pattern": "fuzzy_match",
                "match_text": best_keywords,
            }
            return fuzzy_conf, match_info

        return 0.0, None

    def _finalize_intent_classification(self, intents: list[Intent]) -> list[Intent]:
        """Sort intents by confidence and mark primary intent."""
        # Sort by confidence
        intents.sort(key=lambda x: x.confidence, reverse=True)

        # Mark primary intent
        if intents:
            intents[0].is_primary = True
            for intent in intents[1:]:
                intent.is_primary = False
        else:
            # Add fallback if no intents found
            intents.append(
                Intent(
                    name="unknown",
                    confidence=0.5,
                    parameters={"requires_clarification": True},
                )
            )

        return intents


class PatternEntityExtractor(EntityExtractor):
    """
    Pattern-based entity extraction.

    Extracts common entity types using regex patterns.
    Can be extended with NER models.
    """

    def __init__(self, custom_patterns: dict[str, str] | None = None):
        self.patterns = self._default_patterns()
        if custom_patterns:
            self.patterns.update(custom_patterns)
        self._compiled_patterns = self._compile_patterns()

    def _default_patterns(self) -> dict[str, str]:
        """Default entity patterns."""
        return {
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "phone": r"\b(\+?1?[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
            "order_id": r"\b[A-Z]{2,3}[-]?[0-9]{5,10}\b",
            "date": r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
            "time": r"\b([01]?[0-9]|2[0-3]):[0-5][0-9](\s*(am|pm|AM|PM))?\b",
            "money": r"\$[0-9]+(?:\.[0-9]{2})?",
            "number": r"\b\d+(?:\.\d+)?\b",
            "url": r"https?://[^\s<>\"{}|\\^`\[\]]+",
            "product_code": r"\b[A-Z]{2,4}-[0-9]{3,6}\b",
        }

    def _compile_patterns(self) -> dict[str, re.Pattern]:
        """Compile patterns for efficiency."""
        return {
            entity_type: re.compile(pattern, re.IGNORECASE)
            for entity_type, pattern in self.patterns.items()
        }

    async def extract(
        self,
        text: str,
        context: JSONDict | None = None,
    ) -> list[Entity]:
        """Extract entities from text."""
        entities = []

        for entity_type, pattern in self._compiled_patterns.items():
            for match in pattern.finditer(text):
                entity = Entity(
                    text=match.group(),
                    type=entity_type,
                    value=self._normalize_value(entity_type, match.group()),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9,
                )
                entities.append(entity)

        # Sort by position
        entities.sort(key=lambda x: x.start)
        return entities

    def _normalize_value(self, entity_type: str, raw_value: str) -> JSONValue:
        """Normalize entity value based on type."""
        normalizers = {
            "phone": lambda x: re.sub(r"[^0-9+]", "", x),
            "email": lambda x: x.lower().strip(),
            "number": lambda x: float(x) if "." in x else int(x),
            "money": lambda x: float(x.replace("$", "").replace(",", "")),
        }

        normalizer = normalizers.get(entity_type, lambda x: x)
        try:
            result: JSONValue = normalizer(raw_value)  # type: ignore[assignment]
            return result
        except (ValueError, AttributeError):
            return raw_value


class SentimentAnalyzer(ABC):
    """Abstract base class for sentiment analysis."""

    @abstractmethod
    async def analyze(
        self,
        text: str,
        context: JSONDict | None = None,
    ) -> str:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze
            context: Optional context for analysis

        Returns:
            Sentiment string: "positive", "negative", or "neutral"
        """
        pass


class BasicSentimentAnalyzer(SentimentAnalyzer):
    """
    Simple sentiment analyzer using keyword matching.

    Can be replaced with ML-based sentiment analysis.
    """

    def __init__(self):
        self.positive_words = {
            "great",
            "good",
            "excellent",
            "amazing",
            "wonderful",
            "fantastic",
            "love",
            "like",
            "best",
            "happy",
            "pleased",
            "satisfied",
            "thank",
            "thanks",
            "helpful",
            "perfect",
            "awesome",
            "brilliant",
            "superb",
        }
        self.negative_words = {
            "bad",
            "terrible",
            "awful",
            "horrible",
            "worst",
            "hate",
            "angry",
            "frustrated",
            "disappointed",
            "upset",
            "annoyed",
            "poor",
            "problem",
            "issue",
            "broken",
            "wrong",
            "fail",
            "failed",
            "error",
            "bug",
        }
        self.intensifiers = {"very", "really", "extremely", "absolutely", "totally"}
        self.negators = {"not", "no", "never", "don't", "doesn't", "didn't", "won't"}

    async def analyze(
        self,
        text: str,
        context: JSONDict | None = None,
    ) -> str:
        """Analyze sentiment of text and return sentiment string."""
        sentiment, _score = self._analyze_internal(text)

        # Map enum to simple string
        if sentiment in (Sentiment.POSITIVE, Sentiment.VERY_POSITIVE):
            return "positive"
        elif sentiment in (Sentiment.NEGATIVE, Sentiment.VERY_NEGATIVE):
            return "negative"
        else:
            return "neutral"

    def _analyze_internal(self, text: str) -> tuple[Sentiment, float]:
        """Internal analysis returning enum and score."""
        words = text.lower().split()
        word_count = len(words)

        if word_count == 0:
            return Sentiment.NEUTRAL, 0.0

        score = self._calculate_sentiment_score(words)
        normalized_score = self._normalize_score(score, word_count)
        sentiment = self._categorize_sentiment(normalized_score)

        return sentiment, normalized_score

    def _calculate_sentiment_score(self, words: list[str]) -> float:
        """Calculate raw sentiment score from words."""
        score = 0.0
        negation = False
        intensity = 1.0

        for word in words:
            if self._is_negator(word):
                negation = True
                continue

            if self._is_intensifier(word):
                intensity = 1.5
                continue

            word_score = self._get_word_score(word, intensity)
            if word_score != 0.0:
                score += -word_score if negation else word_score
                # Reset modifiers after scoring
                negation = False
                intensity = 1.0

        return score

    def _is_negator(self, word: str) -> bool:
        """Check if word is a negation modifier."""
        return word in self.negators

    def _is_intensifier(self, word: str) -> bool:
        """Check if word is an intensity modifier."""
        return word in self.intensifiers

    def _get_word_score(self, word: str, intensity: float) -> float:
        """Get sentiment score for a word with intensity modifier."""
        if word in self.positive_words:
            return 1.0 * intensity
        elif word in self.negative_words:
            return -1.0 * intensity
        return 0.0

    def _normalize_score(self, score: float, word_count: int) -> float:
        """Normalize sentiment score to [-1.0, 1.0] range."""
        normalized = score / max(word_count, 1)
        return max(-1.0, min(1.0, normalized))

    def _categorize_sentiment(self, normalized_score: float) -> Sentiment:
        """Map normalized score to sentiment category."""
        if normalized_score >= 0.5:
            return Sentiment.VERY_POSITIVE
        elif normalized_score >= 0.2:
            return Sentiment.POSITIVE
        elif normalized_score <= -0.5:
            return Sentiment.VERY_NEGATIVE
        elif normalized_score <= -0.2:
            return Sentiment.NEGATIVE
        else:
            return Sentiment.NEUTRAL


class NLUEngine:
    """
    Complete NLU processing engine.

    Combines intent classification, entity extraction, and sentiment analysis
    with constitutional governance integration.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier | None = None,
        entity_extractor: EntityExtractor | None = None,
        sentiment_analyzer: SentimentAnalyzer | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        confidence_threshold: float = 0.65,
    ):
        self.intent_classifier = intent_classifier or RuleBasedIntentClassifier()
        self.entity_extractor = entity_extractor or PatternEntityExtractor()
        self.sentiment_analyzer = sentiment_analyzer or BasicSentimentAnalyzer()
        self.constitutional_hash = constitutional_hash
        self.confidence_threshold = confidence_threshold

    async def process(
        self,
        text: str,
        context: JSONDict | None = None,
    ) -> NLUResult:
        """
        Process text through full NLU pipeline.

        Args:
            text: Input text to process
            context: Optional conversation context

        Returns:
            NLUResult with intents, entities, sentiment
        """
        start_time = time.perf_counter()

        # Preprocess text
        processed_text = self._preprocess(text)

        # Classify intent
        intents = await self.intent_classifier.classify(processed_text, context)
        primary_intent = intents[0] if intents else None
        secondary_intents = intents[1:] if len(intents) > 1 else []

        # Extract entities
        entities = await self.entity_extractor.extract(processed_text, context)

        # Analyze sentiment
        sentiment_str = await self.sentiment_analyzer.analyze(processed_text, context)
        # Map string back to enum for NLUResult
        sentiment_map = {
            "positive": Sentiment.POSITIVE,
            "negative": Sentiment.NEGATIVE,
            "neutral": Sentiment.NEUTRAL,
        }
        sentiment = sentiment_map.get(sentiment_str, Sentiment.NEUTRAL)
        sentiment_score = (
            0.5 if sentiment_str == "positive" else (-0.5 if sentiment_str == "negative" else 0.0)
        )

        # Detect language (simplified - just English detection)
        language = self._detect_language(text)

        # Calculate overall confidence
        confidence = self._calculate_confidence(primary_intent, entities)

        # Determine if clarification is needed
        requires_clarification = self._needs_clarification(
            primary_intent, secondary_intents, confidence
        )

        processing_time = (time.perf_counter() - start_time) * 1000

        return NLUResult(
            original_text=text,
            processed_text=processed_text,
            primary_intent=primary_intent,
            secondary_intents=secondary_intents,
            entities=entities,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            language=language,
            confidence=confidence,
            requires_clarification=requires_clarification,
            constitutional_hash=self.constitutional_hash,
            processing_time_ms=processing_time,
        )

    def _preprocess(self, text: str) -> str:
        """Preprocess text for NLU."""
        # Remove extra whitespace
        text = " ".join(text.split())

        # Basic normalization
        text = text.strip()

        return text

    def _detect_language(self, text: str) -> str:
        """Simple language detection."""
        # This is a placeholder - would use a proper language detection library
        return "en"

    def _calculate_confidence(
        self,
        primary_intent: Intent | None,
        entities: list[Entity],
    ) -> float:
        """Calculate overall NLU confidence."""
        if not primary_intent:
            return 0.0

        intent_confidence = primary_intent.confidence

        # Boost confidence if entities were found
        if entities:
            entity_boost = min(0.1, len(entities) * 0.02)
            intent_confidence = min(1.0, intent_confidence + entity_boost)

        return intent_confidence

    def _needs_clarification(
        self,
        primary_intent: Intent | None,
        secondary_intents: list[Intent],
        confidence: float,
    ) -> bool:
        """Determine if clarification is needed."""
        # Unknown intent
        if not primary_intent or primary_intent.name == "unknown":
            return True

        # Low confidence
        if confidence < self.confidence_threshold:
            return True

        # Competing intents with similar confidence
        if secondary_intents:
            for secondary in secondary_intents:
                if primary_intent.confidence - secondary.confidence < 0.15:
                    return True

        return False

    def add_intent_pattern(self, intent_name: str, patterns: list[str]) -> None:
        """Add or update intent patterns."""
        if isinstance(self.intent_classifier, RuleBasedIntentClassifier):
            self.intent_classifier.intent_patterns[intent_name] = patterns
            self.intent_classifier._compiled_patterns = self.intent_classifier._compile_patterns()

    def add_entity_pattern(self, entity_type: str, pattern: str) -> None:
        """Add or update entity pattern."""
        if isinstance(self.entity_extractor, PatternEntityExtractor):
            self.entity_extractor.patterns[entity_type] = pattern
            self.entity_extractor._compiled_patterns = self.entity_extractor._compile_patterns()
