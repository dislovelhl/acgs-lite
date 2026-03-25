"""
Comprehensive tests for MACI Role Mapping Service.
Constitutional Hash: 608508a9bd224290

Phase 10 Task 6: MACI Role Mapping

Test Coverage:
- Task 6.1: Role mapping creation (LDAP group → MACI role)
- Task 6.3: Role resolution with multiple mappings and priority
- Task 6.5: SAML attribute mapping to MACI roles
- Task 6.7: OAuth scope mapping to MACI roles
- Task 6.9: Role mapping cache with 5-minute TTL
- Task 6.10: Integration tests for role mapping
"""

import time
import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enterprise_sso.role_mapping import (
    CONSTITUTIONAL_HASH,
    RoleMapping,
    RoleMappingCache,
    RoleMappingResult,
    RoleMappingService,
    RoleMappingSource,
)
from maci_enforcement import MACIRole

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def role_mapping_service():
    """Create a role mapping service with default 5-minute cache TTL."""
    return RoleMappingService(cache_ttl_seconds=300)


@pytest.fixture
def populated_service():
    """Create a role mapping service with pre-configured mappings."""
    service = RoleMappingService(cache_ttl_seconds=300)

    # LDAP group mappings
    service.create_mapping(
        source_type=RoleMappingSource.LDAP_GROUP,
        source_value="CN=Admins,OU=Groups,DC=example,DC=com",
        maci_role=MACIRole.EXECUTIVE,
        priority=100,
        tenant_id="tenant-1",
    )
    service.create_mapping(
        source_type=RoleMappingSource.LDAP_GROUP,
        source_value="CN=Developers,OU=Groups,DC=example,DC=com",
        maci_role=MACIRole.IMPLEMENTER,
        priority=50,
        tenant_id="tenant-1",
    )
    service.create_mapping(
        source_type=RoleMappingSource.LDAP_GROUP,
        source_value="CN=Auditors,OU=Groups,DC=example,DC=com",
        maci_role=MACIRole.AUDITOR,
        priority=75,
        tenant_id="tenant-1",
    )

    # SAML attribute mappings
    service.create_mapping(
        source_type=RoleMappingSource.SAML_ATTRIBUTE,
        source_value="governance-admin",
        maci_role=MACIRole.EXECUTIVE,
        priority=100,
        tenant_id="tenant-1",
    )
    service.create_mapping(
        source_type=RoleMappingSource.SAML_ATTRIBUTE,
        source_value="policy-writer",
        maci_role=MACIRole.LEGISLATIVE,
        priority=90,
        tenant_id="tenant-1",
    )

    # OAuth scope mappings
    service.create_mapping(
        source_type=RoleMappingSource.OAUTH_SCOPE,
        source_value="governance:admin",
        maci_role=MACIRole.EXECUTIVE,
        priority=100,
        tenant_id="tenant-1",
    )
    service.create_mapping(
        source_type=RoleMappingSource.OAUTH_SCOPE,
        source_value="governance:read",
        maci_role=MACIRole.MONITOR,
        priority=30,
        tenant_id="tenant-1",
    )

    return service


@pytest.fixture
def role_mapping_cache():
    """Create a role mapping cache with 5-second TTL for testing."""
    return RoleMappingCache(ttl_seconds=5)


# =============================================================================
# Task 6.1: Role Mapping Creation (LDAP Group → MACI Role)
# =============================================================================


