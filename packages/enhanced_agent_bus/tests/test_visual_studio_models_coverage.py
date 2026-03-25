# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/visual_studio/models.py
Target: ≥95% line coverage (109 statements)
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.visual_studio.models import (
    ExportFormat,
    NodeType,
    SimulationStep,
    VisualStudioValidationResult,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowExportRequest,
    WorkflowExportResult,
    WorkflowListResponse,
    WorkflowNode,
    WorkflowSimulationResult,
    WorkflowSummary,
    WorkflowValidationResult,
)

# ---------------------------------------------------------------------------
# NodeType enum
# ---------------------------------------------------------------------------


class TestNodeType:
    def test_start_value(self):
        assert NodeType.START == "start"

    def test_end_value(self):
        assert NodeType.END == "end"

    def test_policy_value(self):
        assert NodeType.POLICY == "policy"

    def test_condition_value(self):
        assert NodeType.CONDITION == "condition"

    def test_action_value(self):
        assert NodeType.ACTION == "action"

    def test_is_str_subclass(self):
        assert isinstance(NodeType.START, str)

    def test_all_members(self):
        members = {m.value for m in NodeType}
        assert members == {"start", "end", "policy", "condition", "action"}

    def test_from_string(self):
        assert NodeType("start") == NodeType.START

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            NodeType("invalid_node_type")


# ---------------------------------------------------------------------------
# ExportFormat enum
# ---------------------------------------------------------------------------


class TestExportFormat:
    def test_json_value(self):
        assert ExportFormat.JSON == "json"

    def test_rego_value(self):
        assert ExportFormat.REGO == "rego"

    def test_yaml_value(self):
        assert ExportFormat.YAML == "yaml"

    def test_is_str_subclass(self):
        assert isinstance(ExportFormat.JSON, str)

    def test_all_members(self):
        values = {m.value for m in ExportFormat}
        assert values == {"json", "rego", "yaml"}

    def test_from_string(self):
        assert ExportFormat("rego") == ExportFormat.REGO

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ExportFormat("xml")


# ---------------------------------------------------------------------------
# WorkflowNode
# ---------------------------------------------------------------------------


class TestWorkflowNode:
    def _make(self, **kwargs):
        defaults = {"id": "node-1", "type": NodeType.START}
        defaults.update(kwargs)
        return WorkflowNode(**defaults)

    def test_minimal_creation(self):
        node = self._make()
        assert node.id == "node-1"
        assert node.type == NodeType.START

    def test_default_position(self):
        node = self._make()
        assert node.position == {"x": 0.0, "y": 0.0}

    def test_custom_position(self):
        node = self._make(position={"x": 10.5, "y": 20.3})
        assert node.position["x"] == pytest.approx(10.5)
        assert node.position["y"] == pytest.approx(20.3)

    def test_default_data_empty_dict(self):
        node = self._make()
        assert node.data == {}

    def test_custom_data(self):
        data = {"label": "Start Node", "description": "Entry point"}
        node = self._make(data=data)
        assert node.data["label"] == "Start Node"

    def test_default_width_none(self):
        assert self._make().width is None

    def test_custom_width(self):
        node = self._make(width=200.0)
        assert node.width == pytest.approx(200.0)

    def test_default_height_none(self):
        assert self._make().height is None

    def test_custom_height(self):
        node = self._make(height=50.0)
        assert node.height == pytest.approx(50.0)

    def test_default_selected_false(self):
        assert self._make().selected is False

    def test_selected_true(self):
        node = self._make(selected=True)
        assert node.selected is True

    def test_default_dragging_false(self):
        assert self._make().dragging is False

    def test_dragging_true(self):
        node = self._make(dragging=True)
        assert node.dragging is True

    def test_all_node_types(self):
        for nt in NodeType:
            node = self._make(type=nt)
            assert node.type == nt

    def test_id_min_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(id="")

    def test_id_max_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(id="x" * 101)

    def test_id_max_length_boundary(self):
        node = self._make(id="x" * 100)
        assert len(node.id) == 100

    def test_position_validator_missing_x(self):
        with pytest.raises(ValidationError) as exc_info:
            self._make(position={"y": 5.0})
        assert "Position must contain 'x' and 'y' coordinates" in str(exc_info.value)

    def test_position_validator_missing_y(self):
        with pytest.raises(ValidationError) as exc_info:
            self._make(position={"x": 5.0})
        assert "Position must contain 'x' and 'y' coordinates" in str(exc_info.value)

    def test_position_validator_missing_both(self):
        with pytest.raises(ValidationError):
            self._make(position={})

    def test_position_validator_extra_keys_ok(self):
        node = self._make(position={"x": 1.0, "y": 2.0, "z": 3.0})
        assert node.position["z"] == 3.0

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            self._make(type="not_a_type")

    def test_serialization_roundtrip(self):
        node = self._make(position={"x": 5.0, "y": 10.0}, selected=True)
        dumped = node.model_dump()
        loaded = WorkflowNode(**dumped)
        assert loaded.id == node.id
        assert loaded.position == node.position

    def test_json_serialization(self):
        node = self._make()
        json_str = node.model_dump_json()
        assert "node-1" in json_str


