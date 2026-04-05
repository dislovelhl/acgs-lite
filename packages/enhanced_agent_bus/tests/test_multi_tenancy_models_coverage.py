# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/multi_tenancy/models.py.

Target: ≥95% line coverage of multi_tenancy/models.py (75 stmts).
"""

import uuid
from datetime import UTC, datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.multi_tenancy.models import (
    Tenant,
    TenantConfig,
    TenantQuota,
    TenantStatus,
    TenantUsage,
)

# ---------------------------------------------------------------------------
# TenantStatus enum
# ---------------------------------------------------------------------------


class TestTenantStatus:
    def test_values_are_strings(self) -> None:
        assert TenantStatus.PENDING == "pending"
        assert TenantStatus.ACTIVE == "active"
        assert TenantStatus.SUSPENDED == "suspended"
        assert TenantStatus.DEACTIVATED == "deactivated"
        assert TenantStatus.MIGRATING == "migrating"

    def test_all_members_present(self) -> None:
        names = {m.name for m in TenantStatus}
        assert names == {"PENDING", "ACTIVE", "SUSPENDED", "DEACTIVATED", "MIGRATING"}

    def test_is_str_subclass(self) -> None:
        assert isinstance(TenantStatus.ACTIVE, str)

    def test_equality_with_plain_string(self) -> None:
        assert TenantStatus.PENDING == "pending"
        assert TenantStatus.ACTIVE != "pending"

    def test_construction_from_string(self) -> None:
        assert TenantStatus("active") is TenantStatus.ACTIVE
        assert TenantStatus("suspended") is TenantStatus.SUSPENDED

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            TenantStatus("unknown")


# ---------------------------------------------------------------------------
# TenantQuota dataclass
# ---------------------------------------------------------------------------


class TestTenantQuotaDefaults:
    def test_default_values(self) -> None:
        q = TenantQuota()
        assert q.max_agents == 100
        assert q.max_policies == 1000
        assert q.max_messages_per_minute == 10000
        assert q.max_batch_size == 1000
        assert q.max_storage_mb == 10240
        assert q.max_concurrent_sessions == 100

    def test_custom_values(self) -> None:
        q = TenantQuota(
            max_agents=5,
            max_policies=50,
            max_messages_per_minute=500,
            max_batch_size=10,
            max_storage_mb=512,
            max_concurrent_sessions=20,
        )
        assert q.max_agents == 5
        assert q.max_policies == 50
        assert q.max_messages_per_minute == 500
        assert q.max_batch_size == 10
        assert q.max_storage_mb == 512
        assert q.max_concurrent_sessions == 20


class TestTenantQuotaToDict:
    def test_to_dict_returns_all_keys(self) -> None:
        q = TenantQuota()
        d = q.to_dict()
        assert set(d.keys()) == {
            "max_agents",
            "max_policies",
            "max_messages_per_minute",
            "max_batch_size",
            "max_storage_mb",
            "max_concurrent_sessions",
        }

    def test_to_dict_values_match_fields(self) -> None:
        q = TenantQuota(max_agents=7, max_policies=77)
        d = q.to_dict()
        assert d["max_agents"] == 7
        assert d["max_policies"] == 77

    def test_to_dict_all_int_values(self) -> None:
        q = TenantQuota()
        for v in q.to_dict().values():
            assert isinstance(v, int)


class TestTenantQuotaFromDict:
    def test_from_dict_defaults_when_empty(self) -> None:
        q = TenantQuota.from_dict({})
        assert q.max_agents == 100
        assert q.max_policies == 1000
        assert q.max_messages_per_minute == 10000
        assert q.max_batch_size == 1000
        assert q.max_storage_mb == 10240
        assert q.max_concurrent_sessions == 100

    def test_from_dict_custom_values(self) -> None:
        data = {
            "max_agents": 5,
            "max_policies": 50,
            "max_messages_per_minute": 500,
            "max_batch_size": 10,
            "max_storage_mb": 256,
            "max_concurrent_sessions": 25,
        }
        q = TenantQuota.from_dict(data)
        assert q.max_agents == 5
        assert q.max_policies == 50
        assert q.max_messages_per_minute == 500
        assert q.max_batch_size == 10
        assert q.max_storage_mb == 256
        assert q.max_concurrent_sessions == 25

    def test_from_dict_partial_override(self) -> None:
        q = TenantQuota.from_dict({"max_agents": 42})
        assert q.max_agents == 42
        assert q.max_policies == 1000  # default

    def test_round_trip(self) -> None:
        q1 = TenantQuota(max_agents=3, max_policies=30)
        q2 = TenantQuota.from_dict(q1.to_dict())
        assert q1.max_agents == q2.max_agents
        assert q1.max_policies == q2.max_policies

    def test_from_dict_returns_tenant_quota_instance(self) -> None:
        q = TenantQuota.from_dict({})
        assert isinstance(q, TenantQuota)


# ---------------------------------------------------------------------------
# TenantUsage dataclass
# ---------------------------------------------------------------------------


class TestTenantUsageDefaults:
    def test_default_values(self) -> None:
        u = TenantUsage()
        assert u.agent_count == 0
        assert u.policy_count == 0
        assert u.message_count_minute == 0
        assert u.storage_used_mb == 0.0
        assert u.concurrent_sessions == 0
        assert isinstance(u.last_updated, datetime)

    def test_last_updated_is_utc_aware(self) -> None:
        u = TenantUsage()
        assert u.last_updated.tzinfo is not None

    def test_custom_values(self) -> None:
        dt = datetime(2025, 1, 1, tzinfo=UTC)
        u = TenantUsage(
            agent_count=5,
            policy_count=10,
            message_count_minute=100,
            storage_used_mb=50.5,
            concurrent_sessions=3,
            last_updated=dt,
        )
        assert u.agent_count == 5
        assert u.policy_count == 10
        assert u.message_count_minute == 100
        assert u.storage_used_mb == 50.5
        assert u.concurrent_sessions == 3
        assert u.last_updated == dt


class TestTenantUsageToDict:
    def test_to_dict_keys(self) -> None:
        u = TenantUsage()
        d = u.to_dict()
        assert set(d.keys()) == {
            "agent_count",
            "policy_count",
            "message_count_minute",
            "storage_used_mb",
            "concurrent_sessions",
            "last_updated",
        }

    def test_to_dict_last_updated_is_isoformat(self) -> None:
        u = TenantUsage()
        d = u.to_dict()
        # Should be a valid ISO format string
        parsed = datetime.fromisoformat(d["last_updated"])
        assert isinstance(parsed, datetime)

    def test_to_dict_numeric_values(self) -> None:
        u = TenantUsage(
            agent_count=3,
            policy_count=5,
            message_count_minute=7,
            storage_used_mb=1.5,
            concurrent_sessions=2,
        )
        d = u.to_dict()
        assert d["agent_count"] == 3
        assert d["policy_count"] == 5
        assert d["message_count_minute"] == 7
        assert d["storage_used_mb"] == 1.5
        assert d["concurrent_sessions"] == 2


class TestTenantUsageIsWithinQuota:
    def _make_quota(self, **kwargs: Any) -> TenantQuota:
        defaults = {
            "max_agents": 10,
            "max_policies": 100,
            "max_messages_per_minute": 1000,
            "max_batch_size": 50,
            "max_storage_mb": 500,
            "max_concurrent_sessions": 20,
        }
        defaults.update(kwargs)
        return TenantQuota(**defaults)

    def test_all_zeros_within_quota(self) -> None:
        u = TenantUsage()
        q = self._make_quota()
        assert u.is_within_quota(q) is True

    def test_at_exact_limits_is_within(self) -> None:
        q = self._make_quota(
            max_agents=5,
            max_policies=50,
            max_messages_per_minute=200,
            max_storage_mb=100,
            max_concurrent_sessions=10,
        )
        u = TenantUsage(
            agent_count=5,
            policy_count=50,
            message_count_minute=200,
            storage_used_mb=100.0,
            concurrent_sessions=10,
        )
        assert u.is_within_quota(q) is True

    def test_agent_count_exceeds_quota(self) -> None:
        q = self._make_quota(max_agents=5)
        u = TenantUsage(agent_count=6)
        assert u.is_within_quota(q) is False

    def test_policy_count_exceeds_quota(self) -> None:
        q = self._make_quota(max_policies=10)
        u = TenantUsage(policy_count=11)
        assert u.is_within_quota(q) is False

    def test_message_count_exceeds_quota(self) -> None:
        q = self._make_quota(max_messages_per_minute=100)
        u = TenantUsage(message_count_minute=101)
        assert u.is_within_quota(q) is False

    def test_storage_exceeds_quota(self) -> None:
        q = self._make_quota(max_storage_mb=50)
        u = TenantUsage(storage_used_mb=50.1)
        assert u.is_within_quota(q) is False

    def test_concurrent_sessions_exceeds_quota(self) -> None:
        q = self._make_quota(max_concurrent_sessions=5)
        u = TenantUsage(concurrent_sessions=6)
        assert u.is_within_quota(q) is False

    def test_multiple_violations(self) -> None:
        q = self._make_quota(max_agents=1, max_policies=1)
        u = TenantUsage(agent_count=10, policy_count=10)
        assert u.is_within_quota(q) is False

    def test_one_field_over_rest_ok(self) -> None:
        q = self._make_quota(max_agents=2)
        # Only agent_count exceeds
        u = TenantUsage(
            agent_count=3,
            policy_count=0,
            message_count_minute=0,
            storage_used_mb=0.0,
            concurrent_sessions=0,
        )
        assert u.is_within_quota(q) is False


# ---------------------------------------------------------------------------
# TenantConfig Pydantic model
# ---------------------------------------------------------------------------


class TestTenantConfigDefaults:
    def test_default_constitutional_hash(self) -> None:
        cfg = TenantConfig()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_feature_flags_defaults(self) -> None:
        cfg = TenantConfig()
        assert cfg.enable_batch_processing is True
        assert cfg.enable_deliberation is True
        assert cfg.enable_blockchain_anchoring is False
        assert cfg.enable_maci_enforcement is True

    def test_performance_defaults(self) -> None:
        cfg = TenantConfig()
        assert cfg.default_timeout_ms == 5000
        assert cfg.cache_ttl_seconds == 300

    def test_security_defaults(self) -> None:
        cfg = TenantConfig()
        assert cfg.require_jwt_auth is True
        assert cfg.allowed_ip_ranges == []

    def test_integration_defaults(self) -> None:
        cfg = TenantConfig()
        assert cfg.sso_provider is None
        assert cfg.sso_config == {}


class TestTenantConfigCustomValues:
    def test_custom_constitutional_hash(self) -> None:
        cfg = TenantConfig(constitutional_hash="abc123")
        assert cfg.constitutional_hash == "abc123"

    def test_disable_features(self) -> None:
        cfg = TenantConfig(
            enable_batch_processing=False,
            enable_deliberation=False,
            enable_blockchain_anchoring=True,
            enable_maci_enforcement=False,
        )
        assert cfg.enable_batch_processing is False
        assert cfg.enable_deliberation is False
        assert cfg.enable_blockchain_anchoring is True
        assert cfg.enable_maci_enforcement is False

    def test_custom_performance_settings(self) -> None:
        cfg = TenantConfig(default_timeout_ms=10000, cache_ttl_seconds=600)
        assert cfg.default_timeout_ms == 10000
        assert cfg.cache_ttl_seconds == 600

    def test_allowed_ip_ranges(self) -> None:
        cfg = TenantConfig(allowed_ip_ranges=["10.0.0.0/8", "192.168.0.0/16"])
        assert cfg.allowed_ip_ranges == ["10.0.0.0/8", "192.168.0.0/16"]

    def test_sso_provider(self) -> None:
        cfg = TenantConfig(sso_provider="saml", sso_config={"entity_id": "foo"})
        assert cfg.sso_provider == "saml"
        assert cfg.sso_config["entity_id"] == "foo"

    def test_extra_fields_allowed(self) -> None:
        cfg = TenantConfig(custom_field="hello")
        assert cfg.custom_field == "hello"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tenant Pydantic model
# ---------------------------------------------------------------------------


class TestTenantCreation:
    def test_minimal_required_fields(self) -> None:
        t = Tenant(name="Acme Corp", slug="acme-corp")
        assert t.name == "Acme Corp"
        assert t.slug == "acme-corp"

    def test_tenant_id_auto_generated(self) -> None:
        t = Tenant(name="A", slug="a0")
        # Should be a valid UUID string
        parsed = uuid.UUID(t.tenant_id)
        assert str(parsed) == t.tenant_id

    def test_tenant_id_unique_per_instance(self) -> None:
        t1 = Tenant(name="A", slug="a0")
        t2 = Tenant(name="B", slug="b0")
        assert t1.tenant_id != t2.tenant_id

    def test_default_status_pending(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.status == TenantStatus.PENDING

    def test_default_constitutional_hash(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.constitutional_hash == CONSTITUTIONAL_HASH

    def test_timestamps_are_utc_aware(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.created_at.tzinfo is not None
        assert t.updated_at.tzinfo is not None

    def test_activated_at_none_by_default(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.activated_at is None

    def test_suspended_at_none_by_default(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.suspended_at is None

    def test_parent_tenant_id_none_by_default(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.parent_tenant_id is None

    def test_config_is_tenant_config(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert isinstance(t.config, TenantConfig)

    def test_quota_has_default_keys(self) -> None:
        t = Tenant(name="A", slug="a0")
        expected_keys = {
            "max_agents",
            "max_policies",
            "max_messages_per_minute",
            "max_batch_size",
            "max_storage_mb",
            "max_concurrent_sessions",
        }
        assert set(t.quota.keys()) == expected_keys

    def test_metadata_empty_by_default(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.metadata == {}

    def test_extra_fields_allowed(self) -> None:
        t = Tenant(name="A", slug="a0", extra_info="test")
        assert t.extra_info == "test"  # type: ignore[attr-defined]


class TestTenantSlugValidation:
    def test_valid_slug_alphanumeric(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.slug == "a0"

    def test_valid_slug_with_dashes(self) -> None:
        t = Tenant(name="A", slug="my-org-name")
        assert t.slug == "my-org-name"

    def test_slug_must_start_with_alnum(self) -> None:
        with pytest.raises(ValidationError):
            Tenant(name="A", slug="-bad-slug")

    def test_slug_must_end_with_alnum(self) -> None:
        with pytest.raises(ValidationError):
            Tenant(name="A", slug="bad-slug-")

    def test_slug_max_length_63(self) -> None:
        slug = "a" * 31 + "-" + "b" * 31  # 63 chars
        t = Tenant(name="A", slug=slug)
        assert t.slug == slug

    def test_slug_too_long(self) -> None:
        slug = "a" * 32 + "-" + "b" * 32  # 65 chars
        with pytest.raises(ValidationError):
            Tenant(name="A", slug=slug)

    def test_slug_too_short(self) -> None:
        with pytest.raises(ValidationError):
            Tenant(name="A", slug="")

    def test_name_too_long(self) -> None:
        with pytest.raises(ValidationError):
            Tenant(name="X" * 256, slug="valid-slug")

    def test_name_too_short(self) -> None:
        with pytest.raises(ValidationError):
            Tenant(name="", slug="valid-slug")


class TestTenantMethods:
    def _make_active_tenant(self) -> Tenant:
        return Tenant(name="Acme", slug="acme", status=TenantStatus.ACTIVE)

    def _make_pending_tenant(self) -> Tenant:
        return Tenant(name="Acme", slug="acme", status=TenantStatus.PENDING)

    # is_active()
    def test_is_active_true_when_active(self) -> None:
        t = self._make_active_tenant()
        assert t.is_active() is True

    def test_is_active_false_when_pending(self) -> None:
        t = self._make_pending_tenant()
        assert t.is_active() is False

    def test_is_active_false_when_suspended(self) -> None:
        t = Tenant(name="A", slug="a0", status=TenantStatus.SUSPENDED)
        assert t.is_active() is False

    def test_is_active_false_when_deactivated(self) -> None:
        t = Tenant(name="A", slug="a0", status=TenantStatus.DEACTIVATED)
        assert t.is_active() is False

    def test_is_active_false_when_migrating(self) -> None:
        t = Tenant(name="A", slug="a0", status=TenantStatus.MIGRATING)
        assert t.is_active() is False

    # get_quota()
    def test_get_quota_returns_tenant_quota_instance(self) -> None:
        t = Tenant(name="A", slug="a0")
        q = t.get_quota()
        assert isinstance(q, TenantQuota)

    def test_get_quota_reflects_custom_quota(self) -> None:
        custom_quota = TenantQuota(max_agents=42).to_dict()
        t = Tenant(name="A", slug="a0", quota=custom_quota)
        q = t.get_quota()
        assert q.max_agents == 42

    def test_get_quota_default_values(self) -> None:
        t = Tenant(name="A", slug="a0")
        q = t.get_quota()
        assert q.max_agents == 100
        assert q.max_policies == 1000

    # validate_constitutional_compliance()
    def test_validate_compliance_true_by_default(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.validate_constitutional_compliance() is True

    def test_validate_compliance_false_when_tenant_hash_wrong(self) -> None:
        t = Tenant(name="A", slug="a0", constitutional_hash="wrong-hash")
        assert t.validate_constitutional_compliance() is False

    def test_validate_compliance_false_when_config_hash_wrong(self) -> None:
        cfg = TenantConfig(constitutional_hash="wrong-hash")
        t = Tenant(name="A", slug="a0", config=cfg)
        assert t.validate_constitutional_compliance() is False

    def test_validate_compliance_false_when_both_hashes_wrong(self) -> None:
        cfg = TenantConfig(constitutional_hash="bad")
        t = Tenant(name="A", slug="a0", constitutional_hash="bad", config=cfg)
        assert t.validate_constitutional_compliance() is False

    def test_validate_compliance_true_with_correct_hashes(self) -> None:
        cfg = TenantConfig(constitutional_hash=CONSTITUTIONAL_HASH)
        t = Tenant(name="A", slug="a0", constitutional_hash=CONSTITUTIONAL_HASH, config=cfg)
        assert t.validate_constitutional_compliance() is True

    # to_rls_context()
    def test_to_rls_context_keys(self) -> None:
        t = Tenant(name="A", slug="a0")
        ctx = t.to_rls_context()
        assert set(ctx.keys()) == {"tenant_id", "constitutional_hash"}

    def test_to_rls_context_tenant_id_matches(self) -> None:
        t = Tenant(name="A", slug="a0")
        ctx = t.to_rls_context()
        assert ctx["tenant_id"] == t.tenant_id

    def test_to_rls_context_hash_matches(self) -> None:
        t = Tenant(name="A", slug="a0")
        ctx = t.to_rls_context()
        assert ctx["constitutional_hash"] == t.constitutional_hash

    def test_to_rls_context_returns_strings(self) -> None:
        t = Tenant(name="A", slug="a0")
        ctx = t.to_rls_context()
        for v in ctx.values():
            assert isinstance(v, str)


class TestTenantWithExplicitValues:
    def test_explicit_tenant_id(self) -> None:
        tid = "12345678-1234-5678-1234-567812345678"
        t = Tenant(name="A", slug="a0", tenant_id=tid)
        assert t.tenant_id == tid

    def test_explicit_timestamps(self) -> None:
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        t = Tenant(name="A", slug="a0", created_at=dt, updated_at=dt)
        assert t.created_at == dt
        assert t.updated_at == dt

    def test_activated_at_explicit(self) -> None:
        dt = datetime(2024, 6, 1, tzinfo=UTC)
        t = Tenant(name="A", slug="a0", activated_at=dt)
        assert t.activated_at == dt

    def test_suspended_at_explicit(self) -> None:
        dt = datetime(2024, 6, 1, tzinfo=UTC)
        t = Tenant(name="A", slug="a0", suspended_at=dt)
        assert t.suspended_at == dt

    def test_parent_tenant_id_explicit(self) -> None:
        parent = "parent-000-id"
        t = Tenant(name="A", slug="a0", parent_tenant_id=parent)
        assert t.parent_tenant_id == parent

    def test_metadata_explicit(self) -> None:
        meta = {"env": "prod", "region": "us-east"}
        t = Tenant(name="A", slug="a0", metadata=meta)
        assert t.metadata == meta

    def test_status_active_explicit(self) -> None:
        t = Tenant(name="A", slug="a0", status=TenantStatus.ACTIVE)
        assert t.status == TenantStatus.ACTIVE

    def test_status_suspended_explicit(self) -> None:
        t = Tenant(name="A", slug="a0", status=TenantStatus.SUSPENDED)
        assert t.status == TenantStatus.SUSPENDED

    def test_full_construction(self) -> None:
        """Construct a fully specified Tenant with all fields."""
        tid = str(uuid.uuid4())
        dt = datetime(2024, 1, 1, tzinfo=UTC)
        cfg = TenantConfig(enable_blockchain_anchoring=True)
        quota_dict = TenantQuota(max_agents=50).to_dict()
        t = Tenant(
            tenant_id=tid,
            name="Full Corp",
            slug="full-corp",
            status=TenantStatus.ACTIVE,
            config=cfg,
            quota=quota_dict,
            metadata={"plan": "enterprise"},
            created_at=dt,
            updated_at=dt,
            activated_at=dt,
            suspended_at=None,
            parent_tenant_id=None,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        assert t.tenant_id == tid
        assert t.name == "Full Corp"
        assert t.slug == "full-corp"
        assert t.status == TenantStatus.ACTIVE
        assert t.config.enable_blockchain_anchoring is True
        assert t.get_quota().max_agents == 50
        assert t.metadata["plan"] == "enterprise"
        assert t.created_at == dt
        assert t.validate_constitutional_compliance() is True
        assert t.is_active() is True


# ---------------------------------------------------------------------------
# Integration: quota round-trip via Tenant
# ---------------------------------------------------------------------------


class TestTenantQuotaRoundTrip:
    def test_custom_quota_roundtrip_via_tenant(self) -> None:
        q_in = TenantQuota(
            max_agents=77,
            max_policies=888,
            max_messages_per_minute=9999,
            max_batch_size=333,
            max_storage_mb=2048,
            max_concurrent_sessions=55,
        )
        t = Tenant(name="Rt", slug="rt", quota=q_in.to_dict())
        q_out = t.get_quota()
        assert q_out.max_agents == 77
        assert q_out.max_policies == 888
        assert q_out.max_messages_per_minute == 9999
        assert q_out.max_batch_size == 333
        assert q_out.max_storage_mb == 2048
        assert q_out.max_concurrent_sessions == 55


# ---------------------------------------------------------------------------
# TenantUsage + TenantQuota quota-check edge cases
# ---------------------------------------------------------------------------


class TestTenantUsageQuotaEdgeCases:
    def test_storage_float_precision(self) -> None:
        q = TenantQuota(max_storage_mb=100)
        u = TenantUsage(storage_used_mb=99.9999)
        assert u.is_within_quota(q) is True

    def test_storage_barely_over(self) -> None:
        q = TenantQuota(max_storage_mb=100)
        u = TenantUsage(storage_used_mb=100.0001)
        assert u.is_within_quota(q) is False

    def test_all_zeros_with_zero_quota(self) -> None:
        q = TenantQuota(
            max_agents=0,
            max_policies=0,
            max_messages_per_minute=0,
            max_batch_size=0,
            max_storage_mb=0,
            max_concurrent_sessions=0,
        )
        u = TenantUsage()
        assert u.is_within_quota(q) is True  # 0 <= 0

    def test_any_usage_with_zero_quota_fails(self) -> None:
        q = TenantQuota(
            max_agents=0,
            max_policies=0,
            max_messages_per_minute=0,
            max_batch_size=0,
            max_storage_mb=0,
            max_concurrent_sessions=0,
        )
        u = TenantUsage(agent_count=1)
        assert u.is_within_quota(q) is False


# ---------------------------------------------------------------------------
# TenantConfig pydantic model_config extra="allow"
# ---------------------------------------------------------------------------


class TestTenantConfigModelConfig:
    def test_serialize_to_dict(self) -> None:
        cfg = TenantConfig()
        d = cfg.model_dump()
        assert "constitutional_hash" in d
        assert "enable_batch_processing" in d

    def test_serialization_round_trip(self) -> None:
        cfg1 = TenantConfig(cache_ttl_seconds=999)
        data = cfg1.model_dump()
        cfg2 = TenantConfig(**data)
        assert cfg2.cache_ttl_seconds == 999


# ---------------------------------------------------------------------------
# CONSTITUTIONAL_HASH import from models module
# ---------------------------------------------------------------------------


class TestConstitutionalHashConstant:
    def test_hash_value(self) -> None:
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_tenant_default_hash_equals_constant(self) -> None:
        t = Tenant(name="A", slug="a0")
        assert t.constitutional_hash == CONSTITUTIONAL_HASH

    def test_tenant_config_default_hash_equals_constant(self) -> None:
        cfg = TenantConfig()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH
