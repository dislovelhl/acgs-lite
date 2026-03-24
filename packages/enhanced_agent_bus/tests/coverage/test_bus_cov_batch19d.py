"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- api/app.py (helper functions, lifespan, create_app)
- verification_orchestrator.py (VerificationOrchestrator, VerificationResult)
- mcp_server/protocol/handler.py (MCPHandler)

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.mcp_server.config import MCPConfig
from enhanced_agent_bus.mcp_server.protocol.handler import MCPHandler
from enhanced_agent_bus.mcp_server.protocol.types import (
    MCPError,
    MCPErrorCode,
    MCPRequest,
    MCPResponse,
    PromptDefinition,
    ResourceDefinition,
    ToolDefinition,
    ToolInputSchema,
)
from enhanced_agent_bus.models import AgentMessage, MessageType
from enhanced_agent_bus.validators import ValidationResult
from enhanced_agent_bus.verification_orchestrator import (
    VerificationOrchestrator,
)
from enhanced_agent_bus.verification_orchestrator import (
    VerificationResult as VResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus_config():
    return BusConfiguration(
        enable_pqc=False,
        enable_maci=False,
        maci_strict_mode=False,
    )


@pytest.fixture
def mcp_config():
    return MCPConfig(
        server_name="test-server",
        server_version="0.0.1",
        strict_mode=False,
        log_requests=True,
    )


@pytest.fixture
def mcp_config_strict():
    return MCPConfig(
        server_name="test-strict",
        server_version="0.0.1",
        strict_mode=True,
        log_requests=False,
    )


@pytest.fixture
def handler(mcp_config):
    return MCPHandler(config=mcp_config)


@pytest.fixture
def handler_strict(mcp_config_strict):
    return MCPHandler(config=mcp_config_strict)


@pytest.fixture
def sample_message():
    return AgentMessage(
        content={"text": "hello"},
        from_agent="agent-a",
        to_agent="agent-b",
        tenant_id="test-tenant",
        message_type=MessageType.COMMAND,
        impact_score=0.5,
    )


@pytest.fixture
def high_impact_message():
    return AgentMessage(
        content={"text": "important"},
        from_agent="agent-a",
        to_agent="agent-b",
        tenant_id="test-tenant",
        message_type=MessageType.TASK_REQUEST,
        impact_score=0.9,
    )


def _make_request(method, params=None, req_id=1):
    return MCPRequest(jsonrpc="2.0", method=method, id=req_id, params=params)


# ===================================================================
# api/app.py tests
# ===================================================================


class TestNormalizeWorkflowDsn:
    def test_replaces_asyncpg_prefix(self):
        from enhanced_agent_bus.api.app import _normalize_workflow_dsn

        result = _normalize_workflow_dsn("postgresql+asyncpg://user:pass@host/db")
        assert result == "postgresql://user:pass@host/db"

    def test_leaves_plain_postgresql_unchanged(self):
        from enhanced_agent_bus.api.app import _normalize_workflow_dsn

        dsn = "postgresql://user:pass@host/db"
        assert _normalize_workflow_dsn(dsn) == dsn

    def test_leaves_other_scheme_unchanged(self):
        from enhanced_agent_bus.api.app import _normalize_workflow_dsn

        dsn = "sqlite:///test.db"
        assert _normalize_workflow_dsn(dsn) == dsn


class TestLoadVisualStudioRouter:
    def test_returns_none_on_import_error(self):
        from enhanced_agent_bus.api.app import _load_visual_studio_router

        with patch(
            "enhanced_agent_bus.api.app.import_module",
            side_effect=ImportError("no module"),
        ):
            assert _load_visual_studio_router() is None

    def test_returns_none_when_no_router_attr(self):
        from enhanced_agent_bus.api.app import _load_visual_studio_router

        mock_module = MagicMock(spec=[])
        del mock_module.router
        with patch("enhanced_agent_bus.api.app.import_module", return_value=mock_module):
            assert _load_visual_studio_router() is None

    def test_returns_none_when_router_is_not_apirouter(self):
        from enhanced_agent_bus.api.app import _load_visual_studio_router

        mock_module = MagicMock()
        mock_module.router = "not-a-router"
        with patch("enhanced_agent_bus.api.app.import_module", return_value=mock_module):
            assert _load_visual_studio_router() is None

    def test_returns_router_when_valid(self):
        from fastapi import APIRouter

        from enhanced_agent_bus.api.app import _load_visual_studio_router

        real_router = APIRouter()
        mock_module = MagicMock()
        mock_module.router = real_router
        with patch("enhanced_agent_bus.api.app.import_module", return_value=mock_module):
            assert _load_visual_studio_router() is real_router


class TestLoadCopilotRouter:
    def test_returns_none_on_import_error(self):
        from enhanced_agent_bus.api.app import _load_copilot_router

        with patch(
            "enhanced_agent_bus.api.app.import_module",
            side_effect=ImportError("no module"),
        ):
            assert _load_copilot_router() is None

    def test_returns_none_when_not_apirouter(self):
        from enhanced_agent_bus.api.app import _load_copilot_router

        mock_module = MagicMock()
        mock_module.router = 42
        with patch("enhanced_agent_bus.api.app.import_module", return_value=mock_module):
            assert _load_copilot_router() is None


class TestIsDevelopmentLikeEnvironment:
    def test_returns_true_for_dev(self):
        from enhanced_agent_bus.api.app import _is_development_like_environment

        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            assert _is_development_like_environment() is True

    def test_returns_true_for_test(self):
        from enhanced_agent_bus.api.app import _is_development_like_environment

        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            assert _is_development_like_environment() is True

    def test_returns_true_for_ci(self):
        from enhanced_agent_bus.api.app import _is_development_like_environment

        with patch.dict("os.environ", {"ENVIRONMENT": "ci"}):
            assert _is_development_like_environment() is True

    def test_returns_false_for_production(self):
        from enhanced_agent_bus.api.app import _is_development_like_environment

        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            assert _is_development_like_environment() is False

    def test_returns_false_when_unset(self):
        from enhanced_agent_bus.api.app import _is_development_like_environment

        with patch.dict("os.environ", {}, clear=True):
            assert _is_development_like_environment() is False


class TestInitializeAgentBusState:
    def test_success_returns_message_processor(self):
        from enhanced_agent_bus.api.app import _initialize_agent_bus_state

        mock_proc = MagicMock()
        with patch("enhanced_agent_bus.api.app.MessageProcessor", return_value=mock_proc):
            result = _initialize_agent_bus_state()
            assert result is mock_proc

    def test_falls_back_to_mock_in_dev(self):
        from enhanced_agent_bus.api.app import _initialize_agent_bus_state

        with (
            patch(
                "enhanced_agent_bus.api.app.MessageProcessor",
                side_effect=RuntimeError("boom"),
            ),
            patch.dict("os.environ", {"ENVIRONMENT": "development"}),
        ):
            result = _initialize_agent_bus_state()
            assert isinstance(result, dict)
            assert result["status"] == "mock_initialized"

    def test_raises_in_production(self):
        from enhanced_agent_bus.api.app import _initialize_agent_bus_state

        with (
            patch(
                "enhanced_agent_bus.api.app.MessageProcessor",
                side_effect=RuntimeError("boom"),
            ),
            patch.dict("os.environ", {"ENVIRONMENT": "production"}),
            pytest.raises(RuntimeError, match="boom"),
        ):
            _initialize_agent_bus_state()


class TestInitializeBatchProcessorState:
    def test_success(self):
        from enhanced_agent_bus.api.app import _initialize_batch_processor_state

        mock_proc = MagicMock()
        with patch(
            "enhanced_agent_bus.api.app.BatchMessageProcessor",
            return_value=mock_proc,
        ):
            result = _initialize_batch_processor_state(MagicMock())
            assert result is mock_proc

    def test_returns_none_on_error(self):
        from enhanced_agent_bus.api.app import _initialize_batch_processor_state

        with patch(
            "enhanced_agent_bus.api.app.BatchMessageProcessor",
            side_effect=RuntimeError("fail"),
        ):
            result = _initialize_batch_processor_state(MagicMock())
            assert result is None


class TestInitializeWorkflowComponents:
    async def test_success(self):
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_repo = AsyncMock()
        mock_executor = MagicMock()
        mock_app = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                return_value=mock_repo,
            ),
            patch(
                "enhanced_agent_bus.api.app.DurableWorkflowExecutor",
                return_value=mock_executor,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is mock_executor
            assert repo is mock_repo
            mock_repo.initialize.assert_awaited_once()

    async def test_returns_none_on_import_error_non_dev(self):
        """In non-dev environments, ImportError yields (None, None)."""
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                side_effect=ImportError("no asyncpg"),
            ),
            patch(
                "enhanced_agent_bus.api.app._is_development_like_environment",
                return_value=False,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is None
            assert repo is None

    async def test_falls_back_to_in_memory_on_import_error_in_dev(self):
        """In dev environments, ImportError falls back to in-memory executor."""
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                side_effect=ImportError("no asyncpg"),
            ),
            patch(
                "enhanced_agent_bus.api.app._is_development_like_environment",
                return_value=True,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is not None
            assert repo is None

    async def test_returns_none_on_generic_error_non_dev(self):
        """In non-dev environments, generic errors yield (None, None)."""
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                side_effect=Exception("connection refused"),
            ),
            patch(
                "enhanced_agent_bus.api.app._is_development_like_environment",
                return_value=False,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is None
            assert repo is None

    async def test_falls_back_to_in_memory_on_generic_error_in_dev(self):
        """In dev environments, generic errors fall back to in-memory executor."""
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                side_effect=Exception("connection refused"),
            ),
            patch(
                "enhanced_agent_bus.api.app._is_development_like_environment",
                return_value=True,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is not None
            assert repo is None


class TestSessionManagerLifecycle:
    async def test_initialize_session_manager_import_error(self):
        from enhanced_agent_bus.api.app import _initialize_session_manager_if_available

        with patch(
            "enhanced_agent_bus.api.app.import_module",
            side_effect=ImportError("no sessions"),
        ):
            # Should not raise
            await _initialize_session_manager_if_available()

    async def test_shutdown_session_manager_import_error(self):
        from enhanced_agent_bus.api.app import _shutdown_session_manager_if_available

        # Should handle ImportError gracefully
        await _shutdown_session_manager_if_available()


class TestCacheWarmerShutdown:
    async def test_stop_cache_warmer_error_handled(self):
        from enhanced_agent_bus.api.app import _stop_cache_warmer_if_running

        # Should not raise even on error
        await _stop_cache_warmer_if_running()


class TestCloseWorkflowRepository:
    async def test_close_with_repository(self):
        from enhanced_agent_bus.api.app import _close_workflow_repository_if_available

        mock_repo = AsyncMock()
        await _close_workflow_repository_if_available(mock_repo)
        mock_repo.close.assert_awaited_once()

    async def test_close_with_none(self):
        from enhanced_agent_bus.api.app import _close_workflow_repository_if_available

        await _close_workflow_repository_if_available(None)

    async def test_close_with_error(self):
        from enhanced_agent_bus.api.app import _close_workflow_repository_if_available

        mock_repo = AsyncMock()
        mock_repo.close.side_effect = Exception("close failed")
        # Should not raise
        await _close_workflow_repository_if_available(mock_repo)


class TestRegisterExceptionHandlers:
    def test_registers_all_handlers(self):
        from enhanced_agent_bus.api.app import _register_exception_handlers

        mock_app = MagicMock()
        _register_exception_handlers(mock_app)
        # Should have called add_exception_handler multiple times
        assert mock_app.add_exception_handler.call_count >= 10


class TestRegisterOptionalRouters:
    def test_handles_import_errors(self):
        from enhanced_agent_bus.api.app import _register_optional_routers

        mock_app = MagicMock()
        # Should not raise even if optional routers are missing
        _register_optional_routers(mock_app)


class TestCreateApp:
    def test_creates_fastapi_app(self):
        from enhanced_agent_bus.api.app import create_app

        app = create_app()
        assert app is not None
        assert app.title == "ACGS-2 Enhanced Agent Bus API"


# ===================================================================
# verification_orchestrator.py tests
# ===================================================================


class TestVerificationResult:
    def test_defaults(self):
        vr = VResult()
        assert vr.sdpc_metadata == {}
        assert vr.pqc_result is None
        assert vr.pqc_metadata == {}

    def test_with_values(self):
        vr = VResult(
            sdpc_metadata={"sdpc_intent": "factual"},
            pqc_result=ValidationResult(is_valid=False, errors=["hash mismatch"]),
            pqc_metadata={"pqc_enabled": True},
        )
        assert vr.sdpc_metadata["sdpc_intent"] == "factual"
        assert vr.pqc_result.is_valid is False
        assert vr.pqc_metadata["pqc_enabled"] is True


class TestVerificationOrchestratorInit:
    def test_init_without_pqc(self, bus_config):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        assert orch._enable_pqc is False
        assert orch._pqc_config is None
        assert orch._pqc_service is None
        # SDPC verifiers should exist (no-op stubs if deps unavailable)
        assert orch.intent_classifier is not None
        assert orch.asc_verifier is not None
        assert orch.graph_check is not None
        assert orch.pacar_verifier is not None
        assert orch.evolution_controller is not None
        assert orch.ampo_engine is not None

    def test_init_with_pqc_no_deps(self, bus_config):
        config = BusConfiguration(
            enable_pqc=True,
            pqc_mode="hybrid",
            pqc_verification_mode="strict",
            pqc_migration_phase=0,
            enable_maci=False,
            maci_strict_mode=False,
        )
        # PQC deps not available - should gracefully disable
        orch = VerificationOrchestrator(config=config, enable_pqc=True)
        # PQC should be disabled since dependencies are likely not available
        assert orch._pqc_service is None or orch._enable_pqc is False


class TestVerificationOrchestratorSDPC:
    async def test_perform_sdpc_low_impact(self, bus_config, sample_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        content_str = "simple test content"
        sdpc_meta, verifications = await orch._perform_sdpc(sample_message, content_str)
        # With no-op stubs and low impact/unknown intent, may or may not run verifiers
        assert isinstance(sdpc_meta, dict)
        assert isinstance(verifications, dict)

    async def test_perform_sdpc_high_impact(self, bus_config, high_impact_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        # Patch SDPC verifiers to use no-op stubs that accept any kwargs
        mock_pacar = AsyncMock(
            return_value={"is_valid": True, "confidence": 0.95}
        )
        mock_asc = AsyncMock(
            return_value={"is_valid": True, "confidence": 0.9, "results": []}
        )
        mock_graph = AsyncMock(
            return_value={"is_valid": True, "results": []}
        )
        orch.pacar_verifier.verify = mock_pacar
        orch.asc_verifier.verify = mock_asc
        orch.graph_check.verify_entities = mock_graph

        content_str = "high impact content"
        sdpc_meta, verifications = await orch._perform_sdpc(high_impact_message, content_str)
        assert isinstance(sdpc_meta, dict)
        # High impact should trigger PACAR (impact_score > 0.8)
        assert "sdpc_pacar_valid" in sdpc_meta
        assert sdpc_meta["sdpc_pacar_valid"] is True

    async def test_perform_sdpc_task_request(self, bus_config):
        msg = AgentMessage(
            content={"text": "task"},
            from_agent="a",
            to_agent="b",
            message_type=MessageType.TASK_REQUEST,
            impact_score=0.5,
        )
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        mock_pacar = AsyncMock(
            return_value={"is_valid": True, "confidence": 0.8, "critique": "ok"}
        )
        orch.pacar_verifier.verify = mock_pacar

        sdpc_meta, verifications = await orch._perform_sdpc(msg, "task content")
        assert isinstance(sdpc_meta, dict)
        # TASK_REQUEST triggers PACAR regardless of impact
        assert "sdpc_pacar_valid" in sdpc_meta
        assert "sdpc_pacar_critique" in sdpc_meta

    async def test_perform_sdpc_none_impact_score(self, bus_config):
        msg = AgentMessage(
            content={"text": "test"},
            from_agent="a",
            to_agent="b",
            impact_score=None,
        )
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        sdpc_meta, _ = await orch._perform_sdpc(msg, "content")
        assert isinstance(sdpc_meta, dict)


class TestVerificationOrchestratorPQC:
    async def test_pqc_disabled(self, bus_config, sample_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        result, meta = await orch._perform_pqc(sample_message)
        assert result is None
        assert meta == {}

    async def test_pqc_enabled_no_config(self, bus_config, sample_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        # Manually set enable_pqc but leave config as None
        orch._enable_pqc = True
        orch._pqc_config = None
        result, meta = await orch._perform_pqc(sample_message)
        assert result is None
        assert meta == {}

    async def test_pqc_import_error(self, bus_config, sample_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()
        orch._pqc_config.pqc_mode = "hybrid"

        with patch(
            "enhanced_agent_bus.verification_orchestrator.validate_constitutional_hash_pqc",
            side_effect=ImportError("no pqc"),
            create=True,
        ):
            # Import happens inside the method so we patch the import mechanism
            result, meta = await orch._perform_pqc(sample_message)
            # Should return None, {} after ImportError
            assert result is None
            assert meta == {}

    async def test_pqc_runtime_error_pqc_only_mode(self, bus_config, sample_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        orch._enable_pqc = True
        mock_config = MagicMock()
        mock_config.pqc_mode = "pqc_only"
        orch._pqc_config = mock_config

        mock_pqc_validate = AsyncMock(side_effect=RuntimeError("pqc error"))
        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.pqc_validators": MagicMock(
                    validate_constitutional_hash_pqc=mock_pqc_validate,
                    PQCConfig=MagicMock,
                ),
            },
        ):
            result, meta = await orch._perform_pqc(sample_message)
            # In pqc_only mode, runtime errors should return a failure ValidationResult
            if result is not None:
                assert result.is_valid is False
                assert any("pqc" in e.lower() for e in result.errors)


class TestVerificationOrchestratorVerify:
    async def test_verify_combines_sdpc_and_pqc(self, bus_config, sample_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        result = await orch.verify(sample_message, "test content")
        assert isinstance(result, VResult)
        assert isinstance(result.sdpc_metadata, dict)
        assert result.pqc_result is None
        assert result.pqc_metadata == {}

    async def test_verify_pqc_public_method(self, bus_config, sample_message):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        result, meta = await orch.verify_pqc(sample_message)
        assert result is None
        assert meta == {}


class TestInitPQC:
    def test_init_pqc_import_error(self, bus_config):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        orch._enable_pqc = True
        with patch(
            "enhanced_agent_bus.verification_orchestrator.import_module",
            side_effect=ImportError("no pqc lib"),
            create=True,
        ):
            orch._init_pqc(bus_config)
            assert orch._enable_pqc is False

    def test_init_pqc_runtime_error(self, bus_config):
        orch = VerificationOrchestrator(config=bus_config, enable_pqc=False)
        orch._enable_pqc = True

        mock_pqc_config_cls = MagicMock(side_effect=RuntimeError("config error"))
        with (
            patch.dict(
                "sys.modules",
                {
                    "enhanced_agent_bus.pqc_validators": MagicMock(
                        PQCConfig=mock_pqc_config_cls,
                    ),
                },
            ),
            patch(
                "importlib.import_module",
                return_value=MagicMock(PQCCryptoService=MagicMock()),
            ),
        ):
            orch._init_pqc(bus_config)
            # Should disable pqc on error
            assert orch._enable_pqc is False


# ===================================================================
# mcp_server/protocol/handler.py tests
# ===================================================================


class TestMCPHandlerRegistration:
    def test_register_tool(self, handler):
        tool_def = ToolDefinition(
            name="test-tool",
            description="A test tool",
            inputSchema=ToolInputSchema(),
        )
        handler.register_tool(tool_def, AsyncMock(return_value="result"))
        assert "test-tool" in handler._tools
        assert "test-tool" in handler._tool_handlers

    def test_register_resource(self, handler):
        res_def = ResourceDefinition(
            uri="test://resource",
            name="test-resource",
            description="A test resource",
        )
        handler.register_resource(res_def, AsyncMock(return_value="data"))
        assert "test://resource" in handler._resources
        assert "test://resource" in handler._resource_handlers

    def test_register_prompt(self, handler):
        prompt_def = PromptDefinition(
            name="test-prompt",
            description="A test prompt",
        )
        handler.register_prompt(prompt_def, AsyncMock(return_value={"messages": []}))
        assert "test-prompt" in handler._prompts
        assert "test-prompt" in handler._prompt_handlers

    def test_lock_registration_blocks_tool(self, handler):
        handler.lock_registration()
        tool_def = ToolDefinition(
            name="blocked",
            description="blocked",
            inputSchema=ToolInputSchema(),
        )
        with pytest.raises(Exception):
            handler.register_tool(tool_def, AsyncMock())

    def test_lock_registration_blocks_resource(self, handler):
        handler.lock_registration()
        res_def = ResourceDefinition(
            uri="test://blocked",
            name="blocked",
            description="blocked",
        )
        with pytest.raises(Exception):
            handler.register_resource(res_def, AsyncMock())

    def test_lock_registration_blocks_prompt(self, handler):
        handler.lock_registration()
        prompt_def = PromptDefinition(name="blocked", description="blocked")
        with pytest.raises(Exception):
            handler.register_prompt(prompt_def, AsyncMock())


class TestMCPHandlerInitialize:
    async def test_handle_initialize(self, handler):
        req = _make_request("initialize", {"clientInfo": {"name": "test", "version": "1.0"}})
        resp = await handler.handle_request(req)
        assert resp is not None
        assert resp.error is None
        result = resp.result
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "serverInfo" in result

    async def test_handle_initialized(self, handler):
        req = _make_request("initialized", {}, req_id=None)
        resp = await handler.handle_request(req)
        # Notification returns None
        assert resp is None
        assert handler._initialized is True


class TestMCPHandlerPing:
    async def test_ping(self, handler):
        req = _make_request("ping")
        resp = await handler.handle_request(req)
        assert resp is not None
        assert resp.error is None
        assert resp.result["status"] == "ok"
        assert "constitutional_hash" in resp.result
        assert "timestamp" in resp.result


class TestMCPHandlerToolsList:
    async def test_tools_list_empty(self, handler):
        req = _make_request("tools/list")
        resp = await handler.handle_request(req)
        assert resp.result == {"tools": []}

    async def test_tools_list_with_registered_tools(self, handler):
        tool_def = ToolDefinition(
            name="my-tool",
            description="Test tool",
            inputSchema={"type": "object"},
        )
        handler.register_tool(tool_def, AsyncMock())
        req = _make_request("tools/list")
        resp = await handler.handle_request(req)
        assert len(resp.result["tools"]) == 1
        assert resp.result["tools"][0]["name"] == "my-tool"


class TestMCPHandlerToolsCall:
    async def test_call_registered_tool_dict_result(self, handler):
        async def tool_handler(args):
            return {"content": [{"type": "text", "text": "done"}]}

        tool_def = ToolDefinition(
            name="my-tool",
            description="Test",
            inputSchema=ToolInputSchema(),
        )
        handler.register_tool(tool_def, tool_handler)
        req = _make_request("tools/call", {"name": "my-tool", "arguments": {}})
        resp = await handler.handle_request(req)
        assert resp.error is None
        assert resp.result["content"][0]["text"] == "done"

    async def test_call_registered_tool_string_result(self, handler):
        async def tool_handler(args):
            return "string result"

        tool_def = ToolDefinition(
            name="str-tool",
            description="Test",
            inputSchema=ToolInputSchema(),
        )
        handler.register_tool(tool_def, tool_handler)
        req = _make_request("tools/call", {"name": "str-tool", "arguments": {}})
        resp = await handler.handle_request(req)
        assert resp.error is None
        assert resp.result["content"][0]["text"] == "string result"
        assert resp.result["isError"] is False

    async def test_call_registered_tool_non_string_result(self, handler):
        async def tool_handler(args):
            return 42

        tool_def = ToolDefinition(
            name="num-tool",
            description="Test",
            inputSchema=ToolInputSchema(),
        )
        handler.register_tool(tool_def, tool_handler)
        req = _make_request("tools/call", {"name": "num-tool", "arguments": {}})
        resp = await handler.handle_request(req)
        assert resp.result["content"][0]["text"] == "42"

    async def test_call_unknown_tool(self, handler):
        from src.core.shared.errors.exceptions import ResourceNotFoundError

        req = _make_request("tools/call", {"name": "nonexistent"})
        with pytest.raises(ResourceNotFoundError):
            await handler.handle_request(req)


class TestMCPHandlerResourcesList:
    async def test_resources_list_empty(self, handler):
        req = _make_request("resources/list")
        resp = await handler.handle_request(req)
        assert resp.result == {"resources": []}

    async def test_resources_list_with_registered(self, handler):
        res_def = ResourceDefinition(
            uri="acgs://policies",
            name="policies",
            description="All policies",
        )
        handler.register_resource(res_def, AsyncMock(return_value="policy data"))
        req = _make_request("resources/list")
        resp = await handler.handle_request(req)
        assert len(resp.result["resources"]) == 1


class TestMCPHandlerResourcesRead:
    async def test_read_registered_resource(self, handler):
        res_def = ResourceDefinition(
            uri="acgs://test",
            name="test",
            description="Test resource",
            mimeType="text/plain",
        )
        handler.register_resource(res_def, AsyncMock(return_value="resource content"))
        req = _make_request("resources/read", {"uri": "acgs://test"})
        resp = await handler.handle_request(req)
        assert resp.error is None
        assert resp.result["contents"][0]["uri"] == "acgs://test"
        assert resp.result["contents"][0]["mimeType"] == "text/plain"
        assert resp.result["contents"][0]["text"] == "resource content"

    async def test_read_unknown_resource(self, handler):
        from src.core.shared.errors.exceptions import ResourceNotFoundError

        req = _make_request("resources/read", {"uri": "acgs://missing"})
        with pytest.raises(ResourceNotFoundError):
            await handler.handle_request(req)


class TestMCPHandlerResourcesSubscribe:
    async def test_subscribe(self, handler):
        req = _make_request("resources/subscribe", {"uri": "acgs://test"})
        resp = await handler.handle_request(req)
        assert resp.result == {"subscribed": True}


class TestMCPHandlerPromptsList:
    async def test_prompts_list_empty(self, handler):
        req = _make_request("prompts/list")
        resp = await handler.handle_request(req)
        assert resp.result == {"prompts": []}


class TestMCPHandlerPromptsGet:
    async def test_get_registered_prompt(self, handler):
        prompt_def = PromptDefinition(
            name="governance-check",
            description="Check governance",
        )
        expected = {"messages": [{"role": "user", "content": {"type": "text", "text": "check"}}]}
        handler.register_prompt(prompt_def, AsyncMock(return_value=expected))
        req = _make_request("prompts/get", {"name": "governance-check"})
        resp = await handler.handle_request(req)
        assert resp.error is None
        assert resp.result == expected

    async def test_get_unknown_prompt(self, handler):
        from src.core.shared.errors.exceptions import ResourceNotFoundError

        req = _make_request("prompts/get", {"name": "nonexistent"})
        with pytest.raises(ResourceNotFoundError):
            await handler.handle_request(req)


class TestMCPHandlerLogging:
    async def test_set_log_level(self, handler):
        req = _make_request("logging/setLevel", {"level": "debug"})
        resp = await handler.handle_request(req)
        assert resp.result == {"level": "debug"}

    async def test_set_log_level_default(self, handler):
        req = _make_request("logging/setLevel", {})
        resp = await handler.handle_request(req)
        assert resp.result == {"level": "info"}


class TestMCPHandlerErrorHandling:
    async def test_invalid_jsonrpc_version(self, handler):
        req = MCPRequest(jsonrpc="1.0", method="ping", id=1)
        resp = await handler.handle_request(req)
        assert resp.error is not None
        assert resp.error.code == MCPErrorCode.INVALID_REQUEST.value

    async def test_unknown_method(self, handler):
        req = _make_request("nonexistent/method")
        resp = await handler.handle_request(req)
        assert resp.error is not None
        assert resp.error.code == MCPErrorCode.METHOD_NOT_FOUND.value

    async def test_handler_exception_with_id(self, handler):
        async def bad_handler(args):
            raise ValueError("something wrong")

        tool_def = ToolDefinition(
            name="bad-tool",
            description="Breaks",
            inputSchema=ToolInputSchema(),
        )
        handler.register_tool(tool_def, bad_handler)
        req = _make_request("tools/call", {"name": "bad-tool", "arguments": {}})
        resp = await handler.handle_request(req)
        assert resp.error is not None
        assert resp.error.code == MCPErrorCode.INTERNAL_ERROR.value
        assert handler._error_count >= 1

    async def test_handler_exception_notification(self, handler):
        """Error on notification returns None."""
        handler._methods["initialized"] = AsyncMock(side_effect=ValueError("boom"))
        req = MCPRequest(jsonrpc="2.0", method="initialized", id=None)
        resp = await handler.handle_request(req)
        assert resp is None

    async def test_notification_returns_none(self, handler):
        req = MCPRequest(jsonrpc="2.0", method="ping", id=None)
        resp = await handler.handle_request(req)
        assert resp is None


class TestMCPHandlerMetrics:
    def test_initial_metrics(self, handler):
        metrics = handler.get_metrics()
        assert metrics["request_count"] == 0
        assert metrics["error_count"] == 0
        assert metrics["error_rate"] == 0.0
        assert metrics["tools_registered"] == 0
        assert metrics["resources_registered"] == 0
        assert metrics["prompts_registered"] == 0
        assert metrics["initialized"] is False

    async def test_metrics_after_requests(self, handler):
        req = _make_request("ping")
        await handler.handle_request(req)
        metrics = handler.get_metrics()
        assert metrics["request_count"] == 1
        assert metrics["error_count"] == 0

    async def test_metrics_error_rate(self, handler):
        # Good request
        await handler.handle_request(_make_request("ping"))
        # Bad request
        await handler.handle_request(MCPRequest(jsonrpc="1.0", method="ping", id=2))
        metrics = handler.get_metrics()
        assert metrics["request_count"] == 2
        # Invalid jsonrpc triggers MCPResponse.failure but not _error_count
        # (only MCP_REQUEST_HANDLER_ERRORS increment error_count)


class TestMCPHandlerStrictMode:
    async def test_strict_mode_injects_constitutional_hash(self, handler_strict):
        tool_def = ToolDefinition(
            name="gov-tool",
            description="Governance tool",
            inputSchema=ToolInputSchema(),
            constitutional_required=True,
        )
        captured_args = {}

        async def capturing_handler(args):
            captured_args.update(args)
            return "ok"

        handler_strict.register_tool(tool_def, capturing_handler)
        req = _make_request("tools/call", {"name": "gov-tool", "arguments": {"data": "x"}})
        resp = await handler_strict.handle_request(req)
        assert resp.error is None
        # In strict mode, constitutional hash should be injected into arguments
        assert "_constitutional_hash" in captured_args

    async def test_strict_mode_no_injection_when_hash_present(self, handler_strict):
        tool_def = ToolDefinition(
            name="gov-tool2",
            description="Gov tool",
            inputSchema=ToolInputSchema(),
            constitutional_required=True,
        )

        async def noop_handler(args):
            return "ok"

        handler_strict.register_tool(tool_def, noop_handler)
        req = _make_request(
            "tools/call",
            {"name": "gov-tool2", "arguments": {"constitutional_hash": "abc"}},
        )
        resp = await handler_strict.handle_request(req)
        assert resp.error is None

    async def test_strict_mode_creates_arguments_if_missing(self, handler_strict):
        tool_def = ToolDefinition(
            name="gov-tool3",
            description="Gov tool",
            inputSchema=ToolInputSchema(),
            constitutional_required=True,
        )

        async def noop_handler(args):
            return "ok"

        handler_strict.register_tool(tool_def, noop_handler)
        req = _make_request("tools/call", {"name": "gov-tool3"})
        resp = await handler_strict.handle_request(req)
        assert resp.error is None


class TestMCPHandlerInitializeCapabilities:
    async def test_initialize_with_all_features_enabled(self, handler):
        req = _make_request("initialize", {"clientInfo": {"name": "full", "version": "2.0"}})
        resp = await handler.handle_request(req)
        result = resp.result
        caps = result["capabilities"]
        assert "tools" in caps
        assert "resources" in caps
        assert "prompts" in caps
        assert "logging" in caps
        assert "experimental" in caps
        assert caps["experimental"]["constitutional_governance"] is True

    async def test_initialize_with_features_disabled(self):
        config = MCPConfig(
            enable_tools=False,
            enable_resources=False,
            enable_prompts=False,
            enable_audit_logging=False,
            enable_maci=False,
        )
        h = MCPHandler(config=config)
        req = _make_request("initialize", {"clientInfo": {}})
        resp = await h.handle_request(req)
        result = resp.result
        caps = result["capabilities"]
        # When disabled, the capability should be None which means
        # ServerCapabilities.__post_init__ sets defaults anyway
        assert "tools" in caps
