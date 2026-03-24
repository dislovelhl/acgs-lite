"""
Sandbox Provider Abstraction and Implementations.

Provides pluggable sandbox backends for isolated code execution using Docker
or Firecracker microVMs.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import hashlib
import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class SandboxProviderType(str, Enum):
    """Available sandbox provider types."""

    DOCKER = "docker"
    FIRECRACKER = "firecracker"
    MOCK = "mock"


@dataclass
class SandboxResourceLimits:
    """Resource limits for sandboxed execution."""

    cpu_limit: float = 0.5  # CPU cores
    memory_limit_mb: int = 512  # Memory in MB
    timeout_seconds: float = 10.0  # Timeout
    network_disabled: bool = True  # Disable network access
    max_output_size_mb: int = 10  # Max stdout/stderr size


@dataclass
class SandboxSecurityConfig:
    """Security configuration for sandbox execution."""

    run_as_root: bool = False  # Never run as root
    read_only_root: bool = True  # Read-only root filesystem
    drop_all_capabilities: bool = True  # Drop all Linux capabilities
    enable_seccomp: bool = True  # Enable seccomp filtering
    seccomp_profile: str | None = None  # Custom seccomp profile
    no_new_privileges: bool = True  # Prevent privilege escalation
    security_opt: list[str] = field(default_factory=list)  # Additional security options


@dataclass
class SandboxExecutionRequest:
    """Request to execute code in a sandbox."""

    code: str  # Code to execute
    data: JSONDict  # Input data
    context: JSONDict  # Execution context
    trace_id: str = ""
    image: str = "python:3.11-slim"  # Container image
    working_dir: str = "/sandbox"  # Working directory in container
    env_vars: dict[str, str] = field(default_factory=dict)  # Environment variables
    resource_limits: SandboxResourceLimits = field(default_factory=SandboxResourceLimits)
    security_config: SandboxSecurityConfig = field(default_factory=SandboxSecurityConfig)

    def compute_hash(self) -> str:
        """Compute a unique hash for this request."""
        content = f"{self.code}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class SandboxExecutionResult:
    """Result from sandboxed execution."""

    success: bool
    output: JSONDict = field(default_factory=dict)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: float = 0.0
    error_message: str = ""
    container_id: str = ""
    trace_id: str = ""

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "container_id": self.container_id,
            "trace_id": self.trace_id,
        }


class SandboxProvider(ABC):
    """Abstract base class for sandbox providers.

        All sandbox implementations must inherit from this class and implement
    the execute method to provide isolated code execution environments.
    """

    def __init__(self, provider_type: SandboxProviderType):
        self.provider_type = provider_type
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the sandbox provider.

        Returns:
            True if initialization successful, False otherwise.
        """
        pass

    @abstractmethod
    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        """Execute code in an isolated sandbox environment.

        Args:
            request: Execution request containing code, data, and configuration.

        Returns:
            SandboxExecutionResult containing the execution output.
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up any resources held by the provider."""
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, str | bool]:
        """Check provider health.

        Returns:
            Health status dictionary.
        """
        pass

    async def is_available(self) -> bool:
        """Check if provider is available and ready."""
        return self._initialized


