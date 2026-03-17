# Constitutional Hash: cdd01ef066bc6cf2
"""
Additional coverage tests for src/core/enhanced_agent_bus/sandbox.py.

Targets the WuyingSandbox class and all error/edge-code branches that the
existing test_sandbox.py does not exercise, bringing total coverage to ≥90%.
"""

import asyncio
import logging
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

# Mirror the import pattern from the existing test_sandbox.py so that
# coverage is collected under the same module name ("enhanced_agent_bus.sandbox").
try:
    from enhanced_agent_bus.sandbox import (
        _SANDBOX_OPERATION_ERRORS,
        FirecrackerSandbox,
        SandboxProvider,
        WasmSandbox,
        WuyingSandbox,
        get_sandbox_provider,
    )
except ImportError:
    from packages.enhanced_agent_bus.sandbox import (  # type: ignore[no-redef]
        _SANDBOX_OPERATION_ERRORS,
        FirecrackerSandbox,
        SandboxProvider,
        WasmSandbox,
        WuyingSandbox,
        get_sandbox_provider,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeConfig:
    """Minimal stand-in for the real settings object."""

    wuying_access_key_id = "test-key-id"
    wuying_access_key_secret = "test-key-secret"  # pragma: allowlist secret  # noqa: S105
    wuying_region_id = "cn-hangzhou"


def _make_response(
    *,
    exit_code: int = 0,
    stdout: str = "ok",
    stderr: str = "",
    session_id: str = "sess-abc",
) -> MagicMock:
    r = MagicMock()
    r.exit_code = exit_code
    r.stdout = stdout
    r.stderr = stderr
    r.session_id = session_id
    return r


# ---------------------------------------------------------------------------
# _SANDBOX_OPERATION_ERRORS tuple
# ---------------------------------------------------------------------------


class TestSandboxOperationErrors:
    """The module-level error tuple is used in multiple except clauses."""

    def test_tuple_contains_expected_types(self):
        assert RuntimeError in _SANDBOX_OPERATION_ERRORS
        assert ValueError in _SANDBOX_OPERATION_ERRORS
        assert OSError in _SANDBOX_OPERATION_ERRORS
        assert TimeoutError in _SANDBOX_OPERATION_ERRORS
        assert ConnectionError in _SANDBOX_OPERATION_ERRORS

    def test_is_tuple(self):
        assert isinstance(_SANDBOX_OPERATION_ERRORS, tuple)


# ---------------------------------------------------------------------------
# get_sandbox_provider — all branches
# ---------------------------------------------------------------------------


class TestGetSandboxProviderWuying:
    def test_get_wuying_provider(self):
        provider = get_sandbox_provider("wuying")
        assert isinstance(provider, WuyingSandbox)

    def test_get_wuying_provider_case_insensitive(self):
        for name in ["Wuying", "WUYING", "WuYing"]:
            provider = get_sandbox_provider(name)
            assert isinstance(provider, WuyingSandbox)

    def test_get_firecracker_provider(self):
        provider = get_sandbox_provider("firecracker")
        assert isinstance(provider, FirecrackerSandbox)

    def test_get_wasm_provider(self):
        provider = get_sandbox_provider("wasm")
        assert isinstance(provider, WasmSandbox)

    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown sandbox provider"):
            get_sandbox_provider("docker")

    def test_default_is_firecracker(self):
        provider = get_sandbox_provider()
        assert isinstance(provider, FirecrackerSandbox)


# ---------------------------------------------------------------------------
# WuyingSandbox — construction
# ---------------------------------------------------------------------------


class TestWuyingSandboxInit:
    def test_init_with_explicit_config(self):
        cfg = _FakeConfig()
        sb = WuyingSandbox(config=cfg)
        assert sb.config is cfg
        assert sb._client is None
        assert sb._initialized is False

    def test_init_without_config_uses_settings(self):
        """When no config supplied, it reads from the real settings singleton."""
        sb = WuyingSandbox()
        assert sb.config is not None
        assert sb._initialized is False


# ---------------------------------------------------------------------------
# WuyingSandbox._ensure_initialized — success path
# ---------------------------------------------------------------------------


class TestWuyingSandboxEnsureInitialized:
    async def test_initialize_success(self):
        cfg = _FakeConfig()
        sb = WuyingSandbox(config=cfg)

        fake_agentbay = types.ModuleType("agentbay")
        fake_models = types.ModuleType("agentbay.models")

        fake_config_cls = MagicMock(return_value=MagicMock())
        fake_models.Config = fake_config_cls

        fake_client_instance = MagicMock()
        fake_agentbay.Client = MagicMock(return_value=fake_client_instance)
        fake_agentbay.models = fake_models

        with patch.dict(sys.modules, {"agentbay": fake_agentbay, "agentbay.models": fake_models}):
            await sb._ensure_initialized()

        assert sb._initialized is True
        assert sb._client is fake_client_instance

    async def test_initialize_called_only_once(self):
        cfg = _FakeConfig()
        sb = WuyingSandbox(config=cfg)

        fake_agentbay = types.ModuleType("agentbay")
        fake_models = types.ModuleType("agentbay.models")
        fake_models.Config = MagicMock(return_value=MagicMock())
        fake_agentbay.Client = MagicMock(return_value=MagicMock())
        fake_agentbay.models = fake_models

        with patch.dict(sys.modules, {"agentbay": fake_agentbay, "agentbay.models": fake_models}):
            await sb._ensure_initialized()
            call_count_after_first = fake_agentbay.Client.call_count
            await sb._ensure_initialized()  # second call should be a no-op
            assert fake_agentbay.Client.call_count == call_count_after_first

    async def test_initialize_import_error_raises_runtime(self):
        cfg = _FakeConfig()
        sb = WuyingSandbox(config=cfg)

        with patch.dict(sys.modules, {"agentbay": None, "agentbay.models": None}):
            with pytest.raises(RuntimeError, match="Wuying SDK missing"):
                await sb._ensure_initialized()

    async def test_initialize_sdk_error_re_raises(self):
        """An OSError during client construction should propagate unchanged."""
        cfg = _FakeConfig()
        sb = WuyingSandbox(config=cfg)

        fake_agentbay = types.ModuleType("agentbay")
        fake_models = types.ModuleType("agentbay.models")
        fake_models.Config = MagicMock(return_value=MagicMock())
        fake_agentbay.Client = MagicMock(side_effect=OSError("connection refused"))
        fake_agentbay.models = fake_models

        with patch.dict(sys.modules, {"agentbay": fake_agentbay, "agentbay.models": fake_models}):
            with pytest.raises(OSError, match="connection refused"):
                await sb._ensure_initialized()

        assert sb._initialized is False


# ---------------------------------------------------------------------------
# WuyingSandbox.execute_code
# ---------------------------------------------------------------------------


class TestWuyingSandboxExecuteCode:
    def _make_initialized_sandbox(self) -> WuyingSandbox:
        sb = WuyingSandbox(config=_FakeConfig())
        sb._initialized = True
        sb._client = MagicMock()
        return sb

    async def test_execute_code_success_exit_zero(self):
        sb = self._make_initialized_sandbox()
        response = _make_response(exit_code=0, stdout="hello", stderr="", session_id="s1")

        with patch("asyncio.to_thread", new=AsyncMock(return_value=response)):
            result = await sb.execute_code("print('hi')", language="python")

        assert result["status"] == "success"
        assert result["output"] == "hello"
        assert result["exit_code"] == 0
        assert result["isolation"] == "Wuying Cloud Sandbox"
        assert result["session_id"] == "s1"
        assert result["duration_ms"] >= 0

    async def test_execute_code_nonzero_exit_is_error_status(self):
        sb = self._make_initialized_sandbox()
        response = _make_response(exit_code=1, stdout="", stderr="boom", session_id="s2")

        with patch("asyncio.to_thread", new=AsyncMock(return_value=response)):
            result = await sb.execute_code("bad code", language="python")

        assert result["status"] == "error"
        assert result["error"] == "boom"

    async def test_execute_code_non_python_language(self):
        sb = self._make_initialized_sandbox()
        response = _make_response(stdout="result")

        with patch("asyncio.to_thread", new=AsyncMock(return_value=response)) as mock_thread:
            await sb.execute_code("ls -la", language="bash")

        # For non-python, the raw code is passed as the command
        call_kwargs = mock_thread.call_args
        assert call_kwargs is not None

    async def test_execute_code_sandbox_operation_error_returns_failure(self):
        sb = self._make_initialized_sandbox()

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=RuntimeError("timeout"))):
            result = await sb.execute_code("code")

        assert result["status"] == "failure"
        assert "timeout" in result["error"]
        assert "duration_ms" in result

    async def test_execute_code_oserror_returns_failure(self):
        sb = self._make_initialized_sandbox()

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=OSError("network"))):
            result = await sb.execute_code("code")

        assert result["status"] == "failure"
        assert "network" in result["error"]

    async def test_execute_code_default_timeout(self):
        sb = self._make_initialized_sandbox()
        response = _make_response()

        with patch("asyncio.to_thread", new=AsyncMock(return_value=response)):
            result = await sb.execute_code("x = 1")

        assert result["status"] == "success"

    async def test_execute_code_calls_ensure_initialized(self):
        sb = WuyingSandbox(config=_FakeConfig())

        async def fake_ensure():
            sb._initialized = True
            sb._client = MagicMock()

        response = _make_response()
        with patch.object(sb, "_ensure_initialized", side_effect=fake_ensure) as mock_init:
            with patch("asyncio.to_thread", new=AsyncMock(return_value=response)):
                await sb.execute_code("code")

        mock_init.assert_called_once()


