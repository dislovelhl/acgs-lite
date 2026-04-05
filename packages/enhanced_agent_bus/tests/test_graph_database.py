"""
ACGS-2 Enhanced Agent Bus - Graph Database Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the Graph Database Manager module including:
- GraphDatabaseManager abstract interface
- MockGraphManager implementation
- Factory function testing
- Query operations
- Relationship management
- Multi-hop context retrieval
"""

import asyncio

import pytest

# Import graph database module — skip entire module if GraphDatabaseManager is unavailable
try:
    try:
        from enhanced_agent_bus.graph_database import (
            GraphDatabaseManager,
            MockGraphManager,
            create_graph_db_manager,
        )
    except ImportError:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from graph_database import (
            GraphDatabaseManager,
            MockGraphManager,
            create_graph_db_manager,
        )
except (ImportError, Exception) as _graph_db_import_error:
    pytest.skip(
        f"Skipping graph database tests: GraphDatabaseManager unavailable"
        f" ({_graph_db_import_error})",
        allow_module_level=True,
    )


# Constitutional Hash for validation
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


class TestGraphDatabaseManagerInterface:
    """Test GraphDatabaseManager abstract base class."""

    def test_graph_database_manager_is_abstract(self):
        """Test that GraphDatabaseManager cannot be instantiated directly."""
        with pytest.raises(TypeError):
            GraphDatabaseManager()

    def test_has_required_methods(self):
        """Test that GraphDatabaseManager defines required abstract methods."""
        required_methods = [
            "connect",
            "disconnect",
            "query",
            "add_relationships",
            "get_multi_hop_context",
        ]

        for method_name in required_methods:
            assert hasattr(GraphDatabaseManager, method_name), f"Missing method: {method_name}"

    def test_abstract_methods_are_abstract(self):
        """Test that abstract methods are marked correctly."""
        import inspect

        abstract_methods = []
        for name, method in inspect.getmembers(GraphDatabaseManager):
            if hasattr(method, "__isabstractmethod__") and method.__isabstractmethod__:
                abstract_methods.append(name)

        assert "connect" in abstract_methods
        assert "disconnect" in abstract_methods
        assert "query" in abstract_methods
        assert "add_relationships" in abstract_methods
        assert "get_multi_hop_context" in abstract_methods


class TestMockGraphManager:
    """Test MockGraphManager implementation."""

    @pytest.fixture
    def manager(self):
        """Create a MockGraphManager instance for testing."""
        return MockGraphManager()

    def test_mock_is_graph_database_manager(self, manager):
        """Test that MockGraphManager is a GraphDatabaseManager."""
        assert isinstance(manager, GraphDatabaseManager)

    async def test_connect_returns_true(self, manager):
        """Test that connect returns True."""
        result = await manager.connect()
        assert result is True

    async def test_disconnect_returns_none(self, manager):
        """Test that disconnect returns None (no error)."""
        result = await manager.disconnect()
        assert result is None

    async def test_query_returns_empty_list(self, manager):
        """Test that query returns empty list by default."""
        result = await manager.query("MATCH (n) RETURN n")
        assert result == []
        assert isinstance(result, list)

    async def test_query_with_params(self, manager):
        """Test query with parameters."""
        result = await manager.query("MATCH (n {name: $name}) RETURN n", params={"name": "test"})
        assert isinstance(result, list)

    async def test_query_default_params(self, manager):
        """Test query with default None params."""
        result = await manager.query("MATCH (n) RETURN n")
        assert isinstance(result, list)

    async def test_add_relationships_returns_true(self, manager):
        """Test that add_relationships returns True."""
        entities = [{"id": "1", "type": "Person", "name": "Alice"}]
        relationships = [{"from": "1", "to": "2", "type": "KNOWS"}]

        result = await manager.add_relationships(entities, relationships)
        assert result is True

    async def test_add_relationships_empty_lists(self, manager):
        """Test add_relationships with empty lists."""
        result = await manager.add_relationships([], [])
        assert result is True

    async def test_add_relationships_multiple_entities(self, manager):
        """Test add_relationships with multiple entities."""
        entities = [
            {"id": "1", "type": "Person"},
            {"id": "2", "type": "Company"},
            {"id": "3", "type": "Product"},
        ]
        relationships = [
            {"from": "1", "to": "2", "type": "WORKS_AT"},
            {"from": "2", "to": "3", "type": "PRODUCES"},
        ]

        result = await manager.add_relationships(entities, relationships)
        assert result is True


