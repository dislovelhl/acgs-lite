"""
Unit tests for Batch Processor Auto-tuning.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.batch_processor_infra.tuning import BatchAutoTuner


class TestBatchAutoTuner:
    def test_initialization(self):
        tuner = BatchAutoTuner(initial_batch_size=20)
        assert tuner.batch_size == 20

    def test_adjust_increase(self):
        tuner = BatchAutoTuner(initial_batch_size=10)
        # Healthy system -> increase batch size
        new_size = tuner.adjust_from_stats(success_rate=99.0, avg_latency_ms=100.0)
        assert new_size > 10
        assert new_size == 12  # 10 * 1.1 + 1 = 12

    def test_adjust_decrease(self):
        tuner = BatchAutoTuner(initial_batch_size=50)
        # Struggling system -> decrease batch size
        new_size = tuner.adjust_from_stats(success_rate=75.0, avg_latency_ms=100.0)
        assert new_size < 50
        assert new_size == 45  # 50 / 1.1 = 45

    def test_adjust_no_change(self):
        tuner = BatchAutoTuner(initial_batch_size=30)
        # Middle ground -> no change
        new_size = tuner.adjust_from_stats(success_rate=90.0, avg_latency_ms=300.0)
        assert new_size == 30

    def test_boundaries(self):
        tuner = BatchAutoTuner(initial_batch_size=100)
        # Max boundary
        new_size = tuner.adjust_from_stats(success_rate=100.0, avg_latency_ms=10.0)
        assert new_size == 100

        tuner = BatchAutoTuner(initial_batch_size=1)
        # Min boundary
        new_size = tuner.adjust_from_stats(success_rate=50.0, avg_latency_ms=5000.0)
        assert new_size == 1
