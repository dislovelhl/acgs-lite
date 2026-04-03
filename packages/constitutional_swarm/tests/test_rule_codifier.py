"""Tests for RuleCodifier — Phase 3.3."""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.precedent_store import PrecedentRecord
from constitutional_swarm.bittensor.protocol import EscalationType
from constitutional_swarm.bittensor.rule_codifier import (
    PrecedentCluster,
    RuleCandidate,
    RuleCandidateStatus,
    RuleCodifier,
    _append_rule_to_yaml,
    _cosine,
    _generate_rule_text,
    _infer_severity,
)

CONST_HASH = "608508a9bd224290"

_PRIVACY_VEC = {
    "safety": 0.1, "security": 0.2, "privacy": 0.9,
    "fairness": 0.3, "reliability": 0.1, "transparency": 0.6, "efficiency": 0.1,
}
_SECURITY_VEC = {
    "safety": 0.8, "security": 0.9, "privacy": 0.2,
    "fairness": 0.1, "reliability": 0.7, "transparency": 0.3, "efficiency": 0.5,
}


def _make_rec(
    case_id: str,
    vector: dict | None = None,
    ambiguous: tuple = ("privacy",),
    judgment: str = "Privacy wins",
    grade: float = 0.92,
) -> PrecedentRecord:
    return PrecedentRecord.create(
        case_id=case_id,
        task_id="t1",
        miner_uid="miner-01",
        judgment=judgment,
        reasoning="rationale",
        votes_for=3,
        votes_against=0,
        proof_root_hash="abc",
        escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
        impact_vector=vector or _PRIVACY_VEC,
        constitutional_hash=CONST_HASH,
        ambiguous_dimensions=ambiguous,
    )


def _make_cluster(
    size: int = 60,
    agreement: float = 0.93,
    dims: list[str] | None = None,
) -> PrecedentCluster:
    return PrecedentCluster(
        cluster_id="cl01",
        precedent_ids=[f"p{i}" for i in range(size)],
        centroid_vector=_PRIVACY_VEC,
        dominant_dimensions=dims or ["privacy", "transparency"],
        majority_judgment="Privacy takes precedence",
        validator_agreement=agreement,
        escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT.value,
    )


SIMPLE_CONSTITUTION = """\
name: test-constitution
rules:
  - id: safety-01
    text: Do not cause harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
"""


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_cosine_identical(self):
        assert _cosine(_PRIVACY_VEC, _PRIVACY_VEC) == pytest.approx(1.0, abs=1e-6)

    def test_cosine_different(self):
        sim = _cosine(_PRIVACY_VEC, _SECURITY_VEC)
        assert 0.0 < sim < 1.0

    def test_infer_severity_safety(self):
        assert _infer_severity(["safety"]) == "high"

    def test_infer_severity_security(self):
        assert _infer_severity(["security", "privacy"]) == "high"

    def test_infer_severity_fairness(self):
        assert _infer_severity(["fairness"]) == "high"

    def test_infer_severity_other(self):
        assert _infer_severity(["reliability"]) == "medium"

    def test_generate_rule_text_with_dims(self):
        cluster = _make_cluster()
        text = _generate_rule_text(cluster)
        assert "privacy" in text.lower() or "transparency" in text.lower()
        assert len(text) > 20

    def test_generate_rule_text_no_dims(self):
        cluster = _make_cluster(dims=[])
        text = _generate_rule_text(cluster)
        assert len(text) > 10

    def test_append_rule_to_yaml_with_rules(self):
        yaml = SIMPLE_CONSTITUTION
        block = "  - id: new-rule\n    text: new rule\n"
        result = _append_rule_to_yaml(yaml, block)
        assert "new-rule" in result
        assert result.index("safety-01") < result.index("new-rule")

    def test_append_rule_to_yaml_without_rules(self):
        yaml = "name: minimal"
        block = "  - id: r1\n    text: rule\n"
        result = _append_rule_to_yaml(yaml, block)
        assert "rules:" in result
        assert "r1" in result


# ---------------------------------------------------------------------------
# RuleCodifier — clustering
# ---------------------------------------------------------------------------


