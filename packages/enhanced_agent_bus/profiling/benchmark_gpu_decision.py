#!/usr/bin/env python3
"""
ACGS-2 GPU Acceleration Benchmark
Constitutional Hash: 608508a9bd224290

Runs load testing on ML models to determine if GPU acceleration is beneficial.

Usage:
    python -m enhanced_agent_bus.profiling.benchmark_gpu_decision
    python -m enhanced_agent_bus.profiling.benchmark_gpu_decision --samples 500 --concurrency 10

Output:
    - Console report with GPU recommendations
    - JSON file with detailed metrics
    - Prometheus metrics (if enabled)
"""

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from enhanced_agent_bus.observability.structured_logging import get_logger

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.profiling import get_global_profiler

logger = get_logger(__name__)
BENCHMARK_SCORER_INIT_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    OSError,
)

# Sample test messages for realistic workload simulation
SAMPLE_MESSAGES = [
    # High-impact messages (should route to deliberation)
    {
        "content": "Critical security breach detected in blockchain consensus layer",
        "priority": "CRITICAL",
        "tools": [{"name": "admin_execute"}],
        "payload": {"amount": 50000},
    },
    {
        "content": "Emergency governance policy violation requires immediate review",
        "priority": "HIGH",
        "message_type": "governance_request",
        "tools": [{"name": "policy_override"}],
    },
    {
        "content": "Unauthorized financial transfer attempt blocked by constitutional guard",
        "priority": "CRITICAL",
        "tools": [{"name": "blockchain_transfer"}, {"name": "payment_execute"}],
    },
    # Medium-impact messages
    {
        "content": "Requesting compliance check for new user registration flow",
        "priority": "MEDIUM",
        "tools": [{"name": "read_database"}],
    },
    {
        "content": "Performance metrics indicate potential anomaly in request patterns",
        "priority": "HIGH",
        "tools": [{"name": "metrics_read"}],
    },
    # Low-impact messages (should go through fast lane)
    {
        "content": "Standard health check request",
        "priority": "LOW",
        "tools": [],
    },
    {
        "content": "User profile update notification",
        "priority": "LOW",
        "tools": [{"name": "read_profile"}],
    },
    {
        "content": "Cache refresh completed successfully",
        "priority": "LOW",
    },
]


def generate_random_message() -> JSONDict:
    """Generate a random test message."""
    base = random.choice(SAMPLE_MESSAGES).copy()  # type: ignore[attr-defined]
    # Add some variation
    base["timestamp"] = datetime.now(UTC).isoformat()
    base["agent_id"] = f"agent_{random.randint(1, 100)}"
    return base


