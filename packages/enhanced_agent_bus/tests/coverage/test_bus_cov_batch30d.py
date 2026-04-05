"""
Coverage tests for batch 30d: session fallbacks, visual studio service, online learning registry.
Constitutional Hash: 608508a9bd224290

Targets:
- routes/sessions/_fallbacks.py (63.6% -> 95%+)
- visual_studio/service.py (51.2% -> 95%+)
- online_learning_infra/registry.py (50% -> 95%+)
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. routes/sessions/_fallbacks.py
#
# The real session modules are importable in this env, so USING_FALLBACKS=False.
# To exercise the fallback code paths (lines 44-146), we reload the module with
# the real imports blocked so the except-ImportError branches execute.
# ---------------------------------------------------------------------------

_FALLBACKS_MOD = "enhanced_agent_bus.routes.sessions._fallbacks"

# Modules whose import we want to block during reload so fallbacks activate
_BLOCK_SESSION = [
    "enhanced_agent_bus.session_context",
    "enhanced_agent_bus.session_governance_sdk",
    "enhanced_agent_bus.session_models",
    "session_context",
    "session_governance_sdk",
    "session_models",
]
_BLOCK_TENANT = [
    "src.core.shared.security.tenant_context",
    "enhanced_agent_bus._compat.security.tenant_context",
]


class _RaiseOnImport:
    """Sentinel placed in sys.modules to make imports raise ImportError."""

    def __getattr__(self, name):
        raise ImportError("Blocked for testing")


def _reload_fallbacks_module(*, block_session: bool = True, block_tenant: bool = True):
    """Reload _fallbacks with selected imports blocked so fallback code executes."""
    blocked = set()
    if block_session:
        blocked.update(_BLOCK_SESSION)
    if block_tenant:
        blocked.update(_BLOCK_TENANT)

    saved = {}
    # Remove the fallbacks module itself
    if _FALLBACKS_MOD in sys.modules:
        saved[_FALLBACKS_MOD] = sys.modules.pop(_FALLBACKS_MOD)

    # Replace blocked modules with sentinel objects that raise ImportError
    for name in blocked:
        if name in sys.modules:
            saved[name] = sys.modules[name]
        else:
            saved[name] = None
        sys.modules[name] = _RaiseOnImport()

    try:
        mod = importlib.import_module(_FALLBACKS_MOD)
        return mod
    finally:
        # Restore originals so we don't pollute other tests
        for name, m in saved.items():
            if name == _FALLBACKS_MOD:
                continue
            if m is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = m


@pytest.fixture()
def fallback_mod():
    """Provide the _fallbacks module with all fallbacks active."""
    mod = _reload_fallbacks_module(block_session=True, block_tenant=True)
    yield mod
    # Clean up so subsequent imports get the real module
    sys.modules.pop(_FALLBACKS_MOD, None)


class TestFallbackRiskLevel:
    """Tests for the fallback RiskLevel enum."""

    def test_risk_level_values(self, fallback_mod) -> None:
        assert fallback_mod.USING_FALLBACKS is True
        rl = fallback_mod.RiskLevel
        assert rl.LOW == "low"
        assert rl.MEDIUM == "medium"
        assert rl.HIGH == "high"
        assert rl.CRITICAL == "critical"

    def test_risk_level_is_str_enum(self, fallback_mod) -> None:
        rl = fallback_mod.RiskLevel
        assert isinstance(rl.LOW, str)
        assert isinstance(rl.MEDIUM, str)

    def test_risk_level_members_count(self, fallback_mod) -> None:
        assert len(fallback_mod.RiskLevel) == 4


class TestFallbackSessionGovernanceConfig:
    """Tests for the fallback SessionGovernanceConfig model."""

    def test_create_minimal_config(self, fallback_mod) -> None:
        cfg = fallback_mod.SessionGovernanceConfig(
            session_id="sess-001",
            tenant_id="tenant-abc",
        )
        assert cfg.session_id == "sess-001"
        assert cfg.tenant_id == "tenant-abc"
        assert cfg.user_id is None
        assert cfg.policy_id is None
        assert cfg.policy_overrides == {}
        assert cfg.enabled_policies == []
        assert cfg.disabled_policies == []
        assert cfg.require_human_approval is False
        assert cfg.max_automation_level is None

    def test_create_full_config(self, fallback_mod) -> None:
        rl = fallback_mod.RiskLevel
        cfg = fallback_mod.SessionGovernanceConfig(
            session_id="sess-002",
            tenant_id="tenant-xyz",
            user_id="user-1",
            risk_level=rl.HIGH,
            policy_id="pol-99",
            policy_overrides={"key": "value"},
            enabled_policies=["pol-a"],
            disabled_policies=["pol-b"],
            require_human_approval=True,
            max_automation_level="semi",
        )
        assert cfg.risk_level == rl.HIGH
        assert cfg.require_human_approval is True
        assert cfg.max_automation_level == "semi"
        assert cfg.enabled_policies == ["pol-a"]
        assert cfg.disabled_policies == ["pol-b"]

    def test_default_risk_level_is_medium(self, fallback_mod) -> None:
        cfg = fallback_mod.SessionGovernanceConfig(session_id="s", tenant_id="t")
        assert cfg.risk_level == fallback_mod.RiskLevel.MEDIUM


class TestFallbackSessionContext:
    """Tests for the fallback SessionContext model."""

    def test_create_session_context(self, fallback_mod) -> None:
        now = datetime.now(UTC)
        gov = fallback_mod.SessionGovernanceConfig(session_id="s1", tenant_id="t1")
        ctx = fallback_mod.SessionContext(
            session_id="s1",
            governance_config=gov,
            created_at=now,
            updated_at=now,
        )
        assert ctx.session_id == "s1"
        assert ctx.metadata == {}
        assert ctx.expires_at is None

    def test_session_context_with_optional_fields(self, fallback_mod) -> None:
        now = datetime.now(UTC)
        gov = fallback_mod.SessionGovernanceConfig(session_id="s2", tenant_id="t2")
        ctx = fallback_mod.SessionContext(
            session_id="s2",
            governance_config=gov,
            metadata={"foo": "bar"},
            created_at=now,
            updated_at=now,
            expires_at=now,
            constitutional_hash="custom-hash",
        )
        assert ctx.metadata == {"foo": "bar"}
        assert ctx.expires_at == now
        assert ctx.constitutional_hash == "custom-hash"


class TestFallbackSessionContextManager:
    """Tests for the fallback SessionContextManager."""

    async def test_connect_returns_true(self, fallback_mod) -> None:
        mgr = fallback_mod.SessionContextManager()
        assert await mgr.connect() is True

    async def test_create_raises_not_implemented(self, fallback_mod) -> None:
        mgr = fallback_mod.SessionContextManager()
        with pytest.raises(NotImplementedError, match="Mock manager"):
            await mgr.create("session-1", config={})

    async def test_get_returns_none(self, fallback_mod) -> None:
        mgr = fallback_mod.SessionContextManager()
        assert await mgr.get("nonexistent") is None

    async def test_update_returns_none(self, fallback_mod) -> None:
        mgr = fallback_mod.SessionContextManager()
        assert await mgr.update("sess", data={}) is None

    async def test_delete_returns_false(self, fallback_mod) -> None:
        mgr = fallback_mod.SessionContextManager()
        assert await mgr.delete("sess") is False

    async def test_exists_returns_false(self, fallback_mod) -> None:
        mgr = fallback_mod.SessionContextManager()
        assert await mgr.exists("sess") is False

    def test_get_metrics_returns_empty_dict(self, fallback_mod) -> None:
        mgr = fallback_mod.SessionContextManager()
        assert mgr.get_metrics() == {}


class TestFallbackConstants:
    """Tests for USING_FALLBACKS and USING_FALLBACK_TENANT."""

    def test_using_fallbacks_true_when_blocked(self, fallback_mod) -> None:
        assert fallback_mod.USING_FALLBACKS is True

    def test_using_fallback_tenant_true_when_blocked(self, fallback_mod) -> None:
        assert fallback_mod.USING_FALLBACK_TENANT is True

    def test_all_exports(self, fallback_mod) -> None:
        expected = {
            "USING_FALLBACKS",
            "USING_FALLBACK_TENANT",
            "RiskLevel",
            "SessionContext",
            "SessionContextManager",
            "SessionGovernanceConfig",
            "get_tenant_id",
        }
        assert set(fallback_mod.__all__) == expected


class TestIsExplicitDevOrTestMode:
    """Tests for _is_explicit_dev_or_test_mode branches."""

    def _get_fn(self, fallback_mod):
        return fallback_mod._is_explicit_dev_or_test_mode

    def test_returns_true_for_dev_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "dev")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_returns_true_for_development_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "development")
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_returns_true_for_local_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_returns_true_for_test_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        assert fn() is True

    def test_returns_true_for_testing_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "testing")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_returns_true_for_ci_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "ci")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_returns_true_for_qa_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "qa")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_returns_false_for_production(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "production")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is False

    def test_returns_false_for_prod(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "prod")
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is False

    def test_returns_false_for_staging(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("APP_ENV", "staging")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is False

    def test_returns_false_for_stage(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "stage")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        assert fn() is False

    def test_returns_false_for_preprod(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "preprod")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is False

    def test_production_overrides_pytest_current_test(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "some_test.py::test_func")
        monkeypatch.setenv("ACGS_ENV", "production")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is False

    def test_pytest_current_test_fallback_when_no_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_something.py::test_x")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_returns_false_no_env_no_pytest(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ACGS_ENV", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is False

    def test_whitespace_stripped_from_env(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "  Dev  ")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is True

    def test_case_insensitive_production(self, fallback_mod, monkeypatch) -> None:
        fn = self._get_fn(fallback_mod)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ENV", "PRODUCTION")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert fn() is False


class TestFallbackGetTenantId:
    """Tests for the fallback get_tenant_id function."""

    async def test_returns_tenant_id_in_dev_mode(self, fallback_mod, monkeypatch) -> None:
        from fastapi import HTTPException

        monkeypatch.setenv("ACGS_ENV", "dev")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        result = await fallback_mod.get_tenant_id(x_tenant_id="tenant-123")
        assert result == "tenant-123"

    async def test_raises_503_in_production_mode(self, fallback_mod, monkeypatch) -> None:
        from fastapi import HTTPException

        monkeypatch.setenv("ACGS_ENV", "production")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            await fallback_mod.get_tenant_id(x_tenant_id="tenant-123")
        assert exc_info.value.status_code == 503

    async def test_raises_400_when_header_missing(self, fallback_mod, monkeypatch) -> None:
        from fastapi import HTTPException

        monkeypatch.setenv("ACGS_ENV", "dev")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            await fallback_mod.get_tenant_id(x_tenant_id=None)
        assert exc_info.value.status_code == 400

    async def test_raises_400_when_header_empty_string(self, fallback_mod, monkeypatch) -> None:
        from fastapi import HTTPException

        monkeypatch.setenv("ACGS_ENV", "dev")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            await fallback_mod.get_tenant_id(x_tenant_id="")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 2. visual_studio/service.py
# ---------------------------------------------------------------------------


class TestVisualStudioServiceCreateWorkflow:
    """Tests for VisualStudioService.create_workflow."""

    async def test_create_workflow_returns_definition(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Test Workflow")
        assert wf.name == "Test Workflow"
        assert wf.id.startswith("wf-")
        assert len(wf.nodes) == 2
        assert wf.edges == []

    async def test_create_workflow_has_start_and_end_nodes(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("WF2")
        node_types = {n.type for n in wf.nodes}
        assert NodeType.START in node_types
        assert NodeType.END in node_types

    async def test_create_workflow_with_description(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("WF3", description="A test workflow")
        assert wf.description == "A test workflow"

    async def test_create_workflow_with_tenant_id(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("WF4", tenant_id="t-abc")
        assert wf.tenant_id == "t-abc"

    async def test_create_workflow_stored_internally(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Stored")
        assert wf.id in svc._store

    async def test_create_workflow_timestamps(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Timed")
        assert wf.created_at is not None
        assert wf.updated_at is not None


class TestVisualStudioServiceGetWorkflow:
    """Tests for VisualStudioService.get_workflow."""

    async def test_get_unknown_returns_none(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        assert await svc.get_workflow("nonexistent") is None

    async def test_get_known_returns_workflow(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Gettable")
        fetched = await svc.get_workflow(wf.id)
        assert fetched is not None
        assert fetched.id == wf.id
        assert fetched.name == "Gettable"


class TestVisualStudioServiceSaveWorkflow:
    """Tests for VisualStudioService.save_workflow."""

    async def test_save_new_workflow(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowDefinition
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = WorkflowDefinition(id="wf-save-1", name="Saved WF")
        saved = await svc.save_workflow(wf)
        assert saved.id == "wf-save-1"
        assert await svc.get_workflow("wf-save-1") is not None

    async def test_save_overwrites_existing(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Original")
        wf_updated = wf.model_copy(update={"name": "Updated"})
        await svc.save_workflow(wf_updated)
        fetched = await svc.get_workflow(wf.id)
        assert fetched is not None
        assert fetched.name == "Updated"


class TestVisualStudioServiceDeleteWorkflow:
    """Tests for VisualStudioService.delete_workflow."""

    async def test_delete_unknown_returns_false(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        assert await svc.delete_workflow("no-such-id") is False

    async def test_delete_known_returns_true(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Deletable")
        assert await svc.delete_workflow(wf.id) is True
        assert await svc.get_workflow(wf.id) is None

    async def test_delete_twice_returns_false_second_time(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("DeleteTwice")
        assert await svc.delete_workflow(wf.id) is True
        assert await svc.delete_workflow(wf.id) is False


class TestVisualStudioServiceListWorkflows:
    """Tests for VisualStudioService.list_workflows."""

    async def test_list_empty(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        summaries, total = await svc.list_workflows(tenant_id=None, page=1, page_size=10)
        assert summaries == []
        assert total == 0

    async def test_list_returns_all_workflows(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        await svc.create_workflow("WF-A")
        await svc.create_workflow("WF-B")
        summaries, total = await svc.list_workflows(tenant_id=None, page=1, page_size=10)
        assert total == 2
        assert len(summaries) == 2

    async def test_list_filters_by_tenant_id(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        await svc.create_workflow("WF-T1", tenant_id="t1")
        await svc.create_workflow("WF-T2", tenant_id="t2")
        summaries, total = await svc.list_workflows(tenant_id="t1", page=1, page_size=10)
        assert total == 1
        assert summaries[0].name == "WF-T1"

    async def test_list_pagination(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        for i in range(5):
            await svc.create_workflow(f"WF-Page-{i}")
        summaries, total = await svc.list_workflows(tenant_id=None, page=1, page_size=2)
        assert total == 5
        assert len(summaries) == 2

    async def test_list_pagination_page2(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        for i in range(5):
            await svc.create_workflow(f"WF-P2-{i}")
        summaries, total = await svc.list_workflows(tenant_id=None, page=2, page_size=2)
        assert total == 5
        assert len(summaries) == 2

    async def test_list_pagination_last_page_partial(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        for i in range(5):
            await svc.create_workflow(f"WF-Last-{i}")
        summaries, total = await svc.list_workflows(tenant_id=None, page=3, page_size=2)
        assert total == 5
        assert len(summaries) == 1

    async def test_list_summary_fields(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        await svc.create_workflow("Summary-WF", description="desc")
        summaries, _ = await svc.list_workflows(tenant_id=None, page=1, page_size=10)
        s = summaries[0]
        assert s.name == "Summary-WF"
        assert s.node_count == 2  # start + end
        assert s.edge_count == 0
        assert s.version == "1.0.0"
        assert s.is_active is True

    async def test_list_beyond_last_page_returns_empty(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        await svc.create_workflow("WF-Beyond")
        summaries, total = await svc.list_workflows(tenant_id=None, page=100, page_size=10)
        assert total == 1
        assert summaries == []


class TestVisualStudioServiceValidateWorkflow:
    """Tests for VisualStudioService.validate_workflow."""

    async def test_validate_returns_valid(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Valid-WF")
        result = svc.validate_workflow(wf)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []


class TestVisualStudioServiceSimulateWorkflow:
    """Tests for VisualStudioService.simulate_workflow."""

    async def test_simulate_returns_success(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Sim-WF")
        result = await svc.simulate_workflow(wf, {"key": "value"})
        assert result.success is True
        assert result.workflow_id == wf.id
        assert result.steps == []
        assert result.final_output == {"key": "value"}

    async def test_simulate_with_empty_input(self) -> None:
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Sim-Empty")
        result = await svc.simulate_workflow(wf, {})
        assert result.success is True
        assert result.final_output == {}


class TestVisualStudioServiceExportWorkflow:
    """Tests for VisualStudioService.export_workflow."""

    async def test_export_json(self) -> None:
        from enhanced_agent_bus.visual_studio.models import ExportFormat, WorkflowExportRequest
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Export WF")
        req = WorkflowExportRequest(format=ExportFormat.JSON)
        result = await svc.export_workflow(wf, req)
        assert result.workflow_id == wf.id
        assert result.format == ExportFormat.JSON
        assert result.filename == "export_wf.json"
        assert len(result.content) > 0

    async def test_export_rego(self) -> None:
        from enhanced_agent_bus.visual_studio.models import ExportFormat, WorkflowExportRequest
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Rego WF")
        req = WorkflowExportRequest(format=ExportFormat.REGO)
        result = await svc.export_workflow(wf, req)
        assert result.format == ExportFormat.REGO
        assert result.filename == "rego_wf.rego"

    async def test_export_yaml(self) -> None:
        from enhanced_agent_bus.visual_studio.models import ExportFormat, WorkflowExportRequest
        from enhanced_agent_bus.visual_studio.service import VisualStudioService

        svc = VisualStudioService()
        wf = await svc.create_workflow("Yaml WF")
        req = WorkflowExportRequest(format=ExportFormat.YAML)
        result = await svc.export_workflow(wf, req)
        assert result.format == ExportFormat.YAML
        assert result.filename == "yaml_wf.yaml"


class TestGetVisualStudioService:
    """Tests for the get_visual_studio_service singleton."""

    def test_returns_instance(self) -> None:
        import enhanced_agent_bus.visual_studio.service as mod

        mod._visual_studio_service = None
        svc = mod.get_visual_studio_service()
        assert isinstance(svc, mod.VisualStudioService)

    def test_returns_same_instance(self) -> None:
        import enhanced_agent_bus.visual_studio.service as mod

        mod._visual_studio_service = None
        svc1 = mod.get_visual_studio_service()
        svc2 = mod.get_visual_studio_service()
        assert svc1 is svc2

    def test_reset_creates_new_instance(self) -> None:
        import enhanced_agent_bus.visual_studio.service as mod

        mod._visual_studio_service = None
        svc1 = mod.get_visual_studio_service()
        mod._visual_studio_service = None
        svc2 = mod.get_visual_studio_service()
        assert svc1 is not svc2


# ---------------------------------------------------------------------------
# 3. online_learning_infra/registry.py
# ---------------------------------------------------------------------------


@pytest.fixture()
def _reset_registry():
    """Reset global registry state before and after each test."""
    import enhanced_agent_bus.online_learning_infra.registry as reg

    reg._online_learning_adapter = None
    reg._online_learning_pipeline = None
    reg._feedback_kafka_consumer = None
    yield
    reg._online_learning_adapter = None
    reg._online_learning_pipeline = None
    reg._feedback_kafka_consumer = None


class TestGetOnlineLearningAdapter:
    """Tests for get_online_learning_adapter."""

    @pytest.mark.usefixtures("_reset_registry")
    def test_creates_adapter(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.RiverSklearnAdapter"
            ) as MockAdapter,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            mock_instance = MagicMock()
            MockAdapter.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_adapter,
            )

            result = get_online_learning_adapter()
            assert result is mock_instance
            MockAdapter.assert_called_once()

    @pytest.mark.usefixtures("_reset_registry")
    def test_returns_singleton(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.RiverSklearnAdapter"
            ) as MockAdapter,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            mock_instance = MagicMock()
            MockAdapter.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_adapter,
            )

            r1 = get_online_learning_adapter()
            r2 = get_online_learning_adapter()
            assert r1 is r2
            assert MockAdapter.call_count == 1

    @pytest.mark.usefixtures("_reset_registry")
    def test_force_new_creates_new(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.RiverSklearnAdapter"
            ) as MockAdapter,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            mock_a = MagicMock()
            mock_b = MagicMock()
            MockAdapter.side_effect = [mock_a, mock_b]

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_adapter,
            )

            r1 = get_online_learning_adapter()
            r2 = get_online_learning_adapter(force_new=True)
            assert r1 is mock_a
            assert r2 is mock_b
            assert MockAdapter.call_count == 2

    @pytest.mark.usefixtures("_reset_registry")
    def test_passes_model_type_and_n_models(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.RiverSklearnAdapter"
            ) as MockAdapter,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            from enhanced_agent_bus.online_learning_infra.config import ModelType
            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_adapter,
            )

            get_online_learning_adapter(
                model_type=ModelType.REGRESSOR,
                n_models=5,
                feature_names=["a", "b"],
            )
            MockAdapter.assert_called_once_with(
                model_type=ModelType.REGRESSOR,
                n_models=5,
                feature_names=["a", "b"],
            )

    @pytest.mark.usefixtures("_reset_registry")
    def test_calls_load_registry_state(self) -> None:
        with (
            patch("enhanced_agent_bus.online_learning_infra.registry.RiverSklearnAdapter"),
            patch(
                "enhanced_agent_bus.online_learning_infra.registry._load_registry_state"
            ) as mock_load,
        ):
            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_adapter,
            )

            get_online_learning_adapter()
            mock_load.assert_called_once_with("adapter")


class TestGetOnlineLearningPipeline:
    """Tests for get_online_learning_pipeline."""

    @pytest.mark.usefixtures("_reset_registry")
    def test_creates_pipeline(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.OnlineLearningPipeline"
            ) as MockPipeline,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            mock_instance = MagicMock()
            MockPipeline.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_pipeline,
            )

            result = get_online_learning_pipeline()
            assert result is mock_instance

    @pytest.mark.usefixtures("_reset_registry")
    def test_returns_singleton(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.OnlineLearningPipeline"
            ) as MockPipeline,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            mock_instance = MagicMock()
            MockPipeline.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_pipeline,
            )

            r1 = get_online_learning_pipeline()
            r2 = get_online_learning_pipeline()
            assert r1 is r2
            assert MockPipeline.call_count == 1

    @pytest.mark.usefixtures("_reset_registry")
    def test_force_new_creates_new(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.OnlineLearningPipeline"
            ) as MockPipeline,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            mock_a = MagicMock()
            mock_b = MagicMock()
            MockPipeline.side_effect = [mock_a, mock_b]

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_pipeline,
            )

            r1 = get_online_learning_pipeline()
            r2 = get_online_learning_pipeline(force_new=True)
            assert r1 is mock_a
            assert r2 is mock_b

    @pytest.mark.usefixtures("_reset_registry")
    def test_passes_feature_names_and_model_type(self) -> None:
        with (
            patch(
                "enhanced_agent_bus.online_learning_infra.registry.OnlineLearningPipeline"
            ) as MockPipeline,
            patch("enhanced_agent_bus.online_learning_infra.registry._load_registry_state"),
        ):
            from enhanced_agent_bus.online_learning_infra.config import ModelType
            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_pipeline,
            )

            get_online_learning_pipeline(
                feature_names=["x", "y"],
                model_type=ModelType.REGRESSOR,
            )
            MockPipeline.assert_called_once_with(
                feature_names=["x", "y"],
                model_type=ModelType.REGRESSOR,
            )

    @pytest.mark.usefixtures("_reset_registry")
    def test_calls_load_registry_state(self) -> None:
        with (
            patch("enhanced_agent_bus.online_learning_infra.registry.OnlineLearningPipeline"),
            patch(
                "enhanced_agent_bus.online_learning_infra.registry._load_registry_state"
            ) as mock_load,
        ):
            from enhanced_agent_bus.online_learning_infra.registry import (
                get_online_learning_pipeline,
            )

            get_online_learning_pipeline()
            mock_load.assert_called_once_with("pipeline")


class TestGetFeedbackKafkaConsumer:
    """Tests for get_feedback_kafka_consumer."""

    @pytest.mark.usefixtures("_reset_registry")
    async def test_creates_consumer(self) -> None:
        with patch(
            "enhanced_agent_bus.online_learning_infra.registry.FeedbackKafkaConsumer"
        ) as MockConsumer:
            mock_instance = MagicMock()
            MockConsumer.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_feedback_kafka_consumer,
            )

            result = await get_feedback_kafka_consumer()
            assert result is mock_instance

    @pytest.mark.usefixtures("_reset_registry")
    async def test_returns_singleton(self) -> None:
        with patch(
            "enhanced_agent_bus.online_learning_infra.registry.FeedbackKafkaConsumer"
        ) as MockConsumer:
            mock_instance = MagicMock()
            MockConsumer.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_feedback_kafka_consumer,
            )

            r1 = await get_feedback_kafka_consumer()
            r2 = await get_feedback_kafka_consumer()
            assert r1 is r2
            assert MockConsumer.call_count == 1

    @pytest.mark.usefixtures("_reset_registry")
    async def test_passes_pipeline(self) -> None:
        with patch(
            "enhanced_agent_bus.online_learning_infra.registry.FeedbackKafkaConsumer"
        ) as MockConsumer:
            mock_pipeline = MagicMock()
            mock_instance = MagicMock()
            MockConsumer.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                get_feedback_kafka_consumer,
            )

            await get_feedback_kafka_consumer(pipeline=mock_pipeline)
            MockConsumer.assert_called_once_with(pipeline=mock_pipeline)


class TestStartFeedbackConsumer:
    """Tests for start_feedback_consumer."""

    @pytest.mark.usefixtures("_reset_registry")
    async def test_start_calls_consumer_start(self) -> None:
        with patch(
            "enhanced_agent_bus.online_learning_infra.registry.FeedbackKafkaConsumer"
        ) as MockConsumer:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock(return_value=True)
            MockConsumer.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                start_feedback_consumer,
            )

            result = await start_feedback_consumer()
            assert result is True
            mock_instance.start.assert_awaited_once()

    @pytest.mark.usefixtures("_reset_registry")
    async def test_start_with_pipeline(self) -> None:
        with patch(
            "enhanced_agent_bus.online_learning_infra.registry.FeedbackKafkaConsumer"
        ) as MockConsumer:
            mock_pipeline = MagicMock()
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock(return_value=True)
            MockConsumer.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                start_feedback_consumer,
            )

            result = await start_feedback_consumer(pipeline=mock_pipeline)
            assert result is True
            MockConsumer.assert_called_once_with(pipeline=mock_pipeline)

    @pytest.mark.usefixtures("_reset_registry")
    async def test_start_returns_false_on_failure(self) -> None:
        with patch(
            "enhanced_agent_bus.online_learning_infra.registry.FeedbackKafkaConsumer"
        ) as MockConsumer:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock(return_value=False)
            MockConsumer.return_value = mock_instance

            from enhanced_agent_bus.online_learning_infra.registry import (
                start_feedback_consumer,
            )

            result = await start_feedback_consumer()
            assert result is False


class TestStopFeedbackConsumer:
    """Tests for stop_feedback_consumer."""

    @pytest.mark.usefixtures("_reset_registry")
    async def test_stop_when_no_consumer(self) -> None:
        import enhanced_agent_bus.online_learning_infra.registry as reg

        await reg.stop_feedback_consumer()
        assert reg._feedback_kafka_consumer is None

    @pytest.mark.usefixtures("_reset_registry")
    async def test_stop_calls_consumer_stop(self) -> None:
        import enhanced_agent_bus.online_learning_infra.registry as reg

        mock_consumer = MagicMock()
        mock_consumer.stop = AsyncMock()
        reg._feedback_kafka_consumer = mock_consumer

        with patch(
            "enhanced_agent_bus.online_learning_infra.registry._save_registry_state"
        ) as mock_save:
            await reg.stop_feedback_consumer()
            mock_consumer.stop.assert_awaited_once()
            mock_save.assert_called_once_with("consumer")
            assert reg._feedback_kafka_consumer is None

    @pytest.mark.usefixtures("_reset_registry")
    async def test_stop_sets_consumer_to_none(self) -> None:
        import enhanced_agent_bus.online_learning_infra.registry as reg

        mock_consumer = MagicMock()
        mock_consumer.stop = AsyncMock()
        reg._feedback_kafka_consumer = mock_consumer

        with patch("enhanced_agent_bus.online_learning_infra.registry._save_registry_state"):
            await reg.stop_feedback_consumer()
            assert reg._feedback_kafka_consumer is None


class TestGetConsumerStats:
    """Tests for get_consumer_stats."""

    @pytest.mark.usefixtures("_reset_registry")
    def test_returns_none_when_no_consumer(self) -> None:
        from enhanced_agent_bus.online_learning_infra.registry import get_consumer_stats

        assert get_consumer_stats() is None

    @pytest.mark.usefixtures("_reset_registry")
    def test_returns_stats_when_consumer_exists(self) -> None:
        import enhanced_agent_bus.online_learning_infra.registry as reg
        from enhanced_agent_bus.online_learning_infra.models import ConsumerStats

        mock_stats = ConsumerStats(messages_received=42)
        mock_consumer = MagicMock()
        mock_consumer.get_stats.return_value = mock_stats
        reg._feedback_kafka_consumer = mock_consumer

        result = reg.get_consumer_stats()
        assert result is mock_stats
        assert result.messages_received == 42


class TestLoadAndSaveRegistryState:
    """Tests for _load_registry_state and _save_registry_state (no-op placeholders)."""

    def test_load_does_not_raise(self) -> None:
        from enhanced_agent_bus.online_learning_infra.registry import _load_registry_state

        _load_registry_state("adapter")
        _load_registry_state("pipeline")
        _load_registry_state("consumer")

    def test_save_does_not_raise(self) -> None:
        from enhanced_agent_bus.online_learning_infra.registry import _save_registry_state

        _save_registry_state("adapter")
        _save_registry_state("pipeline")
        _save_registry_state("consumer")
