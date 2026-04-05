"""
Coverage batch 29a -- tests for:
  1. middlewares/ifc.py (IFCMiddleware, IFCConfig)
  2. src/core/cognitive/graphrag/retrieval/retriever.py (GraphRAGRetriever)
  3. observability/capacity_metrics/latency_decorators.py (track_request_latency, track_async_request_latency)
  4. _ext_mcp.py (import fallback path)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. IFC Middleware
# ---------------------------------------------------------------------------


class TestIFCConfig:
    """Tests for IFCConfig dataclass."""

    def test_default_config(self):
        from enhanced_agent_bus.ifc.labels import Confidentiality, IFCLabel, Integrity
        from enhanced_agent_bus.middlewares.ifc import IFCConfig

        cfg = IFCConfig()
        assert cfg.audit_only is False
        assert cfg.receiver_clearance == IFCLabel()
        assert cfg.receiver_clearance.confidentiality == Confidentiality.PUBLIC
        assert cfg.receiver_clearance.integrity == Integrity.MEDIUM

    def test_custom_config(self):
        from enhanced_agent_bus.ifc.labels import Confidentiality, IFCLabel, Integrity
        from enhanced_agent_bus.middlewares.ifc import IFCConfig

        label = IFCLabel(
            confidentiality=Confidentiality.SECRET,
            integrity=Integrity.TRUSTED,
        )
        cfg = IFCConfig(receiver_clearance=label, audit_only=True)
        assert cfg.audit_only is True
        assert cfg.receiver_clearance.confidentiality == Confidentiality.SECRET


class TestIFCMiddleware:
    """Tests for IFCMiddleware.process()."""

    def _make_context(
        self,
        msg_conf: int = 0,
        msg_int: int = 2,
    ):
        """Build a mock PipelineContext with configurable IFC label."""
        from enhanced_agent_bus.ifc.labels import Confidentiality, IFCLabel, Integrity

        ctx = MagicMock()
        ctx.ifc_label = IFCLabel(
            confidentiality=Confidentiality(msg_conf),
            integrity=Integrity(msg_int),
        )
        ctx.message.message_id = "msg-001"
        ctx.trace_id = "trace-001"
        ctx.add_violation = MagicMock()
        return ctx

    async def test_flow_allowed(self):
        """PUBLIC/MEDIUM -> PUBLIC/MEDIUM should pass without violation."""
        from enhanced_agent_bus.middlewares.ifc import IFCConfig, IFCMiddleware

        mw = IFCMiddleware(config=IFCConfig())
        ctx = self._make_context(msg_conf=0, msg_int=2)

        # _call_next returns the context
        mw._next = None
        result = await mw.process(ctx)

        assert result is ctx
        ctx.add_violation.assert_not_called()

    async def test_confidentiality_violation_fail_closed(self):
        """SECRET -> PUBLIC should raise SecurityException when fail_closed."""
        from enhanced_agent_bus.middlewares.ifc import IFCConfig, IFCMiddleware
        from enhanced_agent_bus.pipeline.exceptions import SecurityException

        cfg = IFCConfig(audit_only=False)
        cfg.fail_closed = True
        mw = IFCMiddleware(config=cfg)
        ctx = self._make_context(msg_conf=3, msg_int=2)  # SECRET

        with pytest.raises(SecurityException):
            await mw.process(ctx)

        ctx.add_violation.assert_called_once()

    async def test_confidentiality_violation_audit_only(self):
        """SECRET -> PUBLIC in audit_only should log but not raise."""
        from enhanced_agent_bus.middlewares.ifc import IFCConfig, IFCMiddleware

        cfg = IFCConfig(audit_only=True)
        mw = IFCMiddleware(config=cfg)
        mw._next = None
        ctx = self._make_context(msg_conf=3, msg_int=2)

        result = await mw.process(ctx)
        assert result is ctx
        ctx.add_violation.assert_called_once()

    async def test_integrity_violation_fail_closed(self):
        """UNTRUSTED -> TRUSTED receiver should raise SecurityException."""
        from enhanced_agent_bus.ifc.labels import Confidentiality, IFCLabel, Integrity
        from enhanced_agent_bus.middlewares.ifc import IFCConfig, IFCMiddleware
        from enhanced_agent_bus.pipeline.exceptions import SecurityException

        receiver = IFCLabel(
            confidentiality=Confidentiality.PUBLIC,
            integrity=Integrity.TRUSTED,
        )
        cfg = IFCConfig(receiver_clearance=receiver, audit_only=False)
        cfg.fail_closed = True
        mw = IFCMiddleware(config=cfg)
        # Message with UNTRUSTED integrity
        ctx = self._make_context(msg_conf=0, msg_int=0)

        with pytest.raises(SecurityException):
            await mw.process(ctx)

    async def test_violation_not_fail_closed(self):
        """Violation with fail_closed=False should not raise."""
        from enhanced_agent_bus.middlewares.ifc import IFCConfig, IFCMiddleware

        cfg = IFCConfig(audit_only=False)
        cfg.fail_closed = False
        mw = IFCMiddleware(config=cfg)
        mw._next = None
        ctx = self._make_context(msg_conf=3, msg_int=2)

        result = await mw.process(ctx)
        assert result is ctx
        ctx.add_violation.assert_called_once()

    async def test_default_config_when_none(self):
        """Passing None config should use defaults."""
        from enhanced_agent_bus.middlewares.ifc import IFCMiddleware

        mw = IFCMiddleware(config=None)
        assert mw.ifc_config.audit_only is False

    async def test_calls_next_middleware(self):
        """After checking IFC, should call the next middleware."""
        from enhanced_agent_bus.middlewares.ifc import IFCConfig, IFCMiddleware

        next_mw = AsyncMock()
        next_mw.config.enabled = True
        next_mw.process = AsyncMock(return_value="next_result")

        mw = IFCMiddleware(config=IFCConfig())
        mw._next = next_mw
        ctx = self._make_context()

        result = await mw.process(ctx)
        assert result == "next_result"
        next_mw.process.assert_awaited_once_with(ctx)


# ---------------------------------------------------------------------------
# 2. GraphRAG Retriever
# ---------------------------------------------------------------------------


class TestGraphRAGRetriever:
    """Tests for GraphRAGRetriever stub."""

    @pytest.fixture(autouse=True)
    def _restore_cognitive_modules(self):
        """Remove any MagicMock patches of src.core.cognitive.* before each test.

        test_cognitive_graph_rag.py inserts MagicMock objects into sys.modules
        for the src.core.cognitive namespace at module load time.  When it runs
        before this class (alphabetical order), those stubs remain in sys.modules
        and cause the real GraphRAGRetriever import to return a MagicMock
        attribute instead of the actual class.  We clear the polluted entries
        before each test so the real modules get imported fresh.
        """
        polluted = [k for k in list(sys.modules) if k.startswith("src.core.cognitive")]
        saved = {k: sys.modules.pop(k) for k in polluted}
        yield
        for k, v in saved.items():
            sys.modules.setdefault(k, v)

    async def test_retrieve_empty_nodes(self):
        from src.core.cognitive.graphrag.retrieval.models import TraversalResult
        from src.core.cognitive.graphrag.retrieval.retriever import GraphRAGRetriever

        retriever = GraphRAGRetriever()
        result = await retriever.retrieve(
            query="test",
            graph_results=TraversalResult(nodes=[], seed_node_ids=[], query="test"),
        )

        assert len(result.ranked_contexts) == 0
        assert result.assembled_context.text == ""

    async def test_retrieve_single_node(self):
        from src.core.cognitive.graphrag.retrieval.models import (
            GraphNode,
            TraversalResult,
        )
        from src.core.cognitive.graphrag.retrieval.retriever import GraphRAGRetriever

        node = GraphNode(id="n1", text_content="Hello world")
        traversal = TraversalResult(nodes=[node], seed_node_ids=["n1"], query="hello")
        retriever = GraphRAGRetriever()

        result = await retriever.retrieve(query="hello", graph_results=traversal)

        assert len(result.ranked_contexts) == 1
        assert result.ranked_contexts[0].node.id == "n1"
        assert result.ranked_contexts[0].score.total_score == pytest.approx(1.0)
        assert result.assembled_context.text == "Hello world"

    async def test_retrieve_multiple_nodes_decreasing_scores(self):
        from src.core.cognitive.graphrag.retrieval.models import (
            GraphNode,
            TraversalResult,
        )
        from src.core.cognitive.graphrag.retrieval.retriever import GraphRAGRetriever

        nodes = [GraphNode(id=f"n{i}", text_content=f"text{i}") for i in range(5)]
        traversal = TraversalResult(nodes=nodes, seed_node_ids=["n0"], query="q")
        retriever = GraphRAGRetriever()

        result = await retriever.retrieve(query="q", graph_results=traversal)

        assert len(result.ranked_contexts) == 5
        # Scores decrease by 0.1 per position
        assert result.ranked_contexts[0].score.total_score == pytest.approx(1.0)
        assert result.ranked_contexts[1].score.total_score == pytest.approx(0.9)
        assert result.ranked_contexts[4].score.total_score == pytest.approx(0.6)
        assert result.assembled_context.text == "text0 text1 text2 text3 text4"

    async def test_retrieve_with_query_embedding(self):
        from src.core.cognitive.graphrag.retrieval.models import (
            GraphNode,
            TraversalResult,
        )
        from src.core.cognitive.graphrag.retrieval.retriever import GraphRAGRetriever

        node = GraphNode(id="n1", text_content="data")
        traversal = TraversalResult(nodes=[node])
        retriever = GraphRAGRetriever()

        result = await retriever.retrieve(
            query="q",
            graph_results=traversal,
            query_embedding=[0.1, 0.2, 0.3],
        )
        assert len(result.ranked_contexts) == 1

    def test_dataclass_defaults(self):
        from src.core.cognitive.graphrag.retrieval.models import GraphNode
        from src.core.cognitive.graphrag.retrieval.retriever import (
            _AssembledContext,
            _RAGResult,
            _RankedContext,
            _Score,
        )

        score = _Score()
        assert score.total_score == 0.0

        ctx = _AssembledContext()
        assert ctx.text == ""

        node = GraphNode(id="x")
        ranked = _RankedContext(node=node)
        assert ranked.score.total_score == 0.0

        rag = _RAGResult()
        assert rag.ranked_contexts == []
        assert rag.assembled_context.text == ""


# ---------------------------------------------------------------------------
# 3. Latency Decorators
# ---------------------------------------------------------------------------


class TestTrackRequestLatency:
    """Tests for track_request_latency decorator."""

    def test_sync_success(self):
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_request_latency,
        )

        @track_request_latency
        def add(a: int, b: int) -> int:
            return a + b

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request", wraps=metrics.record_request) as spy:
            result = add(2, 3)
            assert result == 5
            spy.assert_called_once()
            assert spy.call_args[1]["success"] is True
            assert spy.call_args[0][0] >= 0.0  # latency_ms

    def test_sync_failure(self):
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_request_latency,
        )

        @track_request_latency
        def fail() -> None:
            raise ValueError("boom")

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request", wraps=metrics.record_request) as spy:
            with pytest.raises(ValueError, match="boom"):
                fail()
            spy.assert_called_once()
            assert spy.call_args[1]["success"] is False

    def test_sync_non_tracked_exception_propagates(self):
        """Exceptions not in the caught tuple propagate without recording."""
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_request_latency,
        )

        @track_request_latency
        def fail_key() -> None:
            raise KeyError("not tracked")

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request") as spy:
            with pytest.raises(KeyError):
                fail_key()
            # KeyError is not in the caught tuple
            spy.assert_not_called()


class TestTrackAsyncRequestLatency:
    """Tests for track_async_request_latency decorator."""

    async def test_async_success(self):
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_async_request_latency,
        )

        @track_async_request_latency
        async def fetch(url: str) -> str:
            return f"data-{url}"

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request", wraps=metrics.record_request) as spy:
            result = await fetch("http://example.com")
            assert result == "data-http://example.com"
            spy.assert_called_once()
            assert spy.call_args[1]["success"] is True

    async def test_async_failure(self):
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_async_request_latency,
        )

        @track_async_request_latency
        async def fail_async() -> None:
            raise RuntimeError("async boom")

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request", wraps=metrics.record_request) as spy:
            with pytest.raises(RuntimeError, match="async boom"):
                await fail_async()
            spy.assert_called_once()
            assert spy.call_args[1]["success"] is False

    async def test_async_os_error(self):
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_async_request_latency,
        )

        @track_async_request_latency
        async def fail_os() -> None:
            raise OSError("disk error")

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request", wraps=metrics.record_request) as spy:
            with pytest.raises(OSError, match="disk error"):
                await fail_os()
            spy.assert_called_once()
            assert spy.call_args[1]["success"] is False

    async def test_async_type_error(self):
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_async_request_latency,
        )

        @track_async_request_latency
        async def fail_type() -> None:
            raise TypeError("wrong type")

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request", wraps=metrics.record_request) as spy:
            with pytest.raises(TypeError, match="wrong type"):
                await fail_type()
            assert spy.call_args[1]["success"] is False

    async def test_latency_is_positive(self):
        from enhanced_agent_bus.observability.capacity_metrics.collector import (
            get_capacity_metrics,
        )
        from enhanced_agent_bus.observability.capacity_metrics.latency_decorators import (
            track_async_request_latency,
        )

        @track_async_request_latency
        async def noop() -> None:
            pass

        metrics = get_capacity_metrics()
        with patch.object(metrics, "record_request", wraps=metrics.record_request) as spy:
            await noop()
            latency_ms = spy.call_args[0][0]
            assert latency_ms >= 0.0


# ---------------------------------------------------------------------------
# 4. _ext_mcp.py fallback path
# ---------------------------------------------------------------------------


class TestExtMcpFallback:
    """Test the ImportError fallback branch of _ext_mcp.py."""

    def test_fallback_flags_are_false(self):
        """When mcp_integration import fails, all flags should be False."""
        import importlib
        import sys

        # Force the ImportError path by temporarily removing the real module
        with patch.dict(sys.modules, {"enhanced_agent_bus.mcp_integration": None}):
            # Remove cached _ext_mcp so it re-imports
            mod_key = "enhanced_agent_bus._ext_mcp"
            saved = sys.modules.pop(mod_key, None)
            try:
                import enhanced_agent_bus._ext_mcp as ext_mcp

                importlib.reload(ext_mcp)
                assert ext_mcp.MCP_INTEGRATION_AVAILABLE is False
                assert ext_mcp.MCP_CLIENT_AVAILABLE is False
                assert ext_mcp.MCP_SERVER_AVAILABLE is False
                assert ext_mcp.MCP_TOOL_REGISTRY_AVAILABLE is False
                assert ext_mcp.MCP_VALIDATORS_AVAILABLE is False
            finally:
                if saved is not None:
                    sys.modules[mod_key] = saved

    def test_fallback_classes_are_object(self):
        """Fallback classes should be `object`."""
        import importlib
        import sys

        with patch.dict(sys.modules, {"enhanced_agent_bus.mcp_integration": None}):
            mod_key = "enhanced_agent_bus._ext_mcp"
            saved = sys.modules.pop(mod_key, None)
            try:
                import enhanced_agent_bus._ext_mcp as ext_mcp

                importlib.reload(ext_mcp)
                assert ext_mcp.MCPClient is object
                assert ext_mcp.MCPClientConfig is object
                assert ext_mcp.MCPConnectionPool is object
                assert ext_mcp.MCPIntegrationServer is object
                assert ext_mcp.MCPToolRegistry is object
                assert ext_mcp.MCPValidationConfig is object
                assert ext_mcp.MCPValidationResult is object
                assert ext_mcp.OperationType is object
                assert ext_mcp.create_mcp_client is object
                assert ext_mcp.create_mcp_integration_server is object
                assert ext_mcp.create_mcp_validator is object
                assert ext_mcp.create_tool_registry is object
            finally:
                if saved is not None:
                    sys.modules[mod_key] = saved

    def test_ext_all_list(self):
        """_EXT_ALL should contain all exported names."""
        import enhanced_agent_bus._ext_mcp as ext_mcp

        assert isinstance(ext_mcp._EXT_ALL, list)
        assert "MCP_INTEGRATION_AVAILABLE" in ext_mcp._EXT_ALL
        assert "MCPClient" in ext_mcp._EXT_ALL
        assert "create_mcp_client" in ext_mcp._EXT_ALL
        assert len(ext_mcp._EXT_ALL) == 25

    def test_current_import_state(self):
        """Verify the module loads without error in current environment."""
        import enhanced_agent_bus._ext_mcp as ext_mcp

        # MCP_INTEGRATION_AVAILABLE is either True or False depending on env
        assert isinstance(ext_mcp.MCP_INTEGRATION_AVAILABLE, bool)

    def test_fallback_remaining_symbols(self):
        """Cover remaining fallback symbols not checked elsewhere."""
        import importlib
        import sys

        with patch.dict(sys.modules, {"enhanced_agent_bus.mcp_integration": None}):
            mod_key = "enhanced_agent_bus._ext_mcp"
            saved = sys.modules.pop(mod_key, None)
            try:
                import enhanced_agent_bus._ext_mcp as ext_mcp

                importlib.reload(ext_mcp)
                assert ext_mcp.MCPClientState is object
                assert ext_mcp.MCPConnectionError is object
                assert ext_mcp.MCPConstitutionalValidator is object
                assert ext_mcp.MCPIntegrationConfig is object
                assert ext_mcp.MCPOperationContext is object
                assert ext_mcp.MCPServerConnection is object
                assert ext_mcp.MCPServerMetrics is object
                assert ext_mcp.MCPServerState is object
            finally:
                if saved is not None:
                    sys.modules[mod_key] = saved
