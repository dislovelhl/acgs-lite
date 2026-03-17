"""
ACGS-2 Enhanced Agent Bus - Root Test Configuration
Constitutional Hash: cdd01ef066bc6cf2

This conftest.py ensures proper PYTHONPATH configuration for coverage collection.
"""

import os
import sys
from pathlib import Path

import pytest

# Add the enhanced_agent_bus directory to sys.path for proper module discovery
# This must happen BEFORE any coverage collection starts
_root_dir = os.path.dirname(os.path.abspath(__file__))
# Ensure repo root and src are importable (supports `import src.*` and `import core.*`).
_repo_root = Path(_root_dir).parents[1]
_src_dir = _repo_root / "src"
for _path in (str(_repo_root), str(_src_dir)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
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
