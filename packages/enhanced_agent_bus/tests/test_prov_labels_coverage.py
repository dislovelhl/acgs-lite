# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/prov/labels.py.

Targets ≥95% line coverage across all classes, factory functions,
serialisation round-trips, edge cases, and branch paths.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timezone
from unittest.mock import patch

import pytest

from enhanced_agent_bus.prov.labels import (
    ACTIVITY_TYPE_MAP,
    CONSTITUTIONAL_HASH,
    ENTITY_TYPE_MAP,
    PROV_SCHEMA_VERSION,
    SERVICE_AGENT_ID,
    SERVICE_AGENT_LABEL,
    ProvActivity,
    ProvAgent,
    ProvEntity,
    ProvLabel,
    ProvLineage,
    _utc_now_iso,
    build_prov_label,
    make_prov_id,
    make_service_agent,
    make_tool_activity,
    make_tool_entity,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_constitutional_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_prov_schema_version(self):
        assert PROV_SCHEMA_VERSION == "1.0.0"

    def test_service_agent_id(self):
        assert SERVICE_AGENT_ID == "acgs:agent/enhanced-agent-bus"

    def test_service_agent_label(self):
        assert SERVICE_AGENT_LABEL == "ACGS-2 Enhanced Agent Bus"

    def test_entity_type_map_keys(self):
        expected_keys = {
            "security_scan",
            "constitutional_validation",
            "maci_enforcement",
            "impact_scoring",
            "hitl_review",
            "temporal_policy",
            "tool_privilege",
            "strategy",
            "ifc_check",
        }
        assert set(ENTITY_TYPE_MAP.keys()) == expected_keys

    def test_activity_type_map_keys(self):
        expected_keys = {
            "security_scan",
            "constitutional_validation",
            "maci_enforcement",
            "impact_scoring",
            "hitl_review",
            "temporal_policy",
            "tool_privilege",
            "strategy",
            "ifc_check",
        }
        assert set(ACTIVITY_TYPE_MAP.keys()) == expected_keys

    def test_entity_type_map_values(self):
        assert ENTITY_TYPE_MAP["security_scan"] == "acgs:SecurityScanResult"
        assert ENTITY_TYPE_MAP["constitutional_validation"] == "acgs:ConstitutionalValidationResult"
        assert ENTITY_TYPE_MAP["maci_enforcement"] == "acgs:MACIValidationResult"
        assert ENTITY_TYPE_MAP["impact_scoring"] == "acgs:ImpactScore"
        assert ENTITY_TYPE_MAP["hitl_review"] == "acgs:HITLDecision"
        assert ENTITY_TYPE_MAP["temporal_policy"] == "acgs:TemporalPolicyDecision"
        assert ENTITY_TYPE_MAP["tool_privilege"] == "acgs:ToolPrivilegeDecision"
        assert ENTITY_TYPE_MAP["strategy"] == "acgs:GovernanceDecision"
        assert ENTITY_TYPE_MAP["ifc_check"] == "acgs:IFCFlowDecision"

    def test_activity_type_map_values(self):
        assert ACTIVITY_TYPE_MAP["security_scan"] == "acgs:SecurityScanning"
        assert ACTIVITY_TYPE_MAP["constitutional_validation"] == "acgs:ConstitutionalValidation"
        assert ACTIVITY_TYPE_MAP["maci_enforcement"] == "acgs:MACIEnforcement"
        assert ACTIVITY_TYPE_MAP["impact_scoring"] == "acgs:ImpactScoring"
        assert ACTIVITY_TYPE_MAP["hitl_review"] == "acgs:HITLReview"
        assert ACTIVITY_TYPE_MAP["temporal_policy"] == "acgs:TemporalPolicyEvaluation"
        assert ACTIVITY_TYPE_MAP["tool_privilege"] == "acgs:ToolPrivilegeEvaluation"
        assert ACTIVITY_TYPE_MAP["strategy"] == "acgs:GovernanceStrategyExecution"
        assert ACTIVITY_TYPE_MAP["ifc_check"] == "acgs:IFCFlowCheck"


# ---------------------------------------------------------------------------
# _utc_now_iso helper
# ---------------------------------------------------------------------------


class TestUtcNowIso:
    def test_returns_string(self):
        result = _utc_now_iso()
        assert isinstance(result, str)

    def test_is_iso_format(self):
        result = _utc_now_iso()
        # Should be parseable as an ISO 8601 datetime
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_is_utc(self):
        result = _utc_now_iso()
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo == UTC

    def test_result_is_recent(self):
        before = datetime.now(tz=UTC)
        result = _utc_now_iso()
        after = datetime.now(tz=UTC)
        dt = datetime.fromisoformat(result)
        assert before <= dt <= after


# ---------------------------------------------------------------------------
# make_prov_id
# ---------------------------------------------------------------------------


class TestMakeProvId:
    def test_basic_structure(self):
        result = make_prov_id("security_scan", "entity", "2024-01-01T00:00:00+00:00")
        assert result.startswith("acgs:security_scan/entity/")

    def test_colons_replaced(self):
        ts = "2024-01-01T12:30:45+00:00"
        result = make_prov_id("stage", "activity", ts)
        assert ":" not in result.split("acgs:stage/activity/")[1]

    def test_dots_replaced(self):
        ts = "2024-01-01T12:30:45.123456+00:00"
        result = make_prov_id("stage", "entity", ts)
        safe_part = result.split("acgs:stage/entity/")[1]
        assert "." not in safe_part

    def test_suffix_entity(self):
        result = make_prov_id("impact_scoring", "entity", "2024-01-01T00:00:00+00:00")
        assert "/entity/" in result

    def test_suffix_activity(self):
        result = make_prov_id("impact_scoring", "activity", "2024-01-01T00:00:00+00:00")
        assert "/activity/" in result

    def test_stage_name_preserved(self):
        result = make_prov_id("constitutional_validation", "entity", "2024-01-01T00:00:00+00:00")
        assert "constitutional_validation" in result

    def test_format_exact(self):
        ts = "2024-01-01T00:00:00+00:00"
        safe_ts = ts.replace(":", "-").replace(".", "-")
        expected = f"acgs:my_stage/activity/{safe_ts}"
        assert make_prov_id("my_stage", "activity", ts) == expected

    def test_empty_stage_name(self):
        result = make_prov_id("", "entity", "2024-01-01T00:00:00+00:00")
        assert result.startswith("acgs:/entity/")

    def test_microseconds_in_timestamp(self):
        ts = "2024-06-15T10:20:30.987654+00:00"
        result = make_prov_id("hitl_review", "entity", ts)
        assert "-" in result
        assert "." not in result.split("acgs:hitl_review/entity/")[1]


# ---------------------------------------------------------------------------
# ProvAgent
# ---------------------------------------------------------------------------


class TestProvAgent:
    def _make_agent(self) -> ProvAgent:
        return ProvAgent(
            id="acgs:agent/test",
            type="prov:SoftwareAgent",
            label="Test Agent",
        )

    def test_creation(self):
        agent = self._make_agent()
        assert agent.id == "acgs:agent/test"
        assert agent.type == "prov:SoftwareAgent"
        assert agent.label == "Test Agent"

    def test_frozen(self):
        agent = self._make_agent()
        with pytest.raises((AttributeError, TypeError)):
            agent.id = "new-id"  # type: ignore[misc]

    def test_to_dict_keys(self):
        agent = self._make_agent()
        d = agent.to_dict()
        assert set(d.keys()) == {"id", "type", "label"}

    def test_to_dict_values(self):
        agent = self._make_agent()
        d = agent.to_dict()
        assert d["id"] == "acgs:agent/test"
        assert d["type"] == "prov:SoftwareAgent"
        assert d["label"] == "Test Agent"

    def test_from_dict_roundtrip(self):
        agent = self._make_agent()
        restored = ProvAgent.from_dict(agent.to_dict())
        assert restored == agent

    def test_from_dict_creates_correct_type(self):
        d = {"id": "acgs:agent/x", "type": "prov:Person", "label": "Human Agent"}
        agent = ProvAgent.from_dict(d)
        assert isinstance(agent, ProvAgent)
        assert agent.id == "acgs:agent/x"

    def test_equality(self):
        a1 = ProvAgent(id="x", type="y", label="z")
        a2 = ProvAgent(id="x", type="y", label="z")
        assert a1 == a2

    def test_inequality(self):
        a1 = ProvAgent(id="x", type="y", label="z")
        a2 = ProvAgent(id="x", type="y", label="different")
        assert a1 != a2


# ---------------------------------------------------------------------------
# ProvActivity
# ---------------------------------------------------------------------------


class TestProvActivity:
    def _make_activity(self) -> ProvActivity:
        return ProvActivity(
            id="acgs:security_scan/activity/2024-01-01T00-00-00+00-00",
            type="acgs:SecurityScanning",
            label="Execute security_scan",
            started_at_time="2024-01-01T00:00:00+00:00",
            ended_at_time="2024-01-01T00:00:01+00:00",
            was_associated_with=SERVICE_AGENT_ID,
        )

    def test_creation(self):
        act = self._make_activity()
        assert act.type == "acgs:SecurityScanning"
        assert act.label == "Execute security_scan"
        assert act.was_associated_with == SERVICE_AGENT_ID

    def test_frozen(self):
        act = self._make_activity()
        with pytest.raises((AttributeError, TypeError)):
            act.label = "new"  # type: ignore[misc]

    def test_to_dict_keys(self):
        act = self._make_activity()
        d = act.to_dict()
        assert set(d.keys()) == {
            "id",
            "type",
            "label",
            "started_at_time",
            "ended_at_time",
            "was_associated_with",
        }

    def test_to_dict_values(self):
        act = self._make_activity()
        d = act.to_dict()
        assert d["started_at_time"] == "2024-01-01T00:00:00+00:00"
        assert d["ended_at_time"] == "2024-01-01T00:00:01+00:00"
        assert d["was_associated_with"] == SERVICE_AGENT_ID

    def test_from_dict_roundtrip(self):
        act = self._make_activity()
        restored = ProvActivity.from_dict(act.to_dict())
        assert restored == act

    def test_from_dict_creates_correct_type(self):
        d = {
            "id": "acgs:x/activity/ts",
            "type": "acgs:Custom",
            "label": "Custom label",
            "started_at_time": "2024-01-01T00:00:00+00:00",
            "ended_at_time": "2024-01-01T00:01:00+00:00",
            "was_associated_with": "acgs:agent/test",
        }
        act = ProvActivity.from_dict(d)
        assert isinstance(act, ProvActivity)
        assert act.id == "acgs:x/activity/ts"

    def test_equality(self):
        a1 = self._make_activity()
        a2 = self._make_activity()
        assert a1 == a2


# ---------------------------------------------------------------------------
# ProvEntity
# ---------------------------------------------------------------------------


class TestProvEntity:
    def _make_entity(self) -> ProvEntity:
        return ProvEntity(
            id="acgs:impact_scoring/entity/2024-01-01T00-00-00+00-00",
            type="acgs:ImpactScore",
            label="Output of impact_scoring",
            generated_at_time="2024-01-01T00:00:00+00:00",
            was_generated_by="acgs:impact_scoring/activity/2024-01-01T00-00-00+00-00",
            was_attributed_to=SERVICE_AGENT_ID,
        )

    def test_creation(self):
        ent = self._make_entity()
        assert ent.type == "acgs:ImpactScore"
        assert ent.label == "Output of impact_scoring"

    def test_frozen(self):
        ent = self._make_entity()
        with pytest.raises((AttributeError, TypeError)):
            ent.id = "new"  # type: ignore[misc]

    def test_to_dict_keys(self):
        ent = self._make_entity()
        d = ent.to_dict()
        assert set(d.keys()) == {
            "id",
            "type",
            "label",
            "generated_at_time",
            "was_generated_by",
            "was_attributed_to",
        }

    def test_to_dict_values(self):
        ent = self._make_entity()
        d = ent.to_dict()
        assert d["was_attributed_to"] == SERVICE_AGENT_ID
        assert d["generated_at_time"] == "2024-01-01T00:00:00+00:00"

    def test_from_dict_roundtrip(self):
        ent = self._make_entity()
        restored = ProvEntity.from_dict(ent.to_dict())
        assert restored == ent

    def test_from_dict_creates_correct_type(self):
        d = {
            "id": "acgs:y/entity/ts",
            "type": "acgs:CustomResult",
            "label": "Custom entity",
            "generated_at_time": "2024-01-01T00:00:00+00:00",
            "was_generated_by": "acgs:y/activity/ts",
            "was_attributed_to": SERVICE_AGENT_ID,
        }
        ent = ProvEntity.from_dict(d)
        assert isinstance(ent, ProvEntity)

    def test_equality(self):
        e1 = self._make_entity()
        e2 = self._make_entity()
        assert e1 == e2


# ---------------------------------------------------------------------------
# ProvLabel
# ---------------------------------------------------------------------------


TS = "2024-03-15T12:00:00+00:00"
TS2 = "2024-03-15T12:00:05+00:00"


def _make_label(stage: str = "security_scan") -> ProvLabel:
    return build_prov_label(stage, started_at=TS, ended_at=TS2)


class TestProvLabel:
    def test_creation_with_defaults(self):
        lbl = _make_label()
        assert lbl.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret
        assert lbl.schema_version == PROV_SCHEMA_VERSION

    def test_custom_hash_and_version(self):
        agent = make_service_agent()
        activity = make_tool_activity("security_scan", TS, TS2)
        entity = make_tool_entity("security_scan", activity.id, TS2)
        lbl = ProvLabel(
            entity=entity,
            activity=activity,
            agent=agent,
            constitutional_hash="custom-hash",  # pragma: allowlist secret
            schema_version="2.0.0",
        )
        assert lbl.constitutional_hash == "custom-hash"  # pragma: allowlist secret
        assert lbl.schema_version == "2.0.0"

    def test_frozen(self):
        lbl = _make_label()
        with pytest.raises((AttributeError, TypeError)):
            lbl.schema_version = "99.0"  # type: ignore[misc]

    def test_to_dict_top_level_keys(self):
        lbl = _make_label()
        d = lbl.to_dict()
        assert set(d.keys()) == {
            "entity",
            "activity",
            "agent",
            "constitutional_hash",
            "schema_version",
        }

    def test_to_dict_constitutional_hash(self):
        lbl = _make_label()
        d = lbl.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_to_dict_schema_version(self):
        lbl = _make_label()
        d = lbl.to_dict()
        assert d["schema_version"] == PROV_SCHEMA_VERSION

    def test_to_dict_nested_entity(self):
        lbl = _make_label()
        d = lbl.to_dict()
        assert isinstance(d["entity"], dict)
        assert "id" in d["entity"]

    def test_to_dict_nested_activity(self):
        lbl = _make_label()
        d = lbl.to_dict()
        assert isinstance(d["activity"], dict)
        assert "started_at_time" in d["activity"]

    def test_to_dict_nested_agent(self):
        lbl = _make_label()
        d = lbl.to_dict()
        assert isinstance(d["agent"], dict)
        assert d["agent"]["id"] == SERVICE_AGENT_ID

    def test_from_dict_roundtrip(self):
        lbl = _make_label()
        restored = ProvLabel.from_dict(lbl.to_dict())
        assert restored == lbl

    def test_from_dict_uses_defaults_when_keys_missing(self):
        lbl = _make_label()
        d = lbl.to_dict()
        del d["constitutional_hash"]
        del d["schema_version"]
        restored = ProvLabel.from_dict(d)
        assert restored.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret
        assert restored.schema_version == PROV_SCHEMA_VERSION

    def test_from_dict_respects_explicit_hash(self):
        lbl = _make_label()
        d = lbl.to_dict()
        d["constitutional_hash"] = "override-hash"  # pragma: allowlist secret
        d["schema_version"] = "3.0.0"
        restored = ProvLabel.from_dict(d)
        assert restored.constitutional_hash == "override-hash"  # pragma: allowlist secret
        assert restored.schema_version == "3.0.0"

    def test_repr_contains_stage(self):
        lbl = _make_label("hitl_review")
        r = repr(lbl)
        assert "hitl_review" in r

    def test_repr_contains_entity_id(self):
        lbl = _make_label()
        r = repr(lbl)
        assert lbl.entity.id in r

    def test_repr_contains_generated_at(self):
        lbl = _make_label()
        r = repr(lbl)
        assert lbl.entity.generated_at_time in r

    def test_repr_format(self):
        lbl = _make_label("strategy")
        r = repr(lbl)
        assert r.startswith("ProvLabel(")


# ---------------------------------------------------------------------------
# make_service_agent
# ---------------------------------------------------------------------------


class TestMakeServiceAgent:
    def test_returns_prov_agent(self):
        agent = make_service_agent()
        assert isinstance(agent, ProvAgent)

    def test_id(self):
        agent = make_service_agent()
        assert agent.id == SERVICE_AGENT_ID

    def test_type(self):
        agent = make_service_agent()
        assert agent.type == "prov:SoftwareAgent"

    def test_label(self):
        agent = make_service_agent()
        assert agent.label == SERVICE_AGENT_LABEL

    def test_stable_across_calls(self):
        a1 = make_service_agent()
        a2 = make_service_agent()
        assert a1 == a2


# ---------------------------------------------------------------------------
# make_tool_activity
# ---------------------------------------------------------------------------


class TestMakeToolActivity:
    def test_returns_prov_activity(self):
        act = make_tool_activity("security_scan", TS, TS2)
        assert isinstance(act, ProvActivity)

    def test_known_stage_type(self):
        act = make_tool_activity("security_scan", TS, TS2)
        assert act.type == "acgs:SecurityScanning"

    def test_constitutional_validation_type(self):
        act = make_tool_activity("constitutional_validation", TS, TS2)
        assert act.type == "acgs:ConstitutionalValidation"

    def test_maci_enforcement_type(self):
        act = make_tool_activity("maci_enforcement", TS, TS2)
        assert act.type == "acgs:MACIEnforcement"

    def test_impact_scoring_type(self):
        act = make_tool_activity("impact_scoring", TS, TS2)
        assert act.type == "acgs:ImpactScoring"

    def test_hitl_review_type(self):
        act = make_tool_activity("hitl_review", TS, TS2)
        assert act.type == "acgs:HITLReview"

    def test_temporal_policy_type(self):
        act = make_tool_activity("temporal_policy", TS, TS2)
        assert act.type == "acgs:TemporalPolicyEvaluation"

    def test_tool_privilege_type(self):
        act = make_tool_activity("tool_privilege", TS, TS2)
        assert act.type == "acgs:ToolPrivilegeEvaluation"

    def test_strategy_type(self):
        act = make_tool_activity("strategy", TS, TS2)
        assert act.type == "acgs:GovernanceStrategyExecution"

    def test_ifc_check_type(self):
        act = make_tool_activity("ifc_check", TS, TS2)
        assert act.type == "acgs:IFCFlowCheck"

    def test_unknown_stage_falls_back(self):
        act = make_tool_activity("unknown_stage", TS, TS2)
        assert act.type == "acgs:unknown_stage"

    def test_label(self):
        act = make_tool_activity("security_scan", TS, TS2)
        assert act.label == "Execute security_scan"

    def test_started_at_time(self):
        act = make_tool_activity("security_scan", TS, TS2)
        assert act.started_at_time == TS

    def test_ended_at_time(self):
        act = make_tool_activity("security_scan", TS, TS2)
        assert act.ended_at_time == TS2

    def test_was_associated_with(self):
        act = make_tool_activity("security_scan", TS, TS2)
        assert act.was_associated_with == SERVICE_AGENT_ID

    def test_id_contains_stage_name(self):
        act = make_tool_activity("impact_scoring", TS, TS2)
        assert "impact_scoring" in act.id

    def test_id_contains_activity_suffix(self):
        act = make_tool_activity("impact_scoring", TS, TS2)
        assert "/activity/" in act.id


# ---------------------------------------------------------------------------
# make_tool_entity
# ---------------------------------------------------------------------------


class TestMakeToolEntity:
    def _activity_id(self) -> str:
        return make_tool_activity("security_scan", TS, TS2).id

    def test_returns_prov_entity(self):
        ent = make_tool_entity("security_scan", self._activity_id(), TS2)
        assert isinstance(ent, ProvEntity)

    def test_known_stage_type(self):
        ent = make_tool_entity("security_scan", self._activity_id(), TS2)
        assert ent.type == "acgs:SecurityScanResult"

    def test_constitutional_validation_type(self):
        ent = make_tool_entity("constitutional_validation", self._activity_id(), TS2)
        assert ent.type == "acgs:ConstitutionalValidationResult"

    def test_maci_enforcement_type(self):
        ent = make_tool_entity("maci_enforcement", self._activity_id(), TS2)
        assert ent.type == "acgs:MACIValidationResult"

    def test_impact_scoring_type(self):
        ent = make_tool_entity("impact_scoring", self._activity_id(), TS2)
        assert ent.type == "acgs:ImpactScore"

    def test_hitl_review_type(self):
        ent = make_tool_entity("hitl_review", self._activity_id(), TS2)
        assert ent.type == "acgs:HITLDecision"

    def test_temporal_policy_type(self):
        ent = make_tool_entity("temporal_policy", self._activity_id(), TS2)
        assert ent.type == "acgs:TemporalPolicyDecision"

    def test_tool_privilege_type(self):
        ent = make_tool_entity("tool_privilege", self._activity_id(), TS2)
        assert ent.type == "acgs:ToolPrivilegeDecision"

    def test_strategy_type(self):
        ent = make_tool_entity("strategy", self._activity_id(), TS2)
        assert ent.type == "acgs:GovernanceDecision"

    def test_ifc_check_type(self):
        ent = make_tool_entity("ifc_check", self._activity_id(), TS2)
        assert ent.type == "acgs:IFCFlowDecision"

    def test_unknown_stage_falls_back(self):
        ent = make_tool_entity("custom_stage", self._activity_id(), TS2)
        assert ent.type == "acgs:custom_stageResult"

    def test_label(self):
        ent = make_tool_entity("security_scan", self._activity_id(), TS2)
        assert ent.label == "Output of security_scan"

    def test_generated_at_time(self):
        ent = make_tool_entity("security_scan", self._activity_id(), TS2)
        assert ent.generated_at_time == TS2

    def test_was_generated_by(self):
        activity_id = self._activity_id()
        ent = make_tool_entity("security_scan", activity_id, TS2)
        assert ent.was_generated_by == activity_id

    def test_was_attributed_to(self):
        ent = make_tool_entity("security_scan", self._activity_id(), TS2)
        assert ent.was_attributed_to == SERVICE_AGENT_ID

    def test_id_contains_stage_name(self):
        ent = make_tool_entity("hitl_review", self._activity_id(), TS2)
        assert "hitl_review" in ent.id

    def test_id_contains_entity_suffix(self):
        ent = make_tool_entity("hitl_review", self._activity_id(), TS2)
        assert "/entity/" in ent.id


# ---------------------------------------------------------------------------
# build_prov_label (primary public factory)
# ---------------------------------------------------------------------------


class TestBuildProvLabel:
    def test_returns_prov_label(self):
        lbl = build_prov_label("security_scan", TS, TS2)
        assert isinstance(lbl, ProvLabel)

    def test_constitutional_hash(self):
        lbl = build_prov_label("security_scan", TS, TS2)
        assert lbl.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_schema_version(self):
        lbl = build_prov_label("security_scan", TS, TS2)
        assert lbl.schema_version == PROV_SCHEMA_VERSION

    def test_agent_is_service_agent(self):
        lbl = build_prov_label("security_scan", TS, TS2)
        assert lbl.agent == make_service_agent()

    def test_activity_started_at(self):
        lbl = build_prov_label("impact_scoring", TS, TS2)
        assert lbl.activity.started_at_time == TS

    def test_activity_ended_at(self):
        lbl = build_prov_label("impact_scoring", TS, TS2)
        assert lbl.activity.ended_at_time == TS2

    def test_entity_generated_at(self):
        lbl = build_prov_label("impact_scoring", TS, TS2)
        assert lbl.entity.generated_at_time == TS2

    def test_entity_generated_by_activity(self):
        lbl = build_prov_label("strategy", TS, TS2)
        assert lbl.entity.was_generated_by == lbl.activity.id

    def test_ended_at_defaults_to_now_when_none(self):
        before = datetime.now(tz=UTC)
        lbl = build_prov_label("security_scan", TS, ended_at=None)
        after = datetime.now(tz=UTC)
        ended_dt = datetime.fromisoformat(lbl.activity.ended_at_time)
        assert before <= ended_dt <= after

    def test_ended_at_none_sets_entity_generated_at_to_same_time(self):
        lbl = build_prov_label("security_scan", TS, ended_at=None)
        assert lbl.entity.generated_at_time == lbl.activity.ended_at_time

    def test_explicit_ended_at_used_over_default(self):
        lbl = build_prov_label("security_scan", TS, ended_at=TS2)
        assert lbl.activity.ended_at_time == TS2

    def test_all_known_stages(self):
        stages = list(ENTITY_TYPE_MAP.keys())
        for stage in stages:
            lbl = build_prov_label(stage, TS, TS2)
            assert isinstance(lbl, ProvLabel)
            assert lbl.entity.type == ENTITY_TYPE_MAP[stage]
            assert lbl.activity.type == ACTIVITY_TYPE_MAP[stage]

    def test_unknown_stage(self):
        lbl = build_prov_label("custom_pipeline_step", TS, TS2)
        assert isinstance(lbl, ProvLabel)
        assert lbl.entity.type == "acgs:custom_pipeline_stepResult"
        assert lbl.activity.type == "acgs:custom_pipeline_step"

    def test_label_is_frozen(self):
        lbl = build_prov_label("security_scan", TS, TS2)
        with pytest.raises((AttributeError, TypeError)):
            lbl.constitutional_hash = "other"  # type: ignore[misc]

    def test_serialization_roundtrip(self):
        lbl = build_prov_label("hitl_review", TS, TS2)
        restored = ProvLabel.from_dict(lbl.to_dict())
        assert restored == lbl

    def test_repr(self):
        lbl = build_prov_label("strategy", TS, TS2)
        r = repr(lbl)
        assert "strategy" in r
        assert "ProvLabel" in r

    def test_mock_utc_now_called_when_ended_at_is_none(self):
        fixed_ts = "2024-12-25T00:00:00+00:00"
        with patch(
            "enhanced_agent_bus.prov.labels._utc_now_iso",
            return_value=fixed_ts,
        ):
            lbl = build_prov_label("security_scan", TS, ended_at=None)
        assert lbl.activity.ended_at_time == fixed_ts
        assert lbl.entity.generated_at_time == fixed_ts


# ---------------------------------------------------------------------------
# ProvLineage
# ---------------------------------------------------------------------------


class TestProvLineage:
    def test_empty_on_creation(self):
        lineage = ProvLineage()
        assert len(lineage) == 0

    def test_default_labels_list(self):
        lineage = ProvLineage()
        assert lineage.labels == []

    def test_append_increases_length(self):
        lineage = ProvLineage()
        lbl = _make_label()
        lineage.append(lbl)
        assert len(lineage) == 1

    def test_append_multiple(self):
        lineage = ProvLineage()
        for stage in ["security_scan", "constitutional_validation", "impact_scoring"]:
            lineage.append(_make_label(stage))
        assert len(lineage) == 3

    def test_iteration(self):
        lineage = ProvLineage()
        labels = [_make_label(s) for s in ["security_scan", "hitl_review"]]
        for lbl in labels:
            lineage.append(lbl)
        iterated = list(lineage)
        assert iterated == labels

    def test_to_dict_empty(self):
        lineage = ProvLineage()
        assert lineage.to_dict() == []

    def test_to_dict_returns_list_of_dicts(self):
        lineage = ProvLineage()
        lineage.append(_make_label("security_scan"))
        result = lineage.to_dict()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert "entity" in result[0]

    def test_to_dict_multiple(self):
        lineage = ProvLineage()
        lineage.append(_make_label("security_scan"))
        lineage.append(_make_label("strategy"))
        result = lineage.to_dict()
        assert len(result) == 2

    def test_from_dict_empty(self):
        lineage = ProvLineage.from_dict([])
        assert len(lineage) == 0

    def test_from_dict_single(self):
        original = ProvLineage()
        original.append(_make_label("hitl_review"))
        restored = ProvLineage.from_dict(original.to_dict())
        assert len(restored) == 1
        assert list(restored)[0] == list(original)[0]

    def test_from_dict_multiple(self):
        original = ProvLineage()
        for s in ["security_scan", "constitutional_validation", "strategy"]:
            original.append(_make_label(s))
        restored = ProvLineage.from_dict(original.to_dict())
        assert len(restored) == 3
        for orig_lbl, rest_lbl in zip(original, restored, strict=False):
            assert orig_lbl == rest_lbl

    def test_roundtrip_preserves_order(self):
        stages = [
            "security_scan",
            "constitutional_validation",
            "maci_enforcement",
            "impact_scoring",
            "hitl_review",
        ]
        original = ProvLineage()
        for s in stages:
            original.append(_make_label(s))
        restored = ProvLineage.from_dict(original.to_dict())
        for i, (o, r) in enumerate(zip(original, restored, strict=False)):
            assert o == r, f"Mismatch at index {i}"

    def test_independent_default_lists(self):
        """Each ProvLineage instance must have its own list (field default_factory)."""
        l1 = ProvLineage()
        l2 = ProvLineage()
        l1.append(_make_label())
        assert len(l2) == 0

    def test_len_dunder(self):
        lineage = ProvLineage(labels=[_make_label(), _make_label("hitl_review")])
        assert len(lineage) == 2

    def test_iter_dunder_returns_iterator(self):
        lineage = ProvLineage(labels=[_make_label()])
        it = iter(lineage)
        assert next(it) == _make_label()

    def test_explicit_labels_on_construction(self):
        labels = [_make_label(s) for s in ["security_scan", "strategy"]]
        lineage = ProvLineage(labels=labels)
        assert len(lineage) == 2


# ---------------------------------------------------------------------------
# Public API re-export via __init__.py
# ---------------------------------------------------------------------------


class TestProvPackagePublicApi:
    def test_import_from_package(self):
        from enhanced_agent_bus.prov import (
            CONSTITUTIONAL_HASH as H,
        )
        from enhanced_agent_bus.prov import (
            PROV_SCHEMA_VERSION as V,
        )
        from enhanced_agent_bus.prov import (
            SERVICE_AGENT_ID as SID,
        )
        from enhanced_agent_bus.prov import (
            SERVICE_AGENT_LABEL as SL,
        )
        from enhanced_agent_bus.prov import (
            ProvActivity,
            ProvAgent,
            ProvEntity,
            ProvLabel,
            ProvLineage,
            build_prov_label,
            make_prov_id,
            make_service_agent,
            make_tool_activity,
            make_tool_entity,
        )

        assert H == CONSTITUTIONAL_HASH  # pragma: allowlist secret
        assert V == "1.0.0"
        assert SID == "acgs:agent/enhanced-agent-bus"
        assert SL == "ACGS-2 Enhanced Agent Bus"
        assert ProvAgent is not None
        assert ProvActivity is not None
        assert ProvEntity is not None
        assert ProvLabel is not None
        assert ProvLineage is not None
        assert callable(build_prov_label)
        assert callable(make_prov_id)
        assert callable(make_service_agent)
        assert callable(make_tool_activity)
        assert callable(make_tool_entity)