class TestRoleMappingCreation:
    """Tests for role mapping creation (Task 6.1)."""

    def test_create_ldap_group_mapping(self, role_mapping_service):
        """Test creating an LDAP group to MACI role mapping."""
        mapping = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Admins,OU=Groups,DC=example,DC=com",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
            tenant_id="tenant-1",
        )

        assert mapping.id is not None
        assert mapping.source_type == RoleMappingSource.LDAP_GROUP
        assert mapping.source_value == "CN=Admins,OU=Groups,DC=example,DC=com"
        assert mapping.maci_role == MACIRole.EXECUTIVE
        assert mapping.priority == 100
        assert mapping.tenant_id == "tenant-1"
        assert mapping.enabled is True

    def test_create_mapping_with_custom_id(self, role_mapping_service):
        """Test creating a mapping with a custom ID."""
        mapping = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Users,DC=example,DC=com",
            maci_role=MACIRole.MONITOR,
            mapping_id="custom-id-123",
        )

        assert mapping.id == "custom-id-123"

    def test_create_mapping_duplicate_id_raises(self, role_mapping_service):
        """Test that creating a mapping with duplicate ID raises error."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Group1,DC=example,DC=com",
            maci_role=MACIRole.MONITOR,
            mapping_id="duplicate-id",
        )

        with pytest.raises(ValueError) as exc_info:
            role_mapping_service.create_mapping(
                source_type=RoleMappingSource.LDAP_GROUP,
                source_value="CN=Group2,DC=example,DC=com",
                maci_role=MACIRole.AUDITOR,
                mapping_id="duplicate-id",
            )

        assert "already exists" in str(exc_info.value)

    def test_create_mapping_with_conditions(self, role_mapping_service):
        """Test creating a mapping with additional conditions."""
        mapping = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Developers,DC=example,DC=com",
            maci_role=MACIRole.IMPLEMENTER,
            conditions={"department": "engineering", "level": "senior"},
        )

        assert mapping.conditions == {"department": "engineering", "level": "senior"}

    def test_create_mapping_default_priority(self, role_mapping_service):
        """Test that default priority is 0."""
        mapping = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Users,DC=example,DC=com",
            maci_role=MACIRole.MONITOR,
        )

        assert mapping.priority == 0

    def test_create_mapping_sets_timestamps(self, role_mapping_service):
        """Test that created_at and updated_at are set."""
        before = datetime.now(UTC)
        mapping = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Users,DC=example,DC=com",
            maci_role=MACIRole.MONITOR,
        )
        after = datetime.now(UTC)

        assert before <= mapping.created_at <= after
        assert before <= mapping.updated_at <= after

    def test_create_mapping_all_maci_roles(self, role_mapping_service):
        """Test creating mappings for all MACI roles."""
        for role in MACIRole:
            mapping = role_mapping_service.create_mapping(
                source_type=RoleMappingSource.LDAP_GROUP,
                source_value=f"CN={role.value}-group,DC=example,DC=com",
                maci_role=role,
            )
            assert mapping.maci_role == role


class TestRoleMappingCRUD:
    """Tests for CRUD operations on role mappings."""

    def test_get_mapping(self, role_mapping_service):
        """Test getting a mapping by ID."""
        created = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Admins,DC=example,DC=com",
            maci_role=MACIRole.EXECUTIVE,
            mapping_id="test-id",
        )

        retrieved = role_mapping_service.get_mapping("test-id")
        assert retrieved == created

    def test_get_nonexistent_mapping(self, role_mapping_service):
        """Test getting a non-existent mapping returns None."""
        result = role_mapping_service.get_mapping("nonexistent-id")
        assert result is None

    def test_list_mappings(self, populated_service):
        """Test listing all mappings."""
        mappings = populated_service.list_mappings()
        assert len(mappings) == 7  # Total mappings in populated_service

    def test_list_mappings_by_tenant(self, populated_service):
        """Test listing mappings filtered by tenant."""
        mappings = populated_service.list_mappings(tenant_id="tenant-1")
        assert len(mappings) == 7

        mappings = populated_service.list_mappings(tenant_id="tenant-2")
        assert len(mappings) == 0

    def test_list_mappings_by_source_type(self, populated_service):
        """Test listing mappings filtered by source type."""
        ldap_mappings = populated_service.list_mappings(source_type=RoleMappingSource.LDAP_GROUP)
        assert len(ldap_mappings) == 3

        saml_mappings = populated_service.list_mappings(
            source_type=RoleMappingSource.SAML_ATTRIBUTE
        )
        assert len(saml_mappings) == 2

        oauth_mappings = populated_service.list_mappings(source_type=RoleMappingSource.OAUTH_SCOPE)
        assert len(oauth_mappings) == 2

    def test_list_mappings_by_maci_role(self, populated_service):
        """Test listing mappings filtered by MACI role."""
        executive_mappings = populated_service.list_mappings(maci_role=MACIRole.EXECUTIVE)
        assert len(executive_mappings) == 3  # One from each source type

    def test_list_mappings_sorted_by_priority(self, populated_service):
        """Test that mappings are sorted by priority descending."""
        mappings = populated_service.list_mappings()

        for i in range(1, len(mappings)):
            assert mappings[i - 1].priority >= mappings[i].priority

    def test_update_mapping(self, role_mapping_service):
        """Test updating a mapping."""
        created = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=Admins,DC=example,DC=com",
            maci_role=MACIRole.EXECUTIVE,
            priority=50,
            mapping_id="update-test",
        )

        # Save original updated_at before modifying
        original_updated_at = created.updated_at

        updated = role_mapping_service.update_mapping(
            "update-test",
            priority=100,
            maci_role=MACIRole.JUDICIAL,
        )

        assert updated.priority == 100
        assert updated.maci_role == MACIRole.JUDICIAL
        assert updated.updated_at >= original_updated_at

    def test_update_nonexistent_mapping(self, role_mapping_service):
        """Test updating a non-existent mapping returns None."""
        result = role_mapping_service.update_mapping("nonexistent", priority=100)
        assert result is None

    def test_delete_mapping(self, role_mapping_service):
        """Test deleting a mapping."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="CN=ToDelete,DC=example,DC=com",
            maci_role=MACIRole.MONITOR,
            mapping_id="delete-me",
        )

        result = role_mapping_service.delete_mapping("delete-me")
        assert result is True

        assert role_mapping_service.get_mapping("delete-me") is None

    def test_delete_nonexistent_mapping(self, role_mapping_service):
        """Test deleting a non-existent mapping returns False."""
        result = role_mapping_service.delete_mapping("nonexistent")
        assert result is False


