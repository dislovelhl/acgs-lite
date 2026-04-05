# Constitutional Hash: 608508a9bd224290
"""
Comprehensive coverage tests for langgraph_orchestration/exceptions.py.

Targets ≥90% coverage of:
  packages/enhanced_agent_bus/langgraph_orchestration/exceptions.py
"""

import sys
import types

# ---------------------------------------------------------------------------
# Stub the langgraph_orchestration package so its __init__.py (which
# transitively triggers a Python-3.14-incompatible `from typing import object`
# in models.py) is never executed.  We only need the exceptions submodule.
# ---------------------------------------------------------------------------
_PKG = "enhanced_agent_bus.langgraph_orchestration"
if _PKG not in sys.modules:
    _stub = types.ModuleType(_PKG)
    _stub.__path__ = ["packages/enhanced_agent_bus/langgraph_orchestration"]
    _stub.__package__ = _PKG
    sys.modules[_PKG] = _stub

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.langgraph_orchestration.exceptions import (
    CheckpointError,
    ConstitutionalViolationError,
    CyclicDependencyError,
    GraphValidationError,
    InterruptError,
    MACIViolationError,
    NodeExecutionError,
    OrchestrationError,
    StateTransitionError,
    TimeoutError,
)

# ---------------------------------------------------------------------------
# OrchestrationError (base)
# ---------------------------------------------------------------------------


class TestOrchestrationError:
    def test_basic_instantiation(self):
        err = OrchestrationError("something went wrong")
        assert "something went wrong" in str(err)
        assert err.http_status_code == 500
        assert err.error_code == "ORCHESTRATION_ERROR"

    def test_with_details(self):
        err = OrchestrationError("oops", details={"key": "value"})
        assert err.details == {"key": "value"}

    def test_default_constitutional_hash(self):
        err = OrchestrationError("msg")
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_constitutional_hash(self):
        err = OrchestrationError("msg", constitutional_hash="custom-hash")
        assert err.constitutional_hash == "custom-hash"

    def test_to_dict_contains_required_keys(self):
        err = OrchestrationError("test error", details={"x": 1})
        d = err.to_dict()
        assert isinstance(d, dict)
        assert d["message"] == "test error"
        # legacy error_type field added by AgentBusError
        assert d["error_type"] == "OrchestrationError"

    def test_to_dict_no_details(self):
        err = OrchestrationError("bare error")
        d = err.to_dict()
        assert "message" in d

    def test_is_exception_subclass(self):
        err = OrchestrationError("x")
        assert isinstance(err, OrchestrationError)

    def test_raise_and_catch(self):
        with pytest.raises(OrchestrationError):
            raise OrchestrationError("boom")


# ---------------------------------------------------------------------------
# StateTransitionError
# ---------------------------------------------------------------------------


class TestStateTransitionError:
    def test_basic(self):
        err = StateTransitionError("IDLE", "RUNNING", "invalid transition")
        assert err.from_state == "IDLE"
        assert err.to_state == "RUNNING"
        assert err.reason == "invalid transition"
        assert err.node_id is None

    def test_message_format(self):
        err = StateTransitionError("A", "B", "reason X")
        assert "A" in str(err)
        assert "B" in str(err)
        assert "reason X" in str(err)

    def test_with_node_id(self):
        err = StateTransitionError("A", "B", "bad", node_id="node-1")
        assert err.node_id == "node-1"
        assert "[Node: node-1]" in str(err)

    def test_without_node_id_no_bracket(self):
        err = StateTransitionError("A", "B", "bad")
        assert "[Node:" not in str(err)

    def test_details_populated(self):
        err = StateTransitionError("S1", "S2", "r", node_id="n1")
        d = err.to_dict()
        assert d["details"]["from_state"] == "S1"
        assert d["details"]["to_state"] == "S2"
        assert d["details"]["reason"] == "r"
        assert d["details"]["node_id"] == "n1"

    def test_details_node_id_none(self):
        err = StateTransitionError("S1", "S2", "r")
        d = err.to_dict()
        assert d["details"]["node_id"] is None

    def test_is_orchestration_error(self):
        err = StateTransitionError("A", "B", "c")
        assert isinstance(err, OrchestrationError)

    def test_raise_and_catch_as_orchestration(self):
        with pytest.raises(OrchestrationError):
            raise StateTransitionError("X", "Y", "z")


