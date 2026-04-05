# Constitutional Hash: 608508a9bd224290
# Sprint 57 — mcp_server/tools/get_principles.py coverage
"""
Comprehensive tests for mcp_server/tools/get_principles.py.
Targets >=95% coverage of all classes, methods, and branches.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.mcp_server.protocol.types import ToolDefinition, ToolInputSchema
from enhanced_agent_bus.mcp_server.tools.get_principles import (
    ConstitutionalPrinciple,
    GetPrinciplesTool,
    PrincipleCategory,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

pytestmark = [pytest.mark.unit, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# PrincipleCategory enum
# ---------------------------------------------------------------------------


class TestPrincipleCategory:
    def test_all_values_exist(self):
        assert PrincipleCategory.CORE.value == "core"
        assert PrincipleCategory.SAFETY.value == "safety"
        assert PrincipleCategory.PRIVACY.value == "privacy"
        assert PrincipleCategory.FAIRNESS.value == "fairness"
        assert PrincipleCategory.TRANSPARENCY.value == "transparency"
        assert PrincipleCategory.GOVERNANCE.value == "governance"

    def test_enum_count(self):
        assert len(PrincipleCategory) == 6

    def test_lookup_by_value(self):
        assert PrincipleCategory("core") is PrincipleCategory.CORE
        assert PrincipleCategory("governance") is PrincipleCategory.GOVERNANCE


# ---------------------------------------------------------------------------
# ConstitutionalPrinciple dataclass
# ---------------------------------------------------------------------------


class TestConstitutionalPrinciple:
    def _make(self, **kwargs) -> ConstitutionalPrinciple:
        defaults = dict(
            id="T001",
            name="test_principle",
            category=PrincipleCategory.CORE,
            description="A test principle",
            enforcement_level="strict",
            version="1.0.0",
        )
        defaults.update(kwargs)
        return ConstitutionalPrinciple(**defaults)

    def test_defaults(self):
        p = self._make()
        assert p.active is True
        assert p.precedence == 100
        assert p.related_principles == []

    def test_custom_values(self):
        p = self._make(
            active=False,
            precedence=50,
            related_principles=["P001", "P002"],
        )
        assert p.active is False
        assert p.precedence == 50
        assert p.related_principles == ["P001", "P002"]

    def test_to_dict_structure(self):
        p = self._make(
            active=True,
            precedence=75,
            related_principles=["P001"],
        )
        d = p.to_dict()
        assert d["id"] == "T001"
        assert d["name"] == "test_principle"
        assert d["category"] == "core"
        assert d["description"] == "A test principle"
        assert d["enforcement_level"] == "strict"
        assert d["version"] == "1.0.0"
        assert d["active"] is True
        assert d["precedence"] == 75
        assert d["related_principles"] == ["P001"]

    def test_to_dict_category_uses_value(self):
        for cat in PrincipleCategory:
            p = self._make(category=cat)
            assert p.to_dict()["category"] == cat.value

    def test_to_dict_inactive(self):
        p = self._make(active=False)
        assert p.to_dict()["active"] is False

    def test_to_dict_no_related_principles(self):
        p = self._make()
        assert p.to_dict()["related_principles"] == []


# ---------------------------------------------------------------------------
# GetPrinciplesTool — construction and class attributes
# ---------------------------------------------------------------------------


class TestGetPrinciplesToolInit:
    def test_default_init_no_adapter(self):
        tool = GetPrinciplesTool()
        assert tool.policy_client_adapter is None
        assert tool._request_count == 0

    def test_default_principles_loaded(self):
        tool = GetPrinciplesTool()
        assert len(tool._principles) == 8

    def test_principle_ids_present(self):
        tool = GetPrinciplesTool()
        for pid in ["P001", "P002", "P003", "P004", "P005", "P006", "P007", "P008"]:
            assert pid in tool._principles

    def test_init_with_adapter(self):
        adapter = MagicMock()
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        assert tool.policy_client_adapter is adapter

    def test_constitutional_hash_present(self):
        assert (
            GetPrinciplesTool.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        )  # pragma: allowlist secret

    def test_default_principles_class_attribute(self):
        # Each element should be a ConstitutionalPrinciple
        for p in GetPrinciplesTool.DEFAULT_PRINCIPLES:
            assert isinstance(p, ConstitutionalPrinciple)


# ---------------------------------------------------------------------------
# GetPrinciplesTool.get_definition
# ---------------------------------------------------------------------------


class TestGetDefinition:
    def test_returns_tool_definition(self):
        defn = GetPrinciplesTool.get_definition()
        assert isinstance(defn, ToolDefinition)

    def test_name_and_description(self):
        defn = GetPrinciplesTool.get_definition()
        assert defn.name == "get_active_principles"
        assert "constitutional principles" in defn.description.lower()

    def test_input_schema_type(self):
        defn = GetPrinciplesTool.get_definition()
        assert isinstance(defn.inputSchema, ToolInputSchema)
        assert defn.inputSchema.type == "object"

    def test_required_is_empty(self):
        defn = GetPrinciplesTool.get_definition()
        assert defn.inputSchema.required == []

    def test_properties_keys(self):
        defn = GetPrinciplesTool.get_definition()
        props = defn.inputSchema.properties
        assert "category" in props
        assert "enforcement_level" in props
        assert "include_inactive" in props
        assert "principle_ids" in props

    def test_constitutional_required_false(self):
        defn = GetPrinciplesTool.get_definition()
        assert defn.constitutional_required is False

    def test_category_enum_values(self):
        defn = GetPrinciplesTool.get_definition()
        cat_enum = defn.inputSchema.properties["category"]["enum"]
        assert sorted(cat_enum) == sorted(
            ["core", "safety", "privacy", "fairness", "transparency", "governance"]
        )

    def test_enforcement_level_enum_values(self):
        defn = GetPrinciplesTool.get_definition()
        enf_enum = defn.inputSchema.properties["enforcement_level"]["enum"]
        assert sorted(enf_enum) == sorted(["strict", "moderate", "advisory"])


# ---------------------------------------------------------------------------
# GetPrinciplesTool.get_principle_by_id
# ---------------------------------------------------------------------------


class TestGetPrincipleById:
    def test_existing_id(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P001")
        assert p is not None
        assert p.id == "P001"
        assert p.name == "beneficence"

    def test_missing_id_returns_none(self):
        tool = GetPrinciplesTool()
        assert tool.get_principle_by_id("DOES_NOT_EXIST") is None

    def test_all_eight_principles_retrievable(self):
        tool = GetPrinciplesTool()
        for pid in ["P001", "P002", "P003", "P004", "P005", "P006", "P007", "P008"]:
            assert tool.get_principle_by_id(pid) is not None


# ---------------------------------------------------------------------------
# GetPrinciplesTool.get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_initial_metrics(self):
        tool = GetPrinciplesTool()
        m = tool.get_metrics()
        assert m["request_count"] == 0
        assert m["total_principles"] == 8
        assert m["active_principles"] == 8
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    async def test_request_count_increments(self):
        tool = GetPrinciplesTool()
        await tool.execute({})
        assert tool.get_metrics()["request_count"] == 1
        await tool.execute({})
        assert tool.get_metrics()["request_count"] == 2

    def test_active_principles_count_with_inactive(self):
        tool = GetPrinciplesTool()
        # Deactivate one principle
        tool._principles["P001"].active = False
        m = tool.get_metrics()
        assert m["active_principles"] == 7
        # Restore
        tool._principles["P001"].active = True


# ---------------------------------------------------------------------------
# GetPrinciplesTool._get_locally
# ---------------------------------------------------------------------------


class TestGetLocally:
    def test_no_filters_returns_all(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally(None, None, False, None)
        # All 8 principles are active by default
        assert len(result) == 8

    def test_category_filter_core(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally("core", None, False, None)
        assert all(p.category == PrincipleCategory.CORE for p in result)
        assert len(result) >= 1

    def test_category_filter_safety(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally("safety", None, False, None)
        assert all(p.category == PrincipleCategory.SAFETY for p in result)

    def test_category_filter_privacy(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally("privacy", None, False, None)
        assert all(p.category == PrincipleCategory.PRIVACY for p in result)

    def test_category_filter_fairness(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally("fairness", None, False, None)
        assert all(p.category == PrincipleCategory.FAIRNESS for p in result)

    def test_category_filter_transparency(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally("transparency", None, False, None)
        assert all(p.category == PrincipleCategory.TRANSPARENCY for p in result)

    def test_category_filter_governance(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally("governance", None, False, None)
        assert all(p.category == PrincipleCategory.GOVERNANCE for p in result)

    def test_enforcement_filter_strict(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally(None, "strict", False, None)
        assert all(p.enforcement_level == "strict" for p in result)
        assert len(result) >= 1

    def test_enforcement_filter_moderate(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally(None, "moderate", False, None)
        assert all(p.enforcement_level == "moderate" for p in result)

    def test_include_inactive_false_excludes_inactive(self):
        tool = GetPrinciplesTool()
        tool._principles["P001"].active = False
        result = tool._get_locally(None, None, False, None)
        ids = [p.id for p in result]
        assert "P001" not in ids
        # Restore
        tool._principles["P001"].active = True

    def test_include_inactive_true_includes_inactive(self):
        tool = GetPrinciplesTool()
        tool._principles["P001"].active = False
        result = tool._get_locally(None, None, True, None)
        ids = [p.id for p in result]
        assert "P001" in ids
        # Restore
        tool._principles["P001"].active = True

    def test_principle_ids_filter(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally(None, None, False, ["P001", "P003"])
        ids = {p.id for p in result}
        assert ids == {"P001", "P003"}

    def test_principle_ids_nonexistent(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally(None, None, False, ["NOPE"])
        assert result == []

    def test_combined_category_and_enforcement(self):
        tool = GetPrinciplesTool()
        result = tool._get_locally("safety", "strict", False, None)
        assert all(
            p.category == PrincipleCategory.SAFETY and p.enforcement_level == "strict"
            for p in result
        )

    def test_principle_ids_combined_with_category(self):
        tool = GetPrinciplesTool()
        # P001 is CORE, P002 is SAFETY
        result = tool._get_locally("safety", None, False, ["P001", "P002"])
        # Only P002 matches both filters
        assert all(p.id == "P002" for p in result)

    def test_principle_ids_empty_list(self):
        tool = GetPrinciplesTool()
        # Empty list matches nothing when principle_ids is truthy-empty?
        # An empty list is falsy in Python, so no filter applied
        result = tool._get_locally(None, None, False, [])
        # [] is falsy — no id filter applied, returns all active
        assert len(result) == 8


# ---------------------------------------------------------------------------
# GetPrinciplesTool.execute — local path (no adapter)
# ---------------------------------------------------------------------------


class TestExecuteLocal:
    async def test_execute_no_filters(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({})
        assert result["isError"] is False
        content = result["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        data = json.loads(content[0]["text"])
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret
        assert data["total_count"] == 8
        assert len(data["principles"]) == 8
        assert "categories" in data
        assert "timestamp" in data

    async def test_execute_increments_request_count(self):
        tool = GetPrinciplesTool()
        assert tool._request_count == 0
        await tool.execute({})
        assert tool._request_count == 1

    async def test_execute_with_category_filter(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({"category": "safety"})
        data = json.loads(result["content"][0]["text"])
        assert all(p["category"] == "safety" for p in data["principles"])
        assert not result["isError"]

    async def test_execute_with_enforcement_filter_strict(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({"enforcement_level": "strict"})
        data = json.loads(result["content"][0]["text"])
        assert all(p["enforcement_level"] == "strict" for p in data["principles"])

    async def test_execute_with_enforcement_filter_moderate(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({"enforcement_level": "moderate"})
        data = json.loads(result["content"][0]["text"])
        assert all(p["enforcement_level"] == "moderate" for p in data["principles"])

    async def test_execute_with_include_inactive_false(self):
        tool = GetPrinciplesTool()
        tool._principles["P001"].active = False
        result = await tool.execute({"include_inactive": False})
        data = json.loads(result["content"][0]["text"])
        ids = [p["id"] for p in data["principles"]]
        assert "P001" not in ids
        tool._principles["P001"].active = True

    async def test_execute_with_include_inactive_true(self):
        tool = GetPrinciplesTool()
        tool._principles["P001"].active = False
        result = await tool.execute({"include_inactive": True})
        data = json.loads(result["content"][0]["text"])
        ids = [p["id"] for p in data["principles"]]
        assert "P001" in ids
        tool._principles["P001"].active = True

    async def test_execute_with_principle_ids(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({"principle_ids": ["P001", "P002"]})
        data = json.loads(result["content"][0]["text"])
        assert data["total_count"] == 2
        ids = {p["id"] for p in data["principles"]}
        assert ids == {"P001", "P002"}

    async def test_execute_sorted_by_precedence_desc(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({})
        data = json.loads(result["content"][0]["text"])
        precedences = [p["precedence"] for p in data["principles"]]
        assert precedences == sorted(precedences, reverse=True)

    async def test_execute_categories_deduped(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({})
        data = json.loads(result["content"][0]["text"])
        cats = data["categories"]
        assert len(cats) == len(set(cats))

    async def test_execute_all_category_values(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({})
        data = json.loads(result["content"][0]["text"])
        cats = set(data["categories"])
        expected = {"core", "safety", "privacy", "fairness", "transparency", "governance"}
        assert cats == expected

    async def test_execute_principle_dict_structure(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({"principle_ids": ["P001"]})
        data = json.loads(result["content"][0]["text"])
        p = data["principles"][0]
        for key in [
            "id",
            "name",
            "category",
            "description",
            "enforcement_level",
            "version",
            "active",
            "precedence",
            "related_principles",
        ]:
            assert key in p

    async def test_execute_is_not_error(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({})
        assert result["isError"] is False

    async def test_execute_content_type_text(self):
        tool = GetPrinciplesTool()
        result = await tool.execute({})
        assert result["content"][0]["type"] == "text"


# ---------------------------------------------------------------------------
# GetPrinciplesTool.execute — with policy_client_adapter
# ---------------------------------------------------------------------------


class TestExecuteWithAdapter:
    async def test_execute_calls_adapter(self):
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(
            return_value=[
                {
                    "id": "X001",
                    "name": "test",
                    "category": PrincipleCategory.CORE,
                    "description": "desc",
                    "enforcement_level": "strict",
                    "version": "1.0.0",
                }
            ]
        )
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        result = await tool.execute({"category": "core"})
        assert result["isError"] is False
        adapter.get_active_principles.assert_called_once_with(category="core")

    async def test_execute_adapter_returns_empty_list(self):
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(return_value=[])
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        result = await tool.execute({})
        data = json.loads(result["content"][0]["text"])
        assert data["total_count"] == 0
        assert data["principles"] == []
        assert result["isError"] is False

    async def test_execute_adapter_multiple_principles(self):
        principles_data = [
            {
                "id": f"X{i:03d}",
                "name": f"principle_{i}",
                "category": PrincipleCategory.SAFETY,
                "description": f"desc {i}",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "precedence": 100 - i,
            }
            for i in range(3)
        ]
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(return_value=principles_data)
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        result = await tool.execute({})
        data = json.loads(result["content"][0]["text"])
        assert data["total_count"] == 3
        assert result["isError"] is False

    async def test_execute_adapter_passes_all_arguments(self):
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(return_value=[])
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        args = {
            "category": "core",
            "enforcement_level": "strict",
            "include_inactive": True,
            "principle_ids": ["P001"],
        }
        await tool.execute(args)
        adapter.get_active_principles.assert_called_once_with(**args)

    async def test_execute_adapter_sorted_by_precedence(self):
        principles_data = [
            {
                "id": "Y001",
                "name": "low",
                "category": PrincipleCategory.CORE,
                "description": "low precedence",
                "enforcement_level": "advisory",
                "version": "1.0.0",
                "precedence": 10,
            },
            {
                "id": "Y002",
                "name": "high",
                "category": PrincipleCategory.CORE,
                "description": "high precedence",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "precedence": 99,
            },
        ]
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(return_value=principles_data)
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        result = await tool.execute({})
        data = json.loads(result["content"][0]["text"])
        precs = [p["precedence"] for p in data["principles"]]
        assert precs == sorted(precs, reverse=True)


# ---------------------------------------------------------------------------
# GetPrinciplesTool.execute — error handling
# ---------------------------------------------------------------------------


class TestExecuteErrorHandling:
    async def test_execute_local_exception_returns_error(self):
        tool = GetPrinciplesTool()
        with patch.object(tool, "_get_locally", side_effect=RuntimeError("boom")):
            result = await tool.execute({})
        assert result["isError"] is True
        data = json.loads(result["content"][0]["text"])
        assert "boom" in data["error"]
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    async def test_execute_adapter_exception_returns_error(self):
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(side_effect=ConnectionError("adapter down"))
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        result = await tool.execute({})
        assert result["isError"] is True
        data = json.loads(result["content"][0]["text"])
        assert "adapter down" in data["error"]

    async def test_execute_error_content_is_text_type(self):
        tool = GetPrinciplesTool()
        with patch.object(tool, "_get_locally", side_effect=ValueError("oops")):
            result = await tool.execute({})
        assert result["content"][0]["type"] == "text"

    async def test_execute_request_count_increments_even_on_error(self):
        tool = GetPrinciplesTool()
        with patch.object(tool, "_get_locally", side_effect=RuntimeError("err")):
            await tool.execute({})
        assert tool._request_count == 1

    async def test_execute_invalid_category_raises_and_returns_error(self):
        """Invalid category value causes ValueError in PrincipleCategory() constructor."""
        tool = GetPrinciplesTool()
        result = await tool.execute({"category": "INVALID_CATEGORY"})
        assert result["isError"] is True


# ---------------------------------------------------------------------------
# GetPrinciplesTool._get_from_policy_client
# ---------------------------------------------------------------------------


class TestGetFromPolicyClient:
    async def test_returns_constitutional_principle_instances(self):
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(
            return_value=[
                {
                    "id": "Z001",
                    "name": "test",
                    "category": PrincipleCategory.GOVERNANCE,
                    "description": "governance test",
                    "enforcement_level": "moderate",
                    "version": "2.0.0",
                }
            ]
        )
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        principles = await tool._get_from_policy_client({"include_inactive": False})
        assert len(principles) == 1
        assert isinstance(principles[0], ConstitutionalPrinciple)
        assert principles[0].id == "Z001"

    async def test_passes_arguments_as_kwargs(self):
        adapter = MagicMock()
        adapter.get_active_principles = AsyncMock(return_value=[])
        tool = GetPrinciplesTool(policy_client_adapter=adapter)
        args = {"category": "privacy", "enforcement_level": "strict"}
        await tool._get_from_policy_client(args)
        adapter.get_active_principles.assert_called_once_with(**args)


# ---------------------------------------------------------------------------
# Integration-style: verify default principles correctness
# ---------------------------------------------------------------------------


class TestDefaultPrinciplesContent:
    def test_p001_beneficence(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P001")
        assert p.name == "beneficence"
        assert p.category == PrincipleCategory.CORE
        assert p.enforcement_level == "strict"
        assert p.precedence == 100
        assert "P002" in p.related_principles
        assert "P003" in p.related_principles

    def test_p002_non_maleficence(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P002")
        assert p.name == "non_maleficence"
        assert p.category == PrincipleCategory.SAFETY
        assert p.enforcement_level == "strict"
        assert "P001" in p.related_principles

    def test_p003_autonomy(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P003")
        assert p.name == "autonomy"
        assert p.category == PrincipleCategory.CORE
        assert p.precedence == 95

    def test_p004_justice(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P004")
        assert p.name == "justice"
        assert p.category == PrincipleCategory.FAIRNESS

    def test_p005_transparency(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P005")
        assert p.name == "transparency"
        assert p.category == PrincipleCategory.TRANSPARENCY
        assert p.enforcement_level == "moderate"

    def test_p006_accountability(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P006")
        assert p.name == "accountability"
        assert p.category == PrincipleCategory.GOVERNANCE

    def test_p007_privacy(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P007")
        assert p.name == "privacy"
        assert p.category == PrincipleCategory.PRIVACY
        assert p.precedence == 95

    def test_p008_safety(self):
        tool = GetPrinciplesTool()
        p = tool.get_principle_by_id("P008")
        assert p.name == "safety"
        assert p.category == PrincipleCategory.SAFETY
        assert p.precedence == 100

    def test_all_active_by_default(self):
        tool = GetPrinciplesTool()
        for p in tool._principles.values():
            assert p.active is True

    def test_all_version_1_0_0(self):
        tool = GetPrinciplesTool()
        for p in tool._principles.values():
            assert p.version == "1.0.0"