# =============================================================================
# Task 6.3: Role Resolution with Multiple Mappings and Priority
# =============================================================================


class TestRoleResolutionWithPriority:
    """Tests for role resolution with priority-based conflict resolution (Task 6.3)."""

    def test_resolve_single_mapping(self, role_mapping_service):
        """Test resolving a single matching mapping."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
        )

        result = role_mapping_service.resolve_from_ldap_groups(["Admins"])

        assert len(result.roles) == 1
        assert result.roles[0] == MACIRole.EXECUTIVE
        assert result.primary_role == MACIRole.EXECUTIVE

    def test_resolve_multiple_mappings_priority_order(self, role_mapping_service):
        """Test that higher priority mappings take precedence."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Users",
            maci_role=MACIRole.MONITOR,
            priority=10,
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Developers",
            maci_role=MACIRole.IMPLEMENTER,
            priority=50,
        )

        result = role_mapping_service.resolve_from_ldap_groups(["Users", "Admins", "Developers"])

        # Primary role should be EXECUTIVE (highest priority)
        assert result.primary_role == MACIRole.EXECUTIVE
        # Roles should be in priority order
        assert result.roles[0] == MACIRole.EXECUTIVE
        assert result.roles[1] == MACIRole.IMPLEMENTER
        assert result.roles[2] == MACIRole.MONITOR

    def test_resolve_no_matches(self, role_mapping_service):
        """Test resolving with no matching mappings."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        result = role_mapping_service.resolve_from_ldap_groups(["NonexistentGroup"])

        assert len(result.roles) == 0
        assert result.primary_role is None
        assert len(result.matched_mappings) == 0

    def test_resolve_same_role_different_priorities(self, role_mapping_service):
        """Test resolving when multiple mappings map to the same role."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="SuperAdmins",
            maci_role=MACIRole.EXECUTIVE,
            priority=150,
        )

        result = role_mapping_service.resolve_from_ldap_groups(["Admins", "SuperAdmins"])

        # Should only have EXECUTIVE once
        assert len(result.roles) == 1
        assert result.roles[0] == MACIRole.EXECUTIVE
        # But both mappings should be recorded
        assert len(result.matched_mappings) == 2

    def test_resolve_disabled_mappings_ignored(self, role_mapping_service):
        """Test that disabled mappings are not matched."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
            mapping_id="disabled-mapping",
        )
        role_mapping_service.update_mapping("disabled-mapping", enabled=False)

        result = role_mapping_service.resolve_from_ldap_groups(["Admins"])

        assert len(result.roles) == 0

    def test_resolve_with_conditions_matching(self, role_mapping_service):
        """Test resolving with conditions that match."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Developers",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
            conditions={"department": "engineering"},
        )

        result = role_mapping_service.resolve_from_ldap_groups(
            ["Developers"],
            attributes={"department": "engineering"},
        )

        assert len(result.roles) == 1
        assert result.primary_role == MACIRole.EXECUTIVE

    def test_resolve_with_conditions_not_matching(self, role_mapping_service):
        """Test resolving with conditions that don't match."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Developers",
            maci_role=MACIRole.EXECUTIVE,
            conditions={"department": "engineering"},
        )

        result = role_mapping_service.resolve_from_ldap_groups(
            ["Developers"],
            attributes={"department": "marketing"},
        )

        assert len(result.roles) == 0

    def test_resolve_with_list_conditions(self, role_mapping_service):
        """Test resolving with list-based conditions."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Developers",
            maci_role=MACIRole.IMPLEMENTER,
            conditions={"level": ["senior", "principal"]},
        )

        result1 = role_mapping_service.resolve_from_ldap_groups(
            ["Developers"],
            attributes={"level": "senior"},
        )
        assert len(result1.roles) == 1

        result2 = role_mapping_service.resolve_from_ldap_groups(
            ["Developers"],
            attributes={"level": "junior"},
        )
        assert len(result2.roles) == 0

    def test_resolve_tenant_isolation(self, role_mapping_service):
        """Test that tenant mappings are isolated."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
            tenant_id="tenant-1",
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.MONITOR,
            tenant_id="tenant-2",
        )

        result1 = role_mapping_service.resolve_from_ldap_groups(
            ["Admins"],
            tenant_id="tenant-1",
        )
        assert result1.primary_role == MACIRole.EXECUTIVE

        result2 = role_mapping_service.resolve_from_ldap_groups(
            ["Admins"],
            tenant_id="tenant-2",
        )
        assert result2.primary_role == MACIRole.MONITOR

    def test_resolve_result_includes_resolution_time(self, role_mapping_service):
        """Test that resolution result includes timing information."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        result = role_mapping_service.resolve_from_ldap_groups(["Admins"])

        assert result.resolution_time_ms >= 0
        assert result.from_cache is False

    def test_resolve_result_includes_constitutional_hash(self, role_mapping_service):
        """Test that resolution result includes constitutional hash."""
        result = role_mapping_service.resolve_from_ldap_groups([])
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Task 6.5: SAML Attribute Mapping to MACI Roles
# =============================================================================