# ---------------------------------------------------------------------------
# NodeExecutionError
# ---------------------------------------------------------------------------


class TestNodeExecutionError:
    def test_basic(self):
        cause = ValueError("inner error")
        err = NodeExecutionError("node-1", "governance", cause)
        assert err.node_id == "node-1"
        assert err.node_type == "governance"
        assert err.original_error is cause
        assert err.execution_time_ms is None

    def test_message_format(self):
        cause = RuntimeError("fail")
        err = NodeExecutionError("n1", "policy", cause)
        assert "n1" in str(err)
        assert "policy" in str(err)

    def test_with_execution_time(self):
        cause = Exception("e")
        err = NodeExecutionError("n1", "type", cause, execution_time_ms=42.5)
        assert err.execution_time_ms == 42.5

    def test_details_populated(self):
        cause = TypeError("bad type")
        err = NodeExecutionError("n2", "t2", cause, execution_time_ms=10.0)
        d = err.to_dict()
        assert d["details"]["node_id"] == "n2"
        assert d["details"]["node_type"] == "t2"
        assert d["details"]["original_error"] == str(cause)
        assert d["details"]["original_error_type"] == "TypeError"
        assert d["details"]["execution_time_ms"] == 10.0

    def test_details_execution_time_none(self):
        err = NodeExecutionError("n", "t", Exception("x"))
        d = err.to_dict()
        assert d["details"]["execution_time_ms"] is None

    def test_is_orchestration_error(self):
        err = NodeExecutionError("n", "t", Exception("x"))
        assert isinstance(err, OrchestrationError)


# ---------------------------------------------------------------------------
# GraphValidationError
# ---------------------------------------------------------------------------


class TestGraphValidationError:
    def test_single_error(self):
        err = GraphValidationError(["missing start node"])
        assert err.validation_errors == ["missing start node"]
        assert err.graph_id is None
        assert "missing start node" in str(err)

    def test_multiple_errors(self):
        errors = ["no start", "cyclic dep", "missing end"]
        err = GraphValidationError(errors)
        assert len(err.validation_errors) == 3

    def test_message_joins_errors(self):
        errors = ["e1", "e2"]
        err = GraphValidationError(errors)
        assert "e1" in str(err)
        assert "e2" in str(err)

    def test_with_graph_id(self):
        err = GraphValidationError(["err"], graph_id="g-1")
        assert err.graph_id == "g-1"
        assert "[Graph: g-1]" in str(err)

    def test_without_graph_id_no_bracket(self):
        err = GraphValidationError(["err"])
        assert "[Graph:" not in str(err)

    def test_details_populated(self):
        err = GraphValidationError(["e1", "e2"], graph_id="gx")
        d = err.to_dict()
        assert d["details"]["validation_errors"] == ["e1", "e2"]
        assert d["details"]["graph_id"] == "gx"

    def test_details_graph_id_none(self):
        err = GraphValidationError(["e1"])
        d = err.to_dict()
        assert d["details"]["graph_id"] is None

    def test_is_orchestration_error(self):
        err = GraphValidationError(["x"])
        assert isinstance(err, OrchestrationError)


# ---------------------------------------------------------------------------
# CheckpointError
# ---------------------------------------------------------------------------


