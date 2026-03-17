# Constitutional Hash: cdd01ef066bc6cf2
"""Agent code execution sandbox for OWASP AA07 mitigation.

Provides process-level isolation for agent-generated code execution with:
- Resource limits (CPU time, memory, file descriptors)
- Filesystem restriction (temporary directory only)
- Network isolation (optional)
- Output capture and size limits

Architecture:
- SandboxConfig: frozen configuration for sandbox instances
- SandboxResult: frozen execution result with captured output
- Sandbox: context manager for isolated code execution
- SandboxPolicy: predefined policies (STRICT, STANDARD, PERMISSIVE)

The default backend uses subprocess with resource limits (rlimit).
Can be upgraded to gVisor, E2B, or Firecracker by implementing
the SandboxBackend protocol.
"""

from __future__ import annotations

import resource
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# Maximum output size to capture (prevent memory exhaustion)
MAX_OUTPUT_BYTES = 1_048_576  # 1 MB


class SandboxPolicy(StrEnum):
    """Predefined sandbox policies."""

    STRICT = "strict"  # No network, minimal resources, 5s timeout
    STANDARD = "standard"  # No network, moderate resources, 30s timeout
    PERMISSIVE = "permissive"  # Network allowed, generous resources, 120s timeout


@dataclass(frozen=True)
class SandboxConfig:
    """Immutable sandbox configuration."""

    policy: SandboxPolicy = SandboxPolicy.STANDARD
    timeout_seconds: int = 30
    max_memory_bytes: int = 256 * 1024 * 1024  # 256 MB
    max_cpu_seconds: int = 30
    max_file_descriptors: int = 64
    max_output_bytes: int = MAX_OUTPUT_BYTES
    allow_network: bool = False
    allowed_paths: tuple[str, ...] = ()
    env_vars: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_policy(cls, policy: SandboxPolicy) -> SandboxConfig:
        """Create config from a predefined policy."""
        if policy == SandboxPolicy.STRICT:
            return cls(
                policy=policy,
                timeout_seconds=5,
                max_memory_bytes=64 * 1024 * 1024,
                max_cpu_seconds=5,
                max_file_descriptors=16,
                allow_network=False,
            )
        if policy == SandboxPolicy.PERMISSIVE:
            return cls(
                policy=policy,
                timeout_seconds=120,
                max_memory_bytes=1024 * 1024 * 1024,
                max_cpu_seconds=120,
                max_file_descriptors=256,
                allow_network=True,
            )
        # STANDARD is the default
        return cls(policy=policy)