class TestSAMLAttributeMapping:
    """Tests for SAML attribute mapping to MACI roles (Task 6.5)."""

    def test_resolve_from_saml_groups(self, role_mapping_service):
        """Test resolving MACI roles from SAML groups."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="governance-admin",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
        )

        result = role_mapping_service.resolve_from_saml_attributes(["governance-admin"])

        assert result.primary_role == MACIRole.EXECUTIVE

    def test_saml_multiple_groups(self, role_mapping_service):
        """Test resolving from multiple SAML groups."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="admin",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="developer",
            maci_role=MACIRole.IMPLEMENTER,
            priority=50,
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="auditor",
            maci_role=MACIRole.AUDITOR,
            priority=75,
        )

        result = role_mapping_service.resolve_from_saml_attributes(["developer", "auditor"])

        assert result.primary_role == MACIRole.AUDITOR  # Higher priority
        assert MACIRole.IMPLEMENTER in result.roles

    def test_saml_with_department_conditions(self, role_mapping_service):
        """Test SAML mapping with department conditions."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="manager",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
            conditions={"department": "governance"},
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="manager",
            maci_role=MACIRole.MONITOR,
            priority=50,
        )

        result = role_mapping_service.resolve_from_saml_attributes(
            ["manager"],
            attributes={"department": "governance"},
        )

        assert result.primary_role == MACIRole.EXECUTIVE

    def test_saml_common_attribute_names(self, role_mapping_service):
        """Test mapping common SAML attribute names."""
        common_groups = [
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/role/Admin",
            "urn:example:groups:governance-team",
            "governance.admin",
            "role:executive",
        ]

        for _i, group in enumerate(common_groups):
            role_mapping_service.create_mapping(
                source_type=RoleMappingSource.SAML_ATTRIBUTE,
                source_value=group,
                maci_role=MACIRole.EXECUTIVE,
            )

        for group in common_groups:
            result = role_mapping_service.resolve_from_saml_attributes([group])
            assert result.primary_role == MACIRole.EXECUTIVE

    def test_saml_role_mapping_with_tenant(self, role_mapping_service):
        """Test SAML role mapping with tenant isolation."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="admin",
            maci_role=MACIRole.EXECUTIVE,
            tenant_id="okta-tenant",
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="admin",
            maci_role=MACIRole.JUDICIAL,
            tenant_id="azure-tenant",
        )

        okta_result = role_mapping_service.resolve_from_saml_attributes(
            ["admin"],
            tenant_id="okta-tenant",
        )
        assert okta_result.primary_role == MACIRole.EXECUTIVE

        azure_result = role_mapping_service.resolve_from_saml_attributes(
            ["admin"],
            tenant_id="azure-tenant",
        )
        assert azure_result.primary_role == MACIRole.JUDICIAL