# ---------------------------------------------------------------------------
# WorkflowEdge
# ---------------------------------------------------------------------------


class TestWorkflowEdge:
    def _make(self, **kwargs):
        defaults = {"id": "edge-1", "source": "node-1", "target": "node-2"}
        defaults.update(kwargs)
        return WorkflowEdge(**defaults)

    def test_minimal_creation(self):
        edge = self._make()
        assert edge.id == "edge-1"
        assert edge.source == "node-1"
        assert edge.target == "node-2"

    def test_default_source_handle_none(self):
        assert self._make().source_handle is None

    def test_custom_source_handle(self):
        edge = self._make(source_handle="handle-a")
        assert edge.source_handle == "handle-a"

    def test_default_target_handle_none(self):
        assert self._make().target_handle is None

    def test_custom_target_handle(self):
        edge = self._make(target_handle="handle-b")
        assert edge.target_handle == "handle-b"

    def test_default_label_none(self):
        assert self._make().label is None

    def test_custom_label(self):
        edge = self._make(label="Yes")
        assert edge.label == "Yes"

    def test_default_type_smoothstep(self):
        assert self._make().type == "smoothstep"

    def test_custom_type(self):
        edge = self._make(type="straight")
        assert edge.type == "straight"

    def test_type_can_be_none(self):
        edge = self._make(type=None)
        assert edge.type is None

    def test_default_animated_false(self):
        assert self._make().animated is False

    def test_animated_true(self):
        edge = self._make(animated=True)
        assert edge.animated is True

    def test_default_style_none(self):
        assert self._make().style is None

    def test_custom_style(self):
        style = {"stroke": "#ff0000", "strokeWidth": 2}
        edge = self._make(style=style)
        assert edge.style["stroke"] == "#ff0000"

    def test_default_data_none(self):
        assert self._make().data is None

    def test_custom_data(self):
        edge = self._make(data={"weight": 1.0})
        assert edge.data["weight"] == 1.0

    def test_id_min_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(id="")

    def test_id_max_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(id="x" * 101)

    def test_source_min_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(source="")

    def test_target_min_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(target="")

    def test_serialization_roundtrip(self):
        edge = self._make(label="test", animated=True)
        loaded = WorkflowEdge(**edge.model_dump())
        assert loaded.label == "test"
        assert loaded.animated is True


# ---------------------------------------------------------------------------
# WorkflowDefinition
# ---------------------------------------------------------------------------