class TestCheckpointError:
    def test_basic(self):
        err = CheckpointError("cp-1", "save", "disk full")
        assert err.checkpoint_id == "cp-1"
        assert err.operation == "save"
        assert err.reason == "disk full"
        assert err.workflow_id is None

    def test_message_format(self):
        err = CheckpointError("cp-1", "load", "not found")
        assert "cp-1" in str(err)
        assert "load" in str(err)
        assert "not found" in str(err)

    def test_with_workflow_id(self):
        err = CheckpointError("cp-1", "save", "err", workflow_id="wf-1")
        assert err.workflow_id == "wf-1"
        assert "[Workflow: wf-1]" in str(err)

    def test_without_workflow_id_no_bracket(self):
        err = CheckpointError("cp-1", "save", "err")
        assert "[Workflow:" not in str(err)

    def test_details_populated(self):
        err = CheckpointError("cp-2", "delete", "reason", workflow_id="wf-2")
        d = err.to_dict()
        assert d["details"]["checkpoint_id"] == "cp-2"
        assert d["details"]["operation"] == "delete"
        assert d["details"]["reason"] == "reason"
        assert d["details"]["workflow_id"] == "wf-2"

    def test_details_workflow_id_none(self):
        err = CheckpointError("cp-1", "op", "r")
        d = err.to_dict()
        assert d["details"]["workflow_id"] is None

    def test_is_orchestration_error(self):
        err = CheckpointError("c", "o", "r")
        assert isinstance(err, OrchestrationError)


# ---------------------------------------------------------------------------
# InterruptError
# ---------------------------------------------------------------------------


class TestInterruptError:
    def test_basic(self):
        err = InterruptError("SIGTERM", "unexpected signal")
        assert err.interrupt_type == "SIGTERM"
        assert err.reason == "unexpected signal"
        assert err.node_id is None
        assert err.workflow_id is None

    def test_message_format(self):
        err = InterruptError("HALT", "stop requested")
        assert "HALT" in str(err)
        assert "stop requested" in str(err)

    def test_with_node_id_only(self):
        err = InterruptError("PAUSE", "paused", node_id="n-1")
        assert "[Node: n-1]" in str(err)
        assert "[Workflow:" not in str(err)

    def test_with_workflow_id_only(self):
        err = InterruptError("PAUSE", "paused", workflow_id="wf-1")
        assert "[Workflow: wf-1]" in str(err)
        assert "[Node:" not in str(err)

    def test_with_both_ids(self):
        err = InterruptError("STOP", "stopped", node_id="n-1", workflow_id="wf-1")
        assert "[Node: n-1]" in str(err)
        assert "[Workflow: wf-1]" in str(err)

    def test_details_populated(self):
        err = InterruptError("T", "r", node_id="n", workflow_id="w")
        d = err.to_dict()
        assert d["details"]["interrupt_type"] == "T"
        assert d["details"]["reason"] == "r"
        assert d["details"]["node_id"] == "n"
        assert d["details"]["workflow_id"] == "w"

    def test_details_nones(self):
        err = InterruptError("T", "r")
        d = err.to_dict()
        assert d["details"]["node_id"] is None
        assert d["details"]["workflow_id"] is None

    def test_is_orchestration_error(self):
        err = InterruptError("T", "r")
        assert isinstance(err, OrchestrationError)


# ---------------------------------------------------------------------------
# TimeoutError
# ---------------------------------------------------------------------------


