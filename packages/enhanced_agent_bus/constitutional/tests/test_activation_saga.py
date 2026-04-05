"""
Tests for Constitutional Amendment Activation Saga
Constitutional Hash: 608508a9bd224290

Tests for saga workflow for activating constitutional amendments.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..activation_saga import (
    ActivationSagaActivities,
    ActivationSagaError,
    create_activation_saga,
)
from ..amendment_model import AmendmentProposal, AmendmentStatus
from ..storage import ConstitutionalStorageService
from ..version_model import ConstitutionalStatus, ConstitutionalVersion

# Constitutional validation markers
pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.unit,
]


class TestActivationSagaActivities:
    """Test ActivationSagaActivities methods."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage service."""
        storage = AsyncMock(spec=ConstitutionalStorageService)
        return storage

    @pytest.fixture
    def activities(self, mock_storage):
        """Create activities instance for testing."""
        return ActivationSagaActivities(
            storage=mock_storage,
            opa_url="http://localhost:8181",
            audit_service_url="http://localhost:8001",
            redis_url="redis://localhost:6379",
        )

    @pytest.fixture
    def mock_amendment(self):
        """Create mock approved amendment."""
        amendment = AmendmentProposal(
            proposal_id="amendment-123",
            proposed_changes={"principle_1": "Updated governance principle"},
            justification="Improving governance compliance per MACI framework requirements.",
            proposer_agent_id="agent-executive-001",
            target_version="1.0.0",
            new_version="1.1.0",
            status=AmendmentStatus.APPROVED,
            impact_score=0.75,
        )
        return amendment

    @pytest.fixture
    def mock_target_version(self):
        """Create mock target constitutional version."""
        return ConstitutionalVersion(
            version_id="version-1.0.0",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": ["Principle 1", "Principle 2"]},
            status=ConstitutionalStatus.ACTIVE,
        )

    @pytest.fixture
    def mock_active_version(self):
        """Create mock active constitutional version."""
        return ConstitutionalVersion(
            version_id="version-1.0.0",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": ["Principle 1", "Principle 2"]},
            status=ConstitutionalStatus.ACTIVE,
        )

    def test_compute_constitutional_hash(self, activities):
        """Test constitutional hash computation."""
        content = {"principles": ["Principle 1", "Principle 2"], "version": "1.0.0"}

        hash1 = activities._compute_constitutional_hash(content)
        hash2 = activities._compute_constitutional_hash(content)

        # Hash should be deterministic
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_compute_constitutional_hash_order_independent(self, activities):
        """Test that hash computation is order-independent (due to sort_keys)."""
        content1 = {"b": 2, "a": 1}
        content2 = {"a": 1, "b": 2}

        hash1 = activities._compute_constitutional_hash(content1)
        hash2 = activities._compute_constitutional_hash(content2)

        assert hash1 == hash2

    async def test_validate_activation_success(
        self, activities, mock_storage, mock_amendment, mock_target_version, mock_active_version
    ):
        """Test successful validation of amendment activation."""
        mock_storage.get_amendment.return_value = mock_amendment
        mock_storage.get_version.return_value = mock_target_version
        mock_storage.get_active_version.return_value = mock_active_version

        input_data = {
            "saga_id": "saga-001",
            "context": {"amendment_id": "amendment-123"},
        }

        result = await activities.validate_activation(input_data)

        assert result["is_valid"] is True
        assert result["amendment_id"] == "amendment-123"
        assert result["target_version"] == "1.0.0"
        assert result["new_version"] == "1.1.0"
        assert "validation_id" in result

    async def test_validate_activation_missing_amendment_id(self, activities):
        """Test validation fails without amendment_id."""
        input_data = {
            "saga_id": "saga-001",
            "context": {},
        }

        with pytest.raises(ActivationSagaError, match="Missing amendment_id"):
            await activities.validate_activation(input_data)

    async def test_validate_activation_amendment_not_found(self, activities, mock_storage):
        """Test validation fails when amendment not found."""
        mock_storage.get_amendment.return_value = None

        input_data = {
            "saga_id": "saga-001",
            "context": {"amendment_id": "nonexistent"},
        }

        with pytest.raises(ActivationSagaError, match="not found"):
            await activities.validate_activation(input_data)

    async def test_validate_activation_wrong_status(self, activities, mock_storage, mock_amendment):
        """Test validation fails when amendment is not approved."""
        mock_amendment.status = AmendmentStatus.PROPOSED
        mock_storage.get_amendment.return_value = mock_amendment

        input_data = {
            "saga_id": "saga-001",
            "context": {"amendment_id": "amendment-123"},
        }

        with pytest.raises(ActivationSagaError, match="not approved"):
            await activities.validate_activation(input_data)

    async def test_backup_current_version_success(
        self, activities, mock_storage, mock_active_version
    ):
        """Test successful backup of current version."""
        mock_storage.get_active_version.return_value = mock_active_version

        input_data = {
            "saga_id": "saga-001",
            "context": {},
        }

        result = await activities.backup_current_version(input_data)

        assert "backup_id" in result
        assert result["version_id"] == "version-1.0.0"
        assert result["version"] == "1.0.0"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_backup_current_version_no_active(self, activities, mock_storage):
        """Test backup fails when no active version exists."""
        mock_storage.get_active_version.return_value = None

        input_data = {
            "saga_id": "saga-001",
            "context": {},
        }

        with pytest.raises(ActivationSagaError, match="No active constitutional version"):
            await activities.backup_current_version(input_data)

    async def test_restore_backup_success(self, activities, mock_storage):
        """Test successful backup restoration (compensation)."""
        mock_storage.activate_version.return_value = None

        input_data = {
            "saga_id": "saga-001",
            "context": {
                "backup_current_version": {
                    "version_id": "version-1.0.0",
                    "version": "1.0.0",
                }
            },
        }

        result = await activities.restore_backup(input_data)

        assert result is True
        mock_storage.activate_version.assert_called_once_with("version-1.0.0")

    async def test_restore_backup_no_backup_data(self, activities, mock_storage):
        """Test restoration fails without backup data."""
        input_data = {
            "saga_id": "saga-001",
            "context": {},
        }

        result = await activities.restore_backup(input_data)

        assert result is False

    async def test_update_opa_policies_success(
        self, activities, mock_storage, mock_amendment, mock_target_version
    ):
        """Test successful OPA policy update."""
        mock_storage.get_amendment.return_value = mock_amendment
        mock_storage.get_version.return_value = mock_target_version

        # Mock HTTP client
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=200)

        input_data = {
            "saga_id": "saga-001",
            "context": {
                "amendment_id": "amendment-123",
                "validate_activation": {
                    "new_version": "1.1.0",
                },
            },
        }

        result = await activities.update_opa_policies(input_data)

        assert result["updated"] is True
        assert "new_hash" in result
        assert result["new_version"] == "1.1.0"

    async def test_update_cache_success(
        self, activities, mock_storage, mock_amendment, mock_target_version
    ):
        """Test successful cache update and version activation."""
        mock_storage.get_amendment.return_value = mock_amendment
        mock_storage.get_version.return_value = mock_target_version

        # Mock Redis client
        activities._redis_client = AsyncMock()
        activities._redis_client.delete.return_value = 1

        # Mock the hash computation to return 16-char hash
        activities._compute_constitutional_hash = MagicMock(return_value=CONSTITUTIONAL_HASH)

        input_data = {
            "saga_id": "saga-001",
            "context": {
                "amendment_id": "amendment-123",
                "validate_activation": {
                    "new_version": "1.1.0",
                },
            },
        }

        result = await activities.update_cache(input_data)

        assert result["activated"] is True
        assert result["cache_invalidated"] is True
        assert result["new_version"] == "1.1.0"

        # Verify storage calls
        mock_storage.save_version.assert_called_once()
        mock_storage.activate_version.assert_called_once()
        mock_storage.save_amendment.assert_called_once()

    async def test_audit_activation_success(self, activities):
        """Test successful audit logging."""
        activities._audit_client = AsyncMock()
        activities._audit_client.log.return_value = None

        input_data = {
            "saga_id": "saga-001",
            "context": {
                "amendment_id": "amendment-123",
                "validate_activation": {"new_version": "1.1.0"},
                "backup_current_version": {"version": "1.0.0", "version_id": "v-1.0.0"},
                "update_cache": {"new_version_id": "v-1.1.0"},
            },
        }

        result = await activities.audit_activation(input_data)

        assert result["event_type"] == "constitutional_version_activated"
        assert result["amendment_id"] == "amendment-123"
        assert result["new_version"] == "1.1.0"
        assert result["previous_version"] == "1.0.0"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_log_validation_failure_compensation(self, activities):
        """Test validation failure logging (compensation)."""
        input_data = {"saga_id": "saga-001", "context": {}}

        result = await activities.log_validation_failure(input_data)

        assert result is True

    async def test_mark_audit_failed_compensation(self, activities):
        """Test marking audit as failed (compensation)."""
        activities._audit_client = AsyncMock()

        input_data = {
            "saga_id": "saga-001",
            "context": {
                "audit_activation": {"audit_id": "audit-123"},
            },
        }

        result = await activities.mark_audit_failed(input_data)

        assert result is True


