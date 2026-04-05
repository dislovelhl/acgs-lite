"""
Tests for Constitutional Hash Validation.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from .conftest import (
    CONSTITUTIONAL_HASH,
    IntegrationConfigService,
    IntegrationType,
)


class TestConstitutionalHashValidation:
    """Tests for constitutional hash validation."""

    def test_invalid_constitutional_hash_raises(self):
        """Test that invalid constitutional hash raises error."""
        with pytest.raises(ValueError) as exc_info:
            IntegrationConfigService(constitutional_hash="invalid-hash")

        assert "Invalid constitutional hash" in str(exc_info.value)

    def test_valid_constitutional_hash_accepted(self):
        """Test that valid constitutional hash is accepted."""
        service = IntegrationConfigService(constitutional_hash=CONSTITUTIONAL_HASH)
        assert service._constitutional_hash == CONSTITUTIONAL_HASH

    async def test_integration_dict_includes_hash(self, integration_service):
        """Test that serialized integration includes hash."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Test",
            config={},
        )

        data = integration.to_dict()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