class TestTimeoutError:
    def test_basic(self):
        err = TimeoutError("validate", 5000.0)
        assert err.operation == "validate"
        assert err.timeout_ms == 5000.0
        assert err.elapsed_ms is None
        assert err.context is None

    def test_message_format(self):
        err = TimeoutError("validate", 5000.0)
        assert "validate" in str(err)
        assert "5000" in str(err)

    def test_with_elapsed(self):
        err = TimeoutError("op", 100.0, elapsed_ms=105.0)
        assert err.elapsed_ms == 105.0
        assert "elapsed: 105.0ms" in str(err)

    def test_without_elapsed_no_elapsed_in_message(self):
        err = TimeoutError("op", 100.0)
        assert "elapsed" not in str(err)

    def test_with_context(self):
        err = TimeoutError("op", 100.0, context="node-processing")
        assert "node-processing" in str(err)

    def test_without_context_no_bracket(self):
        err = TimeoutError("op", 100.0)
        msg = str(err)
        assert "[" not in msg or "elapsed" not in msg  # no context bracket

    def test_with_elapsed_and_context(self):
        err = TimeoutError("op", 100.0, elapsed_ms=110.0, context="ctx")
        msg = str(err)
        assert "elapsed: 110.0ms" in msg
        assert "ctx" in msg

    def test_details_populated(self):
        err = TimeoutError("op", 200.0, elapsed_ms=210.0, context="c")
        d = err.to_dict()
        assert d["details"]["operation"] == "op"
        assert d["details"]["timeout_ms"] == 200.0
        assert d["details"]["elapsed_ms"] == 210.0
        assert d["details"]["context"] == "c"

    def test_details_nones(self):
        err = TimeoutError("op", 200.0)
        d = err.to_dict()
        assert d["details"]["elapsed_ms"] is None
        assert d["details"]["context"] is None

    def test_is_orchestration_error(self):
        err = TimeoutError("op", 100.0)
        assert isinstance(err, OrchestrationError)

    def test_raise_and_catch(self):
        with pytest.raises(TimeoutError):
            raise TimeoutError("slow_op", 1000.0)


# ---------------------------------------------------------------------------
# ConstitutionalViolationError
# ---------------------------------------------------------------------------


class TestConstitutionalViolationError:
    def test_basic(self):
        err = ConstitutionalViolationError(["hash mismatch"])
        assert err.violations == ["hash mismatch"]
        assert err.node_id is None
        assert err.transition is None

    def test_message_format(self):
        err = ConstitutionalViolationError(["v1", "v2"])
        msg = str(err)
        assert "v1" in msg
        assert "v2" in msg

    def test_with_node_id(self):
        err = ConstitutionalViolationError(["v"], node_id="n-1")
        assert "[Node: n-1]" in str(err)

    def test_with_transition(self):
        err = ConstitutionalViolationError(["v"], transition="A->B")
        assert "[Transition: A->B]" in str(err)

    def test_with_both_node_and_transition(self):
        err = ConstitutionalViolationError(["v"], node_id="n-1", transition="A->B")
        msg = str(err)
        assert "[Node: n-1]" in msg
        assert "[Transition: A->B]" in msg

    def test_without_optional_args(self):
        err = ConstitutionalViolationError(["v"])
        msg = str(err)
        assert "[Node:" not in msg
        assert "[Transition:" not in msg

    def test_details_populated(self):
        err = ConstitutionalViolationError(["v1", "v2"], node_id="n", transition="t")
        d = err.to_dict()
        assert d["details"]["violations"] == ["v1", "v2"]
        assert d["details"]["node_id"] == "n"
        assert d["details"]["transition"] == "t"

    def test_details_nones(self):
        err = ConstitutionalViolationError(["v"])
        d = err.to_dict()
        assert d["details"]["node_id"] is None
        assert d["details"]["transition"] is None

    def test_is_orchestration_error(self):
        err = ConstitutionalViolationError(["v"])
        assert isinstance(err, OrchestrationError)


# ---------------------------------------------------------------------------
# CyclicDependencyError
# ---------------------------------------------------------------------------


class TestCyclicDependencyError:
    def test_basic(self):
        err = CyclicDependencyError(["A", "B", "C", "A"])
        assert err.cycle_path == ["A", "B", "C", "A"]
        assert err.graph_id is None

    def test_message_format(self):
        err = CyclicDependencyError(["X", "Y", "X"])
        msg = str(err)
        assert "X -> Y -> X" in msg

    def test_with_graph_id(self):
        err = CyclicDependencyError(["A", "B", "A"], graph_id="g-1")
        assert err.graph_id == "g-1"
        assert "[Graph: g-1]" in str(err)

    def test_without_graph_id_no_bracket(self):
        err = CyclicDependencyError(["A", "B", "A"])
        assert "[Graph:" not in str(err)

    def test_details_populated(self):
        path = ["N1", "N2", "N1"]
        err = CyclicDependencyError(path, graph_id="gx")
        d = err.to_dict()
        assert d["details"]["cycle_path"] == path
        assert d["details"]["graph_id"] == "gx"

    def test_details_graph_id_none(self):
        err = CyclicDependencyError(["A", "B"])
        d = err.to_dict()
        assert d["details"]["graph_id"] is None

    def test_is_orchestration_error(self):
        err = CyclicDependencyError(["A"])
        assert isinstance(err, OrchestrationError)


