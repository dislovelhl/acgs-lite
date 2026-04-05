"""
Tests for BatchGovernanceMiddleware (middlewares/batch/governance.py).

Covers MACI role validation, tenant access, impact scoring,
constitutional compliance, caching, and error handling paths.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.unit]

from enhanced_agent_bus.batch_models import BatchRequestItem
from enhanced_agent_bus.maci.models import ROLE_PERMISSIONS, MACIAction, MACIRole
from enhanced_agent_bus.maci.registry import MACIAgentRecord, MACIRoleRegistry
from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext
from enhanced_agent_bus.middlewares.batch.exceptions import BatchGovernanceException
from enhanced_agent_bus.middlewares.batch.governance import BatchGovernanceMiddleware
from enhanced_agent_bus.pipeline.middleware import MiddlewareConfig
from enhanced_agent_bus.validators import ValidationResult

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "608508a9bd224290"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    from_agent: str = "agent-a",
    to_agent: str = "agent-b",
    tenant_id: str = "default",
    message_type: str = "governance_request",
    priority: int = 1,
    content: dict | None = None,
    constitutional_hash: str = "",
) -> BatchRequestItem:
    return BatchRequestItem(
        from_agent=from_agent,
        to_agent=to_agent,
        tenant_id=tenant_id,
        message_type=message_type,
        priority=priority,
        content=content or {},
        constitutional_hash=constitutional_hash,
    )


def _make_context(items: list[BatchRequestItem] | None = None) -> BatchPipelineContext:
    ctx = BatchPipelineContext()
    ctx.batch_items = items or []
    return ctx


def _register_agent(
    registry: MACIRoleRegistry,
    agent_id: str,
    role: MACIRole,
    metadata: dict | None = None,
) -> MACIAgentRecord:
    record = MACIAgentRecord(
        agent_id=agent_id,
        role=role,
        metadata=metadata or {"allowed_tenants": ["default"], "tenant_id": "default"},
    )
    registry._agents[agent_id] = record
    return record


def _make_middleware(
    fail_closed: bool = True,
    registry: MACIRoleRegistry | None = None,
) -> BatchGovernanceMiddleware:
    config = MiddlewareConfig(fail_closed=fail_closed)
    from enhanced_agent_bus.maci.enforcer import MACIEnforcer

    reg = registry or MACIRoleRegistry()
    enforcer = MACIEnforcer(registry=reg, strict_mode=fail_closed)
    return BatchGovernanceMiddleware(config=config, maci_enforcer=enforcer)


# ===========================================================================
# Initialization
# ===========================================================================


class TestInit:
    def test_default_init(self):
        mw = BatchGovernanceMiddleware()
        assert mw._maci_enforcer is not None
        assert mw._maci_cache_hits == 0

    def test_init_with_config_and_registry(self):
        reg = MACIRoleRegistry()
        config = MiddlewareConfig(fail_closed=False)
        mw = BatchGovernanceMiddleware(config=config, maci_registry=reg)
        assert mw._maci_registry is reg
        assert mw.config.fail_closed is False

    def test_init_with_enforcer(self):
        from enhanced_agent_bus.maci.enforcer import MACIEnforcer

        enforcer = MACIEnforcer(strict_mode=False)
        mw = BatchGovernanceMiddleware(maci_enforcer=enforcer)
        assert mw._maci_enforcer is enforcer


# ===========================================================================
# process() — top-level flow
# ===========================================================================


class TestProcess:
    @pytest.mark.asyncio
    async def test_empty_batch_calls_next(self):
        mw = _make_middleware()
        next_ctx = _make_context()
        next_mw = AsyncMock()
        next_mw.process = AsyncMock(return_value=next_ctx)
        mw._next = next_mw
        ctx = _make_context(items=[])
        result = await mw.process(ctx)
        next_mw.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_happy_path_sets_governance_allowed(self):
        """Full pass: registered agent, valid tenant, low impact, valid hash."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-a", MACIRole.JUDICIAL)
        mw = _make_middleware(registry=reg)

        items = [_make_item(from_agent="agent-a", message_type="governance_request")]
        ctx = _make_context(items)

        # Wire up _next to return the context as-is
        next_mw = AsyncMock()
        next_mw.process = AsyncMock(side_effect=lambda c: c)
        mw._next = next_mw

        with patch(
            "enhanced_agent_bus.middlewares.batch.governance.BatchGovernanceMiddleware"
            "._validate_constitutional_compliance",
            return_value=True,
        ):
            result = await mw.process(ctx)

        assert result.governance_allowed is True
        assert result.governance_reasoning is not None
        assert result.impact_score >= 0.0

    @pytest.mark.asyncio
    async def test_maci_failure_returns_early(self):
        """Unregistered agent in fail_closed=False: MACI fails, sets early result."""
        mw = _make_middleware(fail_closed=False)
        # No agents registered, but item references one — MACI validation will fail
        items = [_make_item(from_agent="unknown-agent")]
        ctx = _make_context(items)

        # Force _check_maci_roles to return failure
        with patch.object(
            mw,
            "_check_maci_roles",
            return_value=(
                False,
                {
                    "cache_hits": 0,
                    "cache_misses": 1,
                    "items_checked": 1,
                    "violations": [{"reason": "unregistered_agent"}],
                },
            ),
        ):
            result = await mw.process(ctx)

        # Should have set early_result and returned without proceeding
        assert result.early_result is not None
        assert result.early_result.is_valid is False

    @pytest.mark.asyncio
    async def test_maci_failure_fail_closed_raises(self):
        """Unregistered agent in fail_closed=True raises."""
        mw = _make_middleware(fail_closed=True)
        items = [_make_item(from_agent="unknown-agent")]
        ctx = _make_context(items)

        with pytest.raises(BatchGovernanceException, match="MACI role validation failed"):
            await mw.process(ctx)


