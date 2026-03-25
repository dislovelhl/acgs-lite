"""
Coverage batch 16: langgraph state_reducer, hitl_integration,
enterprise_sso/middleware, chaos/steady_state, opa_client/cache.

Targets ~500+ missing lines across five modules to gain 322+ covered lines.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. langgraph_orchestration/state_reducer (97 missing lines, 33.1% covered)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.langgraph_orchestration.models import (
    ExecutionContext,
    GraphState,
    InterruptType,
    StateDelta,
)
from enhanced_agent_bus.langgraph_orchestration.state_reducer import (
    AccumulatorStateReducer,
    BaseStateReducer,
    CustomStateReducer,
    ImmutableStateReducer,
    MergeStateReducer,
    OverwriteStateReducer,
    create_state_reducer,
    safe_copy,
)


class TestSafeCopy:
    def test_dict_is_deep_copied(self):
        original = {"a": {"b": 1}}
        copied = safe_copy(original)
        assert copied == original
        assert copied is not original

    def test_list_is_deep_copied(self):
        original = [1, [2, 3]]
        copied = safe_copy(original)
        assert copied == original
        assert copied is not original

    def test_string_not_copied(self):
        original = "hello"
        assert safe_copy(original) is original

    def test_int_not_copied(self):
        assert safe_copy(42) == 42

    def test_none_not_copied(self):
        assert safe_copy(None) is None

    def test_tuple_not_copied(self):
        t = (1, 2, 3)
        assert safe_copy(t) is t

    def test_bool_not_copied(self):
        assert safe_copy(True) is True


class TestBaseStateReducer:
    def test_validate_output_valid(self):
        class ConcreteReducer(BaseStateReducer):
            def reduce(self, current_state, node_output, node_id):
                return current_state

        reducer = ConcreteReducer()
        errors = reducer.validate_output({"key": "value"})
        assert errors == []

    def test_validate_output_invalid(self):
        class ConcreteReducer(BaseStateReducer):
            def reduce(self, current_state, node_output, node_id):
                return current_state

        reducer = ConcreteReducer()
        errors = reducer.validate_output("not a dict")
        assert len(errors) == 1
        assert "dict" in errors[0]

    def test_compute_delta_add(self):
        class ConcreteReducer(BaseStateReducer):
            def reduce(self, current_state, node_output, node_id):
                return current_state

        reducer = ConcreteReducer()
        old = GraphState(data={"a": 1}, version=0)
        new = GraphState(data={"a": 1, "b": 2}, version=1)
        delta = reducer.compute_delta(old, new, "node1")
        assert isinstance(delta, StateDelta)
        changes = delta.changes
        add_ops = [c for c in changes if c["operation"] == "add"]
        assert len(add_ops) == 1
        assert add_ops[0]["key"] == "b"

    def test_compute_delta_modify(self):
        class ConcreteReducer(BaseStateReducer):
            def reduce(self, current_state, node_output, node_id):
                return current_state

        reducer = ConcreteReducer()
        old = GraphState(data={"a": 1}, version=0)
        new = GraphState(data={"a": 2}, version=1)
        delta = reducer.compute_delta(old, new, "node1")
        mod_ops = [c for c in delta.changes if c["operation"] == "modify"]
        assert len(mod_ops) == 1
        assert mod_ops[0]["old_value"] == 1
        assert mod_ops[0]["new_value"] == 2

    def test_compute_delta_remove(self):
        class ConcreteReducer(BaseStateReducer):
            def reduce(self, current_state, node_output, node_id):
                return current_state

        reducer = ConcreteReducer()
        old = GraphState(data={"a": 1, "b": 2}, version=0)
        new = GraphState(data={"a": 1}, version=1)
        delta = reducer.compute_delta(old, new, "node1")
        rm_ops = [c for c in delta.changes if c["operation"] == "remove"]
        assert len(rm_ops) == 1
        assert rm_ops[0]["key"] == "b"


class TestImmutableStateReducer:
    def test_replace_state(self):
        reducer = ImmutableStateReducer()
        state = GraphState(data={"old": True}, version=0)
        new_state = reducer.reduce(state, {"new": True}, "node1")
        assert new_state.data == {"new": True}
        assert new_state.version == 1
        assert new_state.last_node_id == "node1"
        assert len(new_state.mutation_history) > 0
        assert new_state.mutation_history[-1]["operation"] == "replace"

    def test_preserves_history(self):
        reducer = ImmutableStateReducer()
        state = GraphState(
            data={"old": True},
            version=5,
            mutation_history=[{"operation": "prev"}],
        )
        new_state = reducer.reduce(state, {"new": True}, "node2")
        assert len(new_state.mutation_history) == 2


class TestMergeStateReducer:
    def test_shallow_merge(self):
        reducer = MergeStateReducer()
        state = GraphState(data={"a": 1, "b": 2}, version=0)
        new_state = reducer.reduce(state, {"b": 3, "c": 4}, "node1")
        assert new_state.data == {"a": 1, "b": 3, "c": 4}
        assert new_state.version == 1

    def test_deep_merge_dicts(self):
        reducer = MergeStateReducer(deep_merge=True)
        state = GraphState(data={"config": {"x": 1, "y": 2}}, version=0)
        new_state = reducer.reduce(state, {"config": {"y": 3, "z": 4}}, "node1")
        assert new_state.data["config"] == {"x": 1, "y": 3, "z": 4}

    def test_deep_merge_lists_replace(self):
        reducer = MergeStateReducer(deep_merge=True, merge_lists=False)
        state = GraphState(data={"items": [1, 2]}, version=0)
        new_state = reducer.reduce(state, {"items": [3, 4]}, "node1")
        assert new_state.data["items"] == [3, 4]

    def test_deep_merge_lists_concat(self):
        reducer = MergeStateReducer(deep_merge=True, merge_lists=True)
        state = GraphState(data={"items": [1, 2]}, version=0)
        new_state = reducer.reduce(state, {"items": [3, 4]}, "node1")
        assert new_state.data["items"] == [1, 2, 3, 4]

    def test_mutation_history_trimmed(self):
        reducer = MergeStateReducer()
        state = GraphState(
            data={"a": 1},
            version=0,
            mutation_history=[{"op": f"h{i}"} for i in range(150)],
            max_history_size=100,
        )
        new_state = reducer.reduce(state, {"b": 2}, "node1")
        assert len(new_state.mutation_history) <= 100

    def test_mutation_history_records_keys(self):
        reducer = MergeStateReducer()
        state = GraphState(data={}, version=0)
        new_state = reducer.reduce(state, {"x": 1, "y": 2}, "nodeA")
        last_mutation = new_state.mutation_history[-1]
        assert last_mutation["operation"] == "merge"
        assert set(last_mutation["keys"]) == {"x", "y"}


class TestOverwriteStateReducer:
    def test_selective_overwrite(self):
        reducer = OverwriteStateReducer(
            overwrite_keys=["score"],
            preserve_keys=["name"],
        )
        state = GraphState(data={"name": "test", "score": 10, "extra": "old"}, version=0)
        new_state = reducer.reduce(state, {"score": 99, "name": "changed", "extra": "new"}, "node1")
        assert new_state.data["score"] == 99
        assert new_state.data["name"] == "test"  # preserved
        assert new_state.data["extra"] == "new"  # default merge

    def test_remove_keys(self):
        reducer = OverwriteStateReducer(remove_keys=["temp"])
        state = GraphState(data={"temp": 1, "keep": 2}, version=0)
        new_state = reducer.reduce(state, {}, "node1")
        assert "temp" not in new_state.data
        assert new_state.data["keep"] == 2

    def test_mutation_history(self):
        reducer = OverwriteStateReducer(
            overwrite_keys=["x"], preserve_keys=["y"], remove_keys=["z"]
        )
        state = GraphState(data={"x": 1, "y": 2, "z": 3}, version=0)
        new_state = reducer.reduce(state, {"x": 10}, "n1")
        last_mut = new_state.mutation_history[-1]
        assert last_mut["operation"] == "selective_overwrite"
        assert "x" in last_mut["overwritten"]


class TestAccumulatorStateReducer:
    def test_accumulate_new_key(self):
        reducer = AccumulatorStateReducer(accumulate_keys=["results"])
        state = GraphState(data={}, version=0)
        new_state = reducer.reduce(state, {"results": "item1"}, "node1")
        assert new_state.data["results"] == ["item1"]

    def test_accumulate_existing_list(self):
        reducer = AccumulatorStateReducer(accumulate_keys=["results"])
        state = GraphState(data={"results": ["item1"]}, version=0)
        new_state = reducer.reduce(state, {"results": "item2"}, "node1")
        assert new_state.data["results"] == ["item1", "item2"]

    def test_accumulate_max_size(self):
        reducer = AccumulatorStateReducer(accumulate_keys=["log"], max_accumulate_size=3)
        state = GraphState(data={"log": ["a", "b", "c"]}, version=0)
        new_state = reducer.reduce(state, {"log": "d"}, "node1")
        assert len(new_state.data["log"]) == 3
        assert new_state.data["log"][-1] == "d"

    def test_accumulate_non_list_existing(self):
        reducer = AccumulatorStateReducer(accumulate_keys=["val"])
        state = GraphState(data={"val": "scalar"}, version=0)
        new_state = reducer.reduce(state, {"val": "new"}, "node1")
        assert new_state.data["val"] == ["scalar", "new"]

    def test_non_accumulate_key_overwritten(self):
        reducer = AccumulatorStateReducer(accumulate_keys=["log"])
        state = GraphState(data={"status": "old"}, version=0)
        new_state = reducer.reduce(state, {"status": "new"}, "node1")
        assert new_state.data["status"] == "new"


class TestCustomStateReducer:
    def test_custom_function(self):
        def custom_fn(data, output, node_id):
            result = {**data}
            for k, v in output.items():
                result[k] = v * 2 if isinstance(v, (int, float)) else v
            return result

        reducer = CustomStateReducer(reduce_fn=custom_fn)
        state = GraphState(data={"a": 1}, version=0)
        new_state = reducer.reduce(state, {"b": 5}, "node1")
        assert new_state.data["b"] == 10
        assert new_state.version == 1


class TestCreateStateReducer:
    def test_merge(self):
        reducer = create_state_reducer("merge")
        assert isinstance(reducer, MergeStateReducer)

    def test_merge_deep(self):
        reducer = create_state_reducer("merge", deep_merge=True, merge_lists=True)
        assert isinstance(reducer, MergeStateReducer)
        assert reducer.deep_merge is True

    def test_overwrite(self):
        reducer = create_state_reducer("overwrite", overwrite_keys=["a"], preserve_keys=["b"])
        assert isinstance(reducer, OverwriteStateReducer)

    def test_immutable(self):
        reducer = create_state_reducer("immutable")
        assert isinstance(reducer, ImmutableStateReducer)

    def test_accumulate(self):
        reducer = create_state_reducer("accumulate", accumulate_keys=["log"])
        assert isinstance(reducer, AccumulatorStateReducer)

    def test_custom(self):
        reducer = create_state_reducer("custom", reduce_fn=lambda d, o, n: {**d, **o})
        assert isinstance(reducer, CustomStateReducer)

    def test_custom_no_fn_raises(self):
        with pytest.raises(ValueError, match="reduce_fn"):
            create_state_reducer("custom")

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown reducer"):
            create_state_reducer("nonexistent")


# ---------------------------------------------------------------------------
# 2. langgraph_orchestration/hitl_integration (96 missing, 50% covered)
# ---------------------------------------------------------------------------

from enhanced_agent_bus.langgraph_orchestration.hitl_integration import (
    HITLAction,
    HITLConfig,
    HITLInterruptHandler,
    HITLRequest,
    HITLResponse,
    InMemoryHITLHandler,
    create_hitl_handler,
)


class TestHITLAction:
    def test_values(self):
        assert HITLAction.CONTINUE == "continue"
        assert HITLAction.ABORT == "abort"
        assert HITLAction.MODIFY == "modify"
        assert HITLAction.RETRY == "retry"
        assert HITLAction.SKIP == "skip"
        assert HITLAction.ESCALATE == "escalate"


class TestHITLConfig:
    def test_defaults(self):
        cfg = HITLConfig()
        assert cfg.enabled is True
        assert cfg.default_timeout_ms == 300000.0
        assert cfg.auto_continue_on_timeout is False
        assert cfg.audit_all_requests is True
        assert cfg.max_requests_per_workflow == 100


class TestHITLRequest:
    def test_expires_at_calculated(self):
        req = HITLRequest(timeout_ms=5000)
        assert req.expires_at is not None
        assert req.expires_at > req.created_at

    def test_is_expired_false(self):
        req = HITLRequest(timeout_ms=300000)
        assert req.is_expired() is False

    def test_is_expired_true(self):
        req = HITLRequest(timeout_ms=1)
        req.expires_at = datetime.now(UTC) - timedelta(hours=1)
        assert req.is_expired() is True

    def test_is_expired_no_expiry(self):
        req = HITLRequest(timeout_ms=0)
        req.expires_at = None
        assert req.is_expired() is False

    def test_to_dict(self):
        req = HITLRequest(
            workflow_id="wf1",
            node_id="n1",
            reason="test",
        )
        d = req.to_dict()
        assert d["workflow_id"] == "wf1"
        assert d["node_id"] == "n1"
        assert "constitutional_hash" in d
        assert d["reason"] == "test"


class TestHITLResponse:
    def test_to_dict(self):
        resp = HITLResponse(
            request_id="req1",
            action=HITLAction.CONTINUE,
            responded_by="user1",
            reason="approved",
        )
        d = resp.to_dict()
        assert d["request_id"] == "req1"
        assert d["action"] == "continue"
        assert d["responded_by"] == "user1"


class TestInMemoryHITLHandler:
    @pytest.mark.asyncio
    async def test_auto_response(self):
        handler = InMemoryHITLHandler(auto_response=HITLAction.CONTINUE)
        req = HITLRequest(workflow_id="wf1", node_id="n1")
        resp = await handler.request_human_input(req)
        assert resp.action == HITLAction.CONTINUE
        assert resp.responded_by == "auto_responder"
        assert len(handler.request_history) == 1
        assert len(handler.response_history) == 1

    @pytest.mark.asyncio
    async def test_manual_response(self):
        handler = InMemoryHITLHandler()
        req = HITLRequest(workflow_id="wf1", node_id="n1", timeout_ms=5000)

        async def respond_later():
            await asyncio.sleep(0.01)
            handler.respond(
                req.id,
                HITLResponse(
                    request_id=req.id,
                    action=HITLAction.ABORT,
                    responded_by="tester",
                ),
            )

        task = asyncio.create_task(respond_later())
        resp = await handler.request_human_input(req)
        await task
        assert resp.action == HITLAction.ABORT

    @pytest.mark.asyncio
    async def test_timeout(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import TimeoutError as LGTimeout

        handler = InMemoryHITLHandler()
        req = HITLRequest(workflow_id="wf1", node_id="n1", timeout_ms=10)
        with pytest.raises(LGTimeout):
            await handler.request_human_input(req)

    @pytest.mark.asyncio
    async def test_notify_timeout(self):
        handler = InMemoryHITLHandler()
        req = HITLRequest(workflow_id="wf1", node_id="n1")
        handler.pending_requests[req.id] = req
        await handler.notify_timeout(req)
        assert req.id not in handler.pending_requests


class TestHITLInterruptHandler:
    def _make_context(self, wf_id="wf1", run_id="run1"):
        return ExecutionContext(workflow_id=wf_id, run_id=run_id, graph_id="g1")

    @pytest.mark.asyncio
    async def test_create_interrupt(self):
        handler = HITLInterruptHandler()
        ctx = self._make_context()
        state = GraphState(data={"test": True})
        req = await handler.create_interrupt(
            context=ctx,
            node_id="n1",
            interrupt_type=InterruptType.HITL,
            reason="need approval",
            state=state,
        )
        assert req.workflow_id == "wf1"
        assert req.node_id == "n1"
        assert len(handler._audit_log) == 1

    @pytest.mark.asyncio
    async def test_create_interrupt_disabled(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import (
            InterruptError,
        )

        config = HITLConfig(enabled=False)
        handler = HITLInterruptHandler(config=config)
        ctx = self._make_context()
        state = GraphState(data={})
        with pytest.raises(InterruptError):
            await handler.create_interrupt(
                context=ctx,
                node_id="n1",
                interrupt_type=InterruptType.HITL,
                reason="test",
                state=state,
            )

    @pytest.mark.asyncio
    async def test_create_interrupt_rate_limit(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import (
            InterruptError,
        )

        config = HITLConfig(max_requests_per_workflow=0)
        handler = HITLInterruptHandler(config=config)
        ctx = self._make_context()
        state = GraphState(data={})
        with pytest.raises(InterruptError, match="Rate limit"):
            await handler.create_interrupt(
                context=ctx,
                node_id="n1",
                interrupt_type=InterruptType.HITL,
                reason="test",
                state=state,
            )

    @pytest.mark.asyncio
    async def test_handle_interrupt_auto_response(self):
        inner = InMemoryHITLHandler(auto_response=HITLAction.CONTINUE)
        handler = HITLInterruptHandler(handler=inner)
        ctx = self._make_context()
        state = GraphState(data={})
        req = await handler.create_interrupt(
            context=ctx,
            node_id="n1",
            interrupt_type=InterruptType.HITL,
            reason="test",
            state=state,
        )
        resp = await handler.handle_interrupt(req)
        assert resp.action == HITLAction.CONTINUE

    @pytest.mark.asyncio
    async def test_handle_interrupt_auto_continue_on_timeout(self):
        config = HITLConfig(
            auto_continue_on_timeout=True,
            default_timeout_ms=10,
        )
        inner = InMemoryHITLHandler()
        handler = HITLInterruptHandler(handler=inner, config=config)
        req = HITLRequest(workflow_id="wf1", node_id="n1", timeout_ms=10)
        handler._active_requests[req.id] = req
        resp = await handler.handle_interrupt(req)
        assert resp.action == HITLAction.CONTINUE
        assert resp.responded_by == "timeout_handler"

    @pytest.mark.asyncio
    async def test_handle_interrupt_auto_abort_on_timeout(self):
        config = HITLConfig(
            auto_abort_on_timeout=True,
            escalation_enabled=False,
            default_timeout_ms=10,
        )
        inner = InMemoryHITLHandler()
        handler = HITLInterruptHandler(handler=inner, config=config)
        req = HITLRequest(workflow_id="wf1", node_id="n1", timeout_ms=10)
        handler._active_requests[req.id] = req
        resp = await handler.handle_interrupt(req)
        assert resp.action == HITLAction.ABORT

    def test_get_active_requests(self):
        handler = HITLInterruptHandler()
        req1 = HITLRequest(workflow_id="wf1")
        req2 = HITLRequest(workflow_id="wf2")
        handler._active_requests[req1.id] = req1
        handler._active_requests[req2.id] = req2
        assert len(handler.get_active_requests()) == 2
        assert len(handler.get_active_requests(workflow_id="wf1")) == 1

    def test_get_audit_log(self):
        handler = HITLInterruptHandler()
        handler._audit_log = [
            {"event": "e1", "request": {"workflow_id": "wf1"}},
            {"event": "e2", "request": {"workflow_id": "wf2"}},
        ]
        assert len(handler.get_audit_log()) == 2
        assert len(handler.get_audit_log(workflow_id="wf1")) == 1
        assert len(handler.get_audit_log(limit=1)) == 1

    def test_clear_audit_log(self):
        handler = HITLInterruptHandler()
        handler._audit_log = [{"e": 1}, {"e": 2}]
        count = handler.clear_audit_log()
        assert count == 2
        assert len(handler._audit_log) == 0

    @pytest.mark.asyncio
    async def test_handle_interrupt_hash_mismatch_corrected(self):
        """Response with wrong hash gets corrected."""
        inner = InMemoryHITLHandler(auto_response=HITLAction.CONTINUE)
        handler = HITLInterruptHandler(handler=inner)
        req = HITLRequest(workflow_id="wf1", node_id="n1", timeout_ms=5000)
        handler._active_requests[req.id] = req
        # Patch auto response to have wrong hash
        orig_request = inner.request_human_input

        async def patched(request):
            resp = await orig_request(request)
            resp.constitutional_hash = "wrong_hash"
            return resp

        inner.request_human_input = patched
        resp = await handler.handle_interrupt(req)
        # Hash should be corrected
        assert resp.constitutional_hash == handler.constitutional_hash

    @pytest.mark.asyncio
    async def test_create_interrupt_with_cooldown(self):
        """Test that cooldown between requests is enforced."""
        config = HITLConfig(cooldown_ms=1)  # 1ms cooldown
        handler = HITLInterruptHandler(config=config)
        ctx = self._make_context()
        state = GraphState(data={})
        # First request
        await handler.create_interrupt(
            context=ctx,
            node_id="n1",
            interrupt_type=InterruptType.HITL,
            reason="first",
            state=state,
        )
        # Second request should trigger cooldown check
        await handler.create_interrupt(
            context=ctx,
            node_id="n2",
            interrupt_type=InterruptType.HITL,
            reason="second",
            state=state,
        )
        assert handler._request_counts[ctx.workflow_id] == 2

    @pytest.mark.asyncio
    async def test_create_interrupt_with_checkpoint_manager(self):
        """Test checkpoint creation during interrupt."""
        mock_cm = AsyncMock()
        mock_checkpoint = MagicMock()
        mock_checkpoint.id = "cp-123"
        mock_cm.create_checkpoint = AsyncMock(return_value=mock_checkpoint)

        handler = HITLInterruptHandler(checkpoint_manager=mock_cm)
        ctx = self._make_context()
        state = GraphState(data={"test": True})
        req = await handler.create_interrupt(
            context=ctx,
            node_id="n1",
            interrupt_type=InterruptType.HITL,
            reason="test",
            state=state,
        )
        assert req.checkpoint_id == "cp-123"
        mock_cm.create_checkpoint.assert_called_once()


class TestCreateHITLHandler:
    def test_default(self):
        h = create_hitl_handler()
        assert isinstance(h, HITLInterruptHandler)

    def test_with_auto_response(self):
        h = create_hitl_handler(auto_response=HITLAction.CONTINUE)
        assert isinstance(h.handler, InMemoryHITLHandler)
        assert h.handler.auto_response == HITLAction.CONTINUE

    def test_with_custom_config(self):
        cfg = HITLConfig(enabled=False)
        h = create_hitl_handler(config=cfg)
        assert h.config.enabled is False


# ---------------------------------------------------------------------------
# 3. enterprise_sso/middleware (116 missing lines, 55% covered)
# ---------------------------------------------------------------------------

from enhanced_agent_bus.enterprise_sso.middleware import (
    SSOMiddlewareConfig,
    SSOSessionContext,
    clear_sso_session,
    get_current_sso_session,
    require_sso_authentication,
    set_sso_session,
)


class TestSSOSessionContext:
    def _make_session(self, **overrides):
        defaults = {
            "session_id": "sess-1",
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "email": "test@example.com",
            "display_name": "Test User",
            "maci_roles": ["ADMIN", "OPERATOR"],
            "idp_groups": ["engineering"],
            "attributes": {"key": "val"},
            "authenticated_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
        defaults.update(overrides)
        return SSOSessionContext(**defaults)

    def test_is_expired_false(self):
        session = self._make_session()
        assert session.is_expired is False

    def test_is_expired_true(self):
        session = self._make_session(expires_at=datetime.now(UTC) - timedelta(hours=1))
        assert session.is_expired is True

    def test_time_until_expiry(self):
        session = self._make_session(expires_at=datetime.now(UTC) + timedelta(seconds=60))
        assert session.time_until_expiry > 0

    def test_time_until_expiry_past(self):
        session = self._make_session(expires_at=datetime.now(UTC) - timedelta(seconds=60))
        assert session.time_until_expiry == 0.0

    def test_has_role(self):
        session = self._make_session()
        assert session.has_role("admin") is True
        assert session.has_role("ADMIN") is True
        assert session.has_role("viewer") is False

    def test_has_any_role(self):
        session = self._make_session()
        assert session.has_any_role(["admin", "viewer"]) is True
        assert session.has_any_role(["viewer", "auditor"]) is False

    def test_has_all_roles(self):
        session = self._make_session()
        assert session.has_all_roles(["admin", "operator"]) is True
        assert session.has_all_roles(["admin", "viewer"]) is False

    def test_to_dict(self):
        session = self._make_session()
        d = session.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["user_id"] == "user-1"
        assert d["tenant_id"] == "tenant-1"
        assert d["email"] == "test@example.com"
        assert "maci_roles" in d
        assert "constitutional_hash" in d


class TestSSOContextVarOps:
    def test_set_get_clear(self):
        clear_sso_session()
        assert get_current_sso_session() is None

        session = SSOSessionContext(
            session_id="s",
            user_id="u",
            tenant_id="t",
            email="e@e.com",
            display_name="d",
            maci_roles=[],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        set_sso_session(session)
        assert get_current_sso_session() is session

        clear_sso_session()
        assert get_current_sso_session() is None


class TestSSOMiddlewareConfig:
    def test_defaults(self):
        cfg = SSOMiddlewareConfig()
        assert "/health" in cfg.excluded_paths
        assert cfg.token_prefix == "Bearer"
        assert cfg.allow_cookie_auth is True
        assert cfg.require_authentication is True
        assert cfg.auto_refresh_sessions is True
        assert cfg.refresh_threshold_seconds == 300

    def test_custom_config(self):
        cfg = SSOMiddlewareConfig(
            require_authentication=False,
            refresh_threshold_seconds=600,
        )
        assert cfg.require_authentication is False
        assert cfg.refresh_threshold_seconds == 600


class TestRequireSSOAuthentication:
    @pytest.mark.asyncio
    async def test_decorator_no_session_raises(self):
        clear_sso_session()

        @require_sso_authentication()
        async def protected():
            return "ok"

        with pytest.raises((PermissionError, Exception)):
            await protected()

    @pytest.mark.asyncio
    async def test_decorator_with_valid_session(self):
        session = SSOSessionContext(
            session_id="s",
            user_id="u",
            tenant_id="t",
            email="e@e.com",
            display_name="d",
            maci_roles=["ADMIN"],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        set_sso_session(session)

        @require_sso_authentication()
        async def protected():
            return "ok"

        try:
            result = await protected()
            assert result == "ok"
        finally:
            clear_sso_session()

    @pytest.mark.asyncio
    async def test_decorator_role_check_fails(self):
        session = SSOSessionContext(
            session_id="s",
            user_id="u",
            tenant_id="t",
            email="e@e.com",
            display_name="d",
            maci_roles=["VIEWER"],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        set_sso_session(session)

        @require_sso_authentication(roles=["ADMIN"], any_role=True)
        async def admin_only():
            return "ok"

        try:
            with pytest.raises((PermissionError, Exception)):
                await admin_only()
        finally:
            clear_sso_session()

    def test_sync_decorator_no_session(self):
        clear_sso_session()

        @require_sso_authentication()
        def protected_sync():
            return "ok"

        with pytest.raises(PermissionError):
            protected_sync()

    def test_sync_decorator_with_session(self):
        session = SSOSessionContext(
            session_id="s",
            user_id="u",
            tenant_id="t",
            email="e@e.com",
            display_name="d",
            maci_roles=["ADMIN"],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        set_sso_session(session)

        @require_sso_authentication()
        def protected_sync():
            return "ok"

        try:
            result = protected_sync()
            assert result == "ok"
        finally:
            clear_sso_session()

    def test_sync_decorator_expired_session(self):
        session = SSOSessionContext(
            session_id="s",
            user_id="u",
            tenant_id="t",
            email="e@e.com",
            display_name="d",
            maci_roles=["ADMIN"],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        set_sso_session(session)

        @require_sso_authentication(allow_expired=False)
        def protected_sync():
            return "ok"

        try:
            with pytest.raises(PermissionError, match="expired"):
                protected_sync()
        finally:
            clear_sso_session()

    def test_sync_decorator_role_all_required(self):
        session = SSOSessionContext(
            session_id="s",
            user_id="u",
            tenant_id="t",
            email="e@e.com",
            display_name="d",
            maci_roles=["ADMIN"],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        set_sso_session(session)

        @require_sso_authentication(roles=["ADMIN", "SUPERADMIN"], any_role=False)
        def needs_all():
            return "ok"

        try:
            with pytest.raises(PermissionError, match="all roles"):
                needs_all()
        finally:
            clear_sso_session()


# ---------------------------------------------------------------------------
# 4. chaos/steady_state (101 missing lines, 45.7% covered)
# ---------------------------------------------------------------------------

from enhanced_agent_bus.chaos.steady_state import (
    InMemoryMetricCollector,
    MetricOperator,
    SteadyStateHypothesis,
    SteadyStateValidator,
    ValidationMetric,
    create_constitutional_validation_steady_state,
    create_maci_enforcement_steady_state,
    create_message_bus_steady_state,
)
from enhanced_agent_bus.chaos.steady_state import (
    ValidationResult as SSValidationResult,
)


class TestMetricOperator:
    def test_values(self):
        assert MetricOperator.LESS_THAN == "<"
        assert MetricOperator.LESS_EQUAL == "<="
        assert MetricOperator.EQUAL == "=="
        assert MetricOperator.GREATER_EQUAL == ">="
        assert MetricOperator.GREATER_THAN == ">"
        assert MetricOperator.NOT_EQUAL == "!="
        assert MetricOperator.BETWEEN == "between"


class TestValidationMetric:
    def test_less_than(self):
        m = ValidationMetric(name="lat", operator=MetricOperator.LESS_THAN, threshold=5.0)
        assert m.validate(4.0) is True
        assert m.validate(5.0) is False

    def test_less_equal(self):
        m = ValidationMetric(name="lat", operator=MetricOperator.LESS_EQUAL, threshold=5.0)
        assert m.validate(5.0) is True
        assert m.validate(5.1) is False

    def test_equal(self):
        m = ValidationMetric(name="lat", operator=MetricOperator.EQUAL, threshold=5.0)
        assert m.validate(5.0) is True
        assert m.validate(5.001) is False

    def test_greater_equal(self):
        m = ValidationMetric(name="lat", operator=MetricOperator.GREATER_EQUAL, threshold=5.0)
        assert m.validate(5.0) is True
        assert m.validate(4.9) is False

    def test_greater_than(self):
        m = ValidationMetric(name="lat", operator=MetricOperator.GREATER_THAN, threshold=5.0)
        assert m.validate(5.1) is True
        assert m.validate(5.0) is False

    def test_not_equal(self):
        m = ValidationMetric(name="lat", operator=MetricOperator.NOT_EQUAL, threshold=5.0)
        assert m.validate(4.0) is True
        assert m.validate(5.0) is False

    def test_between(self):
        m = ValidationMetric(
            name="lat",
            operator=MetricOperator.BETWEEN,
            threshold=3.0,
            threshold_max=7.0,
        )
        assert m.validate(5.0) is True
        assert m.validate(2.0) is False
        assert m.validate(8.0) is False

    def test_between_no_max_raises(self):
        m = ValidationMetric(name="lat", operator=MetricOperator.BETWEEN, threshold=3.0)
        with pytest.raises(ValueError, match="threshold_max"):
            m.validate(5.0)

    def test_to_dict(self):
        m = ValidationMetric(
            name="latency",
            operator=MetricOperator.LESS_THAN,
            threshold=5.0,
            unit="ms",
            weight=2.0,
        )
        d = m.to_dict()
        assert d["name"] == "latency"
        assert d["operator"] == "<"
        assert d["threshold"] == 5.0
        assert d["unit"] == "ms"
        assert d["weight"] == 2.0


class TestSSValidationResult:
    def test_to_dict(self):
        r = SSValidationResult(
            valid=True,
            metric_name="latency",
            expected_value="<= 5.0",
            actual_value=3.0,
            deviation=10.0,
            message="OK",
        )
        d = r.to_dict()
        assert d["valid"] is True
        assert d["metric_name"] == "latency"
        assert "timestamp" in d
        assert "constitutional_hash" in d


class TestInMemoryMetricCollector:
    @pytest.mark.asyncio
    async def test_record_and_collect(self):
        mc = InMemoryMetricCollector()
        mc.record("latency", 5.0)
        val = await mc.collect("latency")
        assert val == 5.0

    @pytest.mark.asyncio
    async def test_collect_missing_raises(self):
        mc = InMemoryMetricCollector()
        with pytest.raises(KeyError):
            await mc.collect("missing")

    def test_get_average(self):
        mc = InMemoryMetricCollector()
        mc.record("lat", 2.0)
        mc.record("lat", 4.0)
        avg = mc.get_average("lat", window_seconds=60.0)
        assert avg == 3.0

    def test_get_average_missing_raises(self):
        mc = InMemoryMetricCollector()
        with pytest.raises(KeyError):
            mc.get_average("missing")

    def test_get_percentile(self):
        mc = InMemoryMetricCollector()
        for v in range(1, 101):
            mc.record("lat", float(v))
        p50 = mc.get_percentile("lat", 50)
        assert 40 <= p50 <= 60

    def test_get_percentile_missing_raises(self):
        mc = InMemoryMetricCollector()
        with pytest.raises(KeyError):
            mc.get_percentile("missing", 50)

    def test_get_available_metrics(self):
        mc = InMemoryMetricCollector()
        mc.record("a", 1.0)
        mc.record("b", 2.0)
        metrics = mc.get_available_metrics()
        assert "a" in metrics
        assert "b" in metrics

    def test_clear(self):
        mc = InMemoryMetricCollector()
        mc.record("a", 1.0)
        mc.clear()
        assert mc.get_available_metrics() == []


class TestSteadyStateHypothesis:
    def test_to_dict(self):
        h = SteadyStateHypothesis(
            name="test",
            description="Test hypothesis",
            metrics=[
                ValidationMetric(
                    name="lat",
                    operator=MetricOperator.LESS_THAN,
                    threshold=5.0,
                )
            ],
        )
        d = h.to_dict()
        assert d["name"] == "test"
        assert len(d["metrics"]) == 1
        assert "constitutional_hash" in d


class TestSteadyStateValidator:
    @pytest.mark.asyncio
    async def test_validate_passing(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 10.0)},
        )
        v.record_metric("latency", 5.0)
        results = await v.validate()
        assert all(r.valid for r in results)
        assert v.is_valid() is True

    @pytest.mark.asyncio
    async def test_validate_failing(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 2.0)},
        )
        v.record_metric("latency", 5.0)
        for _ in range(4):
            v.record_metric("latency", 5.0)
            await v.validate(consecutive_failures_allowed=0)
        assert v.is_valid() is False

    @pytest.mark.asyncio
    async def test_validate_missing_metric(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 10.0)},
        )
        results = await v.validate()
        assert all(r.valid for r in results)

    @pytest.mark.asyncio
    async def test_add_metric(self):
        v = SteadyStateValidator(name="test")
        m = ValidationMetric(
            name="throughput",
            operator=MetricOperator.GREATER_EQUAL,
            threshold=100.0,
        )
        v.add_metric(m)
        v.record_metric("throughput", 200.0)
        results = await v.validate()
        assert len(results) == 1
        assert results[0].valid is True

    @pytest.mark.asyncio
    async def test_get_violations(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 1.0)},
        )
        v.record_metric("latency", 10.0)
        for _ in range(5):
            v.record_metric("latency", 10.0)
            await v.validate(consecutive_failures_allowed=0)
        violations = v.get_violations()
        assert len(violations) > 0

    @pytest.mark.asyncio
    async def test_get_summary(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 10.0)},
        )
        v.record_metric("latency", 5.0)
        await v.validate()
        summary = v.get_summary()
        assert summary["name"] == "test"
        assert "is_valid" in summary
        assert "constitutional_hash" in summary

    def test_reset(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 10.0)},
        )
        v._is_valid = False
        v.reset()
        assert v.is_valid() is True

    def test_to_hypothesis(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 10.0)},
        )
        h = v.to_hypothesis(tolerance_window_s=10.0)
        assert isinstance(h, SteadyStateHypothesis)
        assert h.name == "test"
        assert h.tolerance_window_s == 10.0

    def test_record_metric_non_collector_raises(self):
        v = SteadyStateValidator(name="test")
        v._collector = MagicMock()
        with pytest.raises(TypeError, match="InMemoryMetricCollector"):
            v.record_metric("lat", 1.0)

    def test_parse_operator_invalid(self):
        v = SteadyStateValidator(name="test")
        with pytest.raises(ValueError, match="Unknown operator"):
            v._parse_operator("~=")

    @pytest.mark.asyncio
    async def test_deviation_calculation(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"latency": ("<=", 5.0)},
        )
        v.record_metric("latency", 10.0)
        results = await v.validate(consecutive_failures_allowed=0)
        assert results[0].deviation is not None
        assert results[0].deviation == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_metric_with_unit(self):
        v = SteadyStateValidator(name="test")
        m = ValidationMetric(
            name="lat",
            operator=MetricOperator.LESS_EQUAL,
            threshold=5.0,
            unit="ms",
        )
        v.add_metric(m)
        v.record_metric("lat", 3.0)
        results = await v.validate()
        assert "ms" in results[0].expected_value

    @pytest.mark.asyncio
    async def test_consecutive_failure_tolerance(self):
        v = SteadyStateValidator(
            name="test",
            metrics={"lat": ("<=", 5.0)},
        )
        v.record_metric("lat", 10.0)
        results = await v.validate(consecutive_failures_allowed=2)
        assert results[0].valid is True

    @pytest.mark.asyncio
    async def test_collection_error(self):
        v = SteadyStateValidator(name="test")
        m = ValidationMetric(
            name="err_metric",
            operator=MetricOperator.LESS_EQUAL,
            threshold=5.0,
        )
        v.add_metric(m)

        mock_collector = MagicMock()
        mock_collector.collect = AsyncMock(side_effect=RuntimeError("collector error"))
        v._collector = mock_collector

        results = await v.validate()
        assert len(results) == 1
        assert results[0].valid is False
        assert "Error collecting" in results[0].message


class TestSteadyStateFactories:
    def test_create_message_bus(self):
        v = create_message_bus_steady_state()
        assert v.name == "enhanced_agent_bus_steady_state"
        assert len(v._validation_metrics) == 7

    def test_create_constitutional_validation(self):
        v = create_constitutional_validation_steady_state()
        assert v.name == "constitutional_validation_steady_state"
        assert len(v._validation_metrics) == 4

    def test_create_maci_enforcement(self):
        v = create_maci_enforcement_steady_state()
        assert v.name == "maci_enforcement_steady_state"
        assert len(v._validation_metrics) == 3


# ---------------------------------------------------------------------------
# 5. opa_client/cache (93 missing lines, 51.1% covered)
# ---------------------------------------------------------------------------

from enhanced_agent_bus.opa_client.cache import (
    DEFAULT_CACHE_HASH_MODE,
    OPAClientCacheMixin,
    _redis_client_available,
)


class TestOPAClientCacheMixinUnit:
    """Test OPAClientCacheMixin methods in isolation using a stub host."""

    def _make_host(self, **overrides):
        class Host(OPAClientCacheMixin):
            pass

        host = Host()
        host.redis_url = overrides.get("redis_url", "redis://localhost:6379/0")
        host.enable_cache = overrides.get("enable_cache", True)
        host.cache_ttl = overrides.get("cache_ttl", 300)
        host.cache_hash_mode = overrides.get("cache_hash_mode", "sha256")
        host._redis_client = overrides.get("_redis_client", None)
        host._memory_cache = overrides.get("_memory_cache", {})
        host._memory_cache_timestamps = overrides.get("_memory_cache_timestamps", {})
        host._memory_cache_maxsize = overrides.get("_memory_cache_maxsize", 1000)
        return host

    def test_generate_cache_key_sha256(self):
        host = self._make_host()
        key = host._generate_cache_key("governance/allow", {"action": "read"})
        assert key.startswith("opa:governance/allow:")
        assert len(key) > 20

    def test_generate_cache_key_deterministic(self):
        host = self._make_host()
        k1 = host._generate_cache_key("p", {"a": 1})
        k2 = host._generate_cache_key("p", {"a": 1})
        assert k1 == k2

    def test_generate_cache_key_different_inputs(self):
        host = self._make_host()
        k1 = host._generate_cache_key("p", {"a": 1})
        k2 = host._generate_cache_key("p", {"a": 2})
        assert k1 != k2

    @pytest.mark.asyncio
    async def test_get_from_cache_disabled(self):
        host = self._make_host(enable_cache=False)
        result = await host._get_from_cache("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_from_cache_memory_hit(self):
        host = self._make_host()
        host._memory_cache["testkey"] = {"allowed": True, "timestamp": time.time()}
        host._memory_cache_timestamps["testkey"] = time.time()
        result = await host._get_from_cache("testkey")
        assert result is not None
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_get_from_cache_memory_expired(self):
        host = self._make_host(cache_ttl=0)
        host._memory_cache["testkey"] = {"allowed": True}
        host._memory_cache_timestamps["testkey"] = time.time() - 1000
        result = await host._get_from_cache("testkey")
        assert result is None

    def test_read_memory_cache_miss(self):
        host = self._make_host()
        result = host._read_memory_cache("nonexistent")
        assert result is None

    def test_read_memory_cache_ttl_expired(self):
        host = self._make_host(cache_ttl=1)
        host._memory_cache["k"] = {"allowed": True}
        host._memory_cache_timestamps["k"] = time.time() - 100
        result = host._read_memory_cache("k")
        assert result is None
        assert "k" not in host._memory_cache

    def test_read_memory_cache_nested_result(self):
        host = self._make_host()
        host._memory_cache["k"] = {"result": {"allowed": True}, "timestamp": time.time()}
        host._memory_cache_timestamps["k"] = time.time()
        result = host._read_memory_cache("k")
        assert result == {"allowed": True}

    def test_read_memory_cache_raw_entry(self):
        host = self._make_host()
        host._memory_cache["k"] = {"some_data": True}
        host._memory_cache_timestamps["k"] = time.time()
        result = host._read_memory_cache("k")
        assert result == {"some_data": True}

    def test_resolve_timestamp_from_cache(self):
        host = self._make_host()
        ts = time.time()
        host._memory_cache_timestamps["k"] = ts
        result = host._resolve_memory_cache_timestamp("k", {})
        assert result == ts

    def test_resolve_timestamp_from_entry(self):
        host = self._make_host()
        result = host._resolve_memory_cache_timestamp("k", {"timestamp": 12345.0})
        assert result == 12345.0
        assert host._memory_cache_timestamps["k"] == 12345.0

    def test_resolve_timestamp_default(self):
        host = self._make_host()
        before = time.time()
        result = host._resolve_memory_cache_timestamp("k", {})
        after = time.time()
        assert before <= result <= after

    def test_normalize_entry_with_allowed(self):
        host = self._make_host()
        entry = {"allowed": True, "reason": "ok"}
        assert host._normalize_memory_cache_entry(entry) == entry

    def test_normalize_entry_nested_result(self):
        host = self._make_host()
        entry = {"result": {"allowed": False}}
        assert host._normalize_memory_cache_entry(entry) == {"allowed": False}

    def test_normalize_entry_fallback(self):
        host = self._make_host()
        entry = {"something": "else"}
        assert host._normalize_memory_cache_entry(entry) == entry

    @pytest.mark.asyncio
    async def test_set_to_cache_disabled(self):
        host = self._make_host(enable_cache=False)
        await host._set_to_cache("key", {"allowed": True})
        assert len(host._memory_cache) == 0

    @pytest.mark.asyncio
    async def test_set_to_cache_memory(self):
        host = self._make_host()
        await host._set_to_cache("testkey", {"allowed": True})
        assert "testkey" in host._memory_cache

    @pytest.mark.asyncio
    async def test_set_to_cache_eviction(self):
        host = self._make_host(_memory_cache_maxsize=2)
        host._memory_cache["old1"] = {"result": {}, "timestamp": 1.0}
        host._memory_cache_timestamps["old1"] = 1.0
        host._memory_cache["old2"] = {"result": {}, "timestamp": 2.0}
        host._memory_cache_timestamps["old2"] = 2.0
        await host._set_to_cache("new", {"allowed": True})
        assert "new" in host._memory_cache

    def test_clear_memory_cache_all(self):
        host = self._make_host()
        host._memory_cache["k1"] = {}
        host._memory_cache["k2"] = {}
        host._memory_cache_timestamps["k1"] = 1.0
        host._memory_cache_timestamps["k2"] = 2.0
        host._clear_memory_cache(None)
        assert len(host._memory_cache) == 0
        assert len(host._memory_cache_timestamps) == 0

    def test_clear_memory_cache_by_path(self):
        host = self._make_host()
        host._memory_cache["opa:governance:abc"] = {}
        host._memory_cache["opa:other:def"] = {}
        host._memory_cache_timestamps["opa:governance:abc"] = 1.0
        host._memory_cache_timestamps["opa:other:def"] = 2.0
        host._clear_memory_cache("governance")
        assert "opa:governance:abc" not in host._memory_cache
        assert "opa:other:def" in host._memory_cache

    @pytest.mark.asyncio
    async def test_clear_cache_no_redis(self):
        host = self._make_host()
        host._memory_cache["k"] = {}
        host._memory_cache_timestamps["k"] = 1.0
        await host.clear_cache()
        assert len(host._memory_cache) == 0

    @pytest.mark.asyncio
    async def test_clear_cache_disabled(self):
        host = self._make_host(enable_cache=False)
        await host.clear_cache()

    @pytest.mark.asyncio
    async def test_clear_cache_specific_path(self):
        host = self._make_host()
        host._memory_cache["opa:test:abc"] = {}
        host._memory_cache_timestamps["opa:test:abc"] = 1.0
        await host.clear_cache(policy_path="test")
        assert "opa:test:abc" not in host._memory_cache

    @pytest.mark.asyncio
    async def test_read_redis_cache_no_client(self):
        host = self._make_host()
        result = await host._read_redis_cache("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_read_redis_cache_hit(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"allowed": true}')
        host = self._make_host(_redis_client=mock_redis)
        result = await host._read_redis_cache("key")
        assert result == {"allowed": True}

    @pytest.mark.asyncio
    async def test_read_redis_cache_json_error(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="not-json{{")
        host = self._make_host(_redis_client=mock_redis)
        result = await host._read_redis_cache("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_redis_keys_empty(self):
        host = self._make_host()
        host._redis_client = AsyncMock()
        await host._delete_redis_keys([])
        host._redis_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_redis_keys_batch(self):
        mock_redis = AsyncMock()
        host = self._make_host(_redis_client=mock_redis)
        keys = [f"key{i}" for i in range(10)]
        await host._delete_redis_keys(keys)
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_to_cache_redis_success(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        host = self._make_host(_redis_client=mock_redis)
        await host._set_to_cache("opa:test:key1", {"allowed": True})
        mock_redis.setex.assert_called_once()
        # Should NOT write to memory cache when Redis succeeds
        assert "opa:test:key1" not in host._memory_cache

    @pytest.mark.asyncio
    async def test_set_to_cache_redis_failure_fallback(self):
        from redis.exceptions import ConnectionError as RedisConnError

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=RedisConnError("redis down"))
        host = self._make_host(_redis_client=mock_redis)
        await host._set_to_cache("testkey", {"allowed": True})
        # Should fall back to memory cache
        assert "testkey" in host._memory_cache

    @pytest.mark.asyncio
    async def test_clear_redis_cache_with_path(self):
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={"key1", "key2"})
        mock_redis.delete = AsyncMock()
        host = self._make_host(_redis_client=mock_redis)
        await host._clear_redis_cache("governance")
        mock_redis.smembers.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_redis_cache_all(self):
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, ["opa:a", "opa:b"]))
        mock_redis.delete = AsyncMock()
        host = self._make_host(_redis_client=mock_redis)
        await host._clear_redis_cache(None)
        mock_redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_initialize_redis_cache_success(self):
        mock_redis_mod = MagicMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_redis_mod.from_url = AsyncMock(return_value=mock_client)

        host = self._make_host()
        with patch(
            "enhanced_agent_bus.opa_client.cache._get_aioredis",
            return_value=mock_redis_mod,
        ):
            await host._initialize_redis_cache()
        assert host._redis_client is mock_client

    @pytest.mark.asyncio
    async def test_initialize_redis_cache_connection_failure(self):
        from redis.exceptions import ConnectionError as RedisConnError

        mock_redis_mod = MagicMock()
        mock_redis_mod.from_url = AsyncMock(side_effect=RedisConnError("fail"))

        host = self._make_host()
        with patch(
            "enhanced_agent_bus.opa_client.cache._get_aioredis",
            return_value=mock_redis_mod,
        ):
            await host._initialize_redis_cache()
        assert host._redis_client is None

    @pytest.mark.asyncio
    async def test_initialize_redis_cache_timeout(self):
        from redis.exceptions import TimeoutError as RedisTimeout

        mock_redis_mod = MagicMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=RedisTimeout("timeout"))
        mock_redis_mod.from_url = AsyncMock(return_value=mock_client)

        host = self._make_host()
        with patch(
            "enhanced_agent_bus.opa_client.cache._get_aioredis",
            return_value=mock_redis_mod,
        ):
            await host._initialize_redis_cache()
        assert host._redis_client is None

    @pytest.mark.asyncio
    async def test_initialize_redis_cache_generic_error(self):
        from redis.exceptions import RedisError

        mock_redis_mod = MagicMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=RedisError("bad"))
        mock_redis_mod.from_url = AsyncMock(return_value=mock_client)

        host = self._make_host()
        with patch(
            "enhanced_agent_bus.opa_client.cache._get_aioredis",
            return_value=mock_redis_mod,
        ):
            await host._initialize_redis_cache()
        assert host._redis_client is None


class TestRedisClientAvailable:
    def test_returns_bool(self):
        result = _redis_client_available()
        assert isinstance(result, bool)


class TestDefaultCacheHashMode:
    def test_value(self):
        assert DEFAULT_CACHE_HASH_MODE == "sha256"
