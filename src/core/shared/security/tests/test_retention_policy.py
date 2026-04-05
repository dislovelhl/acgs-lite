"""
FR-11 Data Retention Controls Integration Tests
Constitutional Hash: 608508a9bd224290

Tests for RetentionPolicyEngine, disposal handlers, and GDPR compliance.
"""

from datetime import UTC, datetime, timedelta

from src.core.shared.security.data_classification import (
    CONSTITUTIONAL_HASH,
    DataClassificationTier,
    DisposalMethod,
    PIICategory,
)
from src.core.shared.security.retention_policy import (
    AnonymizeHandler,
    ArchiveHandler,
    DeleteHandler,
    DisposalResult,
    InMemoryRetentionStorage,
    PseudonymizeHandler,
    RetentionAction,
    RetentionActionType,
    RetentionEnforcementReport,
    RetentionPolicyEngine,
    RetentionRecord,
    RetentionStatus,
    get_retention_engine,
    reset_retention_engine,
)


class TestRetentionRecord:
    """Tests for RetentionRecord model."""

    def test_record_creation_with_defaults(self):
        """Test retention record creates with proper defaults."""
        record = RetentionRecord(
            data_id="data-123",
            data_type="user_message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.CONFIDENTIAL,
            retention_until=datetime.now(UTC) + timedelta(days=90),
        )

        assert record.record_id is not None
        assert record.status == RetentionStatus.ACTIVE
        assert record.legal_hold is False
        assert record.constitutional_hash == CONSTITUTIONAL_HASH

    def test_record_creation_with_pii_categories(self):
        """Test retention record with PII categories."""
        record = RetentionRecord(
            data_id="data-456",
            data_type="customer_profile",
            policy_id="policy-002",
            classification_tier=DataClassificationTier.RESTRICTED,
            pii_categories=[PIICategory.CONTACT_INFO, PIICategory.PERSONAL_IDENTIFIERS],
            retention_until=datetime.now(UTC) + timedelta(days=30),
            tenant_id="tenant-abc",
        )

        assert len(record.pii_categories) == 2
        assert PIICategory.CONTACT_INFO in record.pii_categories
        assert record.tenant_id == "tenant-abc"

    def test_record_with_legal_hold(self):
        """Test retention record with legal hold."""
        record = RetentionRecord(
            data_id="data-789",
            data_type="audit_log",
            policy_id="policy-003",
            classification_tier=DataClassificationTier.RESTRICTED,
            retention_until=datetime.now(UTC) + timedelta(days=365),
            legal_hold=True,
            legal_hold_reason="Litigation pending - Case #12345",
        )

        assert record.legal_hold is True
        assert "Litigation" in record.legal_hold_reason


class TestRetentionAction:
    """Tests for RetentionAction audit model."""

    def test_action_creation(self):
        """Test retention action audit entry creation."""
        action = RetentionAction(
            record_id="rec-123",
            action_type=RetentionActionType.CREATED,
            new_status=RetentionStatus.ACTIVE,
            performed_by="system",
            details={"policy_id": "policy-001"},
        )

        assert action.action_id is not None
        assert action.action_type == RetentionActionType.CREATED
        assert action.constitutional_hash == CONSTITUTIONAL_HASH

    def test_action_with_status_change(self):
        """Test retention action with status transition."""
        action = RetentionAction(
            record_id="rec-456",
            action_type=RetentionActionType.DISPOSED,
            previous_status=RetentionStatus.ACTIVE,
            new_status=RetentionStatus.DISPOSED,
            performed_by="retention_job",
        )

        assert action.previous_status == RetentionStatus.ACTIVE
        assert action.new_status == RetentionStatus.DISPOSED