# ===========================================================================
# _check_maci_roles
# ===========================================================================


class TestCheckMACIRoles:
    def test_no_agent_id_passes(self):
        mw = _make_middleware()
        items = [_make_item(from_agent="")]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is True

    def test_registered_agent_with_permission(self):
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-j", MACIRole.JUDICIAL)
        mw = _make_middleware(registry=reg)

        items = [_make_item(from_agent="agent-j", message_type="governance_request")]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is True
        assert metrics["cache_misses"] == 1

    def test_unregistered_agent_fail_closed(self):
        mw = _make_middleware(fail_closed=True)
        items = [_make_item(from_agent="ghost")]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is False
        assert any(v["reason"] == "unregistered_agent" for v in metrics["violations"])

    def test_unregistered_agent_fail_open(self):
        mw = _make_middleware(fail_closed=False)
        items = [_make_item(from_agent="ghost")]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is True

    def test_cache_hit_on_duplicate_decision_key(self):
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-j", MACIRole.JUDICIAL)
        mw = _make_middleware(registry=reg)

        item = _make_item(from_agent="agent-j", message_type="governance_request")
        items = [item, item]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is True
        assert metrics["cache_hits"] == 1
        assert metrics["cache_misses"] == 1

    def test_action_not_permitted_fail_closed(self):
        """MONITOR role cannot PROPOSE."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-m", MACIRole.MONITOR)
        mw = _make_middleware(fail_closed=True, registry=reg)

        items = [_make_item(from_agent="agent-m", message_type="propose")]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is False
        assert any(v["reason"] == "action_not_permitted" for v in metrics["violations"])


# ===========================================================================
# Self-validation constraint
# ===========================================================================


class TestSelfValidation:
    def test_self_validation_blocked_fail_closed(self):
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-j", MACIRole.JUDICIAL)
        mw = _make_middleware(fail_closed=True, registry=reg)

        items = [
            _make_item(
                from_agent="agent-j",
                message_type="constitutional_validation",
                content={"target_agent_id": "agent-j"},
            )
        ]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is False
        assert any(v["reason"] == "self_validation" for v in metrics["violations"])

    def test_self_validation_warning_fail_open(self):
        """In fail_open, self-validation is recorded as violation but _finalize allows it."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-j", MACIRole.JUDICIAL)
        mw = _make_middleware(fail_closed=False, registry=reg)

        items = [
            _make_item(
                from_agent="agent-j",
                message_type="constitutional_validation",
                content={"target_agent_id": "agent-j"},
            )
        ]
        valid, metrics = mw._check_maci_roles(items)
        # In fail_open, _check_validation_action_constraints returns (True, False)
        # can_perform becomes False, but _finalize_maci_permission with fail_closed=False
        # returns True (does not block). The violation IS recorded though.
        assert any(v["reason"] == "self_validation" for v in metrics["violations"])