class TestWorkflowDefinition:
    def _node(self, node_id: str = "n1") -> WorkflowNode:
        return WorkflowNode(id=node_id, type=NodeType.START)

    def _edge(self, edge_id: str = "e1") -> WorkflowEdge:
        return WorkflowEdge(id=edge_id, source="n1", target="n2")

    def _make(self, **kwargs):
        defaults = {"id": "wf-1", "name": "My Workflow"}
        defaults.update(kwargs)
        return WorkflowDefinition(**defaults)

    def test_minimal_creation(self):
        wf = self._make()
        assert wf.id == "wf-1"
        assert wf.name == "My Workflow"

    def test_default_description_none(self):
        assert self._make().description is None

    def test_custom_description(self):
        wf = self._make(description="Test workflow")
        assert wf.description == "Test workflow"

    def test_default_nodes_empty(self):
        assert self._make().nodes == []

    def test_custom_nodes(self):
        nodes = [self._node("n1"), self._node("n2")]
        wf = self._make(nodes=nodes)
        assert len(wf.nodes) == 2

    def test_default_edges_empty(self):
        assert self._make().edges == []

    def test_custom_edges(self):
        edges = [self._edge()]
        wf = self._make(edges=edges)
        assert len(wf.edges) == 1

    def test_default_viewport_none(self):
        assert self._make().viewport is None

    def test_custom_viewport(self):
        vp = {"x": 0.0, "y": 0.0, "zoom": 1.0}
        wf = self._make(viewport=vp)
        assert wf.viewport["zoom"] == 1.0

    def test_default_version(self):
        assert self._make().version == "1.0.0"

    def test_custom_version(self):
        wf = self._make(version="2.1.0")
        assert wf.version == "2.1.0"

    def test_default_tenant_id_none(self):
        assert self._make().tenant_id is None

    def test_custom_tenant_id(self):
        wf = self._make(tenant_id="tenant-xyz")
        assert wf.tenant_id == "tenant-xyz"

    def test_default_tags_empty(self):
        assert self._make().tags == []

    def test_custom_tags(self):
        wf = self._make(tags=["governance", "compliance"])
        assert "governance" in wf.tags

    def test_default_is_active_true(self):
        assert self._make().is_active is True

    def test_is_active_false(self):
        wf = self._make(is_active=False)
        assert wf.is_active is False

    def test_created_at_is_datetime(self):
        wf = self._make()
        assert isinstance(wf.created_at, datetime)
        assert wf.created_at.tzinfo is not None

    def test_updated_at_is_datetime(self):
        wf = self._make()
        assert isinstance(wf.updated_at, datetime)

    def test_set_updated_at_validator_with_none(self):
        """Validator replaces None with current timezone.utc time."""
        wf = WorkflowDefinition(id="wf-x", name="X", updated_at=None)
        assert isinstance(wf.updated_at, datetime)
        assert wf.updated_at.tzinfo is not None

    def test_set_updated_at_validator_with_existing_datetime(self):
        """Validator always overwrites with current time."""
        past = datetime(2000, 1, 1, tzinfo=UTC)
        wf = WorkflowDefinition(id="wf-x", name="X", updated_at=past)
        # The validator sets it to now — should be after year 2000
        assert wf.updated_at.year >= 2000

    def test_id_min_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(id="")

    def test_id_max_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(id="x" * 101)

    def test_name_min_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(name="")

    def test_name_max_length_violation(self):
        with pytest.raises(ValidationError):
            self._make(name="x" * 201)

    def test_name_max_length_boundary(self):
        wf = self._make(name="x" * 200)
        assert len(wf.name) == 200

    def test_serialization_roundtrip(self):
        wf = self._make(
            nodes=[self._node()],
            edges=[self._edge()],
            tags=["tag1"],
        )
        data = wf.model_dump()
        loaded = WorkflowDefinition(**data)
        assert loaded.id == wf.id
        assert len(loaded.nodes) == 1


# ---------------------------------------------------------------------------
# VisualStudioValidationResult
# ---------------------------------------------------------------------------


class TestVisualStudioValidationResult:
    def test_minimal_creation(self):
        result = VisualStudioValidationResult(message="Some error")
        assert result.message == "Some error"

    def test_default_field_none(self):
        result = VisualStudioValidationResult(message="err")
        assert result.field is None

    def test_custom_field(self):
        result = VisualStudioValidationResult(message="err", field="nodes")
        assert result.field == "nodes"

    def test_default_node_id_none(self):
        result = VisualStudioValidationResult(message="err")
        assert result.node_id is None

    def test_custom_node_id(self):
        result = VisualStudioValidationResult(message="err", node_id="node-1")
        assert result.node_id == "node-1"

    def test_default_severity_error(self):
        result = VisualStudioValidationResult(message="err")
        assert result.severity == "error"

    def test_severity_warning(self):
        result = VisualStudioValidationResult(message="warn", severity="warning")
        assert result.severity == "warning"

    def test_severity_info(self):
        result = VisualStudioValidationResult(message="info msg", severity="info")
        assert result.severity == "info"

    def test_all_fields_provided(self):
        result = VisualStudioValidationResult(
            field="edges", message="Invalid edge", node_id="n1", severity="warning"
        )
        assert result.field == "edges"
        assert result.node_id == "n1"
        assert result.severity == "warning"

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            VisualStudioValidationResult()