class TestMultiHopContext:
    """Test multi-hop context retrieval."""

    @pytest.fixture
    def manager(self):
        """Create a MockGraphManager instance for testing."""
        return MockGraphManager()

    async def test_get_multi_hop_context_supply_chain(self, manager):
        """Test multi-hop context for supply chain entity."""
        result = await manager.get_multi_hop_context("supply chain")

        assert isinstance(result, list)
        assert len(result) > 0

        # Check first result
        first_result = result[0]
        assert "entity" in first_result
        assert "relation" in first_result
        assert "target" in first_result

    async def test_get_multi_hop_context_supply_chain_case_insensitive(self, manager):
        """Test that supply chain matching is case insensitive."""
        variations = ["Supply Chain", "SUPPLY CHAIN", "supply chain"]

        for variation in variations:
            result = await manager.get_multi_hop_context(variation)
            assert len(result) > 0, f"Failed for: {variation}"

    async def test_get_multi_hop_context_unknown_entity(self, manager):
        """Test multi-hop context for unknown entity returns empty list."""
        result = await manager.get_multi_hop_context("unknown_entity")
        assert result == []

    async def test_get_multi_hop_context_default_hops(self, manager):
        """Test multi-hop context with default hops value."""
        result = await manager.get_multi_hop_context("supply chain")
        # Default hops is 2, should return data
        assert isinstance(result, list)

    async def test_get_multi_hop_context_custom_hops(self, manager):
        """Test multi-hop context with custom hops value."""
        result = await manager.get_multi_hop_context("supply chain", hops=3)
        assert isinstance(result, list)

    async def test_get_multi_hop_context_supply_chain_relations(self, manager):
        """Test that supply chain returns expected relations."""
        result = await manager.get_multi_hop_context("supply chain")

        relations = [r["relation"] for r in result]
        assert "EXTENDS_TO" in relations
        assert "HAS_RISK" in relations

    async def test_get_multi_hop_context_structure(self, manager):
        """Test structure of multi-hop context results."""
        result = await manager.get_multi_hop_context("supply chain")

        for item in result:
            assert "entity" in item
            assert "relation" in item
            assert "target" in item