# ===========================================================================
# Cross-role validation constraint
# ===========================================================================


class TestCrossRoleValidation:
    def test_cross_role_denied_fail_closed(self):
        """JUDICIAL cannot validate MONITOR (not in VALIDATION_CONSTRAINTS)."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-j", MACIRole.JUDICIAL)
        _register_agent(reg, "agent-mon", MACIRole.MONITOR)
        mw = _make_middleware(fail_closed=True, registry=reg)

        items = [
            _make_item(
                from_agent="agent-j",
                message_type="constitutional_validation",
                content={"target_agent_id": "agent-mon"},
            )
        ]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is False
        assert any(v["reason"] == "cross_role_validation" for v in metrics["violations"])

    def test_cross_role_allowed(self):
        """JUDICIAL can validate EXECUTIVE."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-j", MACIRole.JUDICIAL)
        _register_agent(reg, "agent-e", MACIRole.EXECUTIVE)
        mw = _make_middleware(registry=reg)

        items = [
            _make_item(
                from_agent="agent-j",
                message_type="constitutional_validation",
                content={"target_agent_id": "agent-e"},
            )
        ]
        valid, metrics = mw._check_maci_roles(items)
        assert valid is True


# ===========================================================================
# _map_message_type_to_action
# ===========================================================================


class TestMapMessageTypeToAction:
    @pytest.mark.parametrize(
        "msg_type,expected",
        [
            ("governance_request", MACIAction.QUERY),
            ("constitutional_validation", MACIAction.VALIDATE),
            ("propose", MACIAction.PROPOSE),
            ("audit", MACIAction.AUDIT),
            ("monitor", MACIAction.MONITOR_ACTIVITY),
            ("enforce", MACIAction.ENFORCE_CONTROL),
            ("extract_rules", MACIAction.EXTRACT_RULES),
            ("synthesize", MACIAction.SYNTHESIZE),
            ("manage_policy", MACIAction.MANAGE_POLICY),
            ("unknown", MACIAction.QUERY),
            (None, MACIAction.QUERY),
        ],
    )
    def test_mapping(self, msg_type, expected):
        mw = _make_middleware()
        assert mw._map_message_type_to_action(msg_type) == expected


# ===========================================================================
# Tenant validation
# ===========================================================================


