"""
Tests for the sandbox guardrail system.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from enhanced_agent_bus.guardrails.sandbox import (
    SandboxConfig,
    ToolRunnerSandbox,
)
from enhanced_agent_bus.guardrails.sandbox_providers import (
    DockerSandboxProvider,
    FirecrackerSandboxProvider,
    MockSandboxProvider,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxProviderFactory,
    SandboxProviderType,
    SandboxResourceLimits,
    SandboxSecurityConfig,
    get_default_provider,
)


class TestMockSandboxProvider:
    """Test the mock sandbox provider."""

    async def test_initialization(self):
        """Test mock provider initialization."""
        provider = MockSandboxProvider()
        result = await provider.initialize()

        assert result is True
        assert provider._initialized is True

    async def test_execute_success(self):
        """Test successful execution."""
        provider = MockSandboxProvider()
        await provider.initialize()

        request = SandboxExecutionRequest(
            code="output = data",
            data={"test": "value"},
            context={},
            trace_id="test-trace",
        )

        result = await provider.execute(request)

        assert result.success is True
        assert result.output == {"test": "value"}
        assert result.trace_id == "test-trace"
        assert result.execution_time_ms >= 0

    async def test_health_check(self):
        """Test health check."""
        provider = MockSandboxProvider()
        await provider.initialize()

        health = await provider.health_check()

        assert health["status"] == "healthy"
        assert health["provider"] == "mock"
        assert health["initialized"] is True

    async def test_cleanup(self):
        """Test cleanup (should do nothing for mock)."""
        provider = MockSandboxProvider()
        await provider.initialize()

        # Should not raise
        await provider.cleanup()


class TestDockerSandboxProvider:
    """Test the Docker sandbox provider."""

    async def test_initialization_without_docker(self):
        """Test initialization when Docker is not available."""
        with patch.dict("sys.modules", {"docker": None}):
            provider = DockerSandboxProvider()
            result = await provider.initialize()

            assert result is False
            assert provider._initialized is False

    async def test_initialization_with_mock_docker(self):
        """Test initialization with mocked Docker client."""
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        with patch.dict("sys.modules", {"docker": mock_docker}):
            with patch("docker.from_env", return_value=mock_client):
                provider = DockerSandboxProvider()
                result = await provider.initialize()

                assert result is True
                assert provider._initialized is True

    async def test_execute_without_initialization(self):
        """Test execution without initialization."""
        provider = DockerSandboxProvider()

        request = SandboxExecutionRequest(
            code="output = data",
            data={"test": "value"},
            context={},
        )

        result = await provider.execute(request)

        assert result.success is False
        assert "not initialized" in result.error_message.lower()

    async def test_health_check_without_initialization(self):
        """Test health check without initialization."""
        provider = DockerSandboxProvider()

        health = await provider.health_check()

        assert health["status"] == "unhealthy"
        assert health["initialized"] is False

    async def test_container_config_building(self):
        """Test container configuration building."""
        provider = DockerSandboxProvider()

        request = SandboxExecutionRequest(
            code="output = data",
            data={"test": "value"},
            context={},
            image="python:3.11-slim",
            working_dir="/test",
            resource_limits=SandboxResourceLimits(
                cpu_limit=1.0,
                memory_limit_mb=1024,
                network_disabled=True,
            ),
            security_config=SandboxSecurityConfig(
                run_as_root=False,
                read_only_root=True,
                drop_all_capabilities=True,
                enable_seccomp=True,
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config = provider._build_container_config(request, temp_dir, "test-container")

            assert config["image"] == "python:3.11-slim"
            assert config["name"] == "test-container"
            assert config["working_dir"] == "/test"
            assert config["user"] == "1000:1000"
            assert config["read_only"] is True
            assert config["network_mode"] == "none"
            assert config["mem_limit"] == "1024m"
            assert config["nano_cpus"] == 1_000_000_000
            assert config["cap_drop"] == ["ALL"]
            assert "no-new-privileges:true" in config["security_opt"]

    async def test_script_generation(self):
        """Test execution script generation."""
        provider = DockerSandboxProvider()

        request = SandboxExecutionRequest(
            code="output = data['value'] * 2",
            data={"value": 5},
            context={},
            working_dir="/sandbox",
        )

        # SECURITY Q-C1: _generate_execution_script now requires validated_code param
        validated_code = provider._validate_and_freeze_sandbox_code(request.code)
        script = provider._generate_execution_script(request, validated_code)

        assert "#!/usr/bin/env python3" in script
        assert "import json" in script
        assert "import sys" in script
        assert "/sandbox/input.json" in script
        assert "/sandbox/output.json" in script


class TestFirecrackerSandboxProvider:
    """Test the Firecracker sandbox provider."""

    async def test_initialization_without_binary(self):
        """Test initialization when Firecracker is not available."""
        with patch("os.path.exists", return_value=False):
            provider = FirecrackerSandboxProvider()
            result = await provider.initialize()

            assert result is False

    async def test_initialization_with_binary(self):
        """Test initialization when Firecracker binary exists."""
        with patch("os.path.exists", return_value=True):
            provider = FirecrackerSandboxProvider()
            result = await provider.initialize()

            assert result is True
            assert provider._initialized is True

    async def test_execute_returns_not_implemented(self):
        """Test that execute returns not implemented error."""
        provider = FirecrackerSandboxProvider()
        await provider.initialize()

        request = SandboxExecutionRequest(
            code="output = data",
            data={"test": "value"},
            context={},
            trace_id="test-trace",
        )

        result = await provider.execute(request)

        assert result.success is False
        assert "not yet implemented" in result.error_message.lower()
        assert result.trace_id == "test-trace"


class TestSandboxProviderFactory:
    """Test the sandbox provider factory."""

    def test_create_mock_provider(self):
        """Test creating mock provider."""
        provider = SandboxProviderFactory.create(SandboxProviderType.MOCK)

        assert isinstance(provider, MockSandboxProvider)

    def test_create_docker_provider(self):
        """Test creating Docker provider."""
        provider = SandboxProviderFactory.create(
            SandboxProviderType.DOCKER,
            default_image="custom-image",
            container_prefix="test-prefix",
        )

        assert isinstance(provider, DockerSandboxProvider)
        assert provider.default_image == "custom-image"
        assert provider.container_prefix == "test-prefix"

    def test_create_firecracker_provider(self):
        """Test creating Firecracker provider."""
        provider = SandboxProviderFactory.create(
            SandboxProviderType.FIRECRACKER,
            firecracker_binary="/custom/path",
        )

        assert isinstance(provider, FirecrackerSandboxProvider)
        assert provider.firecracker_binary == "/custom/path"

    def test_create_unknown_provider(self):
        """Test creating unknown provider type."""
        with pytest.raises(ValueError, match="Unknown sandbox provider"):
            SandboxProviderFactory.create("unknown")

    def test_register_custom_provider(self):
        """Test registering custom provider."""

        class CustomProvider(MockSandboxProvider):
            pass

        SandboxProviderFactory.register_provider(SandboxProviderType.MOCK, CustomProvider)

        provider = SandboxProviderFactory.create(SandboxProviderType.MOCK)
        assert isinstance(provider, CustomProvider)

        # Restore original
        SandboxProviderFactory.register_provider(SandboxProviderType.MOCK, MockSandboxProvider)

    def test_get_available_providers(self):
        """Test getting available provider types."""
        providers = SandboxProviderFactory.get_available_providers()

        assert SandboxProviderType.MOCK in providers
        assert SandboxProviderType.DOCKER in providers
        assert SandboxProviderType.FIRECRACKER in providers


class TestSandboxExecutionRequest:
    """Test sandbox execution request."""

    def test_default_values(self):
        """Test default request values."""
        request = SandboxExecutionRequest(
            code="output = data",
            data={"test": "value"},
            context={},
        )

        assert request.image == "python:3.11-slim"
        assert request.working_dir == "/sandbox"
        assert request.trace_id == ""
        assert isinstance(request.resource_limits, SandboxResourceLimits)
        assert isinstance(request.security_config, SandboxSecurityConfig)

    def test_compute_hash(self):
        """Test hash computation."""
        request1 = SandboxExecutionRequest(
            code="output = data",
            data={"test": "value"},
            context={},
        )

        request2 = SandboxExecutionRequest(
            code="output = data",
            data={"test": "value"},
            context={},
        )

        request3 = SandboxExecutionRequest(
            code="different code",
            data={"test": "value"},
            context={},
        )

        assert request1.compute_hash() == request2.compute_hash()
        assert request1.compute_hash() != request3.compute_hash()
        assert len(request1.compute_hash()) == 16


class TestSandboxResourceLimits:
    """Test sandbox resource limits."""

    def test_default_limits(self):
        """Test default resource limits."""
        limits = SandboxResourceLimits()

        assert limits.cpu_limit == 0.5
        assert limits.memory_limit_mb == 512
        assert limits.timeout_seconds == 10.0
        assert limits.network_disabled is True
        assert limits.max_output_size_mb == 10

    def test_custom_limits(self):
        """Test custom resource limits."""
        limits = SandboxResourceLimits(
            cpu_limit=2.0,
            memory_limit_mb=2048,
            timeout_seconds=30.0,
            network_disabled=False,
            max_output_size_mb=50,
        )

        assert limits.cpu_limit == 2.0
        assert limits.memory_limit_mb == 2048
        assert limits.timeout_seconds == 30.0
        assert limits.network_disabled is False
        assert limits.max_output_size_mb == 50


class TestSandboxSecurityConfig:
    """Test sandbox security configuration."""

    def test_default_security(self):
        """Test default security configuration."""
        config = SandboxSecurityConfig()

        assert config.run_as_root is False
        assert config.read_only_root is True
        assert config.drop_all_capabilities is True
        assert config.enable_seccomp is True
        assert config.seccomp_profile is None
        assert config.no_new_privileges is True
        assert config.security_opt == []

    def test_custom_security(self):
        """Test custom security configuration."""
        config = SandboxSecurityConfig(
            run_as_root=True,
            read_only_root=False,
            drop_all_capabilities=False,
            enable_seccomp=False,
            seccomp_profile="/custom/profile.json",
            no_new_privileges=False,
            security_opt=["label:disable"],
        )

        assert config.run_as_root is True
        assert config.read_only_root is False
        assert config.drop_all_capabilities is False
        assert config.enable_seccomp is False
        assert config.seccomp_profile == "/custom/profile.json"
        assert config.no_new_privileges is False
        assert config.security_opt == ["label:disable"]


class TestSandboxExecutionResult:
    """Test sandbox execution result."""

    def test_success_result(self):
        """Test successful execution result."""
        result = SandboxExecutionResult(
            success=True,
            output={"result": "success"},
            exit_code=0,
            stdout="output",
            stderr="",
            execution_time_ms=100.0,
            container_id="abc123",
            trace_id="test-trace",
        )

        assert result.success is True
        assert result.output == {"result": "success"}
        assert result.exit_code == 0

        result_dict = result.to_dict()
        assert result_dict["success"] is True
        assert result_dict["output"] == {"result": "success"}
        assert result_dict["trace_id"] == "test-trace"

    def test_failure_result(self):
        """Test failed execution result."""
        result = SandboxExecutionResult(
            success=False,
            error_message="Execution failed",
            exit_code=1,
            stderr="Error occurred",
        )

        assert result.success is False
        assert result.error_message == "Execution failed"
        assert result.exit_code == 1


class TestToolRunnerSandbox:
    """Test the ToolRunnerSandbox guardrail component."""

    async def test_initialization_with_mock(self):
        """Test initialization with mock provider."""
        config = SandboxConfig(
            use_docker=False,
            use_firecracker=False,
            provider_type=SandboxProviderType.MOCK,
        )
        sandbox = ToolRunnerSandbox(config)

        result = await sandbox.initialize()

        assert result is True
        assert sandbox._initialized is True
        assert isinstance(sandbox._provider, MockSandboxProvider)

    async def test_get_layer(self):
        """Test get_layer method."""
        from enhanced_agent_bus.guardrails.enums import GuardrailLayer

        sandbox = ToolRunnerSandbox()
        assert sandbox.get_layer() == GuardrailLayer.TOOL_RUNNER_SANDBOX

    async def test_process_disabled(self):
        """Test processing when sandbox is disabled."""
        config = SandboxConfig(enabled=False)
        sandbox = ToolRunnerSandbox(config)

        result = await sandbox.process(
            data={"test": "value"},
            context={"trace_id": "test-trace", "should_sandbox": True},
        )

        assert result.allowed is True
        assert result.action.value == "allow"
        assert len(result.violations) == 0

    async def test_process_success(self):
        """Test successful processing."""
        config = SandboxConfig(
            use_docker=False,
            use_firecracker=False,
            provider_type=SandboxProviderType.MOCK,
        )
        sandbox = ToolRunnerSandbox(config)
        await sandbox.initialize()

        result = await sandbox.process(
            data={"test": "value"},
            context={"trace_id": "test-trace", "should_sandbox": True},
        )

        assert result.allowed is True
        assert result.action.value == "allow"
        assert result.trace_id == "test-trace"
        assert result.processing_time_ms >= 0

    async def test_process_sandbox_failure(self):
        """Test processing when sandbox execution fails."""
        config = SandboxConfig(
            use_docker=False,
            use_firecracker=False,
            provider_type=SandboxProviderType.MOCK,
        )
        sandbox = ToolRunnerSandbox(config)
        await sandbox.initialize()

        # Mock the provider to return failure
        async def mock_execute_failure(req):
            return SandboxExecutionResult(
                success=False,
                error_message="Sandbox execution failed",
                trace_id=req.trace_id,
            )

        sandbox._provider.execute = mock_execute_failure

        result = await sandbox.process(
            data={"test": "value"},
            context={"trace_id": "test-trace", "should_sandbox": True},
        )

        assert result.allowed is False
        assert result.action.value == "block"
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "sandbox_execution_failed"

    async def test_process_exception(self):
        """Test processing when exception occurs."""
        config = SandboxConfig(
            use_docker=False,
            use_firecracker=False,
            provider_type=SandboxProviderType.MOCK,
        )
        sandbox = ToolRunnerSandbox(config)
        await sandbox.initialize()

        # Mock the provider to raise exception
        async def raise_exception(req):
            raise RuntimeError("Test error")

        sandbox._provider.execute = raise_exception

        result = await sandbox.process(
            data={"test": "value"},
            context={"trace_id": "test-trace", "should_sandbox": True},
        )

        assert result.allowed is False
        assert result.action.value == "block"
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "sandbox_error"

    async def test_cleanup(self):
        """Test cleanup."""
        config = SandboxConfig(
            provider_type=SandboxProviderType.MOCK,
        )
        sandbox = ToolRunnerSandbox(config)
        await sandbox.initialize()

        assert sandbox._initialized is True

        await sandbox.cleanup()

        assert sandbox._initialized is False

    async def test_execute_in_sandbox_not_initialized(self):
        """Test execution when not initialized."""
        config = SandboxConfig(
            provider_type=SandboxProviderType.MOCK,
        )
        sandbox = ToolRunnerSandbox(config)

        # Don't initialize
        result = await sandbox._execute_in_sandbox(
            data={"test": "value"},
            context={"trace_id": "test-trace"},
        )

        assert result["success"] is True  # Mock provider returns success

    async def test_execute_in_sandbox_no_provider(self):
        """Test execution when provider is None."""
        config = SandboxConfig(enabled=False)
        sandbox = ToolRunnerSandbox(config)
        sandbox._provider = None
        sandbox._initialized = True

        result = await sandbox._execute_in_sandbox(
            data={"test": "value"},
            context={"trace_id": "test-trace"},
        )

        assert result["success"] is False
        assert "no sandbox provider" in result["error"].lower()


class TestGetDefaultProvider:
    """Test the get_default_provider function."""

    async def test_returns_docker_when_available(self):
        """Test that Docker is returned when available."""
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        with patch.dict("sys.modules", {"docker": mock_docker}):
            with patch("docker.from_env", return_value=mock_client):
                provider = await get_default_provider()

                assert isinstance(provider, DockerSandboxProvider)

    async def test_fallback_to_mock(self):
        """Test that mock is returned when Docker unavailable."""
        with patch.object(DockerSandboxProvider, "initialize", return_value=False):
            provider = await get_default_provider()

            assert isinstance(provider, MockSandboxProvider)


class TestSandboxConfig:
    """Test SandboxConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = SandboxConfig()

        assert config.enabled is True
        assert config.use_firecracker is False
        assert config.use_docker is True
        assert config.timeout_ms == 10000
        assert config.memory_limit_mb == 512
        assert config.cpu_limit == 0.5
        assert config.network_isolation is True
        assert config.provider_type == SandboxProviderType.DOCKER

    def test_custom_config(self):
        """Test custom configuration."""
        config = SandboxConfig(
            enabled=False,
            use_firecracker=True,
            use_docker=False,
            timeout_ms=30000,
            memory_limit_mb=1024,
            cpu_limit=1.0,
            network_isolation=False,
            provider_type=SandboxProviderType.MOCK,
        )

        assert config.enabled is False
        assert config.use_firecracker is True
        assert config.use_docker is False
        assert config.timeout_ms == 30000
        assert config.memory_limit_mb == 1024
        assert config.cpu_limit == 1.0
        assert config.network_isolation is False
        assert config.provider_type == SandboxProviderType.MOCK

    def test_with_security_config(self):
        """Test configuration with security settings."""
        security = SandboxSecurityConfig(
            run_as_root=False,
            read_only_root=True,
            enable_seccomp=True,
        )
        config = SandboxConfig(security_config=security)

        assert config.security_config.run_as_root is False
        assert config.security_config.read_only_root is True
        assert config.security_config.enable_seccomp is True

    def test_with_resource_limits(self):
        """Test configuration with resource limits."""
        limits = SandboxResourceLimits(
            cpu_limit=2.0,
            memory_limit_mb=2048,
            timeout_seconds=60.0,
        )
        config = SandboxConfig(resource_limits=limits)

        assert config.resource_limits.cpu_limit == 2.0
        assert config.resource_limits.memory_limit_mb == 2048
        assert config.resource_limits.timeout_seconds == 60.0