class TestCreateGraphDbManager:
    """Test factory function for graph database managers."""

    def test_create_mock_manager(self):
        """Test creating a mock manager."""
        manager = create_graph_db_manager("mock")
        assert isinstance(manager, MockGraphManager)

    def test_create_mock_manager_case_insensitive(self):
        """Test case-insensitive manager type."""
        for type_name in ["Mock", "MOCK", "MoCk"]:
            manager = create_graph_db_manager(type_name)
            assert isinstance(manager, MockGraphManager)

    def test_default_is_mock(self):
        """Test that default manager type is mock."""
        manager = create_graph_db_manager()
        assert isinstance(manager, MockGraphManager)

    def test_unknown_type_raises_error(self):
        """Test that unknown type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            create_graph_db_manager("neo4j")

        assert "Unsupported graph database type" in str(exc_info.value)
        assert "neo4j" in str(exc_info.value)

    def test_empty_type_raises_error(self):
        """Test that empty type raises ValueError."""
        with pytest.raises(ValueError):
            create_graph_db_manager("")


class TestConnectionLifecycle:
    """Test connection lifecycle operations."""

    @pytest.fixture
    def manager(self):
        """Create a MockGraphManager instance for testing."""
        return MockGraphManager()

    async def test_full_lifecycle(self, manager):
        """Test full connection lifecycle."""
        # Connect
        connected = await manager.connect()
        assert connected is True

        # Execute query
        result = await manager.query("MATCH (n) RETURN n")
        assert isinstance(result, list)

        # Disconnect
        await manager.disconnect()
        # No error means success

    async def test_multiple_queries_after_connect(self, manager):
        """Test multiple queries in single session."""
        await manager.connect()

        queries = [
            "MATCH (n) RETURN n",
            "MATCH (n:Person) RETURN n",
            "MATCH (n)-[r]->(m) RETURN n, r, m",
        ]

        for query in queries:
            result = await manager.query(query)
            assert isinstance(result, list)

        await manager.disconnect()


class TestConcurrentOperations:
    """Test concurrent database operations."""

    async def test_concurrent_queries(self):
        """Test multiple concurrent queries."""
        manager = MockGraphManager()
        await manager.connect()

        tasks = [manager.query(f"MATCH (n) WHERE n.id = {i} RETURN n") for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            assert isinstance(result, list)

        await manager.disconnect()

    async def test_concurrent_multi_hop_queries(self):
        """Test concurrent multi-hop context queries."""
        manager = MockGraphManager()

        entities = ["supply chain", "unknown", "supply chain analysis"]
        tasks = [manager.get_multi_hop_context(entity) for entity in entities]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3

    async def test_concurrent_add_relationships(self):
        """Test concurrent add_relationships calls."""
        manager = MockGraphManager()

        tasks = [
            manager.add_relationships(
                [{"id": str(i), "type": "Node"}],
                [{"from": str(i), "to": str(i + 1), "type": "CONNECTS"}],
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        assert all(result is True for result in results)


class TestQueryParameters:
    """Test query parameter handling."""

    @pytest.fixture
    def manager(self):
        """Create a MockGraphManager instance for testing."""
        return MockGraphManager()

    async def test_query_with_string_param(self, manager):
        """Test query with string parameter."""
        result = await manager.query("MATCH (n {name: $name}) RETURN n", params={"name": "Alice"})
        assert isinstance(result, list)

    async def test_query_with_int_param(self, manager):
        """Test query with integer parameter."""
        result = await manager.query("MATCH (n) WHERE n.age = $age RETURN n", params={"age": 30})
        assert isinstance(result, list)

    async def test_query_with_multiple_params(self, manager):
        """Test query with multiple parameters."""
        result = await manager.query(
            "MATCH (n) WHERE n.name = $name AND n.age = $age RETURN n",
            params={"name": "Alice", "age": 30},
        )
        assert isinstance(result, list)

    async def test_query_with_list_param(self, manager):
        """Test query with list parameter."""
        result = await manager.query(
            "MATCH (n) WHERE n.id IN $ids RETURN n", params={"ids": [1, 2, 3]}
        )
        assert isinstance(result, list)


class TestRelationshipOperations:
    """Test relationship operations."""

    @pytest.fixture
    def manager(self):
        """Create a MockGraphManager instance for testing."""
        return MockGraphManager()

    async def test_add_single_entity_single_relationship(self, manager):
        """Test adding single entity with single relationship."""
        entities = [{"id": "1", "type": "Person", "name": "Alice"}]
        relationships = [{"from": "1", "to": "2", "type": "KNOWS"}]

        result = await manager.add_relationships(entities, relationships)
        assert result is True

    async def test_add_complex_graph_structure(self, manager):
        """Test adding complex graph structure."""
        entities = [
            {"id": "1", "type": "Person", "name": "Alice"},
            {"id": "2", "type": "Person", "name": "Bob"},
            {"id": "3", "type": "Company", "name": "ACME"},
            {"id": "4", "type": "Product", "name": "Widget"},
        ]
        relationships = [
            {"from": "1", "to": "3", "type": "WORKS_AT"},
            {"from": "2", "to": "3", "type": "WORKS_AT"},
            {"from": "3", "to": "4", "type": "PRODUCES"},
            {"from": "1", "to": "2", "type": "KNOWS"},
        ]

        result = await manager.add_relationships(entities, relationships)
        assert result is True

    async def test_add_entities_only(self, manager):
        """Test adding entities without relationships."""
        entities = [
            {"id": "1", "type": "Node"},
            {"id": "2", "type": "Node"},
        ]

        result = await manager.add_relationships(entities, [])
        assert result is True


class TestConstitutionalCompliance:
    """Test constitutional compliance in graph operations."""

    def test_constitutional_hash_in_module(self):
        """Test that module has constitutional hash in docstring."""
        try:
            from enhanced_agent_bus import graph_database
        except ImportError:
            import graph_database

        assert CONSTITUTIONAL_HASH in graph_database.__doc__

    async def test_operations_succeed_with_valid_data(self):
        """Test that all operations succeed with valid input."""
        manager = MockGraphManager()

        # Connect
        assert await manager.connect() is True

        # Query
        result = await manager.query("MATCH (n) RETURN n")
        assert isinstance(result, list)

        # Add relationships
        assert (
            await manager.add_relationships(
                [{"id": "1"}], [{"from": "1", "to": "2", "type": "REL"}]
            )
            is True
        )

        # Multi-hop context
        context = await manager.get_multi_hop_context("supply chain")
        assert isinstance(context, list)

        # Disconnect
        await manager.disconnect()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def manager(self):
        """Create a MockGraphManager instance for testing."""
        return MockGraphManager()

    async def test_empty_query_string(self, manager):
        """Test query with empty string."""
        result = await manager.query("")
        assert result == []

    async def test_very_long_query(self, manager):
        """Test query with very long string."""
        long_query = "MATCH " + "(n)-[r]->(m)" * 100 + " RETURN n"
        result = await manager.query(long_query)
        assert isinstance(result, list)

    async def test_special_characters_in_query(self, manager):
        """Test query with special characters."""
        result = await manager.query("MATCH (n {name: '!@#$%^&*()'}) RETURN n")
        assert isinstance(result, list)

    async def test_unicode_in_query(self, manager):
        """Test query with unicode characters."""
        result = await manager.query("MATCH (n {name: '\u4e2d\u6587\u6d4b\u8bd5'}) RETURN n")
        assert isinstance(result, list)

    async def test_multi_hop_with_zero_hops(self, manager):
        """Test multi-hop context with zero hops."""
        result = await manager.get_multi_hop_context("supply chain", hops=0)
        assert isinstance(result, list)

    async def test_multi_hop_with_large_hops(self, manager):
        """Test multi-hop context with large number of hops."""
        result = await manager.get_multi_hop_context("supply chain", hops=100)
        assert isinstance(result, list)