class TestInMemoryRetentionStorage:
    """Tests for in-memory storage backend."""

    def setup_method(self):
        """Set up test fixtures."""
        self.storage = InMemoryRetentionStorage()

    async def test_save_and_get_record(self):
        """Test saving and retrieving a retention record."""
        record = RetentionRecord(
            data_id="data-001",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) + timedelta(days=30),
        )

        await self.storage.save_record(record)
        retrieved = await self.storage.get_record(record.record_id)

        assert retrieved is not None
        assert retrieved.data_id == "data-001"
        assert retrieved.record_id == record.record_id

    async def test_get_nonexistent_record(self):
        """Test retrieving nonexistent record returns None."""
        retrieved = await self.storage.get_record("nonexistent-id")
        assert retrieved is None

    async def test_find_expired_records(self):
        """Test finding expired retention records."""
        # Create expired record
        expired_record = RetentionRecord(
            data_id="expired-001",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
        )
        await self.storage.save_record(expired_record)

        # Create active record
        active_record = RetentionRecord(
            data_id="active-001",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) + timedelta(days=30),
        )
        await self.storage.save_record(active_record)

        expired = await self.storage.find_expired_records()

        assert len(expired) == 1
        assert expired[0].data_id == "expired-001"

    async def test_find_expired_excludes_legal_hold(self):
        """Test that legal hold records are not marked as expired."""
        # Create expired record with legal hold
        held_record = RetentionRecord(
            data_id="held-001",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            legal_hold=True,
            legal_hold_reason="Investigation",
        )
        await self.storage.save_record(held_record)

        expired = await self.storage.find_expired_records()
        assert len(expired) == 0

    async def test_find_expired_with_tenant_filter(self):
        """Test finding expired records filtered by tenant."""
        # Create expired record for tenant A
        record_a = RetentionRecord(
            data_id="data-a",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            tenant_id="tenant-a",
        )
        await self.storage.save_record(record_a)

        # Create expired record for tenant B
        record_b = RetentionRecord(
            data_id="data-b",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            tenant_id="tenant-b",
        )
        await self.storage.save_record(record_b)

        expired = await self.storage.find_expired_records(tenant_id="tenant-a")

        assert len(expired) == 1
        assert expired[0].tenant_id == "tenant-a"

    async def test_log_action(self):
        """Test logging retention actions."""
        action = RetentionAction(
            record_id="rec-001",
            action_type=RetentionActionType.CREATED,
            new_status=RetentionStatus.ACTIVE,
        )

        await self.storage.log_action(action)
        actions = await self.storage.get_actions(record_id="rec-001")

        assert len(actions) == 1
        assert actions[0].action_type == RetentionActionType.CREATED


class TestDisposalHandlers:
    """Tests for disposal handler implementations."""

    async def test_delete_handler_success(self):
        """Test DeleteHandler successful disposal."""
        handler = DeleteHandler()
        record = RetentionRecord(
            data_id="data-001",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )

        result = await handler.dispose(record, data={"content": "test data"})

        assert result.success is True
        assert result.method == DisposalMethod.DELETE
        assert result.audit_trail_hash != ""
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_archive_handler_success(self):
        """Test ArchiveHandler successful disposal."""
        handler = ArchiveHandler()
        record = RetentionRecord(
            data_id="data-002",
            data_type="audit_log",
            policy_id="policy-002",
            classification_tier=DataClassificationTier.CONFIDENTIAL,
            retention_until=datetime.now(UTC),
        )

        result = await handler.dispose(record)

        assert result.success is True
        assert result.method == DisposalMethod.ARCHIVE
        assert result.audit_trail_hash != ""

    async def test_anonymize_handler_success(self):
        """Test AnonymizeHandler successful disposal."""
        handler = AnonymizeHandler()
        record = RetentionRecord(
            data_id="data-003",
            data_type="user_profile",
            policy_id="policy-003",
            classification_tier=DataClassificationTier.RESTRICTED,
            pii_categories=[PIICategory.CONTACT_INFO, PIICategory.PERSONAL_IDENTIFIERS],
            retention_until=datetime.now(UTC),
        )

        result = await handler.dispose(record)

        assert result.success is True
        assert result.method == DisposalMethod.ANONYMIZE
        assert result.bytes_disposed == 0  # Data transformed, not deleted

    async def test_pseudonymize_handler_success(self):
        """Test PseudonymizeHandler successful disposal."""
        handler = PseudonymizeHandler()
        record = RetentionRecord(
            data_id="data-004",
            data_type="analytics",
            policy_id="policy-004",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )

        result = await handler.dispose(record)

        assert result.success is True
        assert result.method == DisposalMethod.PSEUDONYMIZE