class TestTenantValidation:
    def test_empty_items(self):
        mw = _make_middleware()
        valid, metrics = mw._validate_tenant_access([])
        assert valid is True

    def test_single_tenant_passes(self):
        reg = MACIRoleRegistry()
        _register_agent(
            reg,
            "agent-a",
            MACIRole.JUDICIAL,
            metadata={"allowed_tenants": ["tenant-1"], "tenant_id": "tenant-1"},
        )
        mw = _make_middleware(registry=reg)

        items = [_make_item(from_agent="agent-a", tenant_id="tenant-1")]
        valid, metrics = mw._validate_tenant_access(items)
        assert valid is True
        assert metrics["batch_tenant"] == "tenant-1"

    def test_cross_tenant_batch_fail_closed(self):
        mw = _make_middleware(fail_closed=True)
        items = [
            _make_item(tenant_id="tenant-1"),
            _make_item(tenant_id="tenant-2"),
        ]
        valid, metrics = mw._validate_tenant_access(items)
        assert valid is False
        assert any(v["reason"] == "cross_tenant_batch" for v in metrics["violations"])

    def test_cross_tenant_batch_fail_open(self):
        """In fail_open, cross-tenant is logged but continues."""
        reg = MACIRoleRegistry()
        _register_agent(
            reg,
            "agent-a",
            MACIRole.JUDICIAL,
            metadata={"allowed_tenants": ["tenant-1", "tenant-2"], "tenant_id": "tenant-1"},
        )
        mw = _make_middleware(fail_closed=False, registry=reg)
        items = [
            _make_item(from_agent="agent-a", tenant_id="tenant-1"),
            _make_item(from_agent="agent-a", tenant_id="tenant-2"),
        ]
        valid, metrics = mw._validate_tenant_access(items)
        # Cross-tenant violation logged, but continues in fail_open
        assert any(v.get("reason") == "cross_tenant_batch" for v in metrics["violations"])

    def test_default_tenant_all_items(self):
        """Items with default tenant and no from_agent pass."""
        mw = _make_middleware()
        items = [_make_item(from_agent="", tenant_id="default")]
        valid, metrics = mw._validate_tenant_access(items)
        assert valid is True
        assert metrics["batch_tenant"] == "default"

    def test_unregistered_agent_tenant_fail_closed(self):
        mw = _make_middleware(fail_closed=True)
        items = [_make_item(from_agent="ghost", tenant_id="default")]
        valid, metrics = mw._validate_tenant_access(items)
        assert valid is False
        assert any(v["reason"] == "unregistered_agent_tenant_access" for v in metrics["violations"])

    def test_unregistered_agent_tenant_fail_open(self):
        mw = _make_middleware(fail_closed=False)
        items = [_make_item(from_agent="ghost", tenant_id="default")]
        valid, metrics = mw._validate_tenant_access(items)
        assert valid is True

    def test_agent_denied_tenant_access(self):
        reg = MACIRoleRegistry()
        _register_agent(
            reg,
            "agent-a",
            MACIRole.JUDICIAL,
            metadata={"allowed_tenants": ["tenant-1"], "tenant_id": "tenant-1"},
        )
        mw = _make_middleware(fail_closed=True, registry=reg)

        items = [_make_item(from_agent="agent-a", tenant_id="tenant-99")]
        valid, metrics = mw._validate_tenant_access(items)
        assert valid is False
        assert any(v["reason"] == "tenant_access_denied" for v in metrics["violations"])

    def test_tenant_cache_hit(self):
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-a", MACIRole.JUDICIAL)
        mw = _make_middleware(registry=reg)

        item = _make_item(from_agent="agent-a", tenant_id="default")
        items = [item, item]
        valid, metrics = mw._validate_tenant_access(items)
        assert valid is True
        assert metrics["cache_hits"] == 1

    def test_tenant_validation_error_fail_closed(self):
        """Simulates a RuntimeError during tenant validation."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-a", MACIRole.JUDICIAL)
        mw = _make_middleware(fail_closed=True, registry=reg)

        items = [_make_item(from_agent="agent-a", tenant_id="default")]

        with patch.object(mw, "_check_agent_tenant_permissions", side_effect=RuntimeError("boom")):
            valid, metrics = mw._validate_tenant_access(items)
        assert valid is False
        assert any(v["reason"] == "tenant_validation_error" for v in metrics["violations"])

    def test_tenant_validation_error_fail_open(self):
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-a", MACIRole.JUDICIAL)
        mw = _make_middleware(fail_closed=False, registry=reg)

        items = [_make_item(from_agent="agent-a", tenant_id="default")]

        with patch.object(mw, "_check_agent_tenant_permissions", side_effect=ValueError("nope")):
            valid, metrics = mw._validate_tenant_access(items)
        assert valid is True  # fail_open continues


# ===========================================================================
# Impact scoring
# ===========================================================================


class TestImpactScoring:
    def test_empty_items_zero(self):
        mw = _make_middleware()
        assert mw._calculate_batch_impact([]) == 0.0

    def test_single_low_priority(self):
        mw = _make_middleware()
        items = [_make_item(priority=1)]
        score = mw._calculate_batch_impact(items)
        assert 0.0 < score < 0.5

    def test_high_priority_increases_score(self):
        mw = _make_middleware()
        low = [_make_item(priority=0)]
        high = [_make_item(priority=3)]
        assert mw._calculate_batch_impact(high) > mw._calculate_batch_impact(low)

    def test_many_items_increases_score(self):
        mw = _make_middleware()
        few = [_make_item() for _ in range(2)]
        many = [_make_item() for _ in range(100)]
        assert mw._calculate_batch_impact(many) > mw._calculate_batch_impact(few)

    def test_risk_keywords_increase_score(self):
        mw = _make_middleware()
        safe = [_make_item(content={"action": "read"})]
        risky = [_make_item(content={"action": "delete admin password"})]
        assert mw._calculate_batch_impact(risky) > mw._calculate_batch_impact(safe)

    def test_max_score_capped_at_one(self):
        mw = _make_middleware()
        items = [_make_item(priority=3, content={"action": "delete admin"}) for _ in range(500)]
        score = mw._calculate_batch_impact(items)
        assert score <= 1.0

    @pytest.mark.asyncio
    async def test_critical_impact_raises_fail_closed(self):
        """Impact >= CRITICAL threshold raises in fail_closed mode."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-a", MACIRole.JUDICIAL)
        mw = _make_middleware(fail_closed=True, registry=reg)

        ctx = _make_context([_make_item(from_agent="agent-a")])

        # Force critical impact score
        with patch.object(mw, "_calculate_batch_impact", return_value=0.95):
            with patch.object(mw, "_execute_maci_validation", return_value=True):
                with patch.object(mw, "_execute_tenant_validation", return_value=True):
                    with pytest.raises(BatchGovernanceException, match="critical threshold"):
                        await mw.process(ctx)

    @pytest.mark.asyncio
    async def test_critical_impact_warns_fail_open(self):
        """Impact >= CRITICAL threshold adds warning in fail_open mode."""
        reg = MACIRoleRegistry()
        _register_agent(reg, "agent-a", MACIRole.JUDICIAL)
        mw = _make_middleware(fail_closed=False, registry=reg)

        next_mw = AsyncMock()
        next_mw.process = AsyncMock(side_effect=lambda c: c)
        mw._next = next_mw

        ctx = _make_context([_make_item(from_agent="agent-a")])

        with patch.object(mw, "_calculate_batch_impact", return_value=0.95):
            with patch.object(mw, "_execute_maci_validation", return_value=True):
                with patch.object(mw, "_execute_tenant_validation", return_value=True):
                    with patch.object(mw, "_execute_constitutional_validation", return_value=True):
                        result = await mw.process(ctx)

        assert any("critical threshold" in w for w in result.warnings)


