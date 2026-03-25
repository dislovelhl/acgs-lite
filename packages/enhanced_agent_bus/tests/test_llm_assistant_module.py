"""
ACGS-2 Enhanced Agent Bus - LLM Assistant Module Tests
Constitutional Hash: 608508a9bd224290

Tests for the LLM assistant module with mocked LLM dependencies.
"""

import importlib.util
import os
import sys
import types
from typing import ClassVar

import pytest

# Add enhanced_agent_bus directory to path
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

_ORIGINAL_MODULES = {
    "enhanced_agent_bus": sys.modules.get("enhanced_agent_bus"),
    "enhanced_agent_bus.models": sys.modules.get("enhanced_agent_bus.models"),
}


def _load_module(name, path):
    """Load a module directly from path."""
    if "enhanced_agent_bus" not in sys.modules:
        pkg = types.ModuleType("enhanced_agent_bus")
        pkg.__path__ = [enhanced_agent_bus_dir]
        pkg.__file__ = os.path.join(enhanced_agent_bus_dir, "__init__.py")
        pkg.__package__ = "enhanced_agent_bus"
        sys.modules["enhanced_agent_bus"] = pkg
    qualified_name = f"enhanced_agent_bus.{name}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "enhanced_agent_bus"
    sys.modules[qualified_name] = module
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load base models first
_models = _load_module("_llm_test_models", os.path.join(enhanced_agent_bus_dir, "models.py"))


# Create mock parent package that can function as a Python package
class MockEnhancedAgentBus:
    """Mock package that provides all required module attributes for import system."""

    __path__: ClassVar[list] = [enhanced_agent_bus_dir]  # Required for package submodule imports
    __name__ = "enhanced_agent_bus"
    __file__ = os.path.join(enhanced_agent_bus_dir, "__init__.py")
    __spec__ = None  # Mock spec
    __loader__ = None
    __package__ = "enhanced_agent_bus"


mock_parent = MockEnhancedAgentBus()
mock_parent.models = _models


def _patch_modules() -> None:
    sys.modules["enhanced_agent_bus"] = mock_parent
    sys.modules["enhanced_agent_bus.models"] = _models


def _restore_modules() -> None:
    for name, original in _ORIGINAL_MODULES.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


# Import from models
AgentMessage = _models.AgentMessage
MessageType = _models.MessageType
MessageStatus = _models.MessageStatus
Priority = _models.Priority
CONSTITUTIONAL_HASH = _models.CONSTITUTIONAL_HASH

_patch_modules()
try:
    # Load the actual llm_assistant module
    _llm_assistant = _load_module(
        "_llm_assistant_actual",
        os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "llm_assistant.py"),
    )
finally:
    _restore_modules()

LLMAssistant = _llm_assistant.LLMAssistant
get_llm_assistant = _llm_assistant.get_llm_assistant


class TestLLMAssistantInitialization:
    """Tests for LLMAssistant initialization."""

    def test_default_initialization(self):
        """Test default initialization without API key."""
        assistant = LLMAssistant()

        assert assistant.model_name == "gpt-5.4"
        # LLM may or may not be initialized depending on environment

    def test_custom_model_name(self):
        """Test initialization with custom model name."""
        assistant = LLMAssistant(model_name="gpt-5-mini")

        assert assistant.model_name == "gpt-5-mini"

    def test_initialization_without_langchain(self):
        """Test assistant works when LangChain is not available."""
        # This is the fallback scenario
        assistant = LLMAssistant()

        # Should still be able to use fallback methods
        assert assistant is not None


class TestFallbackAnalysis:
    """Tests for fallback analysis when LLM is not available."""

    @pytest.fixture
    def assistant(self):
        """Create an assistant without LLM."""
        assistant = LLMAssistant()
        assistant.llm = None  # Ensure fallback mode
        return assistant

    @pytest.fixture
    def test_message(self):
        """Create a test message."""
        return AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test_action"},
        )

    async def test_fallback_analysis_basic(self, assistant, test_message):
        """Test fallback analysis returns valid structure."""
        result = await assistant.analyze_message_impact(test_message)

        assert "risk_level" in result
        assert "requires_human_review" in result
        assert "recommended_decision" in result
        assert "confidence" in result
        assert "reasoning" in result
        assert "impact_areas" in result
        assert result["analyzed_by"] == "enhanced_fallback_analyzer"

    async def test_fallback_analysis_low_risk(self, assistant):
        """Test enhanced fallback analysis for low-risk content."""
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={"action": "ping"},
        )

        result = await assistant.analyze_message_impact(message)

        # Enhanced fallback now properly detects low-risk vs medium-risk
        assert result["risk_level"] == "low"
        assert result["requires_human_review"] is False
        assert result["recommended_decision"] == "approve"

    async def test_fallback_analysis_high_risk(self, assistant):
        """Test enhanced fallback analysis for high-risk content.

        'breach' is now classified as CRITICAL (highest risk tier).
        """
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "critical security breach detected"},
        )

        result = await assistant.analyze_message_impact(message)

        # Enhanced fallback now uses multi-tier risk classification
        # 'breach' is a critical keyword, 'critical' is a high keyword
        assert result["risk_level"] == "critical"
        assert result["requires_human_review"] is True
        assert result["recommended_decision"] == "review"

    async def test_fallback_analysis_emergency(self, assistant):
        """Test fallback analysis for emergency content."""
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "emergency response required"},
        )

        result = await assistant.analyze_message_impact(message)

        assert result["risk_level"] == "high"
        assert result["requires_human_review"] is True