class GPUBenchmark:
    """
    Benchmark runner for GPU acceleration decision.

    Simulates realistic load and measures:
    - Model inference latency distribution
    - CPU utilization during inference
    - Throughput under concurrency
    """

    def __init__(
        self,
        num_samples: int = 200,
        concurrency: int = 4,
        warmup_samples: int = 20,
    ):
        self.num_samples = num_samples
        self.concurrency = concurrency
        self.warmup_samples = warmup_samples
        self.profiler = get_global_profiler()
        self.results: JSONDict = {}

    def _import_scorer(self):
        """Import scorer with error handling."""
        try:
            from enhanced_agent_bus.deliberation_layer.impact_scorer import (
                ImpactScorer,
                get_gpu_decision_matrix,
                get_impact_scorer,
                get_profiling_report,
            )

            return ImpactScorer, get_impact_scorer, get_profiling_report, get_gpu_decision_matrix
        except ImportError as e:
            logger.warning(f"⚠️  Warning: Could not import ImpactScorer: {e}")
            logger.info("    Running with mock scorer for demonstration...")
            return None, None, None, None

    def run_warmup(self, scorer) -> None:
        """Warm up the model to ensure stable measurements."""
        logger.info(f"🔥 Warming up with {self.warmup_samples} samples...")

        for _i in range(self.warmup_samples):
            msg = generate_random_message()
            scorer.calculate_impact_score(msg, {"agent_id": msg.get("agent_id", "warmup")})

        # Reset profiler after warmup to get clean measurements
        self.profiler.reset()
        logger.info("   Warmup complete, profiler reset.\n")

    def run_sequential_benchmark(self, scorer) -> float:
        """Run sequential (single-threaded) benchmark."""
        logger.info(f"📊 Running sequential benchmark ({self.num_samples} samples)...")

        start = time.perf_counter()
        for i in range(self.num_samples):
            msg = generate_random_message()
            scorer.calculate_impact_score(msg, {"agent_id": msg.get("agent_id", "bench")})

            if (i + 1) % 50 == 0:
                logger.info(f"   Progress: {i + 1}/{self.num_samples}")

        elapsed = time.perf_counter() - start
        rps = self.num_samples / elapsed
        logger.info(f"   Sequential: {elapsed:.2f}s, {rps:.1f} RPS\n")
        return rps

    def run_concurrent_benchmark(self, scorer) -> float:
        """Run concurrent (multi-threaded) benchmark."""
        logger.info(
            f"🚀 Running concurrent benchmark ({self.num_samples} samples, {self.concurrency} threads)..."
        )

        def process_message(_):
            msg = generate_random_message()
            scorer.calculate_impact_score(msg, {"agent_id": msg.get("agent_id", "concurrent")})

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            list(executor.map(process_message, range(self.num_samples)))

        elapsed = time.perf_counter() - start
        rps = self.num_samples / elapsed
        logger.info(f"   Concurrent: {elapsed:.2f}s, {rps:.1f} RPS\n")
        return rps

    def run(self) -> JSONDict:
        """Run the complete benchmark suite."""
        logger.info("=" * 70)
        logger.info("ACGS-2 GPU ACCELERATION BENCHMARK")
        logger.info("Constitutional Hash: 608508a9bd224290")
        logger.info(f"Started: {datetime.now(UTC).isoformat()}")
        logger.info("=" * 70)
        logger.info("")

        # Import scorer
        (
            ImpactScorer,
            get_impact_scorer,
            get_profiling_report,
            get_gpu_decision_matrix,
        ) = self._import_scorer()

        if ImpactScorer is None:
            # Run with mock profiling only
            return self._run_mock_benchmark()

        # Initialize scorer
        logger.info("📦 Initializing ImpactScorer...")
        try:
            scorer = get_impact_scorer()
            logger.info(f"   Model: {scorer.model_name}")
            logger.info(f"   BERT enabled: {scorer._bert_enabled}")
            logger.info(f"   ONNX enabled: {scorer._onnx_enabled}")
            logger.info("")
        except BENCHMARK_SCORER_INIT_ERRORS as e:
            logger.error(f"   ⚠️  Scorer initialization failed: {e}")
            logger.info("   Running with mock benchmark...")
            return self._run_mock_benchmark()

        # Run benchmarks
        self.run_warmup(scorer)

        sequential_rps = self.run_sequential_benchmark(scorer)
        concurrent_rps = self.run_concurrent_benchmark(scorer)

        # Get profiling results
        logger.info("📈 Generating profiling report...")
        report = get_profiling_report()
        gpu_matrix = get_gpu_decision_matrix()

        # Compile results
        self.results = {
            "benchmark_info": {
                "timestamp": datetime.now(UTC).isoformat(),
                "num_samples": self.num_samples,
                "concurrency": self.concurrency,
                "warmup_samples": self.warmup_samples,
            },
            "throughput": {
                "sequential_rps": round(sequential_rps, 2),
                "concurrent_rps": round(concurrent_rps, 2),
                "concurrency_scaling": (
                    round(concurrent_rps / sequential_rps, 2) if sequential_rps > 0 else 0
                ),
            },
            "gpu_decision_matrix": gpu_matrix,
            "summary": self._generate_summary(gpu_matrix, sequential_rps, concurrent_rps),
        }

        # Print report
        logger.info("")
        logger.info(report)
        logger.info("")
        self._print_summary()

        return self.results

    def _run_mock_benchmark(self) -> JSONDict:
        """Run mock benchmark when scorer is not available."""
        logger.info("\n⚠️  Running mock benchmark (scorer not available)")
        logger.info("   This demonstrates the profiling infrastructure.\n")

        # Simulate some profiling data
        for _i in range(100):
            with self.profiler.track("mock_model"):
                time.sleep(random.uniform(0.001, 0.005))  # 1-5ms simulated inference

        report = self.profiler.generate_report()
        metrics = self.profiler.get_all_metrics()

        self.results = {
            "benchmark_info": {
                "timestamp": datetime.now(UTC).isoformat(),
                "mock": True,
            },
            "gpu_decision_matrix": {name: m.to_dict() for name, m in metrics.items()},
            "summary": {
                "recommendation": "Install transformers package to run full benchmark",
                "mock_data": True,
            },
        }

        logger.info(report)
        return self.results

    def _generate_summary(
        self,
        gpu_matrix: JSONDict,
        _seq_rps: float,
        conc_rps: float,
    ) -> JSONDict:
        """Generate executive summary with recommendations."""
        summary = {
            "overall_recommendation": "KEEP_CPU",
            "reasons": [],
            "action_items": [],
        }

        # Analyze each model
        gpu_candidates = []
        for model_name, metrics in gpu_matrix.items():
            if "error" in metrics:
                continue

            analysis = metrics.get("analysis", {})
            bottleneck = analysis.get("bottleneck_type", "unknown")
            latency_p99 = metrics.get("latency", {}).get("p99_ms", 0)

            if bottleneck == "compute_bound":
                gpu_candidates.append(model_name)
                summary["reasons"].append(  # type: ignore[attr-defined]
                    f"{model_name}: Compute-bound ({latency_p99:.2f}ms P99) - GPU may help"
                )
            else:
                summary["reasons"].append(  # type: ignore[attr-defined]
                    f"{model_name}: {bottleneck} ({latency_p99:.2f}ms P99) - GPU unlikely to help"
                )

        # Overall recommendation
        if gpu_candidates:
            summary["overall_recommendation"] = "EVALUATE_GPU"
            summary["action_items"] = [
                f"Consider TensorRT for: {', '.join(gpu_candidates)}",
                "Run A/B test with GPU inference to measure actual improvement",
                "Ensure GPU overhead doesn't exceed current latency",
            ]
        else:
            summary["reasons"].append(f"Current throughput ({conc_rps:.0f} RPS) is excellent")  # type: ignore[attr-defined]
            summary["action_items"] = [
                "Keep current CPU implementation",
                "Focus optimization on non-model code paths",
                "Re-evaluate if throughput requirements increase significantly",
            ]

        return summary

    def _print_summary(self) -> None:
        """Print executive summary."""
        summary = self.results.get("summary", {})
        throughput = self.results.get("throughput", {})

        logger.info("=" * 70)
        logger.info("EXECUTIVE SUMMARY")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Recommendation: {summary.get('overall_recommendation', 'N/A')}")
        logger.info("")
        logger.info("Throughput:")
        logger.info(f"  - Sequential: {throughput.get('sequential_rps', 0):.1f} RPS")
        logger.info(f"  - Concurrent: {throughput.get('concurrent_rps', 0):.1f} RPS")
        logger.info(f"  - Scaling factor: {throughput.get('concurrency_scaling', 0):.2f}x")
        logger.info("")
        logger.info("Analysis:")
        for reason in summary.get("reasons", []):
            logger.info(f"  • {reason}")
        logger.info("")
        logger.info("Action Items:")
        for item in summary.get("action_items", []):
            logger.info(f"  → {item}")
        logger.info("")
        logger.info("=" * 70)

    def save_results(self, output_path: str | None = None) -> str:
        """Save results to JSON file."""
        if output_path is None:
            output_path = f"gpu_benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        logger.info(f"\n📁 Results saved to: {output_path}")
        return output_path