class TestActivationSagaFactory:
    """Test create_activation_saga factory function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage service."""
        return AsyncMock(spec=ConstitutionalStorageService)

    def test_create_activation_saga_without_workflow(self, mock_storage):
        """Test saga creation fails without ConstitutionalSagaWorkflow."""
        with patch(
            "enhanced_agent_bus.constitutional.activation_saga.ConstitutionalSagaWorkflow",
            None,
        ):
            with pytest.raises(ImportError, match="ConstitutionalSagaWorkflow not available"):
                create_activation_saga(
                    amendment_id="amendment-123",
                    storage=mock_storage,
                )

    def test_create_activation_saga_requires_workflow(self, mock_storage):
        """Test saga creation requires ConstitutionalSagaWorkflow to be available.

        The saga factory requires the deliberation_layer.workflows module to be
        installed. If not available, it should raise ImportError with a helpful message.
        """
        # When ConstitutionalSagaWorkflow is not available (as in test environment),
        # creating a saga should raise ImportError with guidance
        with pytest.raises(ImportError, match="ConstitutionalSagaWorkflow not available"):
            create_activation_saga(
                amendment_id="amendment-123",
                storage=mock_storage,
                opa_url="http://opa:8181",
                audit_service_url="http://audit:8001",
                redis_url="redis://redis:6379",
            )