class TestFallbackReasoning:
    """Tests for fallback reasoning generation."""

    @pytest.fixture
    def assistant(self):
        """Create an assistant without LLM."""
        assistant = LLMAssistant()
        assistant.llm = None
        return assistant

    @pytest.fixture
    def test_message(self):
        """Create a test message."""
        return AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test_action"},
        )

    async def test_fallback_reasoning_no_votes(self, assistant, test_message):
        """Test fallback reasoning with no votes."""
        votes = []

        result = await assistant.generate_decision_reasoning(
            message=test_message, votes=votes, human_decision=None
        )

        assert "process_summary" in result
        assert "consensus_analysis" in result
        assert "final_recommendation" in result
        assert result["generated_by"] == "enhanced_fallback_reasoner"

    async def test_fallback_reasoning_with_votes(self, assistant, test_message):
        """Test enhanced fallback reasoning with votes."""
        votes = [
            {"vote": "approve", "reasoning": "Looks good"},
            {"vote": "approve", "reasoning": "Valid"},
            {"vote": "reject", "reasoning": "Concerns"},
        ]

        result = await assistant.generate_decision_reasoning(
            message=test_message, votes=votes, human_decision=None
        )

        # Enhanced fallback provides detailed percentage-based analysis
        assert "66.7%" in result["consensus_analysis"]
        assert result["final_recommendation"] == "approve"  # 66% approval - moderate consensus

    async def test_fallback_reasoning_with_human_decision(self, assistant, test_message):
        """Test fallback reasoning respects human decision."""
        votes = [
            {"vote": "approve", "reasoning": "Looks good"},
        ]

        result = await assistant.generate_decision_reasoning(
            message=test_message, votes=votes, human_decision="rejected"
        )

        assert result["final_recommendation"] == "rejected"

    async def test_fallback_reasoning_low_approval(self, assistant, test_message):
        """Test fallback reasoning with low approval rate."""
        votes = [
            {"vote": "reject", "reasoning": "Bad"},
            {"vote": "reject", "reasoning": "No"},
            {"vote": "approve", "reasoning": "Maybe"},
        ]

        result = await assistant.generate_decision_reasoning(
            message=test_message, votes=votes, human_decision=None
        )

        # 33% approval rate is below 60% threshold
        assert result["final_recommendation"] == "review"


class TestTrendAnalysis:
    """Tests for trend analysis functionality."""

    @pytest.fixture
    def assistant(self):
        """Create an assistant without LLM."""
        assistant = LLMAssistant()
        assistant.llm = None
        return assistant

    async def test_trend_analysis_empty_history(self, assistant):
        """Test trend analysis with no history."""
        result = await assistant.analyze_deliberation_trends([])

        assert "patterns" in result
        assert "threshold_recommendations" in result
        assert result["threshold_recommendations"] == "Maintain current threshold"

    async def test_trend_analysis_high_approval(self, assistant):
        """Test trend analysis with high approval rate."""
        history = [{"outcome": "approved", "impact_score": 0.7} for _ in range(10)]

        result = await assistant.analyze_deliberation_trends(history)

        # High approval rate should suggest lowering threshold
        assert "lower" in result["threshold_recommendations"].lower()

    async def test_trend_analysis_low_approval(self, assistant):
        """Test trend analysis with low approval rate."""
        history = [{"outcome": "rejected", "impact_score": 0.8} for _ in range(8)] + [
            {"outcome": "approved", "impact_score": 0.6} for _ in range(2)
        ]

        result = await assistant.analyze_deliberation_trends(history)

        # Low approval rate should suggest raising threshold
        assert "raising" in result["threshold_recommendations"].lower()


