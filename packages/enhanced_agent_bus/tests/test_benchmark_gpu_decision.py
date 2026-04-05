"""
Tests for enhanced_agent_bus.profiling.benchmark_gpu_decision
Constitutional Hash: 608508a9bd224290
"""

import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.profiling.benchmark_gpu_decision import (
    SAMPLE_MESSAGES,
    GPUBenchmark,
    generate_random_message,
)

# ---------------------------------------------------------------------------
# generate_random_message
# ---------------------------------------------------------------------------


class TestGenerateRandomMessage:
    def test_returns_dict(self):
        msg = generate_random_message()
        assert isinstance(msg, dict)

    def test_contains_timestamp(self):
        msg = generate_random_message()
        assert "timestamp" in msg

    def test_contains_agent_id(self):
        msg = generate_random_message()
        assert "agent_id" in msg
        assert msg["agent_id"].startswith("agent_")

    def test_does_not_mutate_sample_messages(self):
        originals = [m.copy() for m in SAMPLE_MESSAGES]
        for _ in range(20):
            generate_random_message()
        for _orig, current in zip(originals, SAMPLE_MESSAGES, strict=False):
            assert "timestamp" not in current
            assert "agent_id" not in current


# ---------------------------------------------------------------------------
# GPUBenchmark.__init__
# ---------------------------------------------------------------------------


class TestGPUBenchmarkInit:
    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_defaults(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()
        assert b.num_samples == 200
        assert b.concurrency == 4
        assert b.warmup_samples == 20
        assert b.results == {}

    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_custom_params(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark(num_samples=10, concurrency=2, warmup_samples=5)
        assert b.num_samples == 10
        assert b.concurrency == 2
        assert b.warmup_samples == 5


# ---------------------------------------------------------------------------
# GPUBenchmark._import_scorer  (always falls back in test env)
# ---------------------------------------------------------------------------


class TestImportScorer:
    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_import_scorer_returns_none_tuple_on_import_error(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()
        result = b._import_scorer()
        # In CI the real scorer is typically not available
        assert len(result) == 4


# ---------------------------------------------------------------------------
# GPUBenchmark.run_warmup / run_sequential / run_concurrent
# ---------------------------------------------------------------------------


class TestBenchmarkPhases:
    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_run_warmup(self, mock_profiler):
        profiler = MagicMock()
        mock_profiler.return_value = profiler
        b = GPUBenchmark(warmup_samples=3)

        scorer = MagicMock()
        b.run_warmup(scorer)

        assert scorer.calculate_impact_score.call_count == 3
        profiler.reset.assert_called_once()

    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_run_sequential_benchmark(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark(num_samples=5)
        scorer = MagicMock()

        rps = b.run_sequential_benchmark(scorer)

        assert scorer.calculate_impact_score.call_count == 5
        assert rps > 0

    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_run_concurrent_benchmark(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark(num_samples=8, concurrency=2)
        scorer = MagicMock()

        rps = b.run_concurrent_benchmark(scorer)

        assert scorer.calculate_impact_score.call_count == 8
        assert rps > 0


# ---------------------------------------------------------------------------
# GPUBenchmark.run  (mock path — scorer not available)
# ---------------------------------------------------------------------------


class TestBenchmarkRun:
    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_run_mock_benchmark(self, mock_profiler):
        profiler = MagicMock()
        profiler.generate_report.return_value = "mock report"
        profiler.get_all_metrics.return_value = {}
        # Make track() return a context manager
        profiler.track.return_value.__enter__ = MagicMock()
        profiler.track.return_value.__exit__ = MagicMock(return_value=False)
        mock_profiler.return_value = profiler

        b = GPUBenchmark(num_samples=5)
        results = b._run_mock_benchmark()

        assert "benchmark_info" in results
        assert results["benchmark_info"]["mock"] is True
        assert "gpu_decision_matrix" in results
        assert "summary" in results


# ---------------------------------------------------------------------------
# GPUBenchmark._generate_summary
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_keep_cpu_when_no_gpu_candidates(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()

        gpu_matrix = {
            "model_a": {
                "analysis": {"bottleneck_type": "io_bound"},
                "latency": {"p99_ms": 5.0},
            }
        }
        summary = b._generate_summary(gpu_matrix, 100.0, 200.0)

        assert summary["overall_recommendation"] == "KEEP_CPU"
        assert len(summary["reasons"]) >= 1
        assert len(summary["action_items"]) >= 1

    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_evaluate_gpu_when_compute_bound(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()

        gpu_matrix = {
            "model_a": {
                "analysis": {"bottleneck_type": "compute_bound"},
                "latency": {"p99_ms": 50.0},
            }
        }
        summary = b._generate_summary(gpu_matrix, 100.0, 200.0)

        assert summary["overall_recommendation"] == "EVALUATE_GPU"

    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_skips_entries_with_error(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()

        gpu_matrix = {"broken": {"error": "failed to load"}}
        summary = b._generate_summary(gpu_matrix, 50.0, 100.0)

        assert summary["overall_recommendation"] == "KEEP_CPU"


# ---------------------------------------------------------------------------
# GPUBenchmark._print_summary
# ---------------------------------------------------------------------------


class TestPrintSummary:
    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_print_summary_no_error(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()
        b.results = {
            "summary": {
                "overall_recommendation": "KEEP_CPU",
                "reasons": ["test reason"],
                "action_items": ["test action"],
            },
            "throughput": {
                "sequential_rps": 100.0,
                "concurrent_rps": 200.0,
                "concurrency_scaling": 2.0,
            },
        }
        # Should not raise
        b._print_summary()


# ---------------------------------------------------------------------------
# GPUBenchmark.save_results
# ---------------------------------------------------------------------------


class TestSaveResults:
    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_save_results_custom_path(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()
        b.results = {"test": True}

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        returned = b.save_results(path)
        assert returned == path

        with open(path) as f:
            data = json.load(f)
        assert data == {"test": True}

    @patch("enhanced_agent_bus.profiling.benchmark_gpu_decision.get_global_profiler")
    def test_save_results_auto_path(self, mock_profiler):
        mock_profiler.return_value = MagicMock()
        b = GPUBenchmark()
        b.results = {"auto": True}

        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            orig_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                path = b.save_results()
                assert path.startswith("gpu_benchmark_results_")
                assert path.endswith(".json")
            finally:
                os.chdir(orig_cwd)