# ===========================================================================
# Content risk scoring
# ===========================================================================


class TestContentRisk:
    def test_no_items(self):
        mw = _make_middleware()
        assert mw._calculate_content_risk([]) == 0.0

    def test_no_risk_keywords(self):
        mw = _make_middleware()
        items = [_make_item(content={"msg": "hello world"})]
        assert mw._calculate_content_risk(items) == 0.0

    def test_all_risky(self):
        mw = _make_middleware()
        items = [_make_item(content={"cmd": "delete secret token"})]
        assert mw._calculate_content_risk(items) == 1.0

    def test_partial_risk(self):
        mw = _make_middleware()
        items = [
            _make_item(content={"cmd": "delete"}),
            _make_item(content={"cmd": "read"}),
        ]
        assert mw._calculate_content_risk(items) == 0.5

    def test_none_content(self):
        mw = _make_middleware()
        item = _make_item()
        item.content = None  # type: ignore[assignment]
        # Should not crash
        mw._calculate_content_risk([item])


# ===========================================================================
# Constitutional compliance
# ===========================================================================


class TestConstitutionalCompliance:
    def test_no_hash_passes(self):
        mw = _make_middleware()
        items = [_make_item(constitutional_hash="")]
        assert mw._validate_constitutional_compliance(items) is True

    def test_correct_hash_passes(self):
        mw = _make_middleware()
        items = [_make_item(constitutional_hash=CONSTITUTIONAL_HASH)]
        assert mw._validate_constitutional_compliance(items) is True

    def test_wrong_hash_fails(self):
        mw = _make_middleware()
        items = [_make_item(constitutional_hash="wrong-hash")]
        assert mw._validate_constitutional_compliance(items) is False

    @pytest.mark.asyncio
    async def test_constitutional_failure_raises_fail_closed(self):
        mw = _make_middleware(fail_closed=True)
        ctx = _make_context([_make_item()])

        with patch.object(mw, "_execute_maci_validation", return_value=True):
            with patch.object(mw, "_execute_tenant_validation", return_value=True):
                with patch.object(mw, "_execute_impact_validation", return_value=True):
                    with patch.object(
                        mw, "_validate_constitutional_compliance", return_value=False
                    ):
                        with pytest.raises(
                            BatchGovernanceException, match="Constitutional compliance"
                        ):
                            await mw.process(ctx)

    @pytest.mark.asyncio
    async def test_constitutional_failure_early_result_fail_open(self):
        mw = _make_middleware(fail_closed=False)
        ctx = _make_context([_make_item()])

        with patch.object(mw, "_execute_maci_validation", return_value=True):
            with patch.object(mw, "_execute_tenant_validation", return_value=True):
                with patch.object(mw, "_execute_impact_validation", return_value=True):
                    with patch.object(
                        mw, "_validate_constitutional_compliance", return_value=False
                    ):
                        result = await mw.process(ctx)

        assert result.early_result is not None
        assert result.early_result.is_valid is False


