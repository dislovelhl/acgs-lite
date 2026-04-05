"""
Tests for Saga Metrics Collection.
Constitutional Hash: 608508a9bd224290
"""

import uuid

import pytest

from enterprise_sso.saga_orchestration import (
    CONSTITUTIONAL_HASH,
    SagaExecutionResult,
    SagaMetrics,
    SagaStatus,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaMetrics:
    """Tests for saga metrics collection."""

    def test_record_successful_saga(self):
        """Test recording a successful saga."""
        metrics = SagaMetrics()

        result = SagaExecutionResult(
            saga_id="saga-001",
            success=True,
            status=SagaStatus.COMPLETED,
            completed_steps=["step1", "step2"],
            execution_time_ms=100.0,
        )

        metrics.record_saga_completed(result)

        stats = metrics.get_stats()
        assert stats["total_sagas"] == 1
        assert stats["successful_sagas"] == 1
        assert stats["failed_sagas"] == 0
        assert stats["total_steps_executed"] == 2

    def test_record_failed_saga_with_compensation(self):
        """Test recording a failed saga with compensation."""
        metrics = SagaMetrics()

        result = SagaExecutionResult(
            saga_id="saga-001",
            success=False,
            status=SagaStatus.COMPENSATED,
            completed_steps=["step1"],
            failed_step="step2",
            compensated_steps=["step1"],
            execution_time_ms=150.0,
        )

        metrics.record_saga_completed(result)

        stats = metrics.get_stats()
        assert stats["total_sagas"] == 1
        assert stats["failed_sagas"] == 1
        assert stats["compensated_sagas"] == 1
        assert stats["total_compensations"] == 1

    def test_calculate_success_rate(self):
        """Test success rate calculation."""
        metrics = SagaMetrics()

        # Record 3 successful, 2 failed
        for i in range(3):
            metrics.record_saga_completed(
                SagaExecutionResult(
                    saga_id=f"saga-{i}",
                    success=True,
                    status=SagaStatus.COMPLETED,
                    completed_steps=["step1"],
                    execution_time_ms=100.0,
                )
            )

        for i in range(2):
            metrics.record_saga_completed(
                SagaExecutionResult(
                    saga_id=f"saga-fail-{i}",
                    success=False,
                    status=SagaStatus.FAILED,
                    completed_steps=[],
                    execution_time_ms=50.0,
                )
            )

        stats = metrics.get_stats()
        assert stats["success_rate"] == 60.0  # 3/5 * 100

    def test_average_execution_time(self):
        """Test average execution time calculation."""
        metrics = SagaMetrics()

        for time_ms in [100.0, 200.0, 300.0]:
            metrics.record_saga_completed(
                SagaExecutionResult(
                    saga_id=str(uuid.uuid4()),
                    success=True,
                    status=SagaStatus.COMPLETED,
                    completed_steps=["step1"],
                    execution_time_ms=time_ms,
                )
            )

        stats = metrics.get_stats()
        assert stats["average_execution_time_ms"] == 200.0

    def test_metrics_include_constitutional_hash(self):
        """Test that metrics include constitutional hash."""
        metrics = SagaMetrics()
        stats = metrics.get_stats()

        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