class TestMessageSummaryExtraction:
    """Tests for message summary extraction."""

    def test_extract_message_summary_basic(self):
        """Test basic message summary extraction."""
        assistant = LLMAssistant()

        message = AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test_action"},
        )

        summary = assistant._extract_message_summary(message)

        assert "Message ID" in summary
        assert "type" in summary.lower()
        assert "governance_request" in summary.lower()
        assert "Content" in summary

    def test_extract_message_summary_long_content(self):
        """Test summary truncation for long content."""
        assistant = LLMAssistant()

        long_content = {"data": "x" * 1000}
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content=long_content,
        )

        summary = assistant._extract_message_summary(message)

        # Content should be truncated with ellipsis
        assert "..." in summary

    def test_extract_message_summary_with_payload(self):
        """Test summary includes payload."""
        assistant = LLMAssistant()

        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            payload={"extra": "data"},
        )

        summary = assistant._extract_message_summary(message)

        assert "Payload" in summary


class TestVoteSummarization:
    """Tests for vote summarization."""

    def test_summarize_votes_empty(self):
        """Test summarizing empty votes list."""
        assistant = LLMAssistant()

        summary = assistant._summarize_votes([])

        assert summary == "No votes recorded"

    def test_summarize_votes_with_data(self):
        """Test summarizing votes with data."""
        assistant = LLMAssistant()

        votes = [
            {"vote": "approve", "reasoning": "Looks good"},
            {"vote": "approve", "reasoning": "Valid request"},
            {"vote": "reject", "reasoning": "Security concerns"},
        ]

        summary = assistant._summarize_votes(votes)

        assert "Total votes: 3" in summary
        assert "Approve: 2" in summary
        assert "Reject: 1" in summary
        assert "Sample reasoning" in summary

    def test_summarize_votes_truncates_reasoning(self):
        """Test that long reasoning is truncated."""
        assistant = LLMAssistant()

        votes = [
            {"vote": "approve", "reasoning": "x" * 200},
        ]

        summary = assistant._summarize_votes(votes)

        assert "..." in summary


class TestDeliberationHistorySummarization:
    """Tests for deliberation history summarization."""

    def test_summarize_empty_history(self):
        """Test summarizing empty history."""
        assistant = LLMAssistant()

        summary = assistant._summarize_deliberation_history([])

        assert "No deliberation history available" in summary

    def test_summarize_history_with_data(self):
        """Test summarizing history with data."""
        assistant = LLMAssistant()

        history = [
            {"outcome": "approved", "impact_score": 0.7},
            {"outcome": "approved", "impact_score": 0.6},
            {"outcome": "rejected", "impact_score": 0.9},
            {"outcome": "timed_out", "impact_score": 0.5},
        ]

        summary = assistant._summarize_deliberation_history(history)

        assert "Total deliberations: 4" in summary
        assert "Approved: 2" in summary
        assert "Rejected: 1" in summary
        assert "Timed out: 1" in summary
        assert "Average impact score" in summary


class TestGlobalSingleton:
    """Tests for global singleton instance."""

    def test_get_llm_assistant_singleton(self):
        """Test LLM assistant singleton."""
        # Reset global instance
        _llm_assistant._llm_assistant = None

        assistant1 = get_llm_assistant()
        assistant2 = get_llm_assistant()

        assert assistant1 is assistant2


class TestFallbackAnalysisKeywords:
    """Tests for keyword detection in fallback analysis."""

    @pytest.fixture
    def assistant(self):
        """Create an assistant without LLM."""
        assistant = LLMAssistant()
        assistant.llm = None
        return assistant

    async def test_critical_keyword(self, assistant):
        """Test 'critical' keyword triggers high risk."""
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content={"action": "critical system update"},
        )

        result = await assistant.analyze_message_impact(message)

        assert result["risk_level"] == "high"

    async def test_security_keyword(self, assistant):
        """Test 'security' keyword triggers high risk."""
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content={"action": "security audit required"},
        )

        result = await assistant.analyze_message_impact(message)

        assert result["risk_level"] == "high"

    async def test_breach_keyword(self, assistant):
        """Test 'breach' keyword triggers critical risk.

        Enhanced fallback classifies 'breach' as critical tier (highest risk).
        """
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content={"description": "potential breach detected"},
        )

        result = await assistant.analyze_message_impact(message)

        # 'breach' is now critical tier
        assert result["risk_level"] == "critical"

    async def test_violation_keyword(self, assistant):
        """Test 'violation' keyword triggers high risk."""
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content={"alert": "policy violation"},
        )

        result = await assistant.analyze_message_impact(message)

        assert result["risk_level"] == "high"


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