def main():
    parser = argparse.ArgumentParser(
        description="ACGS-2 GPU Acceleration Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmark_gpu_decision.py                    # Run with defaults
  python benchmark_gpu_decision.py --samples 500     # More samples for accuracy
  python benchmark_gpu_decision.py --concurrency 8   # Test higher concurrency
  python benchmark_gpu_decision.py --output report.json  # Save to specific file
        """,
    )
    parser.add_argument(
        "--samples",
        "-n",
        type=int,
        default=200,
        help="Number of samples per benchmark (default: 200)",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=4,
        help="Number of concurrent threads (default: 4)",
    )
    parser.add_argument(
        "--warmup",
        "-w",
        type=int,
        default=20,
        help="Number of warmup samples (default: 20)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output JSON file path (optional)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to file",
    )

    args = parser.parse_args()

    benchmark = GPUBenchmark(
        num_samples=args.samples,
        concurrency=args.concurrency,
        warmup_samples=args.warmup,
    )

    results = benchmark.run()

    if not args.no_save:
        benchmark.save_results(args.output)

    # Exit with code based on recommendation
    recommendation = results.get("summary", {}).get("overall_recommendation", "")
    if recommendation == "EVALUATE_GPU":
        sys.exit(1)  # Signal that GPU evaluation is recommended
    sys.exit(0)


if __name__ == "__main__":
    main()