# =============================================================================
# Task 6.7: OAuth Scope Mapping to MACI Roles
# =============================================================================


class TestOAuthScopeMapping:
    """Tests for OAuth scope mapping to MACI roles (Task 6.7)."""

    def test_resolve_from_oauth_scopes(self, role_mapping_service):
        """Test resolving MACI roles from OAuth scopes."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="governance:admin",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
        )

        result = role_mapping_service.resolve_from_oauth_scopes(["governance:admin"])

        assert result.primary_role == MACIRole.EXECUTIVE

    def test_oauth_scope_priority_resolution(self, role_mapping_service):
        """Test OAuth scope resolution with priority."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="governance:read",
            maci_role=MACIRole.MONITOR,
            priority=10,
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="governance:write",
            maci_role=MACIRole.IMPLEMENTER,
            priority=50,
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="governance:admin",
            maci_role=MACIRole.EXECUTIVE,
            priority=100,
        )

        result = role_mapping_service.resolve_from_oauth_scopes(
            ["governance:read", "governance:write"]
        )

        assert result.primary_role == MACIRole.IMPLEMENTER
        assert result.roles == [MACIRole.IMPLEMENTER, MACIRole.MONITOR]

    def test_oauth_common_scope_patterns(self, role_mapping_service):
        """Test mapping common OAuth scope patterns."""
        scope_mappings = [
            ("admin", MACIRole.EXECUTIVE),
            ("read", MACIRole.MONITOR),
            ("write", MACIRole.IMPLEMENTER),
            ("audit", MACIRole.AUDITOR),
            ("policy:read", MACIRole.LEGISLATIVE),
        ]

        for scope, role in scope_mappings:
            role_mapping_service.create_mapping(
                source_type=RoleMappingSource.OAUTH_SCOPE,
                source_value=scope,
                maci_role=role,
            )

        for scope, expected_role in scope_mappings:
            result = role_mapping_service.resolve_from_oauth_scopes([scope])
            assert result.primary_role == expected_role

    def test_oauth_scope_with_openid_profile(self, role_mapping_service):
        """Test OAuth scope resolution with common OIDC scopes."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="governance:admin",
            maci_role=MACIRole.EXECUTIVE,
        )

        # Should ignore openid/profile scopes that aren't mapped
        result = role_mapping_service.resolve_from_oauth_scopes(
            ["openid", "profile", "email", "governance:admin"]
        )

        assert len(result.roles) == 1
        assert result.primary_role == MACIRole.EXECUTIVE

    def test_oauth_scope_multi_tenant(self, role_mapping_service):
        """Test OAuth scope mapping with multi-tenant support."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="api:admin",
            maci_role=MACIRole.EXECUTIVE,
            tenant_id="okta-tenant",
        )
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="api:admin",
            maci_role=MACIRole.JUDICIAL,
            tenant_id="auth0-tenant",
        )

        okta_result = role_mapping_service.resolve_from_oauth_scopes(
            ["api:admin"],
            tenant_id="okta-tenant",
        )
        assert okta_result.primary_role == MACIRole.EXECUTIVE

        auth0_result = role_mapping_service.resolve_from_oauth_scopes(
            ["api:admin"],
            tenant_id="auth0-tenant",
        )
        assert auth0_result.primary_role == MACIRole.JUDICIAL


# =============================================================================
# Task 6.9: Role Mapping Cache with 5-minute TTL
# =============================================================================