class MockSandboxProvider(SandboxProvider):
    """Mock sandbox provider for testing and development.

    This provider doesn't actually isolate code but provides the same interface
    for testing purposes.
    """

    def __init__(self):
        super().__init__(SandboxProviderType.MOCK)
        self._execution_count = 0

    async def initialize(self) -> bool:
        """Initialize mock provider."""
        self._initialized = True
        return True

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        """Execute code (not actually sandboxed)."""
        start_time = time.time()
        self._execution_count += 1

        try:
            # In mock mode, we just return the input data
            # This is useful for testing the guardrail pipeline
            execution_time = (time.time() - start_time) * 1000

            return SandboxExecutionResult(
                success=True,
                output=request.data,
                exit_code=0,
                execution_time_ms=execution_time,
                trace_id=request.trace_id,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            return SandboxExecutionResult(
                success=False,
                error_message=str(e),
                trace_id=request.trace_id,
            )

    async def cleanup(self) -> None:
        """No cleanup needed for mock."""
        pass

    async def health_check(self) -> dict[str, str | bool]:
        """Health check for mock provider."""
        return {
            "status": "healthy",
            "provider": "mock",
            "initialized": self._initialized,
            "execution_count": self._execution_count,
        }


class DockerSandboxProvider(SandboxProvider):
    """Docker-based sandbox provider for isolated code execution.

    This provider uses Docker containers to run code in isolated environments
    with resource limits, security policies, and network isolation.
    """

    def __init__(
        self,
        default_image: str = "python:3.11-slim",
        container_prefix: str = "acgs2-sandbox",
    ):
        super().__init__(SandboxProviderType.DOCKER)
        self.default_image = default_image
        self.container_prefix = container_prefix
        self._client: Any | None = None
        self._containers: set[str] = set()

    async def initialize(self) -> bool:
        """Initialize Docker client and verify connection.

        Returns:
            True if Docker is available, False otherwise.
        """
        try:
            import docker

            # Create async-compatible client
            self._client = docker.from_env()

            # Test connection
            self._client.ping()  # type: ignore[union-attr]

            self._initialized = True
            logger.info("Docker sandbox provider initialized successfully")
            return True

        except ImportError:
            logger.error("docker-py library not installed. Run: pip install docker")
            return False

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            return False

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        """Execute code in a Docker container.

        Args:
            request: Execution request with code, data, and security config.

        Returns:
            SandboxExecutionResult with execution output.
        """
        if not self._initialized or not self._client:
            return SandboxExecutionResult(
                success=False,
                error_message="Docker provider not initialized",
                trace_id=request.trace_id,
            )

        container_name = f"{self.container_prefix}-{request.compute_hash()}"
        start_time = time.time()

        try:
            # Create temporary directory for volume mounting
            with tempfile.TemporaryDirectory(prefix="acgs2-sandbox-") as temp_dir:
                temp_path = Path(temp_dir)

                # Write input data to file
                input_file = temp_path / "input.json"
                input_file.write_text(json.dumps(request.data, indent=2))

                # SECURITY Q-C1: Validate and freeze code to prevent TOCTOU
                validated_code = self._validate_and_freeze_sandbox_code(request.code)

                script_file = temp_path / "execute.py"
                script_content = self._generate_execution_script(request, validated_code)
                script_file.write_text(script_content)

                # Build container configuration
                container_config = self._build_container_config(request, temp_dir, container_name)

                # Run container with timeout
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, self._run_container_sync, container_config
                )

                execution_time = (time.time() - start_time) * 1000
                result.execution_time_ms = execution_time
                result.trace_id = request.trace_id

                return result

        except TimeoutError:
            return SandboxExecutionResult(
                success=False,
                error_message=f"Execution timed out after {request.resource_limits.timeout_seconds}s",
                container_id=container_name,
                trace_id=request.trace_id,
                execution_time_ms=request.resource_limits.timeout_seconds * 1000,
            )

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Docker execution error: {e}")
            return SandboxExecutionResult(
                success=False,
                error_message=str(e),
                container_id=container_name,
                trace_id=request.trace_id,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    # Builtin names that can be used to construct dunder access indirectly
    _BLOCKED_BUILTINS = frozenset(
        {
            "getattr",
            "setattr",
            "delattr",
            "eval",
            "exec",
            "compile",
            "__import__",
            "open",
            "breakpoint",
            "vars",
            "dir",
            "globals",
            "locals",
            "type",
        }
    )

    @staticmethod
    def _validate_and_freeze_sandbox_code(code: str) -> str:
        """Validate sandbox code and return frozen copy.

        Parses the code into an AST, validates it, then converts the
        validated AST back to source. This eliminates the TOCTOU gap
        between validation and use (Q-C1 fix).

        Security hardening (C2):
        - Blocks import statements
        - Blocks dunder attribute access (direct syntax)
        - Blocks string constants containing dunder names (indirect escape vectors)
        - Blocks calls to dangerous builtins (getattr, type, etc.)

        Args:
            code: User-provided Python code to validate.

        Returns:
            Validated source code derived from the parsed AST.

        Raises:
            ValueError: If code fails validation (imports, dunder access, syntax).
        """
        import ast as _ast

        try:
            tree = _ast.parse(code, mode="exec")
        except SyntaxError as exc:
            raise ValueError(f"Invalid sandbox code: {exc}") from exc

        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                raise ValueError("Imports are not allowed in sandbox code")

            if isinstance(node, _ast.Name) and (
                node.id in DockerSandboxProvider._BLOCKED_BUILTINS or node.id.startswith("__")
            ):
                raise ValueError(f"Name {node.id!r} is blocked in sandbox code")

            # Block direct dunder attribute access: obj.__class__
            if isinstance(node, _ast.Attribute) and node.attr.startswith("__"):
                raise ValueError("Dunder attribute access is blocked in sandbox code")

            # Block string constants containing dunder names (indirect escape vectors)
            # e.g. getattr(x, '__class__') or '__' + 'class' + '__'
            if isinstance(node, _ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("__") and node.value.endswith("__"):
                    raise ValueError(
                        f"String containing dunder name {node.value!r} is blocked in sandbox code"
                    )

            # Block calls to dangerous builtins: getattr(...), type(...), etc.
            if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
                if node.func.id in DockerSandboxProvider._BLOCKED_BUILTINS:
                    raise ValueError(f"Call to {node.func.id!r} is blocked in sandbox code")

        # SECURITY: Return source derived from validated AST (eliminates TOCTOU)
        return _ast.unparse(tree)

    def _generate_execution_script(
        self, request: SandboxExecutionRequest, validated_code: str
    ) -> str:
        """Generate the Python script to run inside the container.

        Args:
            request: Sandbox execution request.
            validated_code: Pre-validated code (from _validate_and_freeze_sandbox_code).

        Returns:
            Python script content to execute in container.
        """
        return f'''#!/usr/bin/env python3
"""Sandbox execution script."""
import json
import sys
import traceback
import types

def main():
    try:
        # Read input data
        with open("/sandbox/input.json", "r") as f:
            data = json.load(f)

        # Execute user code in restricted namespace
        safe_builtins = {{
            "print": print,
            "len": len,
            "range": range,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "enumerate": enumerate,
            "zip": zip,
            "sorted": sorted,
        }}

        # SECURITY C2: Freeze builtins to prevent mutation via namespace["__builtins__"]
        frozen_builtins = types.MappingProxyType(safe_builtins)

        # SECURITY C2: Only expose json.loads and json.dumps (not the json module
        # itself, which exposes __class__, __spec__, etc.)
        namespace = {{
            "__builtins__": frozen_builtins,
            "data": data,
            "json_loads": json.loads,
            "json_dumps": json.dumps,
        }}

        # SECURITY Q-C1: Use validated code (not request.code) to prevent TOCTOU
        # SECURITY Q-C2: compile() with dont_inherit prevents __future__ flag injection
        # and gives an explicit compilation step before execution.  The exec() is
        # acceptable here because it runs INSIDE an isolated Docker container with:
        # (a) AST-validated code (no imports, no dunder access, no blocked builtins),
        # (b) frozen builtins (MappingProxyType), (c) restricted namespace, and
        # (d) repr()-serialised source derived from the validated AST (TOCTOU-safe).
        _code_obj = compile({repr(validated_code)}, "<sandbox>", "exec", dont_inherit=True)
        exec(_code_obj, namespace)  # noqa: S102 — sandboxed in Docker; see Q-C2 above

        # Get output
        output = namespace.get("output", data)

        # Write output
        with open("/sandbox/output.json", "w") as f:
            json.dump(output, f)

        sys.exit(0)

    except (RuntimeError, TypeError, ValueError, OSError) as e:
        error_info = {{
            "error": str(e),
            "traceback": traceback.format_exc()
        }}
        with open("/sandbox/output.json", "w") as f:
            json.dump(error_info, f)
        sys.exit(1)

if __name__ == "__main__":
    main()
'''

    def _build_container_config(
        self,
        request: SandboxExecutionRequest,
        host_temp_dir: str,
        container_name: str,
    ) -> dict:
        """Build Docker container configuration.

        Args:
            request: Execution request.
            host_temp_dir: Temporary directory on host for volume mounting.
            container_name: Name for the container.

        Returns:
            Dictionary with container configuration.
        """
        sec = request.security_config
        limits = request.resource_limits

        # Build security options
        security_opt = []
        if sec.enable_seccomp:
            if sec.seccomp_profile:
                security_opt.append(f"seccomp={sec.seccomp_profile}")

        if sec.no_new_privileges:
            security_opt.append("no-new-privileges:true")

        security_opt.extend(sec.security_opt)

        # Build container config with parameters passed directly (not via host_config dict)
        # Docker SDK expects these as direct parameters to containers.run()
        config = {
            "image": request.image or self.default_image,
            "name": container_name,
            "command": ["python3", f"{request.working_dir}/execute.py"],
            "working_dir": request.working_dir,
            "environment": request.env_vars,
            "user": "1000:1000" if not sec.run_as_root else "0:0",
            "detach": True,
            "auto_remove": False,  # Don't auto-remove - we need to get logs first
            "mem_limit": f"{limits.memory_limit_mb}m",
            "nano_cpus": int(limits.cpu_limit * 1e9),
            "network_mode": "none" if limits.network_disabled else "bridge",
            "read_only": sec.read_only_root,
            "cap_drop": ["ALL"] if sec.drop_all_capabilities else None,
            "tmpfs": {
                "/tmp": "noexec,nosuid,size=100m",  # nosec B108 - container sandbox tmpfs mount
            },
            "volumes": {
                host_temp_dir: {
                    "bind": request.working_dir,
                    "mode": "rw",
                }
            },
        }

        # Add security options if present
        if security_opt:
            config["security_opt"] = security_opt

        # Remove None values
        config = {k: v for k, v in config.items() if v is not None}

        return config

    def _run_container_sync(self, config: dict) -> SandboxExecutionResult:
        """Synchronous container execution (runs in thread pool).

        Args:
            config: Container configuration.

        Returns:
            Execution result.
        """
        container = None
        container_id = config.get("name", "")

        try:
            # Run container
            container = self._client.containers.run(**config)  # type: ignore[union-attr]
            container_id = container.id[:12]
            self._containers.add(container_id)

            # Wait for completion with timeout
            timeout = config.get("timeout", 10)
            result = container.wait(timeout=timeout)

            # Get logs
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            exit_code = result.get("StatusCode", -1)

            # Read output file if it exists
            output: JSONDict = {}
            temp_dir = None

            # Find temp directory from volumes
            volumes = config.get("volumes", {})
            if volumes:
                temp_dir = list(volumes.keys())[0]

            if temp_dir:
                output_file = Path(temp_dir) / "output.json"
                if output_file.exists():
                    try:
                        output = json.loads(output_file.read_text())
                    except json.JSONDecodeError:
                        output = {"error": "Failed to parse output JSON"}

            return SandboxExecutionResult(
                success=exit_code == 0,
                output=output,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                container_id=container_id,
            )

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Container execution failed: {e}")
            return SandboxExecutionResult(
                success=False,
                error_message=str(e),
                container_id=container_id,
            )

        finally:
            # Cleanup container if still running
            if container:
                try:
                    container.remove(force=True)
                    self._containers.discard(container_id)
                except (
                    AttributeError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as cleanup_error:
                    logger.warning(f"Failed to cleanup container {container_id}: {cleanup_error}")

    async def cleanup(self) -> None:
        """Clean up all running containers."""
        if not self._client:
            return

        for container_id in list(self._containers):
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._cleanup_container_sync, container_id)
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"Failed to cleanup container {container_id}: {e}")

        self._containers.clear()

    def _cleanup_container_sync(self, container_id: str) -> None:
        """Synchronous container cleanup."""
        try:
            container = self._client.containers.get(container_id)  # type: ignore[union-attr]
            container.remove(force=True)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            # Container may not exist or already be removed
            logger.debug(f"Container cleanup failed for {container_id}: {e}")
            pass

    async def health_check(self) -> dict[str, str | bool]:
        """Check Docker provider health."""
        if not self._initialized or not self._client:
            return {
                "status": "unhealthy",
                "provider": "docker",
                "initialized": False,
                "error": "Docker client not initialized",
            }

        try:
            loop = asyncio.get_running_loop()
            version_info = await loop.run_in_executor(None, self._client.version)  # type: ignore[attr-defined]

            return {
                "status": "healthy",
                "provider": "docker",
                "initialized": True,
                "version": version_info.get("Version", "unknown"),
                "active_containers": len(self._containers),
            }

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            return {
                "status": "unhealthy",
                "provider": "docker",
                "initialized": self._initialized,
                "error": str(e),
            }


class FirecrackerSandboxProvider(SandboxProvider):
    """Firecracker microVM-based sandbox provider.

    This provider uses AWS Firecracker to run code in lightweight microVMs
    for enhanced isolation with minimal overhead.

    Note: This is a stub implementation for future use.
    """

    def __init__(self, firecracker_binary: str = "/usr/bin/firecracker"):
        super().__init__(SandboxProviderType.FIRECRACKER)
        self.firecracker_binary = firecracker_binary

    async def initialize(self) -> bool:
        """Initialize Firecracker provider.

        Note: Currently returns False as this is a stub implementation.
        """
        # Check if Firecracker is available
        if not os.path.exists(self.firecracker_binary):
            logger.warning(
                f"Firecracker binary not found at {self.firecracker_binary}. "
                "Firecracker sandbox provider unavailable."
            )
            return False

        logger.info("Firecracker sandbox provider stub initialized")
        self._initialized = True
        return True

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        """Execute code in a Firecracker microVM.

        Note: Currently returns error as this is a stub implementation.
        """
        return SandboxExecutionResult(
            success=False,
            error_message="Firecracker sandbox provider not yet implemented. "
            "Use Docker provider for production sandboxes.",
            trace_id=request.trace_id,
        )

    async def cleanup(self) -> None:
        """Clean up Firecracker resources."""
        pass

    async def health_check(self) -> dict[str, str | bool]:
        """Check Firecracker provider health."""
        return {
            "status": "not_implemented",
            "provider": "firecracker",
            "initialized": self._initialized,
            "note": "Firecracker provider is a stub implementation",
        }


class SandboxProviderFactory:
    """Factory for creating sandbox providers."""

    _providers: ClassVar[dict[SandboxProviderType, type[SandboxProvider]]] = {
        SandboxProviderType.MOCK: MockSandboxProvider,
        SandboxProviderType.DOCKER: DockerSandboxProvider,
        SandboxProviderType.FIRECRACKER: FirecrackerSandboxProvider,
    }

    @classmethod
    def create(
        cls,
        provider_type: SandboxProviderType,
        **kwargs: str | int | float | bool,
    ) -> SandboxProvider:
        """Create a sandbox provider of the specified type.

        Args:
            provider_type: Type of provider to create.
            **kwargs: Additional arguments to pass to the provider constructor.

        Returns:
            Configured sandbox provider instance.

        Raises:
            ValueError: If provider type is unknown.
        """
        provider_class = cls._providers.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unknown sandbox provider type: {provider_type}")

        return provider_class(**kwargs)  # type: ignore[arg-type]

    @classmethod
    def register_provider(
        cls,
        provider_type: SandboxProviderType,
        provider_class: type[SandboxProvider],
    ) -> None:
        """Register a custom sandbox provider.

        Args:
            provider_type: Type identifier for the provider.
            provider_class: Provider class to register.
        """
        cls._providers[provider_type] = provider_class

    @classmethod
    def get_available_providers(cls) -> list[SandboxProviderType]:
        """Get list of available provider types."""
        return list(cls._providers.keys())


async def get_default_provider() -> SandboxProvider:
    """Get the default sandbox provider based on environment.

    Tries Docker first, falls back to Mock if Docker unavailable.

    Returns:
        Initialized sandbox provider.
    """
    # Try Docker first
    docker_provider = DockerSandboxProvider()
    if await docker_provider.initialize():
        return docker_provider

    # Fall back to mock
    logger.warning("Docker unavailable, falling back to mock sandbox provider")
    mock_provider = MockSandboxProvider()
    await mock_provider.initialize()
    return mock_provider