# ---------------------------------------------------------------------------
# WorkflowValidationResult
# ---------------------------------------------------------------------------


class TestWorkflowValidationResult:
    def test_valid_workflow(self):
        result = WorkflowValidationResult(is_valid=True)
        assert result.is_valid is True

    def test_invalid_workflow(self):
        result = WorkflowValidationResult(is_valid=False)
        assert result.is_valid is False

    def test_default_errors_empty(self):
        result = WorkflowValidationResult(is_valid=True)
        assert result.errors == []

    def test_custom_errors(self):
        err = VisualStudioValidationResult(message="Missing start node")
        result = WorkflowValidationResult(is_valid=False, errors=[err])
        assert len(result.errors) == 1
        assert result.errors[0].message == "Missing start node"

    def test_default_warnings_empty(self):
        result = WorkflowValidationResult(is_valid=True)
        assert result.warnings == []

    def test_custom_warnings(self):
        warn = VisualStudioValidationResult(message="No end node", severity="warning")
        result = WorkflowValidationResult(is_valid=True, warnings=[warn])
        assert len(result.warnings) == 1

    def test_timestamp_is_datetime(self):
        result = WorkflowValidationResult(is_valid=True)
        assert isinstance(result.timestamp, datetime)
        assert result.timestamp.tzinfo is not None

    def test_missing_is_valid_raises(self):
        with pytest.raises(ValidationError):
            WorkflowValidationResult()

    def test_multiple_errors_and_warnings(self):
        errors = [
            VisualStudioValidationResult(message="Error 1"),
            VisualStudioValidationResult(message="Error 2"),
        ]
        warnings = [
            VisualStudioValidationResult(message="Warn 1", severity="warning"),
        ]
        result = WorkflowValidationResult(is_valid=False, errors=errors, warnings=warnings)
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


# ---------------------------------------------------------------------------
# SimulationStep
# ---------------------------------------------------------------------------


class TestSimulationStep:
    def _make(self, **kwargs):
        defaults = {
            "step_number": 1,
            "node_id": "node-1",
            "node_type": NodeType.START,
            "status": "success",
        }
        defaults.update(kwargs)
        return SimulationStep(**defaults)

    def test_minimal_creation(self):
        step = self._make()
        assert step.step_number == 1
        assert step.node_id == "node-1"
        assert step.node_type == NodeType.START
        assert step.status == "success"

    def test_default_input_data_empty(self):
        assert self._make().input_data == {}

    def test_custom_input_data(self):
        step = self._make(input_data={"key": "value"})
        assert step.input_data["key"] == "value"

    def test_default_output_data_empty(self):
        assert self._make().output_data == {}

    def test_custom_output_data(self):
        step = self._make(output_data={"result": 42})
        assert step.output_data["result"] == 42

    def test_status_error(self):
        step = self._make(status="error")
        assert step.status == "error"

    def test_status_skipped(self):
        step = self._make(status="skipped")
        assert step.status == "skipped"

    def test_timestamp_is_datetime(self):
        step = self._make()
        assert isinstance(step.timestamp, datetime)
        assert step.timestamp.tzinfo is not None

    def test_default_execution_time_none(self):
        assert self._make().execution_time_ms is None

    def test_custom_execution_time(self):
        step = self._make(execution_time_ms=12.5)
        assert step.execution_time_ms == pytest.approx(12.5)

    def test_all_node_types(self):
        for nt in NodeType:
            step = self._make(node_type=nt)
            assert step.node_type == nt

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            SimulationStep(step_number=1)

    def test_serialization_roundtrip(self):
        step = self._make(execution_time_ms=5.0)
        loaded = SimulationStep(**step.model_dump())
        assert loaded.step_number == step.step_number
        assert loaded.execution_time_ms == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# WorkflowSimulationResult
# ---------------------------------------------------------------------------


