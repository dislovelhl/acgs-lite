"""
Unit tests for AMPOEngine.
Constitutional Hash: cdd01ef066bc6cf2
"""

from enhanced_agent_bus.deliberation_layer.intent_classifier import IntentType
from enhanced_agent_bus.sdpc.ampo_engine import AMPOEngine


def test_ampo_factual_compilation():
    engine = AMPOEngine()
    prompt = engine.compile(IntentType.FACTUAL, "What is GDP?")
    assert "factual precision agent" in prompt
    assert "GROUNDING" in prompt
    assert "What is GDP?" in prompt


def test_ampo_creative_compilation():
    engine = AMPOEngine()
    prompt = engine.compile(IntentType.CREATIVE, "Write a poem")
    assert "creative assistant" in prompt
    assert "Write a poem" in prompt


def test_ampo_reasoning_compilation():
    engine = AMPOEngine()
    prompt = engine.compile(IntentType.REASONING, "Solve for x")
    assert "reasoning agent" in prompt
    assert "step-by-step logic" in prompt
