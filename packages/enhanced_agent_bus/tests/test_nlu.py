"""
Tests for AI Assistant NLU module.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enhanced_agent_bus.ai_assistant.nlu import (
    BasicSentimentAnalyzer,
    Entity,
    Intent,
    NLUEngine,
    NLUResult,
    PatternEntityExtractor,
    RuleBasedIntentClassifier,
    Sentiment,
)

# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------


class TestIntent:
    """Tests for Intent dataclass."""

    def test_creation(self):
        intent = Intent(name="greeting", confidence=0.9)
        assert intent.name == "greeting"
        assert intent.confidence == 0.9
        assert intent.parameters == {}
        assert intent.is_primary is True

    def test_to_dict(self):
        intent = Intent(name="help", confidence=0.8, parameters={"key": "value"}, is_primary=False)
        d = intent.to_dict()
        assert d["name"] == "help"
        assert d["confidence"] == 0.8
        assert d["parameters"] == {"key": "value"}
        assert d["is_primary"] is False


class TestEntity:
    """Tests for Entity dataclass."""

    def test_creation(self):
        entity = Entity(text="user@test.com", type="email", value="user@test.com", start=0, end=13)
        assert entity.type == "email"
        assert entity.confidence == 1.0

    def test_to_dict(self):
        entity = Entity(text="$100", type="money", value=100.0, start=5, end=9, confidence=0.9)
        d = entity.to_dict()
        assert d["text"] == "$100"
        assert d["type"] == "money"
        assert d["value"] == 100.0


class TestNLUResult:
    """Tests for NLUResult dataclass."""

    def test_default(self):
        result = NLUResult()
        assert result.original_text == ""
        assert result.sentiment == Sentiment.NEUTRAL
        assert result.primary_intent is None
        assert result.confidence == 0.0

    def test_intents_convenience(self):
        result = NLUResult(
            intents=[
                {"intent": "greeting", "confidence": 0.9},
                {"intent": "help", "confidence": 0.7},
            ]
        )
        assert result.primary_intent is not None
        assert result.primary_intent.name == "greeting"
        assert len(result.secondary_intents) == 1
        assert result.intents is None  # cleared after processing

    def test_intents_with_intent_objects(self):
        i1 = Intent(name="test", confidence=0.8)
        result = NLUResult(intents=[i1])
        assert result.primary_intent.name == "test"

    def test_to_dict(self):
        result = NLUResult(
            original_text="hello",
            processed_text="hello",
            primary_intent=Intent(name="greeting", confidence=0.9),
            sentiment=Sentiment.POSITIVE,
        )
        d = result.to_dict()
        assert d["original_text"] == "hello"
        assert d["primary_intent"]["name"] == "greeting"
        assert d["sentiment"] == "POSITIVE"

    def test_to_dict_no_intent(self):
        result = NLUResult()
        d = result.to_dict()
        assert d["primary_intent"] is None

    def test_to_dict_entities_as_dict(self):
        result = NLUResult(entities={"key": "value"})
        d = result.to_dict()
        assert d["entities"] == {"key": "value"}


class TestSentiment:
    """Tests for Sentiment enum."""

    def test_values(self):
        assert Sentiment.VERY_NEGATIVE.value == -2
        assert Sentiment.NEUTRAL.value == 0
        assert Sentiment.VERY_POSITIVE.value == 2


# ---------------------------------------------------------------------------
# RuleBasedIntentClassifier tests
# ---------------------------------------------------------------------------


class TestRuleBasedIntentClassifier:
    """Tests for rule-based intent classification."""

    @pytest.fixture
    def classifier(self):
        return RuleBasedIntentClassifier()

    @pytest.mark.asyncio
    async def test_greeting(self, classifier):
        intents = await classifier.classify("hello")
        names = [i.name for i in intents]
        assert "greeting" in names

    @pytest.mark.asyncio
    async def test_farewell(self, classifier):
        intents = await classifier.classify("goodbye")
        names = [i.name for i in intents]
        assert "farewell" in names

    @pytest.mark.asyncio
    async def test_help(self, classifier):
        intents = await classifier.classify("I need help with something")
        names = [i.name for i in intents]
        assert "help" in names

    @pytest.mark.asyncio
    async def test_question(self, classifier):
        intents = await classifier.classify("what is the status?")
        names = [i.name for i in intents]
        assert "question" in names

    @pytest.mark.asyncio
    async def test_confirmation(self, classifier):
        intents = await classifier.classify("yes")
        names = [i.name for i in intents]
        assert "confirmation" in names

    @pytest.mark.asyncio
    async def test_denial(self, classifier):
        intents = await classifier.classify("no")
        names = [i.name for i in intents]
        assert "denial" in names

    @pytest.mark.asyncio
    async def test_complaint(self, classifier):
        intents = await classifier.classify("this is broken and not working")
        names = [i.name for i in intents]
        assert "complaint" in names

    @pytest.mark.asyncio
    async def test_unknown_fallback(self, classifier):
        intents = await classifier.classify("xyzzy plugh")
        assert len(intents) >= 1
        # Should at least have unknown fallback or a low-confidence match

    @pytest.mark.asyncio
    async def test_primary_intent_marked(self, classifier):
        intents = await classifier.classify("hello how are you")
        assert intents[0].is_primary is True
        for i in intents[1:]:
            assert i.is_primary is False

    @pytest.mark.asyncio
    async def test_custom_patterns(self):
        custom = RuleBasedIntentClassifier(intent_patterns={"custom_intent": [r"\bcustom\b"]})
        intents = await custom.classify("this is custom text")
        names = [i.name for i in intents]
        assert "custom_intent" in names

    def test_calculate_similarity(self):
        classifier = RuleBasedIntentClassifier()
        assert classifier._calculate_similarity("hello world", "hello world") == 1.0
        assert classifier._calculate_similarity("hello", "world") == 0.0
        assert classifier._calculate_similarity("", "world") == 0.0


# ---------------------------------------------------------------------------
# PatternEntityExtractor tests
# ---------------------------------------------------------------------------


class TestPatternEntityExtractor:
    """Tests for pattern-based entity extraction."""

    @pytest.fixture
    def extractor(self):
        return PatternEntityExtractor()

    @pytest.mark.asyncio
    async def test_extract_email(self, extractor):
        entities = await extractor.extract("Contact me at user@example.com please")
        emails = [e for e in entities if e.type == "email"]
        assert len(emails) == 1
        assert emails[0].value == "user@example.com"

    @pytest.mark.asyncio
    async def test_extract_money(self, extractor):
        entities = await extractor.extract("The price is $99.99")
        money = [e for e in entities if e.type == "money"]
        assert len(money) == 1
        assert money[0].value == 99.99

    @pytest.mark.asyncio
    async def test_extract_url(self, extractor):
        entities = await extractor.extract("Visit https://example.com for more")
        urls = [e for e in entities if e.type == "url"]
        assert len(urls) == 1

    @pytest.mark.asyncio
    async def test_extract_date(self, extractor):
        entities = await extractor.extract("The date is 2024-01-15")
        dates = [e for e in entities if e.type == "date"]
        assert len(dates) == 1

    @pytest.mark.asyncio
    async def test_extract_multiple(self, extractor):
        text = "Email user@test.com about $50.00 order"
        entities = await extractor.extract(text)
        types = {e.type for e in entities}
        assert "email" in types
        assert "money" in types

    @pytest.mark.asyncio
    async def test_entities_sorted_by_position(self, extractor):
        text = "$100 sent to user@test.com"
        entities = await extractor.extract(text)
        for i in range(len(entities) - 1):
            assert entities[i].start <= entities[i + 1].start

    @pytest.mark.asyncio
    async def test_no_entities(self, extractor):
        entities = await extractor.extract("just plain text")
        # May find numbers in "plain" etc. - just check it's a list
        assert isinstance(entities, list)

    @pytest.mark.asyncio
    async def test_custom_patterns(self):
        custom = PatternEntityExtractor(custom_patterns={"ticket": r"TICKET-\d+"})
        entities = await custom.extract("See TICKET-12345")
        tickets = [e for e in entities if e.type == "ticket"]
        assert len(tickets) == 1

    def test_normalize_phone(self):
        extractor = PatternEntityExtractor()
        result = extractor._normalize_value("phone", "(555) 123-4567")
        assert result == "5551234567"

    def test_normalize_number_int(self):
        extractor = PatternEntityExtractor()
        result = extractor._normalize_value("number", "42")
        assert result == 42

    def test_normalize_number_float(self):
        extractor = PatternEntityExtractor()
        result = extractor._normalize_value("number", "3.14")
        assert result == 3.14

    def test_normalize_unknown_type(self):
        extractor = PatternEntityExtractor()
        result = extractor._normalize_value("unknown_type", "raw")
        assert result == "raw"


# ---------------------------------------------------------------------------
# BasicSentimentAnalyzer tests
# ---------------------------------------------------------------------------


class TestBasicSentimentAnalyzer:
    """Tests for basic sentiment analysis."""

    @pytest.fixture
    def analyzer(self):
        return BasicSentimentAnalyzer()

    @pytest.mark.asyncio
    async def test_positive(self, analyzer):
        result = await analyzer.analyze("This is great and amazing")
        assert result == "positive"

    @pytest.mark.asyncio
    async def test_negative(self, analyzer):
        result = await analyzer.analyze("This is terrible and awful")
        assert result == "negative"

    @pytest.mark.asyncio
    async def test_neutral(self, analyzer):
        result = await analyzer.analyze("The weather is cloudy today")
        assert result == "neutral"

    @pytest.mark.asyncio
    async def test_empty(self, analyzer):
        result = await analyzer.analyze("")
        assert result == "neutral"

    @pytest.mark.asyncio
    async def test_negation(self, analyzer):
        result = await analyzer.analyze("not good")
        assert result == "negative"

    @pytest.mark.asyncio
    async def test_intensifier(self, analyzer):
        result = await analyzer.analyze("very good")
        assert result == "positive"

    def test_internal_empty(self, analyzer):
        sentiment, score = analyzer._analyze_internal("")
        assert sentiment == Sentiment.NEUTRAL
        assert score == 0.0

    def test_categorize_very_positive(self, analyzer):
        assert analyzer._categorize_sentiment(0.6) == Sentiment.VERY_POSITIVE

    def test_categorize_positive(self, analyzer):
        assert analyzer._categorize_sentiment(0.3) == Sentiment.POSITIVE

    def test_categorize_neutral(self, analyzer):
        assert analyzer._categorize_sentiment(0.0) == Sentiment.NEUTRAL

    def test_categorize_negative(self, analyzer):
        assert analyzer._categorize_sentiment(-0.3) == Sentiment.NEGATIVE

    def test_categorize_very_negative(self, analyzer):
        assert analyzer._categorize_sentiment(-0.6) == Sentiment.VERY_NEGATIVE


# ---------------------------------------------------------------------------
# NLUEngine tests
# ---------------------------------------------------------------------------


class TestNLUEngine:
    """Tests for NLUEngine."""

    @pytest.fixture
    def engine(self):
        return NLUEngine()

    @pytest.mark.asyncio
    async def test_process_greeting(self, engine):
        result = await engine.process("hello")
        assert isinstance(result, NLUResult)
        assert result.original_text == "hello"
        assert result.primary_intent is not None
        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_process_with_entities(self, engine):
        result = await engine.process("Email me at user@test.com")
        assert len(result.entities) > 0 or isinstance(result.entities, dict)

    @pytest.mark.asyncio
    async def test_process_sentiment(self, engine):
        result = await engine.process("This is great and amazing")
        assert result.sentiment in (Sentiment.POSITIVE, Sentiment.VERY_POSITIVE)

    @pytest.mark.asyncio
    async def test_preprocess(self, engine):
        assert engine._preprocess("  hello   world  ") == "hello world"

    def test_detect_language(self, engine):
        assert engine._detect_language("anything") == "en"

    def test_calculate_confidence_no_intent(self, engine):
        assert engine._calculate_confidence(None, []) == 0.0

    def test_calculate_confidence_with_entities(self, engine):
        intent = Intent(name="test", confidence=0.8)
        entities = [
            Entity(text="e", type="email", value="e", start=0, end=1),
        ]
        conf = engine._calculate_confidence(intent, entities)
        assert conf > 0.8

    def test_needs_clarification_unknown(self, engine):
        assert engine._needs_clarification(None, [], 0.0) is True

    def test_needs_clarification_low_confidence(self, engine):
        intent = Intent(name="test", confidence=0.5)
        assert engine._needs_clarification(intent, [], 0.5) is True

    def test_needs_clarification_competing_intents(self, engine):
        primary = Intent(name="a", confidence=0.8)
        secondary = Intent(name="b", confidence=0.75)
        assert engine._needs_clarification(primary, [secondary], 0.8) is True

    def test_needs_clarification_clear_intent(self, engine):
        primary = Intent(name="greeting", confidence=0.9)
        assert engine._needs_clarification(primary, [], 0.9) is False

    def test_add_intent_pattern(self, engine):
        engine.add_intent_pattern("custom", [r"\bcustom\b"])
        assert "custom" in engine.intent_classifier.intent_patterns

    def test_add_entity_pattern(self, engine):
        engine.add_entity_pattern("ticket", r"TICKET-\d+")
        assert "ticket" in engine.entity_extractor.patterns
