"""Governance Quality Benchmark — measures capabilities beyond latency/compliance.

Complements the existing benchmark.py (which measures compliance_rate, p99,
throughput, false_negative_rate) by evaluating governance *quality* dimensions
that neutral-kept experiments add.

Does NOT replace or modify benchmark.py (which is frozen for the autoresearch loop).

Dimensions:
  1. module_coverage   — How many governance domains have active modules?
  2. chain_detection   — Can the engine detect multi-step attack chains?
  3. contract_enforcement — Can session contracts detect behavioral divergence?
  4. breach_prediction  — Can the Markov model predict obligation breaches?
  5. refusal_quality    — Do refusals provide structured reasoning + alternatives?
  6. registry_health    — Are all symbols resolvable? Domain classification complete?

Usage:
    cd autoresearch
    PYTHONPATH=../packages/acgs-lite/src:$PYTHONPATH python governance_quality_benchmark.py
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "../packages/acgs-lite/src")


def _score(passed: int, total: int) -> float:
    return passed / total if total else 0.0


def benchmark_registry_health() -> dict[str, float | int]:
    import acgs_lite.constitution as c
    from acgs_lite.constitution import modules_by_domain

    total = len(c.__all__)
    errors = 0
    for name in c.__all__:
        try:
            getattr(c, name)
        except Exception:
            errors += 1

    domains = modules_by_domain()
    domain_count = len(domains)
    module_count = sum(len(mods) for mods in domains.values())

    return {
        "total_symbols": total,
        "resolvable_symbols": total - errors,
        "symbol_errors": errors,
        "domain_count": domain_count,
        "lazy_module_count": module_count,
        "score": _score(total - errors, total),
    }


def benchmark_chain_detection() -> dict[str, float | int]:
    from acgs_lite.constitution import CausalChainTracker, builtin_patterns

    tracker = CausalChainTracker.with_builtin_patterns()
    tests_passed = 0
    tests_total = 0

    chains = [
        ("read customer data", "export to external API", "CHAIN-001"),
        ("suppress audit logs", "run query", "resume audit logs", "CHAIN-002"),
        ("create new user", "grant admin privileges", "deploy to prod", "CHAIN-003"),
        ("scan all records", "backup database", "destroy all records", "CHAIN-004"),
        ("query user profiles", "log full output", "CHAIN-005"),
        ("inspect governance rules", "modify access policy", "approve own changes", "CHAIN-006"),
    ]

    for chain_spec in chains:
        *actions, expected_id = chain_spec
        tests_total += 1
        t = CausalChainTracker.with_builtin_patterns()
        result = None
        for action in actions:
            result = t.record_and_check("test-agent", action)
        if result and result.completed and result.completed[0].pattern_id == expected_id:
            tests_passed += 1

    tests_total += 1
    tracker2 = CausalChainTracker.with_builtin_patterns()
    tracker2.record_and_check("x", "read file")
    for i in range(10):
        tracker2.record_and_check("x", f"unrelated {i}")
    r = tracker2.record_and_check("x", "send file")
    if not r.completed:
        tests_passed += 1

    return {
        "builtin_patterns": len(builtin_patterns()),
        "detection_tests_passed": tests_passed,
        "detection_tests_total": tests_total,
        "score": _score(tests_passed, tests_total),
    }


def benchmark_contract_enforcement() -> dict[str, float | int]:
    from acgs_lite.constitution import BehaviorContract, SessionContractTracker

    contract = BehaviorContract(
        allowed_actions=frozenset({"read", "summarise", "list", "query"}),
        resource_scopes=frozenset({"documents"}),
        max_actions=5,
    )
    tracker = SessionContractTracker()
    tracker.bind("test", contract)

    tests_passed = 0
    tests_total = 0

    tests_total += 1
    r1 = tracker.check_action("test", "read quarterly report")
    if r1.is_compliant:
        tests_passed += 1

    tests_total += 1
    r2 = tracker.check_action("test", "write malicious payload")
    if not r2.is_compliant:
        tests_passed += 1

    tests_total += 1
    if contract.verify_integrity():
        tests_passed += 1

    for _ in range(4):
        tracker.check_action("test", "read document")
    tests_total += 1
    r3 = tracker.check_action("test", "list files")
    if any(d.divergence_type.value == "volume_exceeded" for d in r3.divergences):
        tests_passed += 1

    tests_total += 1
    report = tracker.unbind("test")
    if report and report.total_actions == 7:
        tests_passed += 1

    return {
        "enforcement_tests_passed": tests_passed,
        "enforcement_tests_total": tests_total,
        "score": _score(tests_passed, tests_total),
    }


def benchmark_breach_prediction() -> dict[str, float | int]:
    from acgs_lite.constitution import ObligationPredictor

    pred = ObligationPredictor(warn_threshold=0.1)
    for _ in range(70):
        pred.observe("pending", "fulfilled")
    for _ in range(20):
        pred.observe("pending", "breached")
    for _ in range(10):
        pred.observe("pending", "waived")

    tests_passed = 0
    tests_total = 0

    tests_total += 1
    m = pred.matrix()
    if all(abs(sum(row) - 1.0) < 1e-9 for row in m):
        tests_passed += 1

    tests_total += 1
    risk = pred.predict("pending", lookahead=10)
    if 0.15 <= risk.breach_probability <= 0.25:
        tests_passed += 1

    tests_total += 1
    if risk.should_warn:
        tests_passed += 1

    tests_total += 1
    risk_f = pred.predict("fulfilled")
    if risk_f.breach_probability == 0.0:
        tests_passed += 1

    tests_total += 1
    portfolio = pred.scan(["pending", "pending", "fulfilled", "breached"])
    if portfolio.warnings_count >= 1 and portfolio.pending_count == 2:
        tests_passed += 1

    return {
        "observations": pred.observation_count(),
        "prediction_tests_passed": tests_passed,
        "prediction_tests_total": tests_total,
        "score": _score(tests_passed, tests_total),
    }


def benchmark_refusal_quality() -> dict[str, float | int]:
    from acgs_lite.constitution import Constitution, Rule, Severity
    from acgs_lite.constitution import RefusalReasoningEngine

    c = Constitution(
        rules=[
            Rule(
                id="R1",
                text="No finance",
                severity=Severity.CRITICAL,
                keywords=["invest", "stocks"],
            ),
            Rule(
                id="R2",
                text="No destruction",
                severity=Severity.HIGH,
                keywords=["delete", "destroy"],
            ),
        ]
    )
    engine = RefusalReasoningEngine(c)

    tests_passed = 0
    tests_total = 0

    tests_total += 1
    d = engine.reason_refusal("invest in stocks", ["R1"])
    if d.reasons and d.reasons[0].matched_keywords:
        tests_passed += 1

    tests_total += 1
    if d.can_retry and d.suggestions:
        tests_passed += 1

    tests_total += 1
    if any("research" in s.alternative_action.lower() for s in d.suggestions):
        tests_passed += 1

    tests_total += 1
    d2 = engine.reason_refusal("destroy all records", ["R2"])
    if any(
        "archive" in s.alternative_action.lower() or "decommission" in s.alternative_action.lower()
        for s in d2.suggestions
    ):
        tests_passed += 1

    tests_total += 1
    d3 = engine.reason_refusal("invest and destroy", ["R1", "R2"])
    if d3.rule_count == 2 and d3.refusal_severity == "critical":
        tests_passed += 1

    return {
        "refusal_tests_passed": tests_passed,
        "refusal_tests_total": tests_total,
        "score": _score(tests_passed, tests_total),
    }


def main() -> None:
    print("=" * 60)
    print("ACGS-2 Governance Quality Benchmark")
    print("=" * 60)

    t0 = time.monotonic()

    results = {
        "registry_health": benchmark_registry_health(),
        "chain_detection": benchmark_chain_detection(),
        "contract_enforcement": benchmark_contract_enforcement(),
        "breach_prediction": benchmark_breach_prediction(),
        "refusal_quality": benchmark_refusal_quality(),
    }

    elapsed = time.monotonic() - t0

    scores = []
    for dimension, data in results.items():
        score = data["score"]
        scores.append(score)
        status = "PASS" if score >= 0.9 else "WARN" if score >= 0.7 else "FAIL"
        print(f"\n--- {dimension} [{status}] score={score:.3f} ---")
        for k, v in data.items():
            if k != "score":
                print(f"  {k}: {v}")

    composite = sum(scores) / len(scores) if scores else 0.0
    print(f"\n{'=' * 60}")
    print(f"governance_quality_score: {composite:.6f}")
    print(f"dimensions_tested: {len(results)}")
    print(f"dimensions_passing: {sum(1 for s in scores if s >= 0.9)}")
    print(f"elapsed_seconds: {elapsed:.3f}")
    print(f"{'=' * 60}")

    return composite


if __name__ == "__main__":
    main()