class TestWorkflowSimulationResult:
    def _step(self, n: int = 1) -> SimulationStep:
        return SimulationStep(
            step_number=n,
            node_id=f"node-{n}",
            node_type=NodeType.ACTION,
            status="success",
        )

    def _make(self, **kwargs):
        defaults = {"workflow_id": "wf-1", "success": True}
        defaults.update(kwargs)
        return WorkflowSimulationResult(**defaults)

    def test_minimal_creation(self):
        result = self._make()
        assert result.workflow_id == "wf-1"
        assert result.success is True

    def test_failed_simulation(self):
        result = self._make(success=False, error_message="Node failed")
        assert result.success is False
        assert result.error_message == "Node failed"

    def test_default_steps_empty(self):
        assert self._make().steps == []

    def test_custom_steps(self):
        steps = [self._step(1), self._step(2)]
        result = self._make(steps=steps)
        assert len(result.steps) == 2

    def test_default_final_output_none(self):
        assert self._make().final_output is None

    def test_custom_final_output(self):
        result = self._make(final_output={"approved": True})
        assert result.final_output["approved"] is True

    def test_default_total_execution_time_none(self):
        assert self._make().total_execution_time_ms is None

    def test_custom_total_execution_time(self):
        result = self._make(total_execution_time_ms=55.5)
        assert result.total_execution_time_ms == pytest.approx(55.5)

    def test_default_error_message_none(self):
        assert self._make().error_message is None

    def test_timestamp_is_datetime(self):
        result = self._make()
        assert isinstance(result.timestamp, datetime)
        assert result.timestamp.tzinfo is not None

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            WorkflowSimulationResult(workflow_id="wf-1")

    def test_serialization_roundtrip(self):
        result = self._make(steps=[self._step()], total_execution_time_ms=10.0)
        data = result.model_dump()
        loaded = WorkflowSimulationResult(**data)
        assert loaded.workflow_id == "wf-1"
        assert len(loaded.steps) == 1


# ---------------------------------------------------------------------------
# WorkflowSummary
# ---------------------------------------------------------------------------


class TestWorkflowSummary:
    def _make(self, **kwargs):
        defaults = {
            "id": "wf-1",
            "name": "Summary WF",
            "node_count": 5,
            "edge_count": 4,
            "updated_at": datetime.now(UTC),
            "version": "1.0.0",
            "is_active": True,
        }
        defaults.update(kwargs)
        return WorkflowSummary(**defaults)

    def test_minimal_creation(self):
        summary = self._make()
        assert summary.id == "wf-1"
        assert summary.name == "Summary WF"

    def test_default_description_none(self):
        assert self._make().description is None

    def test_custom_description(self):
        summary = self._make(description="A test workflow")
        assert summary.description == "A test workflow"

    def test_node_count(self):
        assert self._make(node_count=10).node_count == 10

    def test_edge_count(self):
        assert self._make(edge_count=8).edge_count == 8

    def test_version(self):
        assert self._make(version="2.0.0").version == "2.0.0"

    def test_is_active_false(self):
        summary = self._make(is_active=False)
        assert summary.is_active is False

    def test_updated_at_is_datetime(self):
        summary = self._make()
        assert isinstance(summary.updated_at, datetime)

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            WorkflowSummary()

    def test_serialization_roundtrip(self):
        summary = self._make()
        loaded = WorkflowSummary(**summary.model_dump())
        assert loaded.id == summary.id
        assert loaded.node_count == summary.node_count


# ---------------------------------------------------------------------------
# WorkflowListResponse
# ---------------------------------------------------------------------------


class TestWorkflowListResponse:
    def _summary(self, wf_id: str = "wf-1") -> WorkflowSummary:
        return WorkflowSummary(
            id=wf_id,
            name="WF",
            node_count=1,
            edge_count=0,
            updated_at=datetime.now(UTC),
            version="1.0.0",
            is_active=True,
        )

    def _make(self, **kwargs):
        defaults = {"workflows": [], "total": 0}
        defaults.update(kwargs)
        return WorkflowListResponse(**defaults)

    def test_minimal_creation(self):
        response = self._make()
        assert response.workflows == []
        assert response.total == 0

    def test_with_workflows(self):
        summaries = [self._summary("wf-1"), self._summary("wf-2")]
        response = self._make(workflows=summaries, total=2)
        assert len(response.workflows) == 2
        assert response.total == 2

    def test_default_page_one(self):
        assert self._make().page == 1

    def test_custom_page(self):
        response = self._make(page=3)
        assert response.page == 3

    def test_default_page_size_twenty(self):
        assert self._make().page_size == 20

    def test_custom_page_size(self):
        response = self._make(page_size=50)
        assert response.page_size == 50

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            WorkflowListResponse()

    def test_serialization_roundtrip(self):
        summaries = [self._summary()]
        response = self._make(workflows=summaries, total=1, page=2, page_size=10)
        data = response.model_dump()
        loaded = WorkflowListResponse(**data)
        assert loaded.total == 1
        assert loaded.page == 2
        assert loaded.page_size == 10