# ---------------------------------------------------------------------------
# WuyingSandbox.spawn_instance
# ---------------------------------------------------------------------------


class TestWuyingSandboxSpawnInstance:
    def _make_initialized_sandbox(self) -> WuyingSandbox:
        sb = WuyingSandbox(config=_FakeConfig())
        sb._initialized = True
        sb._client = MagicMock()
        return sb

    async def test_spawn_instance_success(self):
        sb = self._make_initialized_sandbox()
        fake_resp = MagicMock()
        fake_resp.session_id = "new-session-42"

        with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_resp)):
            sid = await sb.spawn_instance({"type": "browser"})

        assert sid == "new-session-42"

    async def test_spawn_instance_default_env_type(self):
        sb = self._make_initialized_sandbox()
        fake_resp = MagicMock()
        fake_resp.session_id = "sess-default"

        with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_resp)):
            sid = await sb.spawn_instance({})

        assert sid == "sess-default"

    async def test_spawn_instance_computer_env(self):
        sb = self._make_initialized_sandbox()
        fake_resp = MagicMock()
        fake_resp.session_id = "sess-computer"

        with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_resp)):
            sid = await sb.spawn_instance({"type": "computer"})

        assert sid == "sess-computer"

    async def test_spawn_instance_operation_error_re_raises(self):
        sb = self._make_initialized_sandbox()

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=ConnectionError("refused"))):
            with pytest.raises(ConnectionError, match="refused"):
                await sb.spawn_instance({"type": "python"})

    async def test_spawn_instance_calls_ensure_initialized(self):
        sb = WuyingSandbox(config=_FakeConfig())

        async def fake_ensure():
            sb._initialized = True
            sb._client = MagicMock()

        fake_resp = MagicMock()
        fake_resp.session_id = "s99"

        with patch.object(sb, "_ensure_initialized", side_effect=fake_ensure) as mock_init:
            with patch("asyncio.to_thread", new=AsyncMock(return_value=fake_resp)):
                await sb.spawn_instance({})

        mock_init.assert_called_once()


