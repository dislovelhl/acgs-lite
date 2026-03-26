"""Test invariants.rego policy file for syntax and basic logic.

Validates that the Rego policy contains all required invariant rules,
violation rules, and constitutional metadata.
"""

from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[1] / "policies" / "invariants.rego"


class TestInvariantsRego:
    """Validate invariants.rego structure and content."""

    def test_policy_file_exists(self) -> None:
        assert POLICY_PATH.exists(), f"Policy file not found at {POLICY_PATH}"

    def test_policy_package_correct(self) -> None:
        content = POLICY_PATH.read_text()
        assert "package acgs.invariants" in content

    def test_policy_contains_all_invariants(self) -> None:
        content = POLICY_PATH.read_text()
        invariants = [
            "invariant_maci_separation",
            "invariant_fail_closed",
            "invariant_append_only_audit",
            "invariant_hash_required",
            "invariant_tenant_isolation",
            "invariant_human_approval",
        ]
        for inv in invariants:
            assert inv in content, f"Missing invariant rule: {inv}"

    def test_policy_contains_violation_rules(self) -> None:
        content = POLICY_PATH.read_text()
        violations = [
            "violation_maci",
            "violation_fail_closed",
            "violation_append_only",
            "violation_hash",
            "violation_tenant",
            "violation_human_approval",
        ]
        for v in violations:
            assert v in content, f"Missing violation rule: {v}"

    def test_policy_has_constitutional_hash(self) -> None:
        content = POLICY_PATH.read_text()
        assert "608508a9bd224290" in content

    def test_policy_has_allow_amendment_rule(self) -> None:
        content = POLICY_PATH.read_text()
        assert "allow_amendment" in content

    def test_policy_has_all_violations_aggregate(self) -> None:
        content = POLICY_PATH.read_text()
        assert "all_violations" in content

    def test_policy_has_invariant_manifest(self) -> None:
        content = POLICY_PATH.read_text()
        assert "invariant_manifest" in content
        assert '"invariant_count": 6' in content

    def test_policy_has_future_keywords(self) -> None:
        content = POLICY_PATH.read_text()
        assert "import future.keywords.contains" in content
        assert "import future.keywords.if" in content
        assert "import future.keywords.in" in content

    def test_policy_has_p99_eval_comment(self) -> None:
        content = POLICY_PATH.read_text()
        assert "P99 eval <1ms" in content

    def test_invariant_count_matches_manifest(self) -> None:
        content = POLICY_PATH.read_text()
        invariant_prefix = "invariant_"
        # Count unique invariant rule definitions (lines starting with invariant_)
        invariant_names = set()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(invariant_prefix) and " if {" in stripped:
                name = stripped.split(" ")[0]
                invariant_names.add(name)
        # _tenant_cross_boundary is a helper, not an invariant
        invariant_names.discard("_tenant_cross_boundary")
        assert len(invariant_names) == 6, (
            f"Expected 6 invariant rules, found {len(invariant_names)}: {invariant_names}"
        )
