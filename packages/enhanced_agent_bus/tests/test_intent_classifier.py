"""
Unit tests for SDPC IntentClassifier.
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, patch

from enhanced_agent_bus.deliberation_layer.intent_classifier import (
    ClassificationResult,
    IntentClassifier,
    IntentType,
    RoutingPath,
)


def test_classify_factual():
    classifier = IntentClassifier()
    assert classifier.classify("Tell me about the history of Rome") == IntentType.FACTUAL
    assert classifier.classify("Who is the president of France?") == IntentType.FACTUAL


def test_classify_reasoning():
    classifier = IntentClassifier()
    assert (
        classifier.classify("Analyze the impact of climate change on agriculture")
        == IntentType.REASONING
    )
    assert classifier.classify("Calculate the derivative of x^2") == IntentType.REASONING


def test_classify_creative():
    classifier = IntentClassifier()
    assert classifier.classify("Write a poem about the sea") == IntentType.CREATIVE
    assert classifier.classify("Imagine a world where dragons exist") == IntentType.CREATIVE


def test_classify_general():
    classifier = IntentClassifier()
    assert classifier.classify("Hello, how are you?") == IntentType.GENERAL
    assert classifier.classify("Remind me to buy milk") == IntentType.GENERAL


async def test_classify_async_heuristic():
    classifier = IntentClassifier()
    result = await classifier.classify_async("What happened in 1989?")
    assert result == IntentType.FACTUAL


async def test_llm_classification_ambiguous():
    """Test LLM classification is invoked for ambiguous low-confidence inputs."""
    # Create classifier with LLM enabled and low threshold to trigger LLM path
    classifier = IntentClassifier(
        llm_enabled=True,
        llm_confidence_threshold=0.8,  # Threshold above BASE_CONFIDENCE (0.7)
    )

    # Mock LLM client as initialized
    classifier._llm_client_initialized = True

    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": '{"intent": "REASONING", "confidence": 0.85, "reasoning": "Query requires analysis"}'
                }
            }
        ]
    }

    # Both patches must be active simultaneously when classify_async is called.
    # Use classifier's own module path to avoid dual-import alias mismatch.
    _mod = IntentClassifier.__module__
    with (
        patch(f"{_mod}.LITELLM_AVAILABLE", True),
        patch(
            f"{_mod}.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ) as mock_acompletion,
    ):
        result = await classifier.classify_async("Help me understand this concept")

        # Verify LLM was called since confidence (0.5) < threshold (0.8)
        mock_acompletion.assert_called_once()

        # Verify LLM result was used (REASONING from mock)
        assert result == IntentType.REASONING


async def test_llm_classification_fallback_on_failure():
    """Test fallback to rule-based when LLM fails."""
    classifier = IntentClassifier(
        llm_enabled=True,
        llm_confidence_threshold=0.8,
    )
    classifier._llm_client_initialized = True

    # Mock LLM to raise an exception; use classifier's own module path
    _mod = IntentClassifier.__module__
    with (
        patch(f"{_mod}.LITELLM_AVAILABLE", True),
        patch(
            f"{_mod}.litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM API error"),
        ),
    ):
        # Query with some factual keyword but low confidence
        result = await classifier.classify_async("What about this thing?")

        # Should fallback to rule-based result (GENERAL for this query)
        assert result == IntentType.GENERAL


async def test_llm_classification_with_metadata():
    """Test classify_async_with_metadata returns proper routing metadata."""
    classifier = IntentClassifier(
        llm_enabled=True,
        llm_confidence_threshold=0.8,
    )
    classifier._llm_client_initialized = True

    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": '{"intent": "CREATIVE", "confidence": 0.9, "reasoning": "Creative request"}'
                }
            }
        ]
    }

    _mod = IntentClassifier.__module__
    with (
        patch(f"{_mod}.LITELLM_AVAILABLE", True),
        patch(
            f"{_mod}.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ),
    ):
        result = await classifier.classify_async_with_metadata("Make something interesting")

        assert isinstance(result, ClassificationResult)
        assert result.intent == IntentType.CREATIVE
        assert result.routing_path == RoutingPath.LLM
        assert result.llm_confidence == 0.9
        assert result.llm_reasoning == "Creative request"


async def test_llm_skipped_for_high_confidence():
    """Test LLM is NOT invoked when rule-based confidence is high."""
    classifier = IntentClassifier(
        llm_enabled=True,
        llm_confidence_threshold=0.6,  # Lower than BASE_CONFIDENCE (0.7)
    )
    classifier._llm_client_initialized = True

    with patch(
        "enhanced_agent_bus.deliberation_layer.intent_classifier.litellm.acompletion",
        new_callable=AsyncMock,
    ) as mock_acompletion:
        # Query with strong factual keywords - high confidence
        result = await classifier.classify_async("Tell me about the history of Rome")

        # Verify LLM was NOT called since confidence (0.7+) >= threshold (0.6)
        mock_acompletion.assert_not_called()

        # Verify rule-based result was used
        assert result == IntentType.FACTUAL


async def test_llm_fallback_on_error():
    """Test LLM fallback to rule-based when LLM returns an error.

    Verifies that when LLM classification fails (raises exception, returns None,
    or returns malformed response), the system gracefully falls back to rule-based
    classification with proper routing metadata.
    """
    classifier = IntentClassifier(
        llm_enabled=True,
        llm_confidence_threshold=0.8,  # High threshold to ensure LLM path is triggered
    )
    classifier._llm_client_initialized = True

    # Force LITELLM_AVAILABLE to True for tests
    with patch("enhanced_agent_bus.deliberation_layer.intent_classifier.LITELLM_AVAILABLE", True):
        # Test Case 1: LLM raises an exception
        with patch(
            "enhanced_agent_bus.deliberation_layer.intent_classifier.litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API connection error"),
        ):
            result = await classifier.classify_async_with_metadata("Help me with something")

            # Verify fallback to rule-based classification
            assert isinstance(result, ClassificationResult)
            assert result.routing_path == RoutingPath.LLM_FALLBACK
            assert result.intent == IntentType.GENERAL  # Default for ambiguous input
            assert result.rule_based_intent == IntentType.GENERAL
            assert result.rule_based_confidence == classifier.DEFAULT_CONFIDENCE
            # LLM fields should be None since LLM failed
            assert result.llm_intent is None
            assert result.llm_confidence is None
            assert result.llm_reasoning is None

        # Test Case 2: LLM returns empty response
        with patch(
            "enhanced_agent_bus.deliberation_layer.intent_classifier.litellm.acompletion",
            new_callable=AsyncMock,
            return_value={"choices": []},  # Empty choices
        ):
            result = await classifier.classify_async_with_metadata("Process this data")

            assert result.routing_path == RoutingPath.LLM_FALLBACK
            assert result.intent == IntentType.GENERAL
            assert result.llm_intent is None

        # Test Case 3: LLM returns malformed response
        with patch(
            "enhanced_agent_bus.deliberation_layer.intent_classifier.litellm.acompletion",
            new_callable=AsyncMock,
            return_value={"choices": [{"message": {"content": "invalid json"}}]},
        ):
            result = await classifier.classify_async_with_metadata("Another query")

            assert result.routing_path == RoutingPath.LLM_FALLBACK
            assert result.intent == IntentType.GENERAL
            assert result.llm_intent is None