# ---------------------------------------------------------------------------
# WuyingSandbox.terminate_instance
# ---------------------------------------------------------------------------


class TestWuyingSandboxTerminateInstance:
    def _make_initialized_sandbox(self) -> WuyingSandbox:
        sb = WuyingSandbox(config=_FakeConfig())
        sb._initialized = True
        sb._client = MagicMock()
        return sb

    async def test_terminate_instance_success(self):
        sb = self._make_initialized_sandbox()

        with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
            result = await sb.terminate_instance("sess-42")

        assert result is True

    async def test_terminate_instance_operation_error_returns_false(self):
        sb = self._make_initialized_sandbox()

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=ValueError("bad id"))):
            result = await sb.terminate_instance("bad-sess")

        assert result is False

    async def test_terminate_instance_oserror_returns_false(self):
        sb = self._make_initialized_sandbox()

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=OSError("gone"))):
            result = await sb.terminate_instance("sess-x")

        assert result is False

    async def test_terminate_instance_calls_ensure_initialized(self):
        sb = WuyingSandbox(config=_FakeConfig())

        async def fake_ensure():
            sb._initialized = True
            sb._client = MagicMock()

        with patch.object(sb, "_ensure_initialized", side_effect=fake_ensure) as mock_init:
            with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
                result = await sb.terminate_instance("sess-1")

        mock_init.assert_called_once()
        assert result is True


# ---------------------------------------------------------------------------
# WuyingSandbox is a SandboxProvider
# ---------------------------------------------------------------------------


class TestWuyingSandboxIsProvider:
    def test_isinstance_check(self):
        sb = WuyingSandbox(config=_FakeConfig())
        assert isinstance(sb, SandboxProvider)


# ---------------------------------------------------------------------------
# FirecrackerSandbox — additional branch coverage
# ---------------------------------------------------------------------------


class TestFirecrackerSandboxAdditional:
    async def test_execute_code_logs_start_and_finish(self, caplog):
        sb = FirecrackerSandbox()
        with caplog.at_level(logging.INFO):
            result = await sb.execute_code("x = 1", language="python")
        assert result["status"] == "success"
        # Log messages should mention Firecracker
        messages = " ".join(caplog.messages)
        assert "Firecracker" in messages

    async def test_spawn_instance_returns_string(self):
        sb = FirecrackerSandbox()
        sid = await sb.spawn_instance({"anything": "here"})
        assert isinstance(sid, str)
        assert sid.startswith("vm-accel-")

    async def test_terminate_instance_any_id(self):
        sb = FirecrackerSandbox()
        assert await sb.terminate_instance("") is True
        assert await sb.terminate_instance("vm-accel-999") is True


# ---------------------------------------------------------------------------
# WasmSandbox — additional branch coverage
# ---------------------------------------------------------------------------


class TestWasmSandboxAdditional:
    async def test_execute_code_logs_info(self, caplog):
        sb = WasmSandbox()
        with caplog.at_level(logging.INFO):
            await sb.execute_code("(module)")
        messages = " ".join(caplog.messages)
        assert "WASM" in messages

    async def test_terminate_instance_returns_true_always(self):
        sb = WasmSandbox()
        assert await sb.terminate_instance("wasm-rt-anything") is True
        assert await sb.terminate_instance("") is True

    async def test_spawn_instance_various_workers(self):
        sb = WasmSandbox()
        for worker_name in ["alpha", "beta", "gamma-123"]:
            sid = await sb.spawn_instance({"worker": worker_name})
            assert sid == f"wasm-rt-{worker_name}"