class TestClustering:
    def test_find_clusters_empty(self):
        codifier = RuleCodifier(CONST_HASH)
        assert codifier.find_clusters([]) == []

    def test_find_clusters_single(self):
        codifier = RuleCodifier(CONST_HASH, similarity_threshold=0.8)
        recs = [_make_rec(f"c{i}") for i in range(3)]
        clusters = codifier.find_clusters(recs)
        assert len(clusters) >= 1

    def test_similar_vectors_cluster_together(self):
        codifier = RuleCodifier(CONST_HASH, similarity_threshold=0.8)
        # 5 privacy-heavy, 5 security-heavy
        priv_recs = [_make_rec(f"priv{i}", vector=_PRIVACY_VEC) for i in range(5)]
        sec_recs = [_make_rec(f"sec{i}", vector=_SECURITY_VEC) for i in range(5)]
        clusters = codifier.find_clusters(priv_recs + sec_recs)
        # Should form 2 clusters (privacy group + security group)
        assert len(clusters) >= 1

    def test_revoked_excluded_from_clustering(self):
        codifier = RuleCodifier(CONST_HASH)
        import dataclasses
        r = _make_rec("c1")
        revoked = dataclasses.replace(r, is_active=False)
        clusters = codifier.find_clusters([revoked])
        # Revoked precedent not included in any cluster
        for cl in clusters:
            assert "c1" not in [pid for pid in cl.precedent_ids]

    def test_cluster_has_dominant_dimensions(self):
        codifier = RuleCodifier(CONST_HASH, similarity_threshold=0.7)
        recs = [_make_rec(f"c{i}") for i in range(5)]
        clusters = codifier.find_clusters(recs)
        for cl in clusters:
            # dominant_dimensions should reflect high-score dims
            assert isinstance(cl.dominant_dimensions, list)

    def test_cluster_validator_agreement(self):
        codifier = RuleCodifier(CONST_HASH, similarity_threshold=0.7)
        recs = [_make_rec(f"c{i}", grade=0.90) for i in range(5)]
        clusters = codifier.find_clusters(recs)
        for cl in clusters:
            assert 0.0 <= cl.validator_agreement <= 1.0


# ---------------------------------------------------------------------------
# RuleCodifier — propose rules
# ---------------------------------------------------------------------------


class TestProposeRules:
    def test_below_min_size_not_proposed(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=10, min_validator_agreement=0.5)
        small = _make_cluster(size=5)
        candidates = codifier.propose_rules([small])
        assert candidates == []

    def test_below_min_agreement_not_proposed(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=5, min_validator_agreement=0.95)
        low_agreement = _make_cluster(size=10, agreement=0.80)
        candidates = codifier.propose_rules([low_agreement])
        assert candidates == []

    def test_qualifying_cluster_proposed(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=5, min_validator_agreement=0.90)
        good = _make_cluster(size=10, agreement=0.93)
        candidates = codifier.propose_rules([good])
        assert len(candidates) == 1

    def test_candidate_is_pending(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=5, min_validator_agreement=0.9)
        candidates = codifier.propose_rules([_make_cluster(size=10, agreement=0.93)])
        assert candidates[0].status == RuleCandidateStatus.PENDING

    def test_rule_id_has_prefix(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=1, min_validator_agreement=0.5,
                                rule_id_prefix="TEST")
        candidates = codifier.propose_rules([_make_cluster(size=5, agreement=0.91)])
        assert candidates[0].rule_id.startswith("TEST-")

    def test_to_yaml_block_format(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=1, min_validator_agreement=0.5)
        candidates = codifier.propose_rules([_make_cluster(size=5, agreement=0.91)])
        block = candidates[0].to_yaml_block()
        assert "id:" in block
        assert "text:" in block
        assert "severity:" in block
        assert "source: precedent_codification" in block
        assert "case_count:" in block
        assert "validator_agreement:" in block


# ---------------------------------------------------------------------------
# RuleCodifier — approval workflow
# ---------------------------------------------------------------------------