class TestRetentionPolicyEngine:
    """Tests for RetentionPolicyEngine."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_retention_engine()
        self.engine = RetentionPolicyEngine()

    def teardown_method(self):
        """Clean up after tests."""
        reset_retention_engine()

    def test_engine_constitutional_hash(self):
        """Test engine has constitutional hash set."""
        assert self.engine.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_create_retention_record(self):
        """Test creating a retention record."""
        record = await self.engine.create_retention_record(
            data_id="data-new-001",
            data_type="message",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
            tenant_id="test-tenant",
        )

        assert record is not None
        assert record.data_id == "data-new-001"
        assert record.status == RetentionStatus.ACTIVE
        assert record.tenant_id == "test-tenant"
        assert record.retention_until > datetime.now(UTC)

    async def test_create_retention_record_with_pii(self):
        """Test creating retention record with PII categories."""
        record = await self.engine.create_retention_record(
            data_id="data-pii-001",
            data_type="customer_data",
            policy_id="retention-restricted-90",
            classification_tier=DataClassificationTier.RESTRICTED,
            pii_categories=[PIICategory.CONTACT_INFO, PIICategory.PERSONAL_IDENTIFIERS],
            metadata={"source": "registration"},
        )

        assert len(record.pii_categories) == 2
        assert PIICategory.PERSONAL_IDENTIFIERS in record.pii_categories
        assert record.metadata.get("source") == "registration"

    async def test_extend_retention(self):
        """Test extending retention period."""
        # Create record
        record = await self.engine.create_retention_record(
            data_id="data-extend-001",
            data_type="document",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
        )

        original_retention = record.retention_until

        # Extend by 30 days
        updated = await self.engine.extend_retention(
            record_id=record.record_id,
            additional_days=30,
            reason="Business requirement extension",
            performed_by="admin",
        )

        assert updated is not None
        assert updated.retention_until > original_retention
        expected_extension = original_retention + timedelta(days=30)
        assert updated.retention_until == expected_extension

    async def test_extend_retention_nonexistent(self):
        """Test extending nonexistent record returns None."""
        result = await self.engine.extend_retention(
            record_id="nonexistent-id",
            additional_days=30,
            reason="Test",
        )
        assert result is None

    async def test_apply_legal_hold(self):
        """Test applying legal hold."""
        # Create record
        record = await self.engine.create_retention_record(
            data_id="data-hold-001",
            data_type="communication",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.CONFIDENTIAL,
        )

        # Apply legal hold
        held = await self.engine.apply_legal_hold(
            record_id=record.record_id,
            reason="Legal investigation - Case #2024-001",
            performed_by="legal-team",
        )

        assert held is not None
        assert held.legal_hold is True
        assert "Case #2024-001" in held.legal_hold_reason

    async def test_release_legal_hold(self):
        """Test releasing legal hold."""
        # Create record with legal hold
        record = await self.engine.create_retention_record(
            data_id="data-release-001",
            data_type="communication",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.CONFIDENTIAL,
        )

        await self.engine.apply_legal_hold(
            record_id=record.record_id,
            reason="Investigation",
        )

        # Release hold
        released = await self.engine.release_legal_hold(
            record_id=record.record_id,
            performed_by="legal-team",
        )

        assert released is not None
        assert released.legal_hold is False
        assert released.legal_hold_reason is None

    async def test_dispose_record_delete(self):
        """Test disposing record with delete method."""
        # Create record
        record = await self.engine.create_retention_record(
            data_id="data-dispose-001",
            data_type="temp_data",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
        )

        # Dispose
        result = await self.engine.dispose_record(
            record_id=record.record_id,
            method=DisposalMethod.DELETE,
        )

        assert result.success is True
        assert result.method == DisposalMethod.DELETE

        # Verify record status updated
        updated = await self.engine.storage.get_record(record.record_id)
        assert updated.status == RetentionStatus.DISPOSED

    async def test_dispose_record_archive(self):
        """Test disposing record with archive method."""
        record = await self.engine.create_retention_record(
            data_id="data-archive-001",
            data_type="audit_log",
            policy_id="retention-confidential-730",
            classification_tier=DataClassificationTier.CONFIDENTIAL,
        )

        result = await self.engine.dispose_record(
            record_id=record.record_id,
            method=DisposalMethod.ARCHIVE,
        )

        assert result.success is True
        assert result.method == DisposalMethod.ARCHIVE

        updated = await self.engine.storage.get_record(record.record_id)
        assert updated.status == RetentionStatus.ARCHIVED

    async def test_dispose_record_anonymize(self):
        """Test disposing record with anonymize method."""
        record = await self.engine.create_retention_record(
            data_id="data-anon-001",
            data_type="user_analytics",
            policy_id="retention-restricted-90",
            classification_tier=DataClassificationTier.RESTRICTED,
            pii_categories=[PIICategory.CONTACT_INFO],
        )

        result = await self.engine.dispose_record(
            record_id=record.record_id,
            method=DisposalMethod.ANONYMIZE,
        )

        assert result.success is True

        updated = await self.engine.storage.get_record(record.record_id)
        assert updated.status == RetentionStatus.ANONYMIZED

    async def test_dispose_record_blocked_by_legal_hold(self):
        """Test disposal blocked by legal hold."""
        record = await self.engine.create_retention_record(
            data_id="data-blocked-001",
            data_type="evidence",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.RESTRICTED,
        )

        await self.engine.apply_legal_hold(
            record_id=record.record_id,
            reason="Active litigation",
        )

        result = await self.engine.dispose_record(record_id=record.record_id)

        assert result.success is False
        assert "legal hold" in result.error_message.lower()

    async def test_dispose_nonexistent_record(self):
        """Test disposing nonexistent record."""
        result = await self.engine.dispose_record(
            record_id="nonexistent-id",
            method=DisposalMethod.DELETE,
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()

    async def test_enforce_retention(self):
        """Test automated retention enforcement."""
        # Create multiple expired records
        for i in range(3):
            record = RetentionRecord(
                data_id=f"expired-{i}",
                data_type="message",
                policy_id="retention-internal-365",
                classification_tier=DataClassificationTier.INTERNAL,
                retention_until=datetime.now(UTC) - timedelta(days=1),
            )
            await self.engine.storage.save_record(record)

        # Create one active record
        active = RetentionRecord(
            data_id="active-001",
            data_type="message",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) + timedelta(days=30),
        )
        await self.engine.storage.save_record(active)

        # Run enforcement
        report = await self.engine.enforce_retention()

        assert report.records_scanned == 3
        assert report.records_expired == 3
        assert report.records_disposed == 3
        assert report.records_errored == 0
        assert report.duration_ms >= 0
        assert report.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_enforce_retention_skips_legal_hold(self):
        """Test enforcement skips records with legal hold.

        Note: Legal hold records are filtered out at the storage level by
        find_expired_records, so they never reach the enforcement loop.
        records_held counts records that made it to enforcement but were
        skipped due to legal hold - which won't happen with current design.
        """
        # Create expired record with legal hold
        held = RetentionRecord(
            data_id="held-001",
            data_type="evidence",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.RESTRICTED,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            legal_hold=True,
            legal_hold_reason="Investigation",
        )
        await self.engine.storage.save_record(held)

        # Create expired record without hold
        expired = RetentionRecord(
            data_id="expired-001",
            data_type="message",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
        )
        await self.engine.storage.save_record(expired)

        report = await self.engine.enforce_retention()

        # Legal hold records are excluded at storage level, so they don't
        # appear in enforcement. Only the non-held expired record is processed.
        assert report.records_scanned == 1  # Only non-held record scanned
        assert report.records_disposed == 1
        assert report.records_held == 0  # Legal hold filtered at storage level

    async def test_enforce_retention_with_tenant_filter(self):
        """Test enforcement with tenant isolation."""
        # Create expired records for different tenants
        for tenant in ["tenant-a", "tenant-b"]:
            record = RetentionRecord(
                data_id=f"data-{tenant}",
                data_type="message",
                policy_id="retention-internal-365",
                classification_tier=DataClassificationTier.INTERNAL,
                retention_until=datetime.now(UTC) - timedelta(days=1),
                tenant_id=tenant,
            )
            await self.engine.storage.save_record(record)

        # Enforce only for tenant-a
        report = await self.engine.enforce_retention(tenant_id="tenant-a")

        assert report.records_disposed == 1
        assert report.tenant_id == "tenant-a"

    async def test_get_record_history(self):
        """Test retrieving action history for a record."""
        # Create record
        record = await self.engine.create_retention_record(
            data_id="data-history-001",
            data_type="document",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
        )

        # Extend retention
        await self.engine.extend_retention(
            record_id=record.record_id,
            additional_days=30,
            reason="Extension requested",
        )

        # Get history
        history = await self.engine.get_record_history(record.record_id)

        assert len(history) >= 2
        action_types = [a.action_type for a in history]
        assert RetentionActionType.CREATED in action_types
        assert RetentionActionType.EXTENDED in action_types


class TestRetentionEngineSingleton:
    """Tests for singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_retention_engine()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_retention_engine()

    def test_get_retention_engine_returns_singleton(self):
        """Test that get_retention_engine returns same instance."""
        engine1 = get_retention_engine()
        engine2 = get_retention_engine()
        assert engine1 is engine2

    def test_reset_retention_engine(self):
        """Test that reset creates new instance."""
        engine1 = get_retention_engine()
        reset_retention_engine()
        engine2 = get_retention_engine()
        assert engine1 is not engine2