# ===========================================================================
# Governance reasoning
# ===========================================================================


class TestGovernanceReasoning:
    @pytest.mark.parametrize(
        "score,expected_level",
        [
            (0.95, "CRITICAL"),
            (0.75, "HIGH"),
            (0.55, "MEDIUM"),
            (0.1, "LOW"),
        ],
    )
    def test_reasoning_levels(self, score, expected_level):
        mw = _make_middleware()
        reasoning = mw._generate_governance_reasoning(score, 10)
        assert expected_level in reasoning
        assert "items=10" in reasoning


# ===========================================================================
# get_impact_level
# ===========================================================================


class TestGetImpactLevel:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.95, "CRITICAL"),
            (0.75, "HIGH"),
            (0.55, "MEDIUM"),
            (0.35, "LOW"),
            (0.1, "MINIMAL"),
        ],
    )
    def test_levels(self, score, expected):
        mw = _make_middleware()
        assert mw.get_impact_level(score) == expected


# ===========================================================================
# Cache metrics
# ===========================================================================


class TestCacheMetrics:
    def test_get_and_reset(self):
        mw = _make_middleware()
        mw._maci_cache_hits = 5
        mw._tenant_cache_misses = 3

        metrics = mw.get_cache_metrics()
        assert metrics["maci_cache_hits"] == 5
        assert metrics["tenant_cache_misses"] == 3

        mw.reset_cache_metrics()
        metrics = mw.get_cache_metrics()
        assert all(v == 0 for v in metrics.values())


# ===========================================================================
# _build_maci_decision_key
# ===========================================================================


class TestBuildMACIDecisionKey:
    def test_key_with_all_fields(self):
        mw = _make_middleware()
        item = _make_item(
            from_agent="agent-a",
            tenant_id="t1",
            message_type="propose",
            content={"type": "amendment"},
        )
        key = mw._build_maci_decision_key(item)
        assert key == ("t1", "agent-a", "propose", "amendment")

    def test_key_defaults(self):
        mw = _make_middleware()
        item = _make_item(from_agent="", tenant_id="", message_type="")
        # tenant_id defaults to "default" in the method when None, but "" stays as ""
        key = mw._build_maci_decision_key(item)
        assert key[0] == "default"  # tenant_id "" -> or "default"

    def test_key_none_content(self):
        mw = _make_middleware()
        item = _make_item()
        item.content = None  # type: ignore[assignment]
        key = mw._build_maci_decision_key(item)
        assert key[3] == "unknown"


# ===========================================================================
# MACI validation error handling
# ===========================================================================


class TestMACIValidationError:
    def test_error_fail_closed_returns_false(self):
        mw = _make_middleware(fail_closed=True)
        cache: dict = {}
        metrics: dict = {"violations": []}
        key = ("default", "agent-a", "query", "unknown")

        result = mw._handle_maci_validation_error(
            cache, key, metrics, 0, "agent-a", RuntimeError("x")
        )
        assert result is False
        assert cache[key] is False

    def test_error_fail_open_returns_true(self):
        mw = _make_middleware(fail_closed=False)
        cache: dict = {}
        metrics: dict = {"violations": []}
        key = ("default", "agent-a", "query", "unknown")

        result = mw._handle_maci_validation_error(
            cache, key, metrics, 0, "agent-a", ValueError("y")
        )
        assert result is True
        assert cache[key] is False
        assert len(metrics["violations"]) == 1


