"""
Coverage tests for:
- enterprise_sso/tenant_sso_config.py
- workflows/workflow_base.py
- message_processor_components.py

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.errors import (
    ConstitutionalViolationError,
    ResourceNotFoundError,
    ServiceUnavailableError,
)
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.core_models import AgentMessage, MessageType, get_enum_value
from enhanced_agent_bus.enterprise_sso.tenant_sso_config import (
    CONSTITUTIONAL_HASH as SSO_HASH,
)

# ---------------------------------------------------------------------------
# tenant_sso_config
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.tenant_sso_config import (
    AttributeMapping,
    IdPProviderType,
    OIDCConfig,
    RoleMappingRule,
    SAMLConfig,
    SSOProtocolType,
    TenantIdPConfig,
    TenantSSOConfig,
    TenantSSOConfigManager,
    create_azure_ad_idp_config,
    create_google_workspace_idp_config,
    create_okta_idp_config,
)

# ---------------------------------------------------------------------------
# message_processor_components
# ---------------------------------------------------------------------------
from enhanced_agent_bus.message_processor_components import (
    apply_latency_metadata,
    apply_session_governance_metrics,
    build_dlq_entry,
    calculate_session_resolution_rate,
    compute_message_cache_key,
    enforce_autonomy_tier_rules,
    enrich_metrics_with_opa_stats,
    enrich_metrics_with_workflow_telemetry,
    extract_pqc_failure_result,
    extract_rejection_reason,
    extract_session_id_for_governance,
    extract_session_id_for_pacar,
    merge_verification_metadata,
    prepare_message_content_string,
    run_message_validation_gates,
    schedule_background_task,
)
from enhanced_agent_bus.validators import ValidationResult
from enhanced_agent_bus.verification_orchestrator import VerificationResult
from enhanced_agent_bus.workflows.workflow_base import (
    CONSTITUTIONAL_HASH as WF_HASH,
)

# ---------------------------------------------------------------------------
# workflow_base
# ---------------------------------------------------------------------------
from enhanced_agent_bus.workflows.workflow_base import (
    InMemoryWorkflowExecutor,
    Query,
    Signal,
    WorkflowContext,
    WorkflowDefinition,
    WorkflowStatus,
)
from enhanced_agent_bus.workflows.workflow_base import (
    query as query_decorator,
)
from enhanced_agent_bus.workflows.workflow_base import (
    signal as signal_decorator,
)

# ===================================================================
# SAML / OIDC Config tests
# ===================================================================


class TestSAMLConfig:
    def test_to_dict_and_from_dict_roundtrip(self):
        cfg = SAMLConfig(entity_id="eid", sso_url="https://sso.example.com")
        d = cfg.to_dict()
        restored = SAMLConfig.from_dict(d)
        assert restored.entity_id == "eid"
        assert restored.sso_url == "https://sso.example.com"
        assert restored.slo_url is None
        assert restored.authn_request_signed is True

    def test_from_dict_custom_values(self):
        data = {
            "entity_id": "e",
            "sso_url": "https://u",
            "slo_url": "https://slo",
            "x509_certificate": "cert",
            "x509_certificate_fingerprint": "fp",
            "name_id_format": "custom_format",
            "authn_request_signed": False,
            "want_assertions_signed": False,
            "want_response_signed": False,
            "binding": "custom_binding",
            "metadata_url": "https://meta",
        }
        cfg = SAMLConfig.from_dict(data)
        assert cfg.slo_url == "https://slo"
        assert cfg.x509_certificate == "cert"
        assert cfg.authn_request_signed is False
        assert cfg.binding == "custom_binding"


class TestOIDCConfig:
    def test_to_dict_excludes_client_secret(self):
        cfg = OIDCConfig(issuer="https://iss", client_id="cid", client_secret="secret")
        d = cfg.to_dict()
        assert "client_secret" not in d
        assert d["issuer"] == "https://iss"

    def test_from_dict_roundtrip(self):
        data = {
            "issuer": "https://iss",
            "client_id": "cid",
            "client_secret": "sec",
            "scopes": ["openid"],
            "response_type": "token",
            "use_pkce": False,
            "token_endpoint_auth_method": "client_secret_basic",
        }
        cfg = OIDCConfig.from_dict(data)
        assert cfg.client_secret == "sec"
        assert cfg.scopes == ["openid"]
        assert cfg.use_pkce is False

    def test_from_dict_defaults(self):
        data = {"issuer": "https://iss", "client_id": "cid"}
        cfg = OIDCConfig.from_dict(data)
        assert cfg.scopes == ["openid", "profile", "email"]
        assert cfg.response_type == "code"
        assert cfg.use_pkce is True


# ===================================================================
# RoleMappingRule tests
# ===================================================================


class TestRoleMappingRule:
    def test_matches_group_present(self):
        rule = RoleMappingRule(idp_group="admins", maci_role="ADMIN")
        assert rule.matches(["admins", "users"]) is True

    def test_matches_group_absent(self):
        rule = RoleMappingRule(idp_group="admins", maci_role="ADMIN")
        assert rule.matches(["users"]) is False

    def test_matches_with_conditions_pass(self):
        rule = RoleMappingRule(
            idp_group="admins",
            maci_role="ADMIN",
            conditions={"department": "eng"},
        )
        assert rule.matches(["admins"], attributes={"department": "eng"}) is True

    def test_matches_with_conditions_fail(self):
        rule = RoleMappingRule(
            idp_group="admins",
            maci_role="ADMIN",
            conditions={"department": "eng"},
        )
        assert rule.matches(["admins"], attributes={"department": "hr"}) is False

    def test_matches_conditions_no_attributes(self):
        rule = RoleMappingRule(
            idp_group="admins",
            maci_role="ADMIN",
            conditions={"department": "eng"},
        )
        # conditions present but attributes is None -> conditions not checked
        assert rule.matches(["admins"], attributes=None) is True

    def test_to_dict_from_dict(self):
        rule = RoleMappingRule(idp_group="g", maci_role="r", priority=5, conditions={"k": "v"})
        d = rule.to_dict()
        restored = RoleMappingRule.from_dict(d)
        assert restored.priority == 5
        assert restored.conditions == {"k": "v"}


# ===================================================================
# AttributeMapping tests
# ===================================================================


class TestAttributeMapping:
    def test_extract_single_values(self):
        am = AttributeMapping()
        raw = {
            "email": "a@b.com",
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "groups": ["admins"],
        }
        result = am.extract(raw)
        assert result["email"] == "a@b.com"
        assert result["groups"] == ["admins"]

    def test_extract_list_value_takes_first(self):
        am = AttributeMapping()
        raw = {
            "email": ["first@b.com", "second@b.com"],
            "name": "n",
            "given_name": "g",
            "family_name": "f",
            "groups": [],
        }
        result = am.extract(raw)
        assert result["email"] == "first@b.com"

    def test_extract_with_external_id(self):
        am = AttributeMapping(external_id="sub")
        raw = {
            "email": "e",
            "name": "n",
            "given_name": "g",
            "family_name": "f",
            "groups": [],
            "sub": "ext-123",
        }
        result = am.extract(raw)
        assert result["external_id"] == "ext-123"

    def test_extract_with_custom_attributes(self):
        am = AttributeMapping(custom_attributes={"dept": "department"})
        raw = {
            "email": "e",
            "name": "n",
            "given_name": "g",
            "family_name": "f",
            "groups": [],
            "department": "engineering",
        }
        result = am.extract(raw)
        assert result["dept"] == "engineering"

    def test_to_dict_from_dict(self):
        am = AttributeMapping(external_id="sub", custom_attributes={"x": "y"})
        d = am.to_dict()
        restored = AttributeMapping.from_dict(d)
        assert restored.external_id == "sub"
        assert restored.custom_attributes == {"x": "y"}

    def test_from_dict_defaults(self):
        restored = AttributeMapping.from_dict({})
        assert restored.email == "email"
        assert restored.display_name == "name"


# ===================================================================
# TenantIdPConfig tests
# ===================================================================


class TestTenantIdPConfig:
    def _make_oidc_idp(self, **kwargs):
        defaults = dict(
            idp_id="idp-1",
            tenant_id="t1",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="Test",
            oidc_config=OIDCConfig(issuer="https://iss", client_id="cid"),
        )
        defaults.update(kwargs)
        return TenantIdPConfig(**defaults)

    def _make_saml_idp(self, **kwargs):
        defaults = dict(
            idp_id="idp-s1",
            tenant_id="t1",
            provider_type=IdPProviderType.CUSTOM_SAML,
            protocol=SSOProtocolType.SAML_2_0,
            display_name="SAML Test",
            saml_config=SAMLConfig(entity_id="eid", sso_url="https://sso"),
        )
        defaults.update(kwargs)
        return TenantIdPConfig(**defaults)

    def test_post_init_invalid_hash(self):
        with pytest.raises(ConstitutionalViolationError):
            TenantIdPConfig(
                idp_id="x",
                tenant_id="t",
                provider_type=IdPProviderType.OKTA,
                protocol=SSOProtocolType.OIDC,
                display_name="x",
                oidc_config=OIDCConfig(issuer="i", client_id="c"),
                constitutional_hash="badhash",
            )

    def test_post_init_saml_requires_config(self):
        with pytest.raises(ACGSValidationError):
            TenantIdPConfig(
                idp_id="x",
                tenant_id="t",
                provider_type=IdPProviderType.CUSTOM_SAML,
                protocol=SSOProtocolType.SAML_2_0,
                display_name="x",
            )

    def test_post_init_oidc_requires_config(self):
        with pytest.raises(ACGSValidationError):
            TenantIdPConfig(
                idp_id="x",
                tenant_id="t",
                provider_type=IdPProviderType.OKTA,
                protocol=SSOProtocolType.OIDC,
                display_name="x",
            )

    def test_get_maci_roles_default(self):
        idp = self._make_oidc_idp()
        roles = idp.get_maci_roles(["any-group"])
        assert roles == ["MONITOR"]

    def test_get_maci_roles_with_mappings(self):
        rules = [
            RoleMappingRule(idp_group="admins", maci_role="ADMIN", priority=10),
            RoleMappingRule(idp_group="users", maci_role="USER", priority=5),
        ]
        idp = self._make_oidc_idp(role_mappings=rules)
        roles = idp.get_maci_roles(["admins", "users"])
        assert roles == ["ADMIN", "USER"]

    def test_get_maci_roles_dedup(self):
        rules = [
            RoleMappingRule(idp_group="admins", maci_role="ADMIN", priority=10),
            RoleMappingRule(idp_group="superadmins", maci_role="ADMIN", priority=20),
        ]
        idp = self._make_oidc_idp(role_mappings=rules)
        roles = idp.get_maci_roles(["admins", "superadmins"])
        assert roles.count("ADMIN") == 1

    def test_is_domain_allowed_no_restrictions(self):
        idp = self._make_oidc_idp()
        assert idp.is_domain_allowed("user@anything.com") is True

    def test_is_domain_allowed_match(self):
        idp = self._make_oidc_idp(allowed_domains=["example.com"])
        assert idp.is_domain_allowed("user@example.com") is True

    def test_is_domain_allowed_no_match(self):
        idp = self._make_oidc_idp(allowed_domains=["example.com"])
        assert idp.is_domain_allowed("user@other.com") is False

    def test_is_domain_allowed_case_insensitive(self):
        idp = self._make_oidc_idp(allowed_domains=["EXAMPLE.COM"])
        assert idp.is_domain_allowed("user@example.com") is True

    def test_to_dict_oidc(self):
        idp = self._make_oidc_idp()
        d = idp.to_dict()
        assert d["provider_type"] == "okta"
        assert d["protocol"] == "oidc"
        assert d["saml_config"] is None
        assert d["oidc_config"] is not None

    def test_to_dict_saml(self):
        idp = self._make_saml_idp()
        d = idp.to_dict()
        assert d["saml_config"] is not None
        assert d["oidc_config"] is None


# ===================================================================
# TenantSSOConfig tests
# ===================================================================


class TestTenantSSOConfig:
    def test_post_init_invalid_hash(self):
        with pytest.raises(ConstitutionalViolationError):
            TenantSSOConfig(tenant_id="t", constitutional_hash="bad")

    def test_get_enabled_idps(self):
        idp_enabled = TenantIdPConfig(
            idp_id="e",
            tenant_id="t",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="E",
            enabled=True,
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        idp_disabled = TenantIdPConfig(
            idp_id="d",
            tenant_id="t",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="D",
            enabled=False,
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        cfg = TenantSSOConfig(tenant_id="t", identity_providers=[idp_enabled, idp_disabled])
        assert len(cfg.get_enabled_idps()) == 1

    def test_get_idp_found(self):
        idp = TenantIdPConfig(
            idp_id="target",
            tenant_id="t",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="T",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        cfg = TenantSSOConfig(tenant_id="t", identity_providers=[idp])
        assert cfg.get_idp("target") is idp

    def test_get_idp_not_found(self):
        cfg = TenantSSOConfig(tenant_id="t")
        assert cfg.get_idp("missing") is None

    def test_get_default_idp_explicit(self):
        idp = TenantIdPConfig(
            idp_id="def",
            tenant_id="t",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="D",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        cfg = TenantSSOConfig(
            tenant_id="t",
            identity_providers=[idp],
            default_idp_id="def",
        )
        assert cfg.get_default_idp() is idp

    def test_get_default_idp_first_enabled(self):
        idp = TenantIdPConfig(
            idp_id="first",
            tenant_id="t",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="F",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        cfg = TenantSSOConfig(tenant_id="t", identity_providers=[idp])
        assert cfg.get_default_idp() is idp

    def test_get_default_idp_none(self):
        cfg = TenantSSOConfig(tenant_id="t")
        assert cfg.get_default_idp() is None

    def test_to_dict(self):
        cfg = TenantSSOConfig(tenant_id="t", sso_enabled=True, sso_enforced=True)
        d = cfg.to_dict()
        assert d["tenant_id"] == "t"
        assert d["sso_enabled"] is True
        assert d["sso_enforced"] is True


# ===================================================================
# TenantSSOConfigManager tests
# ===================================================================


class TestTenantSSOConfigManager:
    def test_invalid_hash_raises(self):
        with pytest.raises(ConstitutionalViolationError):
            TenantSSOConfigManager(constitutional_hash="wrong")

    def test_create_config(self):
        mgr = TenantSSOConfigManager()
        cfg = mgr.create_config("t1", sso_enabled=True)
        assert cfg.tenant_id == "t1"
        assert cfg.sso_enabled is True

    def test_create_duplicate_raises(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        with pytest.raises(ACGSValidationError):
            mgr.create_config("t1")

    def test_get_config(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        assert mgr.get_config("t1") is not None
        assert mgr.get_config("missing") is None

    def test_update_config(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        updated = mgr.update_config(
            "t1", sso_enabled=True, sso_enforced=True, session_timeout_hours=48
        )
        assert updated is not None
        assert updated.sso_enabled is True
        assert updated.sso_enforced is True
        assert updated.session_timeout_hours == 48

    def test_update_config_not_found(self):
        mgr = TenantSSOConfigManager()
        assert mgr.update_config("missing") is None

    def test_add_identity_provider(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        idp = TenantIdPConfig(
            idp_id="idp-1",
            tenant_id="t1",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="O",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        result = mgr.add_identity_provider("t1", idp)
        assert result is not None
        assert result.default_idp_id == "idp-1"

    def test_add_identity_provider_set_as_default(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        idp1 = TenantIdPConfig(
            idp_id="idp-1",
            tenant_id="t1",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="O",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        idp2 = TenantIdPConfig(
            idp_id="idp-2",
            tenant_id="t1",
            provider_type=IdPProviderType.AUTH0,
            protocol=SSOProtocolType.OIDC,
            display_name="A",
            oidc_config=OIDCConfig(issuer="i2", client_id="c2"),
        )
        mgr.add_identity_provider("t1", idp1)
        result = mgr.add_identity_provider("t1", idp2, set_as_default=True)
        assert result.default_idp_id == "idp-2"

    def test_add_identity_provider_duplicate_raises(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        idp = TenantIdPConfig(
            idp_id="dup",
            tenant_id="t1",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="D",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        mgr.add_identity_provider("t1", idp)
        with pytest.raises(ACGSValidationError):
            mgr.add_identity_provider("t1", idp)

    def test_add_identity_provider_tenant_not_found(self):
        mgr = TenantSSOConfigManager()
        idp = TenantIdPConfig(
            idp_id="x",
            tenant_id="t1",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="X",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        assert mgr.add_identity_provider("missing", idp) is None

    def test_remove_identity_provider(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        idp = TenantIdPConfig(
            idp_id="rem",
            tenant_id="t1",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="R",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        mgr.add_identity_provider("t1", idp)
        result = mgr.remove_identity_provider("t1", "rem")
        assert result is not None
        assert len(result.identity_providers) == 0
        assert result.default_idp_id is None

    def test_remove_identity_provider_not_default(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        idp1 = TenantIdPConfig(
            idp_id="keep",
            tenant_id="t1",
            provider_type=IdPProviderType.OKTA,
            protocol=SSOProtocolType.OIDC,
            display_name="K",
            oidc_config=OIDCConfig(issuer="i", client_id="c"),
        )
        idp2 = TenantIdPConfig(
            idp_id="remove",
            tenant_id="t1",
            provider_type=IdPProviderType.AUTH0,
            protocol=SSOProtocolType.OIDC,
            display_name="R",
            oidc_config=OIDCConfig(issuer="i2", client_id="c2"),
        )
        mgr.add_identity_provider("t1", idp1)
        mgr.add_identity_provider("t1", idp2)
        result = mgr.remove_identity_provider("t1", "remove")
        assert result.default_idp_id == "keep"

    def test_remove_identity_provider_tenant_not_found(self):
        mgr = TenantSSOConfigManager()
        assert mgr.remove_identity_provider("missing", "x") is None

    def test_delete_config(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        assert mgr.delete_config("t1") is True
        assert mgr.delete_config("t1") is False

    def test_list_configs(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1")
        mgr.create_config("t2")
        assert len(mgr.list_configs()) == 2

    def test_get_sso_enabled_tenants(self):
        mgr = TenantSSOConfigManager()
        mgr.create_config("t1", sso_enabled=True)
        mgr.create_config("t2", sso_enabled=False)
        assert mgr.get_sso_enabled_tenants() == ["t1"]


# ===================================================================
# Factory function tests
# ===================================================================


class TestFactoryFunctions:
    def test_create_okta_idp_config(self):
        idp = create_okta_idp_config("t1", "company.okta.com", "cid", "secret")
        assert idp.provider_type == IdPProviderType.OKTA
        assert idp.protocol == SSOProtocolType.OIDC
        assert "company.okta.com" in idp.oidc_config.issuer
        assert "groups" in idp.oidc_config.scopes

    def test_create_okta_with_role_mappings(self):
        rules = [RoleMappingRule(idp_group="g", maci_role="r")]
        idp = create_okta_idp_config("t1", "ok.com", "c", role_mappings=rules)
        assert len(idp.role_mappings) == 1

    def test_create_azure_ad_idp_config(self):
        idp = create_azure_ad_idp_config("t1", "az-tenant", "cid")
        assert idp.provider_type == IdPProviderType.AZURE_AD
        assert "az-tenant" in idp.oidc_config.issuer

    def test_create_google_workspace_idp_config(self):
        idp = create_google_workspace_idp_config("t1", "cid", "secret")
        assert idp.provider_type == IdPProviderType.GOOGLE_WORKSPACE
        assert idp.attribute_mapping.external_id == "sub"
        assert idp.allowed_domains == []

    def test_create_google_workspace_with_hosted_domain(self):
        idp = create_google_workspace_idp_config("t1", "cid", "secret", hosted_domain="example.com")
        assert idp.allowed_domains == ["example.com"]


# ===================================================================
# WorkflowContext tests
# ===================================================================


class TestWorkflowContext:
    def test_get_signal_queue_creates_new(self):
        ctx = WorkflowContext(workflow_id="wf1")
        q = ctx.get_signal_queue("sig1")
        assert isinstance(q, asyncio.Queue)
        # Same queue returned on second call
        assert ctx.get_signal_queue("sig1") is q

    async def test_send_signal(self):
        ctx = WorkflowContext(workflow_id="wf1")
        await ctx.send_signal("sig1", {"key": "val"})
        assert "sig1" in ctx._signal_data
        assert len(ctx._signal_data["sig1"]) == 1

    async def test_wait_for_signal_with_data(self):
        ctx = WorkflowContext(workflow_id="wf1")
        await ctx.send_signal("sig1", "hello")
        result = await ctx.wait_for_signal("sig1", timeout=1.0)
        assert result == "hello"

    async def test_wait_for_signal_timeout(self):
        ctx = WorkflowContext(workflow_id="wf1")
        result = await ctx.wait_for_signal("sig1", timeout=0.01)
        assert result is None


# ===================================================================
# WorkflowDefinition tests
# ===================================================================


class _SimpleWorkflow(WorkflowDefinition):
    @property
    def name(self) -> str:
        return "simple"

    async def run(self, input_data):
        return {"result": input_data}


class _FailingWorkflow(WorkflowDefinition):
    @property
    def name(self) -> str:
        return "failing"

    async def run(self, input_data):
        raise ValueError("workflow error")


class _SignalWorkflow(WorkflowDefinition):
    def __init__(self):
        self._received = None
        super().__init__()

    @property
    def name(self) -> str:
        return "signal_wf"

    @signal_decorator("my_signal")
    async def handle_signal(self, data):
        self._received = data

    @query_decorator("get_state")
    def get_state(self):
        return {"received": self._received}

    async def run(self, input_data):
        await self.context.wait_for_signal("my_signal", timeout=2.0)
        return {"done": True, "received": self._received}


class TestWorkflowDefinition:
    def test_context_not_initialized_raises(self):
        wf = _SimpleWorkflow()
        with pytest.raises(ServiceUnavailableError):
            _ = wf.context

    def test_context_setter(self):
        wf = _SimpleWorkflow()
        ctx = WorkflowContext(workflow_id="wf1")
        wf.context = ctx
        assert wf.context is ctx

    def test_get_signals_and_queries(self):
        wf = _SignalWorkflow()
        sigs = wf.get_signals()
        queries = wf.get_queries()
        assert "my_signal" in sigs
        assert "get_state" in queries

    async def test_execute_activity_timeout(self):
        wf = _SimpleWorkflow()
        wf.context = WorkflowContext(workflow_id="wf1")

        activity = MagicMock()
        activity.name = "slow_activity"
        activity.timeout_seconds = 0.01

        async def slow_exec(input_data, context):
            await asyncio.sleep(10)
            return None

        activity.execute = slow_exec

        with pytest.raises(TimeoutError):
            await wf.execute_activity(activity, "data")

    async def test_execute_activity_success(self):
        wf = _SimpleWorkflow()
        wf.context = WorkflowContext(workflow_id="wf1")

        activity = MagicMock()
        activity.name = "fast_activity"
        activity.timeout_seconds = 5.0

        async def fast_exec(input_data, context):
            return "done"

        activity.execute = fast_exec

        result = await wf.execute_activity(activity, "data")
        assert result == "done"

    async def test_wait_condition_true_immediately(self):
        wf = _SimpleWorkflow()
        result = await wf.wait_condition(lambda: True, timeout=1.0)
        assert result is True

    async def test_wait_condition_timeout(self):
        wf = _SimpleWorkflow()
        result = await wf.wait_condition(lambda: False, timeout=0.05, poll_interval=0.01)
        assert result is False


# ===================================================================
# InMemoryWorkflowExecutor tests
# ===================================================================


class TestInMemoryWorkflowExecutor:
    async def test_start_and_get_result(self):
        executor = InMemoryWorkflowExecutor()
        wf = _SimpleWorkflow()
        run_id = await executor.start(wf, "wf-1", "hello")
        assert run_id is not None

        result = await executor.get_result("wf-1", timeout=2.0)
        assert result == {"result": "hello"}

    async def test_get_status(self):
        executor = InMemoryWorkflowExecutor()
        wf = _SimpleWorkflow()
        await executor.start(wf, "wf-2", "x")
        await executor.get_result("wf-2", timeout=2.0)
        status = executor.get_status("wf-2")
        assert status == WorkflowStatus.COMPLETED

    async def test_get_context(self):
        executor = InMemoryWorkflowExecutor()
        wf = _SimpleWorkflow()
        await executor.start(wf, "wf-3", "x")
        ctx = executor.get_context("wf-3")
        assert ctx.workflow_id == "wf-3"

    async def test_get_status_not_found(self):
        executor = InMemoryWorkflowExecutor()
        with pytest.raises(ResourceNotFoundError):
            executor.get_status("missing")

    async def test_get_context_not_found(self):
        executor = InMemoryWorkflowExecutor()
        with pytest.raises(ResourceNotFoundError):
            executor.get_context("missing")

    async def test_workflow_failure(self):
        executor = InMemoryWorkflowExecutor()
        wf = _FailingWorkflow()
        await executor.start(wf, "wf-fail", "x")
        # Let the task complete
        await asyncio.sleep(0.05)
        status = executor.get_status("wf-fail")
        assert status == WorkflowStatus.FAILED
        with pytest.raises(ServiceUnavailableError):
            await executor.get_result("wf-fail", timeout=1.0)

    async def test_cancel(self):
        executor = InMemoryWorkflowExecutor()

        class _LongWorkflow(WorkflowDefinition):
            @property
            def name(self):
                return "long"

            async def run(self, input_data):
                await asyncio.sleep(100)
                return None

        wf = _LongWorkflow()
        await executor.start(wf, "wf-cancel", "x")
        await executor.cancel("wf-cancel")
        status = executor.get_status("wf-cancel")
        assert status == WorkflowStatus.CANCELLED

    async def test_cancel_not_found(self):
        executor = InMemoryWorkflowExecutor()
        with pytest.raises(ResourceNotFoundError):
            await executor.cancel("missing")

    async def test_get_result_not_found(self):
        executor = InMemoryWorkflowExecutor()
        with pytest.raises(ResourceNotFoundError):
            await executor.get_result("missing")

    async def test_send_signal(self):
        executor = InMemoryWorkflowExecutor()
        wf = _SignalWorkflow()
        await executor.start(wf, "wf-sig", "x")
        await asyncio.sleep(0.05)
        await executor.send_signal("wf-sig", "my_signal", {"val": 42})
        result = await executor.get_result("wf-sig", timeout=2.0)
        assert result is not None

    async def test_send_signal_not_found(self):
        executor = InMemoryWorkflowExecutor()
        with pytest.raises(ResourceNotFoundError):
            await executor.send_signal("missing", "sig", None)

    async def test_query_workflow(self):
        executor = InMemoryWorkflowExecutor()
        wf = _SignalWorkflow()
        await executor.start(wf, "wf-q", "x")
        await asyncio.sleep(0.05)
        state = await executor.query("wf-q", "get_state")
        assert "received" in state

    async def test_query_not_found_workflow(self):
        executor = InMemoryWorkflowExecutor()
        with pytest.raises(ResourceNotFoundError):
            await executor.query("missing", "q")

    async def test_query_not_found_query_name(self):
        executor = InMemoryWorkflowExecutor()
        wf = _SimpleWorkflow()
        await executor.start(wf, "wf-qn", "x")
        with pytest.raises(ACGSValidationError):
            await executor.query("wf-qn", "nonexistent_query")

    async def test_start_with_metadata(self):
        executor = InMemoryWorkflowExecutor()
        wf = _SimpleWorkflow()
        run_id = await executor.start(
            wf,
            "wf-meta",
            "x",
            tenant_id="tenant-1",
            metadata={"k": "v"},
        )
        ctx = executor.get_context("wf-meta")
        assert ctx.tenant_id == "tenant-1"
        assert ctx.metadata == {"k": "v"}


# ===================================================================
# signal / query decorators
# ===================================================================


class TestDecorators:
    def test_signal_decorator_default_name(self):
        @signal_decorator()
        def my_handler(data):
            pass

        assert my_handler._is_signal is True
        assert my_handler._signal_name == "my_handler"

    def test_signal_decorator_custom_name(self):
        @signal_decorator("custom")
        def my_handler(data):
            pass

        assert my_handler._signal_name == "custom"

    def test_query_decorator_default_name(self):
        @query_decorator()
        def my_query():
            pass

        assert my_query._is_query is True
        assert my_query._query_name == "my_query"

    def test_query_decorator_custom_name(self):
        @query_decorator("custom")
        def my_query():
            pass

        assert my_query._query_name == "custom"


# ===================================================================
# message_processor_components tests
# ===================================================================


class TestExtractSessionIdForGovernance:
    def test_from_headers_x_session_id(self):
        msg = SimpleNamespace(headers={"X-Session-ID": "s1"}, metadata={}, content={})
        assert extract_session_id_for_governance(msg) == "s1"

    def test_from_headers_lowercase(self):
        msg = SimpleNamespace(headers={"x-session-id": "s2"}, metadata={}, content={})
        assert extract_session_id_for_governance(msg) == "s2"

    def test_from_metadata(self):
        msg = SimpleNamespace(headers={}, metadata={"session_id": "s3"}, content={})
        assert extract_session_id_for_governance(msg) == "s3"

    def test_from_content(self):
        msg = SimpleNamespace(headers={}, metadata={}, content={"session_id": "s4"})
        assert extract_session_id_for_governance(msg) == "s4"

    def test_none_when_missing(self):
        msg = SimpleNamespace(headers={}, metadata={}, content={})
        assert extract_session_id_for_governance(msg) is None

    def test_no_headers_attr(self):
        msg = SimpleNamespace(metadata={"session_id": "s5"}, content={})
        assert extract_session_id_for_governance(msg) == "s5"

    def test_headers_none(self):
        msg = SimpleNamespace(headers=None, metadata={"session_id": "s6"}, content={})
        assert extract_session_id_for_governance(msg) == "s6"


class TestExtractSessionIdForPacar:
    def test_from_session_id_attr(self):
        msg = SimpleNamespace(session_id="s1", headers={}, content={})
        assert extract_session_id_for_pacar(msg) == "s1"

    def test_from_headers(self):
        msg = SimpleNamespace(headers={"X-Session-ID": "s2"}, content={})
        assert extract_session_id_for_pacar(msg) == "s2"

    def test_from_conversation_id(self):
        msg = SimpleNamespace(headers={}, conversation_id="c1", content={})
        assert extract_session_id_for_pacar(msg) == "c1"

    def test_from_content(self):
        msg = SimpleNamespace(headers={}, content={"session_id": "s3"})
        assert extract_session_id_for_pacar(msg) == "s3"

    def test_from_payload(self):
        msg = SimpleNamespace(headers={}, content={}, payload={"session_id": "s4"})
        assert extract_session_id_for_pacar(msg) == "s4"

    def test_none_all_empty(self):
        msg = SimpleNamespace(headers={}, content={}, payload={})
        assert extract_session_id_for_pacar(msg) is None


class TestEnforceAutonomyTierRules:
    def test_no_tier_returns_none(self):
        msg = SimpleNamespace(autonomy_tier=None)
        assert enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset()) is None

    def test_advisory_command_blocked(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="advisory"),
            message_type=SimpleNamespace(value="command"),
            metadata={},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None
        assert result.is_valid is False

    def test_advisory_blocked_type(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="advisory"),
            message_type=SimpleNamespace(value="execution"),
            metadata={},
        )
        result = enforce_autonomy_tier_rules(
            msg=msg, advisory_blocked_types=frozenset({"execution"})
        )
        assert result is not None
        assert result.is_valid is False

    def test_advisory_allowed(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="advisory"),
            message_type=SimpleNamespace(value="query"),
            metadata={},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is None

    def test_human_approved_no_validator(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="human_approved"),
            message_type=SimpleNamespace(value="command"),
            metadata={},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None
        assert result.is_valid is False

    def test_human_approved_with_validator(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="human_approved"),
            message_type=SimpleNamespace(value="command"),
            metadata={"validated_by_agent": "agent-1"},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is None

    def test_human_approved_whitespace_validator(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="human_approved"),
            message_type=SimpleNamespace(value="command"),
            metadata={"validated_by_agent": "   "},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None
        assert result.is_valid is False

    def test_unrestricted_missing_grant_id(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="unrestricted"),
            message_type=SimpleNamespace(value="command"),
            metadata={"grant_authority": "admin"},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None
        assert result.is_valid is False

    def test_unrestricted_missing_grant_authority(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="unrestricted"),
            message_type=SimpleNamespace(value="command"),
            metadata={"unrestricted_grant_id": "grant-1"},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None
        assert result.is_valid is False

    def test_unrestricted_valid(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="unrestricted"),
            message_type=SimpleNamespace(value="command"),
            metadata={"unrestricted_grant_id": "grant-1", "grant_authority": "admin"},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is None

    def test_unrestricted_whitespace_grant_id(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="unrestricted"),
            message_type=SimpleNamespace(value="command"),
            metadata={"unrestricted_grant_id": "  ", "grant_authority": "admin"},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None

    def test_unrestricted_whitespace_authority(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="unrestricted"),
            message_type=SimpleNamespace(value="command"),
            metadata={"unrestricted_grant_id": "g1", "grant_authority": "  "},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None

    def test_bounded_tier_passes(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="bounded"),
            message_type=SimpleNamespace(value="command"),
            metadata={},
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is None

    def test_metadata_not_dict(self):
        msg = SimpleNamespace(
            autonomy_tier=SimpleNamespace(value="human_approved"),
            message_type=SimpleNamespace(value="command"),
            metadata="not_a_dict",
        )
        result = enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=frozenset())
        assert result is not None
        assert result.is_valid is False


class TestRunMessageValidationGates:
    async def test_all_pass(self):
        result = await run_message_validation_gates(
            msg="test",
            autonomy_gate=lambda m: None,
            security_scan=AsyncMock(return_value=None),
            independent_validator_gate=lambda m: None,
            prompt_injection_gate=lambda m: None,
            increment_failure=MagicMock(),
        )
        assert result is None

    async def test_autonomy_gate_fails(self):
        fail_result = ValidationResult(is_valid=False, errors=["blocked"])
        inc = MagicMock()
        result = await run_message_validation_gates(
            msg="test",
            autonomy_gate=lambda m: fail_result,
            security_scan=AsyncMock(return_value=None),
            independent_validator_gate=lambda m: None,
            prompt_injection_gate=lambda m: None,
            increment_failure=inc,
        )
        assert result is fail_result
        inc.assert_called_once()

    async def test_security_scan_fails(self):
        fail_result = ValidationResult(is_valid=False, errors=["sec"])
        result = await run_message_validation_gates(
            msg="test",
            autonomy_gate=lambda m: None,
            security_scan=AsyncMock(return_value=fail_result),
            independent_validator_gate=lambda m: None,
            prompt_injection_gate=lambda m: None,
            increment_failure=MagicMock(),
        )
        assert result is fail_result

    async def test_independent_validator_fails(self):
        fail_result = ValidationResult(is_valid=False, errors=["iv"])
        inc = MagicMock()
        result = await run_message_validation_gates(
            msg="test",
            autonomy_gate=lambda m: None,
            security_scan=AsyncMock(return_value=None),
            independent_validator_gate=lambda m: fail_result,
            prompt_injection_gate=lambda m: None,
            increment_failure=inc,
        )
        assert result is fail_result
        inc.assert_called_once()

    async def test_prompt_injection_fails(self):
        fail_result = ValidationResult(is_valid=False, errors=["pi"])
        inc = MagicMock()
        result = await run_message_validation_gates(
            msg="test",
            autonomy_gate=lambda m: None,
            security_scan=AsyncMock(return_value=None),
            independent_validator_gate=lambda m: None,
            prompt_injection_gate=lambda m: fail_result,
            increment_failure=inc,
        )
        assert result is fail_result
        inc.assert_called_once()


class TestComputeMessageCacheKey:
    def test_sha256_default(self):
        msg = AgentMessage(content="hello", from_agent="a")
        key = compute_message_cache_key(msg, cache_hash_mode="sha256", fast_hash_available=False)
        assert len(key) == 64  # sha256 hex

    def test_fast_hash(self):
        msg = AgentMessage(content="hello", from_agent="a")
        key = compute_message_cache_key(
            msg,
            cache_hash_mode="fast",
            fast_hash_available=True,
            fast_hash_func=lambda s: 0xDEADBEEF,
        )
        assert key.startswith("fast:")

    def test_fast_hash_fallback_when_unavailable(self):
        msg = AgentMessage(content="hello", from_agent="a")
        key = compute_message_cache_key(msg, cache_hash_mode="fast", fast_hash_available=False)
        assert len(key) == 64

    def test_dict_content(self):
        msg = AgentMessage(content={"key": "value"}, from_agent="a")
        key = compute_message_cache_key(msg, cache_hash_mode="sha256", fast_hash_available=False)
        assert len(key) == 64


class TestPrepareMessageContentString:
    def test_string_content(self):
        msg = AgentMessage(content="hello")
        assert prepare_message_content_string(msg) == "hello"

    def test_dict_content(self):
        msg = AgentMessage(content={"key": "val"})
        result = prepare_message_content_string(msg)
        assert "key" in result


class TestMergeVerificationMetadata:
    def test_merge_both(self):
        result = merge_verification_metadata({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_empty_pqc(self):
        result = merge_verification_metadata({"a": 1}, {})
        assert result == {"a": 1}

    def test_pqc_overrides(self):
        result = merge_verification_metadata({"a": 1}, {"a": 2})
        assert result == {"a": 2}


class TestExtractPqcFailureResult:
    def test_with_pqc_result(self):
        vr = ValidationResult(is_valid=False, errors=["pqc fail"])
        ver = VerificationResult(pqc_result=vr)
        assert extract_pqc_failure_result(ver) is vr

    def test_without_pqc_result(self):
        ver = VerificationResult()
        assert extract_pqc_failure_result(ver) is None


class TestApplyLatencyMetadata:
    def test_sets_latency(self):
        result = ValidationResult()
        apply_latency_metadata(result, 42.5)
        assert result.metadata["latency_ms"] == 42.5


class TestBuildDlqEntry:
    def test_builds_entry(self):
        msg = AgentMessage(
            message_id="m1",
            from_agent="a",
            to_agent="b",
            message_type=MessageType.COMMAND,
        )
        vr = ValidationResult(is_valid=False, errors=["err"])
        entry = build_dlq_entry(msg, vr, 1234.0)
        assert entry["message_id"] == "m1"
        assert entry["errors"] == ["err"]
        assert entry["timestamp"] == 1234.0


class TestCalculateSessionResolutionRate:
    def test_all_resolved(self):
        assert calculate_session_resolution_rate(10, 0, 0) == 1.0

    def test_none_resolved(self):
        assert calculate_session_resolution_rate(0, 5, 5) == 0.0

    def test_all_zero(self):
        assert calculate_session_resolution_rate(0, 0, 0) == 0.0

    def test_mixed(self):
        rate = calculate_session_resolution_rate(5, 3, 2)
        assert abs(rate - 0.5) < 0.01


class TestApplySessionGovernanceMetrics:
    def test_enabled(self):
        metrics: dict = {}
        apply_session_governance_metrics(
            metrics,
            enabled=True,
            resolved_count=10,
            not_found_count=2,
            error_count=1,
            resolution_rate=0.77,
        )
        assert metrics["session_governance_enabled"] is True
        assert metrics["session_resolved_count"] == 10

    def test_disabled(self):
        metrics: dict = {}
        apply_session_governance_metrics(
            metrics,
            enabled=False,
            resolved_count=0,
            not_found_count=0,
            error_count=0,
            resolution_rate=0.0,
        )
        assert metrics["session_governance_enabled"] is False
        assert "session_resolved_count" not in metrics


class TestEnrichMetricsWithOpaStats:
    def test_with_valid_stats(self):
        metrics: dict = {}
        opa = MagicMock()
        opa.get_stats.return_value = {
            "multipath_evaluation_count": 5,
            "multipath_last_path_count": 3,
            "multipath_last_diversity_ratio": 0.8,
            "multipath_last_support_family_count": 2,
        }
        enrich_metrics_with_opa_stats(metrics, opa)
        assert metrics["opa_multipath_evaluation_count"] == 5

    def test_with_none_client(self):
        metrics: dict = {}
        enrich_metrics_with_opa_stats(metrics, None)
        assert "opa_multipath_evaluation_count" not in metrics

    def test_with_exception(self):
        metrics: dict = {}
        opa = MagicMock()
        opa.get_stats.side_effect = TypeError("boom")
        enrich_metrics_with_opa_stats(metrics, opa)
        assert metrics["opa_multipath_evaluation_count"] == 0

    def test_no_get_stats_attr(self):
        metrics: dict = {}
        opa = object()
        enrich_metrics_with_opa_stats(metrics, opa)
        # hasattr check filters this out, but object() does have __class__ etc.
        # The function checks hasattr(opa_client, "get_stats")
        assert "opa_multipath_evaluation_count" not in metrics


class TestEnrichMetricsWithWorkflowTelemetry:
    def test_with_collector(self):
        metrics: dict = {}
        collector = MagicMock()
        collector.snapshot.return_value = {
            "intervention_rate": 0.1,
            "gate_failures_total": 3,
            "rollback_triggers_total": 1,
            "autonomous_actions_total": 50,
        }
        result = enrich_metrics_with_workflow_telemetry(metrics, collector)
        assert result is True
        assert metrics["workflow_intervention_rate"] == 0.1

    def test_with_none(self):
        metrics: dict = {}
        result = enrich_metrics_with_workflow_telemetry(metrics, None)
        assert result is False


class TestExtractRejectionReason:
    def test_from_metadata(self):
        vr = ValidationResult(
            is_valid=False, metadata={"rejection_reason": "autonomy_tier_violation"}
        )
        assert extract_rejection_reason(vr) == "autonomy_tier_violation"

    def test_default(self):
        vr = ValidationResult(is_valid=False)
        assert extract_rejection_reason(vr) == "validation_failed"

    def test_empty_string_reason(self):
        vr = ValidationResult(is_valid=False, metadata={"rejection_reason": ""})
        assert extract_rejection_reason(vr) == "validation_failed"

    def test_non_string_reason(self):
        vr = ValidationResult(is_valid=False, metadata={"rejection_reason": 123})
        assert extract_rejection_reason(vr) == "validation_failed"


class TestScheduleBackgroundTask:
    async def test_schedules_and_cleans_up(self):
        bg_tasks: set = set()

        async def coro():
            return 42

        task = schedule_background_task(coro(), bg_tasks)
        assert task in bg_tasks
        await task
        # done_callback removes from set
        await asyncio.sleep(0.01)
        assert task not in bg_tasks