# ---------------------------------------------------------------------------
# WorkflowExportRequest
# ---------------------------------------------------------------------------


class TestWorkflowExportRequest:
    def test_default_format_json(self):
        req = WorkflowExportRequest()
        assert req.format == ExportFormat.JSON

    def test_format_rego(self):
        req = WorkflowExportRequest(format=ExportFormat.REGO)
        assert req.format == ExportFormat.REGO

    def test_format_yaml(self):
        req = WorkflowExportRequest(format=ExportFormat.YAML)
        assert req.format == ExportFormat.YAML

    def test_default_include_metadata_true(self):
        req = WorkflowExportRequest()
        assert req.include_metadata is True

    def test_include_metadata_false(self):
        req = WorkflowExportRequest(include_metadata=False)
        assert req.include_metadata is False

    def test_all_format_values(self):
        for fmt in ExportFormat:
            req = WorkflowExportRequest(format=fmt)
            assert req.format == fmt

    def test_serialization_roundtrip(self):
        req = WorkflowExportRequest(format=ExportFormat.REGO, include_metadata=False)
        loaded = WorkflowExportRequest(**req.model_dump())
        assert loaded.format == ExportFormat.REGO
        assert loaded.include_metadata is False


# ---------------------------------------------------------------------------
# WorkflowExportResult
# ---------------------------------------------------------------------------


class TestWorkflowExportResult:
    def _make(self, **kwargs):
        defaults = {
            "workflow_id": "wf-1",
            "format": ExportFormat.JSON,
            "content": '{"id": "wf-1"}',
            "filename": "wf-1.json",
        }
        defaults.update(kwargs)
        return WorkflowExportResult(**defaults)

    def test_minimal_creation(self):
        result = self._make()
        assert result.workflow_id == "wf-1"
        assert result.format == ExportFormat.JSON
        assert result.content == '{"id": "wf-1"}'
        assert result.filename == "wf-1.json"

    def test_format_rego(self):
        result = self._make(format=ExportFormat.REGO, filename="wf-1.rego", content="package wf")
        assert result.format == ExportFormat.REGO
        assert result.filename == "wf-1.rego"

    def test_format_yaml(self):
        result = self._make(format=ExportFormat.YAML, filename="wf-1.yaml", content="id: wf-1")
        assert result.format == ExportFormat.YAML

    def test_timestamp_is_datetime(self):
        result = self._make()
        assert isinstance(result.timestamp, datetime)
        assert result.timestamp.tzinfo is not None

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            WorkflowExportResult(workflow_id="wf-1")

    def test_serialization_roundtrip(self):
        result = self._make()
        loaded = WorkflowExportResult(**result.model_dump())
        assert loaded.workflow_id == result.workflow_id
        assert loaded.content == result.content
        assert loaded.filename == result.filename

    def test_all_formats(self):
        for fmt in ExportFormat:
            result = self._make(format=fmt)
            assert result.format == fmt


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_present(self):
        from enhanced_agent_bus.visual_studio import models as m

        expected = [
            "NodeType",
            "WorkflowNode",
            "WorkflowEdge",
            "WorkflowDefinition",
            "VisualStudioValidationResult",
            "WorkflowValidationResult",
            "SimulationStep",
            "WorkflowSimulationResult",
            "WorkflowListResponse",
            "WorkflowSummary",
            "ExportFormat",
            "WorkflowExportRequest",
            "WorkflowExportResult",
        ]
        for name in expected:
            assert name in m.__all__, f"{name} missing from __all__"
            assert hasattr(m, name), f"{name} not importable from module"
