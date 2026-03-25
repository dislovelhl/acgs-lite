"""
ACGS-2 Autoresearch Benchmark Harness
======================================
Fixed evaluation suite. DO NOT MODIFY.

Runs the governance engine against 847 scenarios and measures:
- Compliance accuracy (correct accept/deny/escalate decisions)
- Latency (p50, p95, p99)
- Throughput (requests per second)
- False positive/negative rates

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

# Add acgs-lite to path
REPO_ROOT = Path(__file__).resolve().parents[1]
ACGS_LITE = REPO_ROOT / "packages" / "acgs-lite" / "src"
sys.path.insert(0, str(ACGS_LITE))

from acgs_lite.constitution import Constitution, Severity
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import ConstitutionalViolationError

# RoCS tracker for governance efficiency measurement
sys.path.insert(0, str(REPO_ROOT))
import contextlib

try:
    from src.core.shared.metrics.rocs import RoCSTracker
except ModuleNotFoundError:
    @dataclass
    class _FallbackGovernanceSpend:
        validation_ns: int = 0
        scoring_ns: int = 0

        @property
        def total_seconds(self) -> float:
            return (self.validation_ns + self.scoring_ns) / 1_000_000_000


    @dataclass
    class _FallbackGovernanceValue:
        total_weighted: float = 0.0


    @dataclass
    class _FallbackRoCSSnapshot:
        rocs: float
        spend: _FallbackGovernanceSpend
        value: _FallbackGovernanceValue


    class RoCSTracker:
        """Local fallback when the platform RoCS module is unavailable."""

        _SEVERITY_WEIGHTS: ClassVar[dict[str, float]] = {
            "critical": 10.0,
            "high": 5.0,
            "medium": 2.0,
            "low": 1.0,
            "allow": 1.0,
        }

        def __init__(self) -> None:
            self._spend = _FallbackGovernanceSpend()
            self._value = _FallbackGovernanceValue()

        def record_validation(self, elapsed_ns: int, severity: str = "allow", correct: bool = True) -> None:
            self._spend.validation_ns += elapsed_ns
            if correct:
                self._value.total_weighted += self._SEVERITY_WEIGHTS.get(severity.lower(), 1.0)

        def snapshot(self) -> _FallbackRoCSSnapshot:
            total_seconds = self._spend.total_seconds
            rocs = self._value.total_weighted / total_seconds if total_seconds > 0 else 0.0
            return _FallbackRoCSSnapshot(rocs=rocs, spend=self._spend, value=self._value)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
CONSTITUTION_FILE = Path(__file__).parent / "constitution.yaml"


def load_scenarios() -> list[dict[str, Any]]:
    """Load all test scenarios from JSON files."""
    scenarios = []
    for f in sorted(SCENARIOS_DIR.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
            if isinstance(data, list):
                scenarios.extend(data)
            else:
                scenarios.append(data)
    return scenarios


def evaluate(engine: GovernanceEngine, scenarios: list[dict]) -> dict[str, Any]:
    """Run all scenarios and collect metrics."""
    latencies: list[float] = []
    correct = 0
    total = 0
    false_positives = 0
    false_negatives = 0
    errors = 0
    rocs_tracker = RoCSTracker()

    for scenario in scenarios:
        action_text = scenario["action"]
        expected = scenario["expected"]  # "allow", "deny", "escalate"
        context = scenario.get("context", {})

        try:
            start = time.perf_counter_ns()
            try:
                result = engine.validate(action_text, context=context)
                elapsed_ns = time.perf_counter_ns() - start
                latencies.append(elapsed_ns / 1_000_000)  # convert to ms

                # Map result to decision
                if result.valid and not result.violations:
                    decision = "allow"
                elif any(v.severity == Severity.CRITICAL for v in result.violations):
                    decision = "deny"
                elif result.violations:
                    decision = "escalate"
                else:
                    decision = "allow"
            except ConstitutionalViolationError:
                elapsed_ns = time.perf_counter_ns() - start
                latencies.append(elapsed_ns / 1_000_000)
                decision = "deny"

            is_correct = decision == expected
            if is_correct:
                correct += 1
            else:
                if decision != "allow" and expected == "allow":
                    false_positives += 1
                elif decision == "allow" and expected != "allow":
                    false_negatives += 1

            # Track RoCS: governance compute cost + decision value
            # Use actual violation severity when available
            if decision == "allow":
                rocs_severity = "allow"
            elif decision == "deny":
                rocs_severity = "critical"
            else:
                rocs_severity = "medium"
            rocs_tracker.record_validation(
                elapsed_ns=elapsed_ns,
                severity=rocs_severity,
                correct=is_correct,
            )

            total += 1

        except Exception:
            errors += 1
            total += 1
            latencies.append(0)

    # Calculate metrics
    compliance_rate = correct / total if total > 0 else 0
    fp_rate = false_positives / total if total > 0 else 0
    fn_rate = false_negatives / total if total > 0 else 0

    if latencies:
        sorted_lat = sorted(latencies)
        p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
        mean_lat = statistics.mean(latencies)
    else:
        p50 = p95 = p99 = mean_lat = 0

    # Throughput: run 1000 rapid-fire validations
    throughput_actions = [s["action"] for s in scenarios[:50]] * 20  # 1000 actions
    t0 = time.perf_counter()
    for action in throughput_actions:
        with contextlib.suppress(ConstitutionalViolationError):
            engine.validate(action)
    throughput_elapsed = time.perf_counter() - t0
    throughput_rps = len(throughput_actions) / throughput_elapsed if throughput_elapsed > 0 else 0

    # Composite score
    composite = (
        compliance_rate * 0.4
        + max(0, (1 - p99 / 10)) * 0.3
        + min(1, throughput_rps / 10000) * 0.2
        + (1 - fn_rate) * 0.1
    )

    # Spec-to-Artifact Score (ref: solveeverything.org)
    # Measures first-attempt governance accuracy: what fraction of decisions
    # are correct without retries or human override.
    # Formula: first_attempt_accuracy * (1 - override_rate) * (1 - fp_rate)
    # In benchmark context, override_rate is 0 (no HITL in benchmarks).
    override_rate = 0.0
    spec_to_artifact = compliance_rate * (1 - override_rate) * (1 - fp_rate)

    # RoCS — Return on Cognitive Spend (ref: solveeverything.org)
    rocs_snap = rocs_tracker.snapshot()

    return {
        "compliance_rate": compliance_rate,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "p99_latency_ms": p99,
        "mean_latency_ms": mean_lat,
        "throughput_rps": throughput_rps,
        "false_positive_rate": fp_rate,
        "false_negative_rate": fn_rate,
        "composite_score": composite,
        "spec_to_artifact_score": spec_to_artifact,
        "rocs": rocs_snap.rocs,
        "rocs_governance_value": rocs_snap.value.total_weighted,
        "rocs_compute_seconds": rocs_snap.spend.total_seconds,
        "scenarios_tested": total,
        "correct": correct,
        "errors": errors,
        "rules_checked": len(engine.constitution.rules),
    }


def main():
    print("=" * 60)
    print("ACGS-2 Autoresearch Benchmark")
    print("=" * 60)

    # Load constitution
    if not CONSTITUTION_FILE.exists():
        print(f"ERROR: Constitution file not found: {CONSTITUTION_FILE}")
        sys.exit(1)

    constitution = Constitution.from_yaml(str(CONSTITUTION_FILE))
    engine = GovernanceEngine(constitution)

    # Load scenarios
    scenarios = load_scenarios()
    if not scenarios:
        print("ERROR: No scenarios found")
        sys.exit(1)

    print(f"Constitution: {len(constitution.rules)} rules")
    print(f"Scenarios: {len(scenarios)}")
    print("Running benchmark...")
    print()

    # Run evaluation
    metrics = evaluate(engine, scenarios)

    # Print results — raw metrics (consumed by autoresearch TSV)
    print("---")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"{key}: {value:>14.6f}")
        else:
            print(f"{key}: {value:>14}")
    print("---")

    # Interpretable summary
    us_per_decision = (
        metrics["rocs_compute_seconds"] / metrics["scenarios_tested"] * 1_000_000
        if metrics["scenarios_tested"] > 0
        else 0
    )
    print()
    print("Governance Efficiency (solveeverything.org metrics)")
    print(
        f"  Cost:     {us_per_decision:.2f} us/decision "
        f"({metrics['rocs_compute_seconds'] * 1000:.3f} ms total)"
    )
    print(f"  Value:    {metrics['rocs_governance_value']:.0f} severity-weighted correct decisions")
    print(f"  RoCS:     {metrics['rocs']:,.0f} value/CPU-sec")
    print(f"  Accuracy: {metrics['spec_to_artifact_score']:.4f} (first-attempt, no overrides)")


if __name__ == "__main__":
    main()
