"""
ACGS-2 Enhanced Agent Bus - Root Test Configuration
Constitutional Hash: 608508a9bd224290

This conftest.py ensures proper PYTHONPATH configuration for coverage collection.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Add the enhanced_agent_bus directory to sys.path for proper module discovery
# This must happen BEFORE any coverage collection starts
_root_dir = os.path.dirname(os.path.abspath(__file__))
# Ensure repo root is importable (supports `import src.*` since src/__init__.py exists).
# Do NOT add _src_dir directly — that would shadow packages/acgs-lite/src/acgs_lite/
# with the legacy src/acgs_lite/ copy and break acgs-lite test collection.
_repo_root = Path(_root_dir).parents[1]
_src_dir = _repo_root / "src"
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

# Also add parent directory for enhanced_agent_bus package imports
_parent_dir = os.path.dirname(_root_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Set PYTHONPATH environment variable for subprocesses
os.environ["PYTHONPATH"] = (
    f"{_repo_root}:{_src_dir}:{_parent_dir}:{os.environ.get('PYTHONPATH', '')}"
)


def _install_root_testclient_compat() -> None:
    """Reuse the repo-root pytest TestClient shim for package-scoped pytest runs."""
    module_name = "_acgs_root_pytest_conftest"
    root_conftest_path = _repo_root / "conftest.py"

    root_conftest = sys.modules.get(module_name)
    if root_conftest is None:
        spec = importlib.util.spec_from_file_location(module_name, root_conftest_path)
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise RuntimeError(f"Unable to load root conftest from {root_conftest_path}")

        root_conftest = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = root_conftest
        spec.loader.exec_module(root_conftest)

    import fastapi.testclient as fastapi_testclient
    import starlette.testclient as starlette_testclient

    fastapi_testclient.TestClient = root_conftest.CompatTestClient
    starlette_testclient.TestClient = root_conftest.CompatTestClient


_install_root_testclient_compat()


@pytest.fixture
def sample_event():
    """Create a sample security event for SIEM tests."""
    from enhanced_agent_bus.runtime_security import (
        SecurityEvent,
        SecurityEventType,
        SecuritySeverity,
    )

    return SecurityEvent(
        event_type=SecurityEventType.AUTHENTICATION_FAILURE,
        severity=SecuritySeverity.HIGH,
        message="Failed authentication attempt",
        tenant_id="tenant-123",
        agent_id="agent-456",
        metadata={"ip": "192.168.1.1", "user": "admin"},
    )


@pytest.fixture
def critical_event():
    """Create a critical security event for SIEM tests."""
    from enhanced_agent_bus.runtime_security import (
        SecurityEvent,
        SecurityEventType,
        SecuritySeverity,
    )

    return SecurityEvent(
        event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
        severity=SecuritySeverity.CRITICAL,
        message="Constitutional hash validation failed",
        tenant_id="tenant-789",
    )


@pytest.fixture
def siem_config():
    """Create a test SIEM config."""
    from enhanced_agent_bus.siem_integration import SIEMConfig, SIEMFormat

    return SIEMConfig(
        format=SIEMFormat.JSON,
        enable_alerting=True,
        max_queue_size=100,
        flush_interval_seconds=0.1,
    )


@pytest.fixture
async def siem_integration(siem_config):
    """Create and start a SIEM integration for testing."""
    from enhanced_agent_bus.siem_integration import SIEMIntegration

    siem = SIEMIntegration(siem_config)
    await siem.start()
    yield siem
    await siem.stop()