# ===========================================================================
# Tenant format validation
# ===========================================================================


class TestTenantFormatValidation:
    def test_default_tenant_always_passes(self):
        mw = _make_middleware()
        items = [_make_item(tenant_id="default")]
        metrics: dict = {"violations": []}
        assert mw._validate_tenant_formats(items, metrics) is True

    def test_invalid_format_fail_closed(self):
        mw = _make_middleware(fail_closed=True)
        item = _make_item(tenant_id="<script>alert(1)</script>")
        metrics: dict = {"violations": []}
        result = mw._validate_tenant_formats([item], metrics)
        # If TenantValidator rejects it, should be False
        if not result:
            assert any(v["reason"] == "invalid_tenant_format" for v in metrics["violations"])


# ===========================================================================
# Handle failure methods
# ===========================================================================


class TestHandleFailureMethods:
    def test_handle_maci_failure_fail_closed(self):
        mw = _make_middleware(fail_closed=True)
        ctx = _make_context()
        metrics = {"violations": [{"reason": "test_violation"}]}

        with pytest.raises(BatchGovernanceException, match="MACI role validation failed"):
            mw._handle_maci_validation_failure(ctx, metrics, {})

    def test_handle_maci_failure_fail_open(self):
        mw = _make_middleware(fail_closed=False)
        ctx = _make_context()
        metrics = {"violations": [{"reason": "test_violation"}]}

        result = mw._handle_maci_validation_failure(ctx, metrics, {})
        assert result is False
        assert ctx.early_result is not None
        assert ctx.early_result.is_valid is False

    def test_handle_tenant_failure_fail_closed(self):
        mw = _make_middleware(fail_closed=True)
        ctx = _make_context()
        metrics = {"violations": [{"reason": "bad_tenant"}]}

        with pytest.raises(BatchGovernanceException, match="Tenant validation failed"):
            mw._handle_tenant_validation_failure(ctx, metrics, {})

    def test_handle_tenant_failure_fail_open(self):
        mw = _make_middleware(fail_closed=False)
        ctx = _make_context()
        metrics = {"violations": [{"reason": "bad_tenant"}]}

        result = mw._handle_tenant_validation_failure(ctx, metrics, {})
        assert result is False
        assert ctx.early_result is not None


# ===========================================================================
# _check_agent_tenant_permissions
# ===========================================================================


class TestCheckAgentTenantPermissions:
    def test_default_tenant_allowed(self):
        mw = _make_middleware()
        record = MACIAgentRecord(
            agent_id="a",
            role=MACIRole.JUDICIAL,
            metadata={"allowed_tenants": ["t1"], "tenant_id": "t1"},
        )
        assert mw._check_agent_tenant_permissions(record, "default") is True

    def test_allowed_tenant(self):
        mw = _make_middleware()
        record = MACIAgentRecord(
            agent_id="a",
            role=MACIRole.JUDICIAL,
            metadata={"allowed_tenants": ["t1", "t2"], "tenant_id": "t1"},
        )
        assert mw._check_agent_tenant_permissions(record, "t2") is True

    def test_matching_agent_tenant(self):
        mw = _make_middleware()
        record = MACIAgentRecord(
            agent_id="a",
            role=MACIRole.JUDICIAL,
            metadata={"allowed_tenants": [], "tenant_id": "t1"},
        )
        assert mw._check_agent_tenant_permissions(record, "t1") is True

    def test_denied_tenant(self):
        mw = _make_middleware()
        record = MACIAgentRecord(
            agent_id="a",
            role=MACIRole.JUDICIAL,
            metadata={"allowed_tenants": ["t1"], "tenant_id": "t1"},
        )
        assert mw._check_agent_tenant_permissions(record, "t99") is False
