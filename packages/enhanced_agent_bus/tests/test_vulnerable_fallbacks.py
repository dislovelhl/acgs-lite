"""
Verification test for VULN-003 remediation.
Ensures that the Deliberation Layer fails closed instead of using mocks.
Constitutional Hash: 608508a9bd224290
"""

import subprocess
import sys
from pathlib import Path

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


def _run_sessions_fallback_subprocess(
    *,
    environment: str,
    header_value: str | None,
    include_pytest_marker: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute fallback tenant extraction in a clean subprocess with forced fallback imports."""
    test_code = """
import asyncio
import builtins
import importlib

from fastapi import HTTPException

BLOCKED_MODULES = {
    "src.core.shared.security.tenant_context",
    "enhanced_agent_bus._compat.security.tenant_context",
}

original_import = builtins.__import__

def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in BLOCKED_MODULES:
        raise ImportError(f"Blocked for fallback test: {name}")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = blocking_import

module = importlib.import_module("enhanced_agent_bus.routes.sessions._fallbacks")
if not getattr(module, "USING_FALLBACK_TENANT", False):
    print("FALLBACK_NOT_ACTIVE")
    raise SystemExit(8)

header = None
raw_header = __import__("os").environ.get("FALLBACK_HEADER_VALUE", "")
if raw_header != "__MISSING__":
    header = raw_header

try:
    result = asyncio.run(module.get_tenant_id(x_tenant_id=header))
    print(f"RESULT:{result}")
except HTTPException as exc:
    print(f"HTTP:{exc.status_code}:{exc.detail}")
"""

    import os

    env = {**dict(os.environ)}
    env["AGENT_RUNTIME_ENVIRONMENT"] = environment
    env["ACGS_ENV"] = environment
    env["APP_ENV"] = environment
    env["ENVIRONMENT"] = environment
    env["FALLBACK_HEADER_VALUE"] = header_value if header_value is not None else "__MISSING__"
    env["ACGS_DISABLE_RATE_LIMITING"] = "1"

    if include_pytest_marker:
        env["PYTEST_CURRENT_TEST"] = "test-marker"
    else:
        env.pop("PYTEST_CURRENT_TEST", None)

    return subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        timeout=60,  # increased from 10s — subprocess startup is slow under xdist load
    )


def test_deliberation_layer_fail_closed_on_missing_deps():
    """
    Test that importing the deliberation layer integration fails
    when critical dependencies are missing, instead of falling back to mocks.

    This test runs in a subprocess to ensure clean module state, avoiding
    interference from other tests that may have already imported the module.
    """
    # Run test in subprocess to get clean import state
    test_code = """
import sys
import builtins

# Block the dependency modules by hooking __import__
# Must block all possible import paths (relative and absolute)
blocked_modules = {
    "interfaces",
    "impact_scorer",
    "adaptive_router",
    "deliberation_queue",
}

original_import = builtins.__import__

def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):
    # Block direct imports of critical modules
    base_name = name.split(".")[-1]
    if base_name in blocked_modules:
        raise ImportError(f"Blocked for security test: {name}")
    # Also block fromlist items
    if fromlist:
        for item in fromlist:
            if item in blocked_modules:
                raise ImportError(f"Blocked fromlist item: {item}")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = blocking_import

try:
    import enhanced_agent_bus.deliberation_layer.integration
    sys.exit(1)
except RuntimeError as e:
    if "CRITICAL" in str(e) or "missing" in str(e).lower():
        sys.exit(0)
    sys.exit(2)
except ImportError as e:
    # ImportError is also acceptable - shows fail-closed behavior
    sys.exit(0)
except (RuntimeError, ValueError, TypeError, AssertionError) as e:
    sys.exit(3)
"""

    import os

    # Dynamically determine the project root from test location
    test_dir = os.path.dirname(os.path.abspath(__file__))
    src_core_dir = os.path.dirname(
        os.path.dirname(test_dir)
    )  # Go up from tests/ to enhanced_agent_bus/ to src/core/

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True,
        cwd=src_core_dir,
        env={
            **dict(os.environ),
            "PYTHONPATH": src_core_dir,
        },
        timeout=60,  # generous timeout for slow xdist load
    )

    if result.returncode != 0:
        pytest.fail(
            f"Fail-closed test failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}\n"
            f"returncode: {result.returncode}"
        )


def test_deliberation_layer_imports_successfully_when_deps_available():
    """
    Verify that the deliberation layer imports successfully when all
    dependencies are available (normal operation).
    """
    try:
        from enhanced_agent_bus.deliberation_layer import integration

        # Verify module loaded with expected attributes
        assert hasattr(integration, "DeliberationEngine") or hasattr(
            integration, "CONSTITUTIONAL_HASH"
        )
    except ImportError as e:
        # If dependencies genuinely missing in test env, skip
        pytest.skip(f"Dependencies not available in test environment: {e}")


def test_sessions_fallback_rejects_header_in_non_dev_mode():
    result = _run_sessions_fallback_subprocess(
        environment="staging",
        header_value="tenant-from-header",
        include_pytest_marker=False,
    )

    assert result.returncode == 0, result.stderr
    assert "HTTP:503:" in result.stdout


def test_sessions_fallback_accepts_header_in_test_mode():
    result = _run_sessions_fallback_subprocess(
        environment="test",
        header_value="tenant-test",
        include_pytest_marker=False,
    )

    assert result.returncode == 0, result.stderr
    assert "RESULT:tenant-test" in result.stdout


def test_sessions_fallback_rejects_missing_header_in_test_mode():
    result = _run_sessions_fallback_subprocess(
        environment="testing",
        header_value=None,
        include_pytest_marker=False,
    )

    assert result.returncode == 0, result.stderr
    assert "HTTP:400:" in result.stdout


def test_sessions_fallback_rejects_staging_even_with_pytest_marker():
    """VULN-003 hardening: PYTEST_CURRENT_TEST must NOT bypass the guard when
    a production-like environment (staging, prod, preprod) is configured."""
    result = _run_sessions_fallback_subprocess(
        environment="staging",
        header_value="tenant-from-header",
        include_pytest_marker=True,
    )

    assert result.returncode == 0, result.stderr
    assert "HTTP:503:" in result.stdout, (
        "Staging + PYTEST_CURRENT_TEST should still reject fallback tenant extraction"
    )


def test_sessions_fallback_allows_dev_with_pytest_marker():
    """Sanity: PYTEST_CURRENT_TEST combined with a dev-like environment is fine."""
    result = _run_sessions_fallback_subprocess(
        environment="development",
        header_value="tenant-dev",
        include_pytest_marker=True,
    )

    assert result.returncode == 0, result.stderr
    assert "RESULT:tenant-dev" in result.stdout
