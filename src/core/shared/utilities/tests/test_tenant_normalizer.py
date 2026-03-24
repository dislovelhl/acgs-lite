"""
Tests for TenantNormalizer utility.
Constitutional Hash: cdd01ef066bc6cf2
"""

from src.core.shared.utilities import TenantNormalizer


class TestTenantNormalizerNormalize:
    """Test TenantNormalizer.normalize() method."""

    def test_normalize_strips_whitespace(self) -> None:
        """Test that whitespace is stripped."""
        assert TenantNormalizer.normalize("  tenant-123  ") == "tenant-123"
        assert TenantNormalizer.normalize("\ttenant\n") == "tenant"

    def test_normalize_lowercases(self) -> None:
        """Test that tenant IDs are lowercased."""
        assert TenantNormalizer.normalize("TENANT-123") == "tenant-123"
        assert TenantNormalizer.normalize("Tenant_ABC") == "tenant_abc"

    def test_normalize_handles_none(self) -> None:
        """Test that None returns None."""
        assert TenantNormalizer.normalize(None) is None

    def test_normalize_handles_empty_string(self) -> None:
        """Test that empty string returns None."""
        assert TenantNormalizer.normalize("") is None
        assert TenantNormalizer.normalize("   ") is None

    def test_normalize_unicode_nfkc(self) -> None:
        """Test that Unicode is normalized to NFKC form."""
        # Full-width characters should normalize
        assert TenantNormalizer.normalize("\uff54\uff45\uff4e\uff41\uff4e\uff54") == "tenant"


class TestTenantNormalizerValidate:
    """Test TenantNormalizer.validate() method."""

    def test_validate_valid_tenant_ids(self) -> None:
        """Test that valid tenant IDs pass validation."""
        assert TenantNormalizer.validate("tenant-123") is True
        assert TenantNormalizer.validate("abc") is True
        assert TenantNormalizer.validate("my_tenant_id") is True
        assert TenantNormalizer.validate("tenant-with-dashes") is True

    def test_validate_rejects_too_short(self) -> None:
        """Test that tenant IDs under 3 chars are rejected."""
        assert TenantNormalizer.validate("ab") is False
        assert TenantNormalizer.validate("a") is False

    def test_validate_rejects_too_long(self) -> None:
        """Test that tenant IDs over 64 chars are rejected."""
        long_id = "a" * 65
        assert TenantNormalizer.validate(long_id) is False

    def test_validate_rejects_invalid_characters(self) -> None:
        """Test that invalid characters are rejected."""
        assert TenantNormalizer.validate("tenant@123") is False
        assert TenantNormalizer.validate("tenant 123") is False
        assert TenantNormalizer.validate("tenant.123") is False

    def test_validate_rejects_reserved_tenants(self) -> None:
        """Test that reserved tenant IDs are rejected."""
        assert TenantNormalizer.validate("admin") is False
        assert TenantNormalizer.validate("system") is False
        assert TenantNormalizer.validate("root") is False
        assert TenantNormalizer.validate("default") is False

    def test_validate_rejects_none(self) -> None:
        """Test that None is rejected."""
        assert TenantNormalizer.validate(None) is False

    def test_validate_rejects_empty_string(self) -> None:
        """Test that empty string is rejected."""
        assert TenantNormalizer.validate("") is False


class TestTenantNormalizerNormalizeAndValidate:
    """Test TenantNormalizer.normalize_and_validate() method."""

    def test_normalize_and_validate_valid(self) -> None:
        """Test combined normalize and validate for valid input."""
        normalized, is_valid = TenantNormalizer.normalize_and_validate("  TENANT-123  ")
        assert normalized == "tenant-123"
        assert is_valid is True

    def test_normalize_and_validate_invalid(self) -> None:
        """Test combined normalize and validate for invalid input."""
        normalized, is_valid = TenantNormalizer.normalize_and_validate("admin")
        assert normalized == "admin"
        assert is_valid is False

    def test_normalize_and_validate_none(self) -> None:
        """Test combined normalize and validate for None."""
        normalized, is_valid = TenantNormalizer.normalize_and_validate(None)
        assert normalized is None
        assert is_valid is False


class TestTenantNormalizerGetSafeTenant:
    """Test TenantNormalizer.get_safe_tenant() method."""

    def test_get_safe_tenant_valid(self) -> None:
        """Test that valid tenant is returned."""
        assert TenantNormalizer.get_safe_tenant("tenant-123") == "tenant-123"

    def test_get_safe_tenant_invalid_returns_default(self) -> None:
        """Test that invalid tenant returns default."""
        assert TenantNormalizer.get_safe_tenant("admin") == "default"

    def test_get_safe_tenant_none_returns_default(self) -> None:
        """Test that None returns default."""
        assert TenantNormalizer.get_safe_tenant(None) == "default"

    def test_get_safe_tenant_custom_default(self) -> None:
        """Test custom default value."""
        assert TenantNormalizer.get_safe_tenant(None, default="fallback") == "fallback"


class TestTenantNormalizerTenantsMatch:
    """Test TenantNormalizer.tenants_match() method."""

    def test_tenants_match_same(self) -> None:
        """Test matching tenants."""
        assert TenantNormalizer.tenants_match("tenant-123", "tenant-123") is True

    def test_tenants_match_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        assert TenantNormalizer.tenants_match("TENANT-123", "tenant-123") is True

    def test_tenants_match_whitespace(self) -> None:
        """Test matching with whitespace."""
        assert TenantNormalizer.tenants_match("  tenant-123  ", "tenant-123") is True

    def test_tenants_match_different(self) -> None:
        """Test non-matching tenants."""
        assert TenantNormalizer.tenants_match("tenant-123", "tenant-456") is False

    def test_tenants_match_both_none(self) -> None:
        """Test that both None matches."""
        assert TenantNormalizer.tenants_match(None, None) is True

    def test_tenants_match_one_none(self) -> None:
        """Test that one None doesn't match."""
        assert TenantNormalizer.tenants_match("tenant-123", None) is False
        assert TenantNormalizer.tenants_match(None, "tenant-123") is False


class TestTenantNormalizerIsReserved:
    """Test TenantNormalizer.is_reserved() method."""

    def test_is_reserved_true(self) -> None:
        """Test reserved tenant detection."""
        assert TenantNormalizer.is_reserved("admin") is True
        assert TenantNormalizer.is_reserved("SYSTEM") is True

    def test_is_reserved_false(self) -> None:
        """Test non-reserved tenant."""
        assert TenantNormalizer.is_reserved("my-tenant") is False

    def test_is_reserved_none(self) -> None:
        """Test None is not reserved."""
        assert TenantNormalizer.is_reserved(None) is False