class TestGDPRCompliance:
    """Tests for GDPR compliance features."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_retention_engine()
        self.engine = RetentionPolicyEngine()

    def teardown_method(self):
        """Clean up after tests."""
        reset_retention_engine()

    async def test_right_to_erasure_workflow(self):
        """Test GDPR right to erasure (Article 17) workflow."""
        # Create user data records
        user_records = []
        for i in range(3):
            record = await self.engine.create_retention_record(
                data_id=f"user-data-{i}",
                data_type="personal_data",
                policy_id="retention-restricted-90",
                classification_tier=DataClassificationTier.RESTRICTED,
                pii_categories=[PIICategory.CONTACT_INFO, PIICategory.PERSONAL_IDENTIFIERS],
                tenant_id="tenant-user-123",
                metadata={"user_id": "user-123"},
            )
            user_records.append(record)

        # Simulate erasure request - dispose all user records
        for record in user_records:
            result = await self.engine.dispose_record(
                record_id=record.record_id,
                method=DisposalMethod.DELETE,
            )
            assert result.success is True

        # Verify all records disposed
        for record in user_records:
            updated = await self.engine.storage.get_record(record.record_id)
            assert updated.status == RetentionStatus.DISPOSED

    async def test_data_minimization_via_anonymization(self):
        """Test data minimization through anonymization."""
        record = await self.engine.create_retention_record(
            data_id="analytics-001",
            data_type="user_behavior",
            policy_id="retention-restricted-90",
            classification_tier=DataClassificationTier.RESTRICTED,
            pii_categories=[PIICategory.LOCATION, PIICategory.BEHAVIORAL],
        )

        # Anonymize to retain analytics while removing PII
        result = await self.engine.dispose_record(
            record_id=record.record_id,
            method=DisposalMethod.ANONYMIZE,
        )

        assert result.success is True

        updated = await self.engine.storage.get_record(record.record_id)
        assert updated.status == RetentionStatus.ANONYMIZED

    async def test_audit_trail_completeness(self):
        """Test that all operations are fully audited."""
        # Create record
        record = await self.engine.create_retention_record(
            data_id="audit-test-001",
            data_type="transaction",
            policy_id="retention-confidential-730",
            classification_tier=DataClassificationTier.CONFIDENTIAL,
        )

        # Apply legal hold
        await self.engine.apply_legal_hold(
            record_id=record.record_id,
            reason="Audit requirement",
        )

        # Release legal hold
        await self.engine.release_legal_hold(record_id=record.record_id)

        # Extend retention
        await self.engine.extend_retention(
            record_id=record.record_id,
            additional_days=90,
            reason="Compliance extension",
        )

        # Dispose
        await self.engine.dispose_record(record_id=record.record_id)

        # Verify complete audit trail
        history = await self.engine.get_record_history(record.record_id)

        action_types = [a.action_type for a in history]
        assert RetentionActionType.CREATED in action_types
        assert RetentionActionType.HOLD_APPLIED in action_types
        assert RetentionActionType.HOLD_RELEASED in action_types
        assert RetentionActionType.EXTENDED in action_types
        assert RetentionActionType.DISPOSED in action_types

        # All actions should have constitutional hash
        for action in history:
            assert action.constitutional_hash == CONSTITUTIONAL_HASH


class TestRetentionEnforcementReport:
    """Tests for enforcement report model."""

    def test_report_creation(self):
        """Test enforcement report creation."""
        report = RetentionEnforcementReport(
            records_scanned=100,
            records_expired=10,
            records_disposed=8,
            records_archived=1,
            records_anonymized=1,
            records_held=2,
            records_errored=0,
            duration_ms=150.5,
        )

        assert report.report_id is not None
        assert report.records_scanned == 100
        assert report.records_disposed == 8
        assert report.constitutional_hash == CONSTITUTIONAL_HASH

    def test_report_with_disposal_results(self):
        """Test report with disposal result details."""
        results = [
            DisposalResult(
                record_id=f"rec-{i}",
                success=True,
                method=DisposalMethod.DELETE,
            )
            for i in range(3)
        ]

        report = RetentionEnforcementReport(
            records_scanned=3,
            records_expired=3,
            records_disposed=3,
            disposal_results=results,
        )

        assert len(report.disposal_results) == 3
        assert all(r.success for r in report.disposal_results)


class TestInMemoryStorageExtended:
    """Extended tests for storage edge cases."""

    def setup_method(self):
        self.storage = InMemoryRetentionStorage()

    async def test_update_record(self):
        record = RetentionRecord(
            data_id="data-upd",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) + timedelta(days=30),
        )
        await self.storage.save_record(record)
        record.status = RetentionStatus.DISPOSED
        await self.storage.update_record(record)
        updated = await self.storage.get_record(record.record_id)
        assert updated.status == RetentionStatus.DISPOSED

    async def test_find_expired_with_limit(self):
        for i in range(5):
            record = RetentionRecord(
                data_id=f"exp-{i}",
                data_type="message",
                policy_id="policy-001",
                classification_tier=DataClassificationTier.INTERNAL,
                retention_until=datetime.now(UTC) - timedelta(days=1),
            )
            await self.storage.save_record(record)
        expired = await self.storage.find_expired_records(limit=2)
        assert len(expired) == 2

    async def test_find_expired_skips_non_active(self):
        record = RetentionRecord(
            data_id="disposed",
            data_type="message",
            policy_id="policy-001",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            status=RetentionStatus.DISPOSED,
        )
        await self.storage.save_record(record)
        expired = await self.storage.find_expired_records()
        assert len(expired) == 0

    async def test_get_actions_without_filter(self):
        action1 = RetentionAction(record_id="rec-1", action_type=RetentionActionType.CREATED)
        action2 = RetentionAction(record_id="rec-2", action_type=RetentionActionType.DISPOSED)
        await self.storage.log_action(action1)
        await self.storage.log_action(action2)
        actions = await self.storage.get_actions()
        assert len(actions) == 2

    async def test_get_actions_with_limit(self):
        for i in range(5):
            await self.storage.log_action(
                RetentionAction(
                    record_id=f"rec-{i}",
                    action_type=RetentionActionType.CREATED,
                )
            )
        actions = await self.storage.get_actions(limit=2)
        assert len(actions) == 2

    def test_get_policy_found(self):
        policy = self.storage.get_policy(next(iter(self.storage.policies)))
        assert policy is not None

    def test_get_policy_not_found(self):
        policy = self.storage.get_policy("nonexistent-policy")
        assert policy is None

    def test_add_policy(self):
        from src.core.shared.security.data_classification import RetentionPolicy

        new_policy = RetentionPolicy(
            name="Custom",
            classification_tier=DataClassificationTier.PUBLIC,
            retention_days=7,
            disposal_method=DisposalMethod.DELETE,
        )
        self.storage.add_policy(new_policy)
        assert self.storage.get_policy(new_policy.policy_id) is not None


class TestRetentionPolicyEngineExtended:
    """Extended engine tests for edge cases."""

    def setup_method(self):
        reset_retention_engine()
        self.engine = RetentionPolicyEngine()

    def teardown_method(self):
        reset_retention_engine()

    async def test_create_record_unknown_policy_uses_tier_default(self):
        record = await self.engine.create_retention_record(
            data_id="data-unknown-policy",
            data_type="message",
            policy_id="nonexistent-policy-id",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        assert record is not None
        assert record.status == RetentionStatus.ACTIVE

    async def test_create_record_with_indefinite_retention(self):
        from src.core.shared.security.data_classification import RetentionPolicy

        indefinite_policy = RetentionPolicy(
            name="Indefinite",
            classification_tier=DataClassificationTier.RESTRICTED,
            retention_days=-1,
            disposal_method=DisposalMethod.ARCHIVE,
        )
        self.engine.storage.add_policy(indefinite_policy)
        record = await self.engine.create_retention_record(
            data_id="data-indef",
            data_type="critical",
            policy_id=indefinite_policy.policy_id,
            classification_tier=DataClassificationTier.RESTRICTED,
        )
        assert record.retention_until.year == datetime.max.year

    async def test_dispose_record_pseudonymize(self):
        record = await self.engine.create_retention_record(
            data_id="data-pseudo",
            data_type="user_data",
            policy_id="retention-restricted-90",
            classification_tier=DataClassificationTier.RESTRICTED,
        )
        result = await self.engine.dispose_record(
            record_id=record.record_id,
            method=DisposalMethod.PSEUDONYMIZE,
        )
        assert result.success is True
        updated = await self.engine.storage.get_record(record.record_id)
        assert updated.status == RetentionStatus.ANONYMIZED

    async def test_dispose_record_no_method_uses_policy(self):
        record = await self.engine.create_retention_record(
            data_id="data-auto-method",
            data_type="message",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        result = await self.engine.dispose_record(record_id=record.record_id)
        assert result.success is True

    async def test_dispose_with_no_handler(self):
        engine = RetentionPolicyEngine()
        # Clear handlers after init to bypass the `or` default
        engine.disposal_handlers = {}
        record = RetentionRecord(
            data_id="data-no-handler",
            data_type="message",
            policy_id="retention-internal-365",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) + timedelta(days=30),
        )
        await engine.storage.save_record(record)
        result = await engine.dispose_record(
            record_id=record.record_id,
            method=DisposalMethod.DELETE,
        )
        assert result.success is False
        assert "No handler" in result.error_message

    async def test_apply_legal_hold_nonexistent(self):
        result = await self.engine.apply_legal_hold(
            record_id="nonexistent",
            reason="test",
        )
        assert result is None

    async def test_release_legal_hold_nonexistent(self):
        result = await self.engine.release_legal_hold(record_id="nonexistent")
        assert result is None

    async def test_enforce_retention_archive_method(self):
        from src.core.shared.security.data_classification import RetentionPolicy

        archive_policy = RetentionPolicy(
            name="ArchivePolicy",
            classification_tier=DataClassificationTier.CONFIDENTIAL,
            retention_days=1,
            disposal_method=DisposalMethod.ARCHIVE,
        )
        self.engine.storage.add_policy(archive_policy)
        record = RetentionRecord(
            data_id="arch-001",
            data_type="audit",
            policy_id=archive_policy.policy_id,
            classification_tier=DataClassificationTier.CONFIDENTIAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
        )
        await self.engine.storage.save_record(record)
        report = await self.engine.enforce_retention()
        assert report.records_archived == 1

    async def test_enforce_retention_anonymize_method(self):
        from src.core.shared.security.data_classification import RetentionPolicy

        anon_policy = RetentionPolicy(
            name="AnonPolicy",
            classification_tier=DataClassificationTier.RESTRICTED,
            retention_days=1,
            disposal_method=DisposalMethod.ANONYMIZE,
        )
        self.engine.storage.add_policy(anon_policy)
        record = RetentionRecord(
            data_id="anon-001",
            data_type="pii",
            policy_id=anon_policy.policy_id,
            classification_tier=DataClassificationTier.RESTRICTED,
            retention_until=datetime.now(UTC) - timedelta(days=1),
        )
        await self.engine.storage.save_record(record)
        report = await self.engine.enforce_retention()
        assert report.records_anonymized == 1
