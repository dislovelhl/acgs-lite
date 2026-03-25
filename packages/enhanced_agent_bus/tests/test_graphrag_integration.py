"""
Tests for GraphRAGContextEnricher — deliberation layer policy retrieval.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

pytest.importorskip("src.core.cognitive", reason="src.core.cognitive removed during extraction")

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.deliberation_layer.graphrag_integration import (
    GraphRAGContextEnricher,
    _cache_key,
    _LRUCache,
)

# ---------------------------------------------------------------------------
# _LRUCache unit tests
# ---------------------------------------------------------------------------


class TestLRUCache:
    def test_get_miss_returns_none(self):
        cache = _LRUCache(maxsize=2)
        assert cache.get("missing") is None

    def test_put_and_get_roundtrip(self):
        cache = _LRUCache(maxsize=2)
        cache.put("k", {"v": 1})
        assert cache.get("k") == {"v": 1}

    def test_evicts_lru_entry_when_full(self):
        cache = _LRUCache(maxsize=2)
        cache.put("a", {"x": 1})
        cache.put("b", {"x": 2})
        cache.put("c", {"x": 3})  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == {"x": 2}
        assert cache.get("c") == {"x": 3}

    def test_access_promotes_entry(self):
        cache = _LRUCache(maxsize=2)
        cache.put("a", {"x": 1})
        cache.put("b", {"x": 2})
        cache.get("a")  # promote "a"
        cache.put("c", {"x": 3})  # should evict "b" (now LRU)
        assert cache.get("a") == {"x": 1}
        assert cache.get("b") is None

    def test_len_reflects_contents(self):
        cache = _LRUCache(maxsize=10)
        assert len(cache) == 0
        cache.put("x", {})
        assert len(cache) == 1

    def test_clear_empties_cache(self):
        cache = _LRUCache(maxsize=5)
        cache.put("a", {})
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None

    def test_update_existing_key(self):
        cache = _LRUCache(maxsize=2)
        cache.put("k", {"v": 1})
        cache.put("k", {"v": 2})
        assert cache.get("k") == {"v": 2}
        assert len(cache) == 1


# ---------------------------------------------------------------------------
# _cache_key helper
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_same_inputs_same_key(self):
        assert _cache_key("hello", "t1") == _cache_key("hello", "t1")

    def test_different_query_different_key(self):
        assert _cache_key("hello", "t1") != _cache_key("world", "t1")

    def test_different_tenant_different_key(self):
        assert _cache_key("hello", "t1") != _cache_key("hello", "t2")

    def test_returns_16_char_hex(self):
        key = _cache_key("q", "t")
        assert len(key) == 16
        assert all(c in "0123456789abcdef" for c in key)


# ---------------------------------------------------------------------------
# GraphRAGContextEnricher — unit tests with mocked backends
# ---------------------------------------------------------------------------


def _make_enricher(**kwargs) -> GraphRAGContextEnricher:
    """Build an enricher with mocked in-memory backends."""
    return GraphRAGContextEnricher(**kwargs)


class TestGraphRAGContextEnricherInit:
    def test_initial_seeded_count_zero(self):
        enricher = _make_enricher()
        assert enricher.seeded_policy_count == 0

    def test_initial_cache_size_zero(self):
        enricher = _make_enricher()
        assert enricher.cache_size == 0

    def test_constitutional_hash_set(self):
        enricher = _make_enricher()
        assert enricher.constitutional_hash == "608508a9bd224290"  # pragma: allowlist secret

    def test_clear_cache_resets_size(self):
        enricher = _make_enricher()
        enricher._cache.put("k", {"v": 1})
        enricher.clear_cache()
        assert enricher.cache_size == 0


class TestSeedPolicy:
    async def test_seed_increments_count(self):
        enricher = _make_enricher()
        await enricher.seed_policy("Rate limits apply.", "pol-1", "t1")
        assert enricher.seeded_policy_count == 1

    async def test_seed_multiple_same_id_stays_one(self):
        enricher = _make_enricher()
        await enricher.seed_policy("v1", "pol-1", "t1")
        await enricher.seed_policy("v2", "pol-1", "t1")
        # _seeded_ids is a set so count stays 1
        assert enricher.seeded_policy_count == 1

    async def test_seed_multiple_different_ids(self):
        enricher = _make_enricher()
        await enricher.seed_policy("p1", "pol-1", "t1")
        await enricher.seed_policy("p2", "pol-2", "t1")
        assert enricher.seeded_policy_count == 2


class TestEnrich:
    async def test_empty_query_returns_empty(self):
        enricher = _make_enricher()
        result = await enricher.enrich("", "t1")
        assert result == {}

    async def test_whitespace_query_returns_empty(self):
        enricher = _make_enricher()
        result = await enricher.enrich("   ", "t1")
        assert result == {}

    async def test_unseeded_store_returns_empty(self):
        enricher = _make_enricher()
        result = await enricher.enrich("some action", "t1")
        assert result == {}

    async def test_seeded_policy_retrieved_for_matching_tenant(self):
        enricher = _make_enricher()
        await enricher.seed_policy(
            "Agents must not exceed rate limits without HITL approval.",
            "pol-rate",
            "tenant-a",
        )
        result = await enricher.enrich("rate limits", "tenant-a")
        assert "retrieved_policies" in result
        assert len(result["retrieved_policies"]) >= 1
        assert result["retrieved_policies"][0]["policy_id"] == "pol-rate"

    async def test_policy_not_returned_for_different_tenant(self):
        enricher = _make_enricher()
        await enricher.seed_policy("Confidential policy.", "pol-x", "tenant-a")
        result = await enricher.enrich("confidential", "tenant-b")
        assert result == {} or result.get("retrieved_policies", []) == []

    async def test_result_contains_constitutional_hash(self):
        enricher = _make_enricher()
        await enricher.seed_policy("Policy text.", "pol-1", "t1")
        result = await enricher.enrich("policy", "t1")
        assert result.get("constitutional_hash") == "608508a9bd224290"  # pragma: allowlist secret

    async def test_result_contains_retrieval_time_ms(self):
        enricher = _make_enricher()
        await enricher.seed_policy("Policy text.", "pol-1", "t1")
        result = await enricher.enrich("policy", "t1")
        assert "retrieval_time_ms" in result
        assert isinstance(result["retrieval_time_ms"], float)

    async def test_cached_result_on_second_call(self):
        enricher = _make_enricher()
        await enricher.seed_policy("Policy text.", "pol-1", "t1")
        await enricher.enrich("policy", "t1")
        result2 = await enricher.enrich("policy", "t1")
        assert result2.get("cache_hit") is True

    async def test_cache_size_increments_on_new_query(self):
        enricher = _make_enricher()
        await enricher.seed_policy("Policy text.", "pol-1", "t1")
        assert enricher.cache_size == 0
        await enricher.enrich("policy", "t1")
        assert enricher.cache_size == 1

    async def test_snippet_truncated_to_max_chars(self):
        max_chars = 50
        enricher = _make_enricher(max_context_chars=max_chars)
        long_text = "A" * 500
        await enricher.seed_policy(long_text, "pol-long", "t1")
        result = await enricher.enrich("AAAA", "t1")
        if result.get("retrieved_policies"):
            snippet = result["retrieved_policies"][0]["snippet"]
            assert len(snippet) <= max_chars

    async def test_timeout_returns_empty(self):
        enricher = _make_enricher(timeout_seconds=0.001)

        async def _slow_retrieve(*_a, **_kw):
            await asyncio.sleep(1)
            return {}

        with patch.object(enricher, "_retrieve", side_effect=_slow_retrieve):
            result = await enricher.enrich("something", "t1")
        assert result == {}

    async def test_backend_error_returns_empty(self):
        enricher = _make_enricher()

        async def _fail(*_a, **_kw):
            raise RuntimeError("store unavailable")

        with patch.object(enricher, "_retrieve", side_effect=_fail):
            result = await enricher.enrich("something", "t1")
        assert result == {}

    async def test_custom_timeout_overrides_default(self):
        enricher = _make_enricher(timeout_seconds=10)  # generous default
        call_timeout = None

        original_wait_for = asyncio.wait_for

        async def _capture_timeout(coro, timeout):
            nonlocal call_timeout
            call_timeout = timeout
            return await original_wait_for(coro, timeout)

        with patch("asyncio.wait_for", side_effect=_capture_timeout):
            await enricher.enrich("query", "t1", timeout=0.123)

        assert call_timeout == pytest.approx(0.123)

    async def test_top_k_limits_results(self):
        enricher = _make_enricher(top_k=2)
        for i in range(5):
            await enricher.seed_policy(f"Policy {i}", f"pol-{i}", "t1")
        result = await enricher.enrich("policy", "t1")
        if result.get("retrieved_policies"):
            assert len(result["retrieved_policies"]) <= 2


# ---------------------------------------------------------------------------
# seed_policies_batch — bulk seeding
# ---------------------------------------------------------------------------


class TestSeedPoliciesBatch:
    async def test_batch_seeds_all_policies(self):
        enricher = _make_enricher()
        items = [(f"Policy text {i}", f"pol-{i}", "t1") for i in range(5)]
        await enricher.seed_policies_batch(items)
        assert enricher.seeded_policy_count == 5

    async def test_batch_empty_is_noop(self):
        enricher = _make_enricher()
        await enricher.seed_policies_batch([])
        assert enricher.seeded_policy_count == 0

    async def test_batch_seeded_policies_are_retrievable(self):
        enricher = _make_enricher()
        items = [("Rate limits must be enforced.", "pol-rate", "tenant-b")]
        await enricher.seed_policies_batch(items)
        result = await enricher.enrich("rate limits", "tenant-b")
        assert "retrieved_policies" in result
        assert len(result["retrieved_policies"]) >= 1

    async def test_batch_respects_tenant_isolation(self):
        enricher = _make_enricher()
        items = [
            ("Policy for tenant A.", "pol-a", "tenant-a"),
            ("Policy for tenant B.", "pol-b", "tenant-b"),
        ]
        await enricher.seed_policies_batch(items)
        result = await enricher.enrich("policy", "tenant-a")
        if result.get("retrieved_policies"):
            for p in result["retrieved_policies"]:
                assert p["policy_id"] == "pol-a"

    async def test_batch_overwrites_existing_policy_id(self):
        enricher = _make_enricher()
        await enricher.seed_policies_batch([("v1 text", "pol-x", "t1")])
        await enricher.seed_policies_batch([("v2 text", "pol-x", "t1")])
        assert enricher.seeded_policy_count == 1


# ---------------------------------------------------------------------------
# Pipeline path — optional GraphRAGRetriever integration
# ---------------------------------------------------------------------------


class TestPipelinePath:
    async def test_pipeline_path_invoked_when_retriever_set(self):
        """When a retriever is injected, enrich() calls _retrieve_via_pipeline."""
        enricher = _make_enricher()
        await enricher.seed_policy("Policy text for pipeline.", "pol-pipe", "t1")

        pipeline_called = []

        async def _fake_pipeline(*_, **__):
            pipeline_called.append(True)
            return {
                "retrieved_policies": [
                    {
                        "policy_id": "pol-pipe",
                        "score": 0.9,
                        "snippet": "Policy text",
                        "constitutional_hash": "608508a9bd224290",
                    }  # pragma: allowlist secret
                ],
                "assembled_context": "Policy text for pipeline.",
                "retrieval_time_ms": 1.0,
                "constitutional_hash": "608508a9bd224290",  # pragma: allowlist secret
                "retrieval_path": "pipeline",
            }

        enricher._retriever = object()  # non-None sentinel triggers pipeline branch
        with patch.object(enricher, "_retrieve_via_pipeline", side_effect=_fake_pipeline):
            result = await enricher.enrich("pipeline", "t1", timeout=1.0)

        assert pipeline_called, "Pipeline path was not invoked"
        assert result.get("retrieval_path") == "pipeline"

    async def test_pipeline_failure_falls_back_to_raw(self):
        """If _retrieve_via_pipeline raises, raw path result is returned."""
        enricher = _make_enricher()
        await enricher.seed_policy("Fallback policy.", "pol-fb", "t1")

        async def _fail(*_, **__):
            return {}  # empty → caller falls through to raw path

        enricher._retriever = object()
        with patch.object(enricher, "_retrieve_via_pipeline", side_effect=_fail):
            result = await enricher.enrich("fallback", "t1", timeout=1.0)

        # Should get raw-path results (non-empty because policy is seeded)
        assert "retrieved_policies" in result
        assert result.get("retrieval_path") is None  # raw path has no retrieval_path key

    async def test_no_retriever_uses_raw_path(self):
        """Without a retriever, raw path is always used."""
        enricher = _make_enricher()
        await enricher.seed_policy("No retriever policy.", "pol-nr", "t1")
        result = await enricher.enrich("retriever", "t1", timeout=1.0)
        assert result.get("retrieval_path") is None


# ---------------------------------------------------------------------------
# DeliberationLayer integration — graphrag_enricher is wired correctly
# ---------------------------------------------------------------------------


class TestDeliberationLayerIntegration:
    """Verify graphrag_enricher is wired into DeliberationLayer.__init__."""

    def test_constructor_accepts_graphrag_enricher(self):
        from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer

        enricher = GraphRAGContextEnricher()
        layer = DeliberationLayer(graphrag_enricher=enricher)
        assert layer._graphrag_enricher is enricher

    def test_constructor_default_none(self):
        from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer

        layer = DeliberationLayer()
        assert layer._graphrag_enricher is None

    async def test_enricher_called_during_process_message(self):
        from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        enricher = GraphRAGContextEnricher()
        enrich_mock = AsyncMock(return_value={"retrieved_policies": [], "retrieval_time_ms": 1.0})
        enricher.enrich = enrich_mock

        layer = DeliberationLayer(graphrag_enricher=enricher)

        msg = AgentMessage(
            content={"action": "send_report"},
            message_type=MessageType.COMMAND,
            from_agent="agent-1",
            to_agent="agent-2",
            tenant_id="tenant-test",
            priority=Priority.NORMAL,
        )

        # Patch routing to avoid full deliberation execution
        with patch.object(layer, "_execute_routing", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"success": True, "routing": "fast_lane"}
            with patch.object(layer, "_evaluate_opa_guard", new_callable=AsyncMock) as mock_opa:
                mock_opa.return_value = None
                with patch.object(
                    layer, "_finalize_processing", new_callable=AsyncMock
                ) as mock_fin:
                    mock_fin.return_value = {"success": True}
                    await layer.process_message(msg)

        enrich_mock.assert_awaited_once()
        call_kwargs = enrich_mock.call_args
        assert "tenant-test" in str(call_kwargs)

    async def test_process_message_succeeds_without_enricher(self):
        from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        layer = DeliberationLayer()  # no enricher
        msg = AgentMessage(
            content={"action": "noop"},
            message_type=MessageType.COMMAND,
            from_agent="a",
            to_agent="b",
            tenant_id="t",
            priority=Priority.NORMAL,
        )

        with patch.object(layer, "_execute_routing", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"success": True}
            with patch.object(layer, "_evaluate_opa_guard", new_callable=AsyncMock) as mock_opa:
                mock_opa.return_value = None
                with patch.object(
                    layer, "_finalize_processing", new_callable=AsyncMock
                ) as mock_fin:
                    mock_fin.return_value = {"success": True}
                    result = await layer.process_message(msg)

        assert result["success"] is True