class TestRoleMappingCache:
    """Tests for role mapping cache with TTL (Task 6.9)."""

    def test_cache_stores_result(self, role_mapping_cache):
        """Test that cache stores a result."""
        result = RoleMappingResult(
            roles=[MACIRole.EXECUTIVE],
            matched_mappings=[],
            primary_role=MACIRole.EXECUTIVE,
        )

        role_mapping_cache.set(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result,
        )

        cached = role_mapping_cache.get(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
        )

        assert cached is not None
        assert cached.primary_role == MACIRole.EXECUTIVE
        assert cached.from_cache is True

    def test_cache_ttl_expiration(self, role_mapping_cache):
        """Test that cache entries expire after TTL."""
        result = RoleMappingResult(
            roles=[MACIRole.EXECUTIVE],
            matched_mappings=[],
            primary_role=MACIRole.EXECUTIVE,
        )

        # Capture the current time when setting the cache entry
        initial_time = time.time()

        role_mapping_cache.set(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result,
        )

        # Mock time.time() in the role_mapping module to advance past TTL
        with patch("enterprise_sso.role_mapping.time.time") as mock_time:
            # Advance time by 6 seconds (past the 5 second TTL)
            mock_time.return_value = initial_time + 6

            cached = role_mapping_cache.get(
                tenant_id="tenant-1",
                source_type=RoleMappingSource.LDAP_GROUP,
                source_values=["Admins"],
            )

            assert cached is None

    def test_cache_key_includes_all_parameters(self, role_mapping_cache):
        """Test that cache key differentiates on all parameters."""
        result1 = RoleMappingResult(
            roles=[MACIRole.EXECUTIVE],
            matched_mappings=[],
            primary_role=MACIRole.EXECUTIVE,
        )
        result2 = RoleMappingResult(
            roles=[MACIRole.MONITOR],
            matched_mappings=[],
            primary_role=MACIRole.MONITOR,
        )

        role_mapping_cache.set(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result1,
        )
        role_mapping_cache.set(
            tenant_id="tenant-2",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result2,
        )

        cached1 = role_mapping_cache.get(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
        )
        cached2 = role_mapping_cache.get(
            tenant_id="tenant-2",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
        )

        assert cached1.primary_role == MACIRole.EXECUTIVE
        assert cached2.primary_role == MACIRole.MONITOR

    def test_cache_invalidate_by_tenant(self, role_mapping_cache):
        """Test invalidating cache by tenant."""
        result = RoleMappingResult(
            roles=[MACIRole.EXECUTIVE],
            matched_mappings=[],
            primary_role=MACIRole.EXECUTIVE,
        )

        role_mapping_cache.set(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result,
        )
        role_mapping_cache.set(
            tenant_id="tenant-2",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result,
        )

        count = role_mapping_cache.invalidate(tenant_id="tenant-1")

        assert count == 1
        assert (
            role_mapping_cache.get(
                tenant_id="tenant-1",
                source_type=RoleMappingSource.LDAP_GROUP,
                source_values=["Admins"],
            )
            is None
        )
        assert (
            role_mapping_cache.get(
                tenant_id="tenant-2",
                source_type=RoleMappingSource.LDAP_GROUP,
                source_values=["Admins"],
            )
            is not None
        )

    def test_cache_invalidate_by_source_type(self, role_mapping_cache):
        """Test invalidating cache by source type."""
        result = RoleMappingResult(
            roles=[MACIRole.EXECUTIVE],
            matched_mappings=[],
            primary_role=MACIRole.EXECUTIVE,
        )

        role_mapping_cache.set(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result,
        )
        role_mapping_cache.set(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_values=["admin"],
            result=result,
        )

        count = role_mapping_cache.invalidate(source_type=RoleMappingSource.LDAP_GROUP)

        assert count == 1
        assert (
            role_mapping_cache.get(
                tenant_id="tenant-1",
                source_type=RoleMappingSource.LDAP_GROUP,
                source_values=["Admins"],
            )
            is None
        )
        assert (
            role_mapping_cache.get(
                tenant_id="tenant-1",
                source_type=RoleMappingSource.SAML_ATTRIBUTE,
                source_values=["admin"],
            )
            is not None
        )

    def test_cache_clear_all(self, role_mapping_cache):
        """Test clearing all cache entries."""
        result = RoleMappingResult(
            roles=[MACIRole.EXECUTIVE],
            matched_mappings=[],
            primary_role=MACIRole.EXECUTIVE,
        )

        for i in range(5):
            role_mapping_cache.set(
                tenant_id=f"tenant-{i}",
                source_type=RoleMappingSource.LDAP_GROUP,
                source_values=["Admins"],
                result=result,
            )

        role_mapping_cache.clear()
        stats = role_mapping_cache.get_stats()

        assert stats["size"] == 0

    def test_cache_statistics(self, role_mapping_cache):
        """Test cache statistics tracking."""
        result = RoleMappingResult(
            roles=[MACIRole.EXECUTIVE],
            matched_mappings=[],
            primary_role=MACIRole.EXECUTIVE,
        )

        # Cache miss
        role_mapping_cache.get(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
        )

        # Cache set
        role_mapping_cache.set(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
            result=result,
        )

        # Cache hit
        role_mapping_cache.get(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
        )
        role_mapping_cache.get(
            tenant_id="tenant-1",
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=["Admins"],
        )

        stats = role_mapping_cache.get_stats()

        assert stats["misses"] == 1
        assert stats["hits"] == 2
        assert stats["size"] == 1

    def test_service_uses_cache(self, role_mapping_service):
        """Test that the service uses cache for repeated lookups."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        # First call should miss cache
        result1 = role_mapping_service.resolve_from_ldap_groups(["Admins"])
        assert result1.from_cache is False

        # Second call should hit cache
        result2 = role_mapping_service.resolve_from_ldap_groups(["Admins"])
        assert result2.from_cache is True

        stats = role_mapping_service.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_service_cache_invalidation_on_create(self, role_mapping_service):
        """Test that cache is invalidated when a new mapping is created."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        # Populate cache
        result1 = role_mapping_service.resolve_from_ldap_groups(["Admins"])
        assert not result1.from_cache

        # Create new mapping - should invalidate cache
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="SuperAdmins",
            maci_role=MACIRole.EXECUTIVE,
        )

        # Should miss cache after invalidation
        result2 = role_mapping_service.resolve_from_ldap_groups(["Admins"])
        assert not result2.from_cache

    def test_service_cache_bypass(self, role_mapping_service):
        """Test bypassing cache."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        # Populate cache
        role_mapping_service.resolve_from_ldap_groups(["Admins"])

        # Bypass cache
        result = role_mapping_service.resolve_from_ldap_groups(
            ["Admins"],
            use_cache=False,
        )

        assert result.from_cache is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestRoleMappingIntegration:
    """Integration tests for role mapping with SSO systems (Task 6.10)."""

    def test_full_ldap_to_maci_flow(self, populated_service):
        """Test complete LDAP group to MACI role resolution flow."""
        ldap_groups = [
            "CN=Admins,OU=Groups,DC=example,DC=com",
            "CN=Developers,OU=Groups,DC=example,DC=com",
        ]

        result = populated_service.resolve_from_ldap_groups(
            ldap_groups,
            tenant_id="tenant-1",
        )

        assert result.primary_role == MACIRole.EXECUTIVE
        assert MACIRole.IMPLEMENTER in result.roles
        assert len(result.matched_mappings) == 2

    def test_full_saml_to_maci_flow(self, populated_service):
        """Test complete SAML attribute to MACI role resolution flow."""
        saml_groups = ["governance-admin", "policy-writer"]

        result = populated_service.resolve_from_saml_attributes(
            saml_groups,
            tenant_id="tenant-1",
        )

        assert result.primary_role == MACIRole.EXECUTIVE
        assert MACIRole.LEGISLATIVE in result.roles

    def test_full_oauth_to_maci_flow(self, populated_service):
        """Test complete OAuth scope to MACI role resolution flow."""
        oauth_scopes = ["governance:admin", "governance:read"]

        result = populated_service.resolve_from_oauth_scopes(
            oauth_scopes,
            tenant_id="tenant-1",
        )

        assert result.primary_role == MACIRole.EXECUTIVE
        assert MACIRole.MONITOR in result.roles

    def test_cross_source_type_isolation(self, populated_service):
        """Test that different source types are properly isolated."""
        # Same value in different source types should use different mappings
        populated_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="admin",
            maci_role=MACIRole.EXECUTIVE,
        )
        populated_service.create_mapping(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_value="admin",
            maci_role=MACIRole.JUDICIAL,
        )
        populated_service.create_mapping(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_value="admin",
            maci_role=MACIRole.LEGISLATIVE,
        )

        ldap_result = populated_service.resolve_from_ldap_groups(["admin"])
        saml_result = populated_service.resolve_from_saml_attributes(["admin"])
        oauth_result = populated_service.resolve_from_oauth_scopes(["admin"])

        assert ldap_result.primary_role == MACIRole.EXECUTIVE
        assert saml_result.primary_role == MACIRole.JUDICIAL
        assert oauth_result.primary_role == MACIRole.LEGISLATIVE

    def test_serialization_roundtrip(self, populated_service):
        """Test service serialization and deserialization."""
        original_data = populated_service.to_dict()

        restored = RoleMappingService.from_dict(original_data)

        assert len(restored.list_mappings()) == len(populated_service.list_mappings())

        result = restored.resolve_from_ldap_groups(
            ["CN=Admins,OU=Groups,DC=example,DC=com"],
            tenant_id="tenant-1",
        )
        assert result.primary_role == MACIRole.EXECUTIVE


# =============================================================================
# Constitutional Hash Validation
# =============================================================================


class TestConstitutionalHashValidation:
    """Tests for constitutional hash validation in role mapping."""

    def test_valid_constitutional_hash(self):
        """Test service creation with valid constitutional hash."""
        service = RoleMappingService(constitutional_hash=CONSTITUTIONAL_HASH)
        assert service is not None

    def test_invalid_constitutional_hash_raises(self):
        """Test that invalid constitutional hash raises error."""
        with pytest.raises(ValueError) as exc_info:
            RoleMappingService(constitutional_hash="invalid-hash")

        assert "Invalid constitutional hash" in str(exc_info.value)

    def test_mapping_includes_constitutional_hash(self, role_mapping_service):
        """Test that mapping serialization includes constitutional hash."""
        mapping = role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        data = mapping.to_dict()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_result_includes_constitutional_hash(self, role_mapping_service):
        """Test that resolution result includes constitutional hash."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        result = role_mapping_service.resolve_from_ldap_groups(["Admins"])
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

        data = result.to_dict()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Edge Cases
