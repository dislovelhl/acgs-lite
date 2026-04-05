from __future__ import annotations

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.data_flywheel.models import DecisionEvent, EvaluationMode, EvaluationRun
from enhanced_agent_bus.data_flywheel.workload_registry import build_workload_key


def test_workload_key_builder_normalizes_segments() -> None:
    workload = build_workload_key(
        tenant_id="tenant-a",
        service="API Gateway",
        route_or_tool="/api/v1/gateway/feedback",
        decision_kind="User Feedback",
        constitutional_hash="608508a9bd224290",
    )
    assert workload.as_key() == (
        "tenant-a/api_gateway/api_v1_gateway_feedback/user_feedback/608508a9bd224290"
    )


def test_decision_event_requires_tenant_id() -> None:
    with pytest.raises(ValidationError):
        DecisionEvent(
            tenant_id="",
            workload_key="tenant/service/tool/kind/hash",
            decision_kind="policy_evaluation",
            outcome="allow",
        )


def test_evaluation_run_uses_explicit_mode_enum() -> None:
    run = EvaluationRun(
        tenant_id="tenant-a",
        workload_key="tenant-a/service/tool/kind/hash",
        candidate_id="cand-1",
        evaluation_mode=EvaluationMode.SHADOW,
        status="running",
    )
    assert run.evaluation_mode is EvaluationMode.SHADOW