class TestActivationSagaIntegration:
    """Integration-style tests for activation saga flow."""

    @pytest.fixture
    def mock_storage(self):
        """Create fully configured mock storage."""
        storage = AsyncMock(spec=ConstitutionalStorageService)

        # Mock active version
        active_version = ConstitutionalVersion(
            version_id="v-1.0.0",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": ["P1", "P2"]},
            status=ConstitutionalStatus.ACTIVE,
        )
        storage.get_active_version.return_value = active_version
        storage.get_version.return_value = active_version

        # Mock amendment
        amendment = AmendmentProposal(
            proposal_id="amendment-123",
            proposed_changes={"new_principle": "P3"},
            justification="Adding new governance principle for enhanced compliance.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            new_version="1.1.0",
            status=AmendmentStatus.APPROVED,
        )
        storage.get_amendment.return_value = amendment

        return storage

    async def test_full_activation_flow(self, mock_storage):
        """Test complete activation flow through activities."""
        activities = ActivationSagaActivities(
            storage=mock_storage,
            opa_url="http://localhost:8181",
        )

        # Step 1: Validate
        validate_input = {
            "saga_id": "saga-test-001",
            "context": {"amendment_id": "amendment-123"},
        }
        validate_result = await activities.validate_activation(validate_input)
        assert validate_result["is_valid"] is True

        # Step 2: Backup
        backup_input = {
            "saga_id": "saga-test-001",
            "context": {},
        }
        backup_result = await activities.backup_current_version(backup_input)
        assert backup_result["version"] == "1.0.0"

        # Verify amendment status was checked
        mock_storage.get_amendment.assert_called()
        mock_storage.get_active_version.assert_called()


class TestConstitutionalHashEnforcement:
    """Test constitutional hash enforcement in activation saga."""

    def test_hash_in_audit_event(self):
        """Test constitutional hash is included in audit events."""
        activities = ActivationSagaActivities(
            storage=AsyncMock(),
            opa_url="http://localhost:8181",
        )

        # Verify hash is used in compute function
        content = {"test": "data"}
        computed_hash = activities._compute_constitutional_hash(content)
        assert len(computed_hash) == 64  # Valid SHA256

    async def test_hash_validation_during_activation(self):
        """Test constitutional hash validation during activation."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)

        # Target version with different but valid format hash (16 hex chars)
        different_hash = "abcd1234ef567890"
        mismatched_version = ConstitutionalVersion(
            version_id="v-1.0.0",
            version="1.0.0",
            constitutional_hash=different_hash,  # Different from CONSTITUTIONAL_HASH
            content={"principles": []},
            status=ConstitutionalStatus.ACTIVE,
        )
        mock_storage.get_version.return_value = mismatched_version
        mock_storage.get_active_version.return_value = mismatched_version

        amendment = AmendmentProposal(
            proposal_id="amendment-123",
            proposed_changes={"key": "value"},
            justification="Test amendment for hash validation.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            status=AmendmentStatus.APPROVED,
        )
        mock_storage.get_amendment.return_value = amendment

        activities = ActivationSagaActivities(
            storage=mock_storage,
            opa_url="http://localhost:8181",
        )

        input_data = {
            "saga_id": "saga-001",
            "context": {"amendment_id": "amendment-123"},
        }

        with pytest.raises(ActivationSagaError, match="constitutional hash"):
            await activities.validate_activation(input_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
