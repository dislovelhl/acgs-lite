"""
Tests for Cognee Knowledge Graph Integration.

All tests mock the cognee dependency so they run without
cognee installed. Tests validate the module's logic,
state management, and interface contracts.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --- Fixtures ---


@pytest.fixture()
def mock_cognee():
    """Mock the cognee module for testing."""
    mock = MagicMock()
    mock.add = AsyncMock()
    mock.cognify = AsyncMock()
    mock.search = AsyncMock(return_value=[])
    mock.prune = MagicMock()
    mock.prune.prune_data = AsyncMock()
    mock.prune.prune_system = AsyncMock()
    return mock


@pytest.fixture()
def _patch_cognee(mock_cognee):
    """Patch cognee import in cognee_memory module."""
    import enhanced_agent_bus.context_memory.cognee_memory as mod

    with (
        patch.dict("sys.modules", {"cognee": mock_cognee}),
        patch.object(mod, "HAS_COGNEE", True),
    ):
        # Set cognee attribute directly since it may not exist when dep is missing
        original = getattr(mod, "cognee", None)
        mod.cognee = mock_cognee  # type: ignore[attr-defined]
        try:
            yield mock_cognee
        finally:
            if original is None:
                try:
                    delattr(mod, "cognee")
                except AttributeError:
                    pass
            else:
                mod.cognee = original  # type: ignore[attr-defined]


# --- ConstitutionalKnowledgeGraph Tests ---


class TestConstitutionalKnowledgeGraph:
    """Tests for the Cognee knowledge graph wrapper."""

    @pytest.mark.usefixtures("_patch_cognee")
    def test_construction(self):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            CogneeConfig,
            ConstitutionalKnowledgeGraph,
        )

        config = CogneeConfig(graph_backend="networkx")
        graph = ConstitutionalKnowledgeGraph(config=config)

        assert not graph.is_initialized
        assert graph.stats["principles_ingested"] == 0

    def test_construction_without_cognee_raises(self):
        with patch(
            "enhanced_agent_bus.context_memory.cognee_memory.HAS_COGNEE",
            False,
        ):
            from enhanced_agent_bus.context_memory.cognee_memory import (
                ConstitutionalKnowledgeGraph,
            )

            with pytest.raises(RuntimeError, match="cognee is not installed"):
                ConstitutionalKnowledgeGraph()

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_initialize(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()

        assert graph.is_initialized
        mock_cognee.prune.prune_data.assert_not_called()
        mock_cognee.prune.prune_system.assert_not_called()

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_initialize_idempotent(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()
        await graph.initialize()

        # Should only initialize once
        mock_cognee.prune.prune_data.assert_not_called()

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_ingest_principles(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()

        principles = [
            {"id": "P1", "category": "safety", "text": "Do no harm", "weight": 1.0},
            {"id": "P2", "category": "fairness", "text": "Be equitable", "weight": 0.8},
        ]
        count = await graph.ingest_principles(principles)

        assert count == 2
        assert graph.stats["principles_ingested"] == 2
        assert mock_cognee.add.await_count == 2
        mock_cognee.cognify.assert_awaited()

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_ingest_precedents(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()

        decisions = [
            {
                "id": "D1",
                "action": "deploy_model",
                "verdict": "approved",
                "reasoning": "Compliant with safety principle",
                "principle_ids": ["P1"],
            },
        ]
        count = await graph.ingest_precedents(decisions)

        assert count == 1
        assert graph.stats["precedents_ingested"] == 1

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_query_compliance(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        mock_result = MagicMock()
        mock_result.score = 0.95
        mock_cognee.search = AsyncMock(return_value=[mock_result])

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()

        result = await graph.query_compliance("Deploy untested model")

        assert result.query == "Deploy untested model"
        assert len(result.findings) == 1
        assert result.findings[0]["relevance"] == 0.95
        assert result.is_compliant is None
        assert result.latency_ms > 0
        assert graph.stats["queries_executed"] == 1

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_query_compliance_marks_violations_non_compliant(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        mock_result = MagicMock()
        mock_result.score = 0.91
        mock_result.__str__.return_value = "Policy violation: action is non-compliant."
        mock_cognee.search = AsyncMock(return_value=[mock_result])

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()

        result = await graph.query_compliance("Deploy untested model")

        assert result.is_compliant is False
        assert "violation" in result.reasoning.lower()

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_query_compliance_marks_positive_findings_compliant(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        mock_result = MagicMock()
        mock_result.score = 0.88
        mock_result.__str__.return_value = "Approved and compliant with constitutional principles."
        mock_cognee.search = AsyncMock(return_value=[mock_result])

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()

        result = await graph.query_compliance("Deploy reviewed model")

        assert result.is_compliant is True
        assert "compliant" in result.reasoning.lower()

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_add_amendment(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        graph = ConstitutionalKnowledgeGraph()
        await graph.initialize()

        await graph.add_amendment(
            amendment_text="Strengthen safety requirement",
            supersedes_ids=["P1"],
        )

        assert graph.stats["amendments_ingested"] == 1
        mock_cognee.add.assert_awaited()

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_not_initialized_raises(self):
        from enhanced_agent_bus.context_memory.cognee_memory import (
            ConstitutionalKnowledgeGraph,
        )

        graph = ConstitutionalKnowledgeGraph()

        with pytest.raises(RuntimeError, match="not initialized"):
            await graph.ingest_principles([])


# --- CogneeLongTermMemory Tests ---


class TestCogneeLongTermMemory:
    """Tests for the Cognee LTM adapter."""

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_store_episodic(self, mock_cognee):
        from datetime import UTC, datetime

        from enhanced_agent_bus.context_memory.cognee_ltm_adapter import (
            CogneeLongTermMemory,
        )
        from enhanced_agent_bus.context_memory.models import EpisodicMemoryEntry

        ltm = CogneeLongTermMemory()
        await ltm.initialize()

        entry = EpisodicMemoryEntry(
            entry_id="E1",
            session_id="S1",
            tenant_id="T1",
            timestamp=datetime.now(UTC),
            event_type="deploy_model",
            content="Deployed model v2 to production",
            outcome="approved",
            context={"principle_ids": ["P1"]},
        )
        await ltm.store_episodic(entry)

        assert ltm.stats["episodic_stored"] == 1

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_store_semantic(self, mock_cognee):
        from datetime import UTC, datetime

        from enhanced_agent_bus.context_memory.cognee_ltm_adapter import (
            CogneeLongTermMemory,
        )
        from enhanced_agent_bus.context_memory.models import SemanticMemoryEntry

        ltm = CogneeLongTermMemory()
        await ltm.initialize()

        entry = SemanticMemoryEntry(
            entry_id="S1",
            knowledge_type="safety",
            content="All deployments require review",
            confidence=0.95,
            source="constitutional_doc",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await ltm.store_semantic(entry)

        assert ltm.stats["semantic_stored"] == 1

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_recall(self, mock_cognee):
        from enhanced_agent_bus.context_memory.cognee_ltm_adapter import (
            CogneeLongTermMemory,
        )
        from enhanced_agent_bus.context_memory.models import MemoryQuery

        mock_result = MagicMock()
        mock_result.score = 0.9
        mock_cognee.search = AsyncMock(return_value=[mock_result])

        ltm = CogneeLongTermMemory()
        await ltm.initialize()

        query = MemoryQuery(
            query_text="safety requirements for deployment",
            query_type="semantic",
        )
        results = await ltm.recall(query)

        assert len(results) == 1
        assert ltm.stats["queries"] == 1

    @pytest.mark.usefixtures("_patch_cognee")
    @pytest.mark.asyncio()
    async def test_audit_trail(self, mock_cognee):
        from datetime import UTC, datetime

        from enhanced_agent_bus.context_memory.cognee_ltm_adapter import (
            CogneeLongTermMemory,
        )
        from enhanced_agent_bus.context_memory.models import (
            EpisodicMemoryEntry,
            MemoryOperationType,
        )

        ltm = CogneeLongTermMemory()
        await ltm.initialize()

        entry = EpisodicMemoryEntry(
            entry_id="E1",
            session_id="S1",
            tenant_id="T1",
            timestamp=datetime.now(UTC),
            event_type="test",
            content="Test content",
        )
        await ltm.store_episodic(entry)

        ops = ltm.get_operations()
        assert len(ops) == 1
        assert ops[0].operation_type == MemoryOperationType.STORE
        assert ops[0].tenant_id == "T1"


# --- Extension Wrapper Tests ---


class TestExtensionWrappers:
    """Test that _ext_*.py wrappers handle missing deps gracefully."""

    def test_ext_cognee_unavailable(self):
        from enhanced_agent_bus._ext_cognee import COGNEE_AVAILABLE

        # Will be False since cognee is not installed in test env
        assert isinstance(COGNEE_AVAILABLE, bool)

    def test_ext_spacetimedb_unavailable(self):
        from enhanced_agent_bus._ext_spacetimedb import SPACETIMEDB_AVAILABLE

        assert isinstance(SPACETIMEDB_AVAILABLE, bool)

    def test_ext_browser_tool_unavailable(self):
        from enhanced_agent_bus._ext_browser_tool import BROWSER_TOOL_AVAILABLE

        assert isinstance(BROWSER_TOOL_AVAILABLE, bool)