# ---------------------------------------------------------------------------
# MACIViolationError
# ---------------------------------------------------------------------------


class TestMACIViolationError:
    def test_basic(self):
        err = MACIViolationError("agent-1", "ADMIN", "USER", "delete_policy")
        assert err.agent_id == "agent-1"
        assert err.required_role == "ADMIN"
        assert err.actual_role == "USER"
        assert err.action == "delete_policy"

    def test_message_format(self):
        err = MACIViolationError("a1", "ADMIN", "USER", "action")
        msg = str(err)
        assert "a1" in msg
        assert "ADMIN" in msg
        assert "USER" in msg
        assert "action" in msg

    def test_actual_role_none_shows_none_string(self):
        err = MACIViolationError("a1", "ADMIN", None, "action")
        assert err.actual_role is None
        assert "none" in str(err).lower()

    def test_details_populated(self):
        err = MACIViolationError("a1", "r1", "r2", "act")
        d = err.to_dict()
        assert d["details"]["agent_id"] == "a1"
        assert d["details"]["required_role"] == "r1"
        assert d["details"]["actual_role"] == "r2"
        assert d["details"]["action"] == "act"

    def test_details_actual_role_none(self):
        err = MACIViolationError("a1", "r1", None, "act")
        d = err.to_dict()
        assert d["details"]["actual_role"] is None

    def test_is_orchestration_error(self):
        err = MACIViolationError("a", "r", "r2", "act")
        assert isinstance(err, OrchestrationError)


# ---------------------------------------------------------------------------
# Exception hierarchy / isinstance checks
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_all_inherit_from_orchestration_error(self):
        exceptions = [
            StateTransitionError("a", "b", "c"),
            NodeExecutionError("n", "t", Exception("e")),
            GraphValidationError(["v"]),
            CheckpointError("c", "o", "r"),
            InterruptError("t", "r"),
            TimeoutError("op", 100.0),
            ConstitutionalViolationError(["v"]),
            CyclicDependencyError(["a", "b"]),
            MACIViolationError("a", "rr", "ra", "act"),
        ]
        for exc in exceptions:
            assert isinstance(exc, OrchestrationError), (
                f"{type(exc).__name__} must inherit OrchestrationError"
            )

    def test_all_are_exceptions(self):
        err = OrchestrationError("x")
        assert isinstance(err, OrchestrationError)

    def test_catching_base_catches_derived(self):
        raised_types = [
            StateTransitionError("a", "b", "c"),
            NodeExecutionError("n", "t", Exception("e")),
            GraphValidationError(["v"]),
            CheckpointError("c", "o", "r"),
            InterruptError("t", "r"),
            TimeoutError("op", 100.0),
            ConstitutionalViolationError(["v"]),
            CyclicDependencyError(["a", "b"]),
            MACIViolationError("a", "rr", "ra", "act"),
        ]
        for exc in raised_types:
            try:
                raise exc
            except OrchestrationError:
                pass
            else:
                pytest.fail(f"{type(exc).__name__} not caught as OrchestrationError")


# ---------------------------------------------------------------------------
# __all__ export list
# ---------------------------------------------------------------------------


class TestDunderAll:
    def test_all_classes_exported(self):
        import importlib

        exc_mod = importlib.import_module("enhanced_agent_bus.langgraph_orchestration.exceptions")

        expected = {
            "OrchestrationError",
            "StateTransitionError",
            "NodeExecutionError",
            "GraphValidationError",
            "CheckpointError",
            "InterruptError",
            "TimeoutError",
            "ConstitutionalViolationError",
            "CyclicDependencyError",
            "MACIViolationError",
        }
        assert set(exc_mod.__all__) == expected