# =============================================================================


class TestRoleMappingEdgeCases:
    """Tests for edge cases in role mapping."""

    def test_empty_source_values(self, role_mapping_service):
        """Test resolving with empty source values."""
        result = role_mapping_service.resolve_from_ldap_groups([])
        assert len(result.roles) == 0
        assert result.primary_role is None

    def test_special_characters_in_source_values(self, role_mapping_service):
        """Test source values with special characters."""
        special_values = [
            "CN=Admin Group,OU=Groups,DC=example,DC=com",
            "role:admin/special",
            "admin@example.com",
            "groups#admins",
        ]

        for value in special_values:
            role_mapping_service.create_mapping(
                source_type=RoleMappingSource.LDAP_GROUP,
                source_value=value,
                maci_role=MACIRole.EXECUTIVE,
            )

            result = role_mapping_service.resolve_from_ldap_groups([value])
            assert result.primary_role == MACIRole.EXECUTIVE

    def test_case_sensitive_source_values(self, role_mapping_service):
        """Test that source values are case-sensitive."""
        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        result1 = role_mapping_service.resolve_from_ldap_groups(["Admins"])
        result2 = role_mapping_service.resolve_from_ldap_groups(["admins"])
        result3 = role_mapping_service.resolve_from_ldap_groups(["ADMINS"])

        assert result1.primary_role == MACIRole.EXECUTIVE
        assert result2.primary_role is None
        assert result3.primary_role is None

    def test_large_number_of_mappings(self, role_mapping_service):
        """Test performance with large number of mappings."""
        # Create 1000 mappings
        for i in range(1000):
            role_mapping_service.create_mapping(
                source_type=RoleMappingSource.LDAP_GROUP,
                source_value=f"Group-{i}",
                maci_role=list(MACIRole)[i % len(MACIRole)],
                priority=i,
            )

        # Resolve with 100 groups
        groups = [f"Group-{i}" for i in range(0, 1000, 10)]  # 100 groups

        result = role_mapping_service.resolve_from_ldap_groups(groups)

        assert len(result.matched_mappings) == 100
        assert result.resolution_time_ms < 100  # Should be fast

    def test_concurrent_cache_access(self, role_mapping_service):
        """Test concurrent cache access doesn't cause issues."""
        import threading

        role_mapping_service.create_mapping(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_value="Admins",
            maci_role=MACIRole.EXECUTIVE,
        )

        errors = []

        def resolve_roles():
            try:
                for _ in range(100):
                    result = role_mapping_service.resolve_from_ldap_groups(["Admins"])
                    assert result.primary_role == MACIRole.EXECUTIVE
            except (RuntimeError, ValueError, TypeError, AssertionError) as e:
                errors.append(e)

        threads = [threading.Thread(target=resolve_roles) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
