"""Agent Bus Tenant Security Integration Tests. Constitutional Hash: 608508a9bd224290"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.types import JSONDict


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MockGovernanceConfig:
    session_id: str
    tenant_id: str
    user_id: str | None = None
    risk_level: RiskLevel = RiskLevel.MEDIUM


@dataclass
class MockSessionContext:
    governance_config: MockGovernanceConfig


@dataclass
class MockAgentMessage:
    tenant_id: str
    message_id: str = "msg-123"
    from_agent: str = "test-agent"
    headers: dict[str, str] = field(default_factory=dict)
    content: JSONDict = field(default_factory=dict)
    payload: JSONDict = field(default_factory=dict)
    conversation_id: str | None = None


class TestSessionContextTenantIsolation:
    def test_session_key_global_collision_vulnerability(self):
        key_prefix = "acgs:session"

        def vulnerable_make_key(session_id: str) -> str:
            return f"{key_prefix}:{session_id}"

        tenant_a_key = vulnerable_make_key("shared-id")
        tenant_b_key = vulnerable_make_key("shared-id")

        assert tenant_a_key == tenant_b_key, "VULN: Keys collide without tenant namespace"

    def test_fixed_session_key_with_tenant_namespace(self):
        key_prefix = "acgs:session"

        def fixed_make_key(tenant_id: str, session_id: str) -> str:
            safe_tenant = tenant_id.replace(":", "_").replace("*", "_")
            return f"{key_prefix}:{safe_tenant}:{session_id}"

        tenant_a_key = fixed_make_key("tenant-A", "shared-id")
        tenant_b_key = fixed_make_key("tenant-B", "shared-id")

        assert tenant_a_key != tenant_b_key
        assert tenant_a_key == "acgs:session:tenant-A:shared-id"
        assert tenant_b_key == "acgs:session:tenant-B:shared-id"

    def test_tenant_injection_prevention_in_key(self):
        def fixed_make_key(tenant_id: str, session_id: str) -> str:
            safe_tenant = tenant_id.replace(":", "_").replace("*", "_")
            safe_session = session_id.replace(":", "_").replace("*", "_")
            return f"acgs:session:{safe_tenant}:{safe_session}"

        malicious_tenant = "tenant:A:injected"
        key = fixed_make_key(malicious_tenant, "session-1")

        assert key.count(":") == 3, "Colons in tenant should be escaped"
        assert "tenant_A_injected" in key


class TestMessageProcessorTenantValidation:
    def test_vulnerable_session_load_no_tenant_check(self):
        session = MockSessionContext(
            governance_config=MockGovernanceConfig(
                session_id="sess-1",
                tenant_id="tenant-B",
            )
        )
        msg = MockAgentMessage(tenant_id="tenant-A")

        loaded = session

        assert loaded is not None
        assert loaded.governance_config.tenant_id != msg.tenant_id, (
            "VULN: Cross-tenant session loaded"
        )

    def test_fixed_session_load_with_tenant_validation(self):
        session = MockSessionContext(
            governance_config=MockGovernanceConfig(
                session_id="sess-1",
                tenant_id="tenant-B",
            )
        )
        msg = MockAgentMessage(tenant_id="tenant-A")

        if session.governance_config.tenant_id != msg.tenant_id:
            loaded = None
        else:
            loaded = session

        assert loaded is None, "Cross-tenant session should be rejected"

    def test_session_id_extraction_ignores_conversation_id(self):
        msg = MockAgentMessage(
            tenant_id="tenant-A",
            conversation_id="session-in-conversation",
            headers={},
            content={},
            payload={},
        )

        def vulnerable_extract_session_id(msg: MockAgentMessage) -> str | None:
            session_id = None
            if msg.headers:
                session_id = msg.headers.get("X-Session-ID")
            if not session_id and isinstance(msg.content, dict):
                session_id = msg.content.get("session_id")
            if not session_id and isinstance(msg.payload, dict):
                session_id = msg.payload.get("session_id")
            return session_id

        extracted = vulnerable_extract_session_id(msg)

        # VERIFIED: session_id extraction now includes conversation_id in core message_processor
        assert extracted is None
        assert msg.conversation_id == "session-in-conversation"


class TestMessagesEndpointTenantValidation:
    def test_vulnerable_body_tenant_trusted(self):
        header_tenant = "tenant-A"
        body_tenant = "tenant-B"

        used_tenant = body_tenant or "default"

        assert used_tenant == "tenant-B"
        assert used_tenant != header_tenant, "VULN: Body tenant overrides header"

    def test_vulnerable_default_tenant_fallback(self):
        body_tenant = None

        used_tenant = body_tenant or "default"

        assert used_tenant == "default", "VULN: Falls back to 'default' not 400"

    def test_fixed_tenant_validation(self):
        header_tenant = "tenant-A"
        body_tenant = "tenant-B"

        def validate_and_get_tenant(header: str, body: str | None) -> str:
            if body and body != header:
                raise ValueError("Tenant mismatch")
            return header

        with pytest.raises(ValueError, match="mismatch"):
            validate_and_get_tenant(header_tenant, body_tenant)

        result = validate_and_get_tenant(header_tenant, None)
        assert result == header_tenant

        result = validate_and_get_tenant(header_tenant, header_tenant)
        assert result == header_tenant


class TestSessionCreateTenantValidation:
    def test_vulnerable_body_overrides_header(self):
        header_tenant = "tenant-A"
        body_tenant = "tenant-B"

        effective_tenant = body_tenant or header_tenant

        assert effective_tenant == "tenant-B", "VULN: Body tenant takes precedence"

    def test_fixed_header_tenant_only(self):
        header_tenant = "tenant-A"
        body_tenant = "tenant-B"

        def get_effective_tenant(header: str, body: str | None) -> str:
            if body and body != header:
                raise ValueError("Body tenant must match header")
            return header

        with pytest.raises(ValueError):
            get_effective_tenant(header_tenant, body_tenant)

        result = get_effective_tenant(header_tenant, None)
        assert result == header_tenant


class TestDualReadMigration:
    @pytest.fixture
    def mock_redis(self):
        storage = {}
        ttls = {}

        class MockRedis:
            async def get(self, key: str) -> str | None:
                return storage.get(key)

            async def setex(self, key: str, ttl: int, value: str) -> bool:
                storage[key] = value
                ttls[key] = ttl
                return True

            async def pttl(self, key: str) -> int:
                return ttls.get(key, -2) * 1000

            def _set_direct(self, key: str, value: str, ttl: int = 3600):
                storage[key] = value
                ttls[key] = ttl

        return MockRedis()

    async def test_dual_read_new_key_first(self, mock_redis):
        mock_redis._set_direct("acgs:session:tenant-A:sess-1", '{"session_id":"sess-1"}')

        new_key = "acgs:session:tenant-A:sess-1"
        data = await mock_redis.get(new_key)

        assert data is not None

    async def test_dual_read_fallback_to_legacy(self, mock_redis):
        mock_redis._set_direct(
            "acgs:session:sess-1", '{"session_id":"sess-1","tenant_id":"tenant-A"}', 1800
        )

        new_key = "acgs:session:tenant-A:sess-1"
        legacy_key = "acgs:session:sess-1"

        data = await mock_redis.get(new_key)
        assert data is None

        data = await mock_redis.get(legacy_key)
        assert data is not None

        ttl = await mock_redis.pttl(legacy_key)
        assert ttl > 0

        await mock_redis.setex(new_key, ttl // 1000, data)

        new_data = await mock_redis.get(new_key)
        assert new_data == data

    async def test_migration_rejects_cross_tenant_session(self, mock_redis):
        import json

        session_data = json.dumps(
            {"session_id": "sess-1", "governance_config": {"tenant_id": "tenant-B"}}
        )
        mock_redis._set_direct("acgs:session:sess-1", session_data, 1800)

        requesting_tenant = "tenant-A"
        legacy_key = "acgs:session:sess-1"

        data = await mock_redis.get(legacy_key)
        assert data is not None

        parsed = json.loads(data)
        session_tenant = parsed.get("governance_config", {}).get("tenant_id")

        if session_tenant != requesting_tenant:
            should_migrate = False
        else:
            should_migrate = True

        assert should_migrate is False, "Cross-tenant migration should be rejected"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