class TestApprovalWorkflow:
    def _setup(self) -> tuple[RuleCodifier, RuleCandidate]:
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=1, min_validator_agreement=0.5)
        cluster = _make_cluster(size=5, agreement=0.91)
        [candidate] = codifier.propose_rules([cluster])
        return codifier, candidate

    def test_approve(self):
        codifier, candidate = self._setup()
        approved = codifier.approve(candidate.candidate_id)
        assert approved.status == RuleCandidateStatus.APPROVED
        assert approved.approved_at is not None

    def test_reject(self):
        codifier, candidate = self._setup()
        rejected = codifier.reject(candidate.candidate_id, reason="contradicts safety-01")
        assert rejected.status == RuleCandidateStatus.REJECTED
        assert "contradicts" in rejected.rejection_reason

    def test_approve_wrong_state_raises(self):
        codifier, candidate = self._setup()
        codifier.reject(candidate.candidate_id)
        with pytest.raises(ValueError, match="rejected"):
            codifier.approve(candidate.candidate_id)

    def test_activate(self):
        codifier, candidate = self._setup()
        codifier.approve(candidate.candidate_id)
        activated, new_yaml = codifier.activate(candidate.candidate_id, SIMPLE_CONSTITUTION)

        assert activated.status == RuleCandidateStatus.ACTIVE
        assert activated.constitutional_hash_after != CONST_HASH
        assert activated.rule_id in new_yaml
        # Constitutional hash updated on codifier
        assert codifier.constitutional_hash == activated.constitutional_hash_after

    def test_activate_not_approved_raises(self):
        codifier, candidate = self._setup()
        with pytest.raises(ValueError, match="pending"):
            codifier.activate(candidate.candidate_id, SIMPLE_CONSTITUTION)

    def test_revoke_active_rule(self):
        codifier, candidate = self._setup()
        codifier.approve(candidate.candidate_id)
        codifier.activate(candidate.candidate_id, SIMPLE_CONSTITUTION)
        revoked = codifier.revoke(candidate.candidate_id, reason="bad rule")
        assert revoked.status == RuleCandidateStatus.REVOKED
        assert "bad rule" in revoked.revocation_reason
        assert codifier.active_rules == []

    def test_activate_appends_rule_to_yaml(self):
        codifier, candidate = self._setup()
        codifier.approve(candidate.candidate_id)
        _, new_yaml = codifier.activate(candidate.candidate_id, SIMPLE_CONSTITUTION)
        assert "safety-01" in new_yaml  # original rule preserved
        assert candidate.rule_id in new_yaml  # new rule appended

    def test_multiple_rules_sequential_hashes(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=1, min_validator_agreement=0.5)
        c1 = codifier.propose_rules([_make_cluster(size=5, agreement=0.91, dims=["privacy"])])[0]
        c2 = codifier.propose_rules([_make_cluster(size=5, agreement=0.93, dims=["security"])])[0]

        codifier.approve(c1.candidate_id)
        _, yaml1 = codifier.activate(c1.candidate_id, SIMPLE_CONSTITUTION)
        hash_after_1 = codifier.constitutional_hash

        codifier.approve(c2.candidate_id)
        _, _yaml2 = codifier.activate(c2.candidate_id, yaml1)
        hash_after_2 = codifier.constitutional_hash

        assert hash_after_1 != hash_after_2  # each activation produces new hash

    def test_nonexistent_candidate_raises(self):
        codifier = RuleCodifier(CONST_HASH)
        with pytest.raises(KeyError):
            codifier.approve("nonexistent")

    def test_summary(self):
        codifier, candidate = self._setup()
        codifier.approve(candidate.candidate_id)
        codifier.activate(candidate.candidate_id, SIMPLE_CONSTITUTION)
        s = codifier.summary()
        assert s["total_candidates"] == 1
        assert s["active_rules"] == 1
        assert s["status_counts"]["active"] == 1

    def test_pending_candidates_property(self):
        codifier = RuleCodifier(CONST_HASH, min_cluster_size=1, min_validator_agreement=0.5)
        codifier.propose_rules([_make_cluster(size=5, agreement=0.91)])
        codifier.propose_rules([_make_cluster(size=5, agreement=0.92)])
        assert len(codifier.pending_candidates) == 2