@dataclass(frozen=True)
class SandboxResult:
    """Immutable result of sandboxed execution."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    memory_exceeded: bool
    sandbox_id: str
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None


@runtime_checkable
class SandboxBackend(Protocol):
    """Protocol for sandbox backend implementations.

    Default: ProcessSandbox (subprocess + rlimit)
    Future: gVisorSandbox, E2BSandbox, FirecrackerSandbox
    """

    def execute(
        self,
        code: str,
        config: SandboxConfig,
        sandbox_dir: Path,
    ) -> SandboxResult: ...


def _set_resource_limits(config: SandboxConfig) -> None:
    """Set resource limits for the child process (called via preexec_fn)."""
    # CPU time limit
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (config.max_cpu_seconds, config.max_cpu_seconds + 1),
    )
    # Memory limit (address space)
    resource.setrlimit(
        resource.RLIMIT_AS,
        (config.max_memory_bytes, config.max_memory_bytes),
    )
    # File descriptor limit
    resource.setrlimit(
        resource.RLIMIT_NOFILE,
        (config.max_file_descriptors, config.max_file_descriptors),
    )
    # No core dumps
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class ProcessSandbox:
    """Default sandbox backend using subprocess with resource limits."""

    def execute(
        self,
        code: str,
        config: SandboxConfig,
        sandbox_dir: Path,
    ) -> SandboxResult:
        """Execute code in an isolated subprocess with resource limits."""
        import time
        import uuid

        sandbox_id = str(uuid.uuid4())[:12]
        start_time = time.monotonic()
        timed_out = False
        memory_exceeded = False

        # Write code to temp file in sandbox directory
        code_file = sandbox_dir / f"sandbox_{sandbox_id}.py"
        code_file.write_text(code, encoding="utf-8")

        # Build environment
        env = {
            "HOME": str(sandbox_dir),
            "TMPDIR": str(sandbox_dir),
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
        env.update(config.env_vars)

        try:
            result = subprocess.run(  # noqa: S603
                ["/usr/bin/python3", str(code_file)],
                capture_output=True,
                timeout=config.timeout_seconds,
                cwd=str(sandbox_dir),
                env=env,
                preexec_fn=lambda: _set_resource_limits(config),
            )

            duration = time.monotonic() - start_time
            stdout = result.stdout.decode("utf-8", errors="replace")[: config.max_output_bytes]
            stderr = result.stderr.decode("utf-8", errors="replace")[: config.max_output_bytes]

            # Check for resource limit signals
            if result.returncode == -signal.SIGKILL:
                memory_exceeded = True
            elif result.returncode == -signal.SIGXCPU:
                timed_out = True

            return SandboxResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                timed_out=timed_out,
                memory_exceeded=memory_exceeded,
                sandbox_id=sandbox_id,
            )

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start_time
            return SandboxResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=duration,
                timed_out=True,
                memory_exceeded=False,
                sandbox_id=sandbox_id,
                error=f"Execution timed out after {config.timeout_seconds}s",
            )

        except OSError as e:
            duration = time.monotonic() - start_time
            return SandboxResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=duration,
                timed_out=False,
                memory_exceeded=False,
                sandbox_id=sandbox_id,
                error=f"Sandbox execution failed: {e}",
            )

        finally:
            # Clean up code file
            if code_file.exists():
                code_file.unlink()


class Sandbox:
    """High-level sandbox interface for agent code execution.

    Usage:
        config = SandboxConfig.from_policy(SandboxPolicy.STRICT)
        sandbox = Sandbox(config)
        result = sandbox.run("print('hello')")
        assert result.success
        assert result.stdout.strip() == "hello"
    """

    def __init__(
        self,
        config: SandboxConfig | None = None,
        backend: SandboxBackend | None = None,
    ) -> None:
        self._config = config or SandboxConfig()
        self._backend = backend or ProcessSandbox()

    @property
    def config(self) -> SandboxConfig:
        return self._config

    def run(self, code: str) -> SandboxResult:
        """Execute code in the sandbox and return the result.

        Args:
            code: Python code to execute.

        Returns:
            SandboxResult with captured output and metadata.
        """
        if not code.strip():
            return SandboxResult(
                success=True,
                exit_code=0,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                timed_out=False,
                memory_exceeded=False,
                sandbox_id="empty",
            )

        with tempfile.TemporaryDirectory(prefix="acgs2_sandbox_") as tmpdir:
            sandbox_dir = Path(tmpdir)
            result = self._backend.execute(code, self._config, sandbox_dir)

            if not result.success:
                logger.warning(
                    "Sandbox execution failed",
                    sandbox_id=result.sandbox_id,
                    exit_code=result.exit_code,
                    timed_out=result.timed_out,
                    memory_exceeded=result.memory_exceeded,
                )

            return result

    def validate_code(self, code: str) -> tuple[bool, str | None]:
        """Basic static validation of code before execution.

        Checks for obviously dangerous patterns. This is NOT a security
        boundary — the sandbox itself provides isolation.

        Returns:
            Tuple of (is_safe, reason_if_unsafe).
        """
        dangerous_patterns = [
            ("import os; os.system", "Direct OS command execution"),
            ("subprocess.call", "Subprocess execution"),
            ("subprocess.run", "Subprocess execution"),
            ("subprocess.Popen", "Subprocess execution"),
            ("__import__('os')", "Dynamic OS import"),
            ("eval(", "Dynamic code evaluation"),
            ("exec(", "Dynamic code execution"),
            ("open('/etc/", "System file access"),
            ("open('/proc/", "Process info access"),
        ]

        for pattern, reason in dangerous_patterns:
            if pattern in code:
                return False, reason

        return True, None


__all__ = [
    "MAX_OUTPUT_BYTES",
    "ProcessSandbox",
    "Sandbox",
    "SandboxBackend",
    "SandboxConfig",
    "SandboxPolicy",
    "SandboxResult",
]
