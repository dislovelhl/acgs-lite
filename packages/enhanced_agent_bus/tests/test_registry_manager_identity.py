"""Tests for RegistryManager identity normalization and audit metadata.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.components.registry_manager import RegistryManager


class _CaptureRegistry:
    """Minimal registry backend for capturing registration metadata."""

    def __init__(self) -> None:
        self.last_agent_id: str | None = None
        self.last_capabilities: list[str] | None = None
        self.last_metadata: dict[str, object] | None = None

    async def register(
        self,
        agent_id: str,
        capabilities: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        self.last_agent_id = agent_id
        self.last_capabilities = capabilities
        self.last_metadata = metadata
        return True

    async def unregister(self, agent_id: str) -> bool:
        return True


@pytest.mark.constitutional
async def test_register_agent_builds_non_anonymous_identity() -> None:
    manager = RegistryManager(config={}, registry_backend=_CaptureRegistry())

    ok = await manager.register_agent(
        agent_id="agent-alpha",
        constitutional_hash=CONSTITUTIONAL_HASH,
        capabilities=["analyze", "validate"],
        tenant_id="tenant-42",
    )

    assert ok is True
    info = manager.get_agent_info("agent-alpha", current_hash=CONSTITUTIONAL_HASH)
    assert info is not None

    identity = info.get("identity")
    assert isinstance(identity, dict)
    assert identity["principal_id"] == "agent-alpha"
    assert identity["principal_type"] == "agent"
    assert identity["tenant_id"] == "tenant-42"
    assert identity["auth_method"] == "internal"
    assert identity["constitutional_hash"] == CONSTITUTIONAL_HASH
    assert identity["scopes"] == ["analyze", "validate"]


@pytest.mark.constitutional
async def test_register_agent_identity_includes_extra_scopes_and_metadata() -> None:
    capture = _CaptureRegistry()
    manager = RegistryManager(config={}, registry_backend=capture)

    ok = await manager.register_agent(
        agent_id="agent-bravo",
        constitutional_hash=CONSTITUTIONAL_HASH,
        capabilities=["analyze"],
        tenant_id="tenant-a",
        auth_token="opaque-token",
        identity_scopes=["governance:execute", "analyze"],
        identity_metadata={"issuer": "unit-test"},
    )

    assert ok is True
    assert capture.last_metadata is not None
    backend_identity = capture.last_metadata["identity"]
    assert isinstance(backend_identity, dict)
    assert backend_identity["auth_method"] == "token"
    assert backend_identity["metadata"] == {"issuer": "unit-test"}
    scopes = backend_identity["scopes"]
    assert isinstance(scopes, list)
    # Deduplicated without requiring strict ordering from caller inputs.
    assert set(scopes) == {"analyze", "governance:execute"}
    assert len(scopes) == 2


@pytest.mark.constitutional
async def test_get_agent_info_refreshes_identity_constitutional_hash() -> None:
    manager = RegistryManager(config={}, registry_backend=_CaptureRegistry())

    ok = await manager.register_agent(
        agent_id="agent-charlie",
        constitutional_hash="old-hash",
        capabilities=["query"],
    )
    assert ok is True

    info = manager.get_agent_info("agent-charlie", current_hash="new-hash")
    assert info is not None
    identity = info.get("identity")
    assert isinstance(identity, dict)
    assert info["constitutional_hash"] == "new-hash"
    assert identity["constitutional_hash"] == "new-hash"


@pytest.mark.constitutional
async def test_register_agent_rejects_blank_agent_id() -> None:
    manager = RegistryManager(config={}, registry_backend=_CaptureRegistry())

    ok = await manager.register_agent(
        agent_id="   ",
        constitutional_hash=CONSTITUTIONAL_HASH,
    )

    assert ok is False
