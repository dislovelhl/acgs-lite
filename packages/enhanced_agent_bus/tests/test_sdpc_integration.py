"""
Integration tests for SDPC Phase 2 Verification Layer

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock

from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import AgentMessage, MessageType


async def test_sdpc_phase2_integration_factual():
    # Initialize processor with MACI disabled for testing SDPC logic
    processor = MessageProcessor(
        enable_maci=False
    )  # test-only: MACI off — testing SDPC integration independently

    # Mock ASC and GraphCheck
    processor.asc_verifier.verify = AsyncMock(return_value={"is_valid": True, "confidence": 0.95})
    processor.graph_check.verify_entities = AsyncMock(
        return_value={"is_valid": True, "results": [{"entity": "test", "status": "grounded"}]}
    )

    # Create a factual message
    message = AgentMessage(
        content={"query": "What is the status of the supply chain in Asia?"},
        message_type=MessageType.QUERY,
        from_agent="user-agent",
        to_agent="research-agent",
    )
    # Simulate high impact score set by router or processor
    message.impact_score = 0.75

    # Process message
    result = await processor.process(message)

    # Verify metadata
    assert result.metadata.get("sdpc_intent") == "factual"
    assert result.metadata.get("sdpc_asc_valid") is True
    assert result.metadata.get("sdpc_graph_grounded") is True
    assert "sdpc_graph_results" in result.metadata


async def test_sdpc_phase2_integration_high_impact():
    # Initialize processor with MACI disabled
    processor = MessageProcessor(
        enable_maci=False
    )  # test-only: MACI off — testing SDPC integration independently

    # Mock PACAR
    processor.pacar_verifier.verify = AsyncMock(
        return_value={"is_valid": True, "confidence": 0.88, "critique": ["No logical gaps found"]}
    )

    # Create a complex reasoning message
    message = AgentMessage(
        content={"task": "Deep analysis of system vulnerabilities"},
        message_type=MessageType.TASK_REQUEST,
        from_agent="admin-agent",
        to_agent="security-agent",
    )
    message.impact_score = 0.85  # Triggers PACAR

    # Process message
    result = await processor.process(message)

    # Verify metadata
    assert result.metadata.get("sdpc_pacar_valid") is True
    # The confidence comes from the mock PACAR verifier which returns 0.88
    assert result.metadata.get("sdpc_pacar_confidence") == 0.88
