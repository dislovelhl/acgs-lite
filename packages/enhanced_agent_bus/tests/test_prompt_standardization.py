"""
Module.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, MagicMock, patch

# Import LLMAssistant
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.deliberation_layer.llm_assistant import LLMAssistant
from enhanced_agent_bus.models import AgentMessage, MessageType, Priority


async def test_analyze_message_impact_prompt_standardization():
    """Verify that analyze_message_impact uses the standardized prompt template."""
    with (
        patch(
            "enhanced_agent_bus.deliberation_layer.llm_assistant.ChatPromptTemplate"
        ) as mock_prompt_class,
        patch(
            "enhanced_agent_bus.deliberation_layer.llm_assistant.JsonOutputParser"
        ) as mock_parser_class,
    ):
        # Mock LLM
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"risk_level": "low", "recommended_decision": "approve"}'
        mock_llm.ainvoke.return_value = mock_response

        # Mock ChatPromptTemplate.from_template
        mock_template = MagicMock()
        mock_prompt_class.from_template.return_value = mock_template

        # Mock parser
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"risk_level": "low", "recommended_decision": "approve"}
        mock_parser_class.return_value = mock_parser

        assistant = LLMAssistant()
        assistant.llm = mock_llm

        message = AgentMessage(
            message_id="test-123",
            from_agent="test-agent",
            to_agent="governance",
            content={"summary": "Test content"},
            message_type=MessageType.EVENT,
            priority=Priority.NORMAL,
        )

        await assistant.analyze_message_impact(message)

        # Verify ChatPromptTemplate.from_template was called with correct string
        args, _ = mock_prompt_class.from_template.call_args
        template_str = args[0]

        # Updated assertions for chain-of-thought enhanced prompts
        assert (
            "CONSTITUTIONAL CONSTRAINT: All analysis must validate against hash {constitutional_hash}"
            in template_str
        )
        assert "Security Analysis:" in template_str
        assert "Performance Analysis:" in template_str
        assert "Compliance Analysis:" in template_str
        assert "mitigations" in template_str.lower()

        # Verify format_messages was called with hash
        args, kwargs = mock_template.format_messages.call_args
        assert kwargs["constitutional_hash"] == CONSTITUTIONAL_HASH


async def test_generate_decision_reasoning_prompt_standardization():
    """Verify that generate_decision_reasoning uses the standardized prompt template."""
    with (
        patch(
            "enhanced_agent_bus.deliberation_layer.llm_assistant.ChatPromptTemplate"
        ) as mock_prompt_class,
        patch(
            "enhanced_agent_bus.deliberation_layer.llm_assistant.JsonOutputParser"
        ) as mock_parser_class,
    ):
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"reasoning": "test"}'
        mock_llm.ainvoke.return_value = mock_response

        mock_template = MagicMock()
        mock_prompt_class.from_template.return_value = mock_template

        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"reasoning": "test"}
        mock_parser_class.return_value = mock_parser

        assistant = LLMAssistant()
        assistant.llm = mock_llm

        message = AgentMessage(
            message_id="test-123",
            from_agent="test-agent",
            to_agent="governance",
            content={"summary": "Test content"},
            message_type=MessageType.GOVERNANCE_REQUEST,
        )

        await assistant.generate_decision_reasoning(message, [], "approve")

        # Verify template
        args, _ = mock_prompt_class.from_template.call_args
        template_str = args[0]

        # Updated assertions for chain-of-thought enhanced prompts
        assert "**Action Under Review:** {message_type}" in template_str
        assert "DELIBERATION CONTEXT" in template_str
        assert (
            "CONSTITUTIONAL CONSTRAINT: Hash {constitutional_hash} must be validated"
            in template_str
        )

        # Verify hash passed
        _, kwargs = mock_template.format_messages.call_args
        assert kwargs["constitutional_hash"] == CONSTITUTIONAL_HASH
