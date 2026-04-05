"""Tests for AuthenticityDetector — Phase 4."""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.authenticity_detector import (
    _DIMENSION_WEIGHTS,
    AuthenticityDetector,
    AuthenticityDimension,
    AuthenticityScore,
    DimensionScore,
)
from constitutional_swarm.bittensor.precedent_store import PrecedentRecord, PrecedentStore
from constitutional_swarm.bittensor.protocol import EscalationType

CONST_HASH = "608508a9bd224290"

# High-quality deliberative judgment
GOOD_JUDGMENT = (
    "In my judgment, privacy takes precedence in this case. "
    "While the transparency concern is valid, the data subject has not consented "
    "under Article 8 ECHR, and the processing lacks a legal basis under GDPR Article 6. "
    "I weigh the privacy interest heavily because the affected individuals are in a "
    "vulnerable position. The security concern, although present, does not outweigh "
    "the fundamental right to data protection. On balance, the governance decision "
    "should be to deny the access request."
)

GOOD_REASONING = (
    "The key question here is whether the transparency interest is sufficient to "
    "override the data subject's privacy rights. I have considered the stakeholder "
    "positions: the controller seeks disclosure, but the individuals who are the "
    "data subjects have not given consent. The constitutional framework requires "
    "that we uphold the fairness and privacy principles above efficiency in this context."
)

# Low-quality / AI-typical judgment
BAD_JUDGMENT = "Sure! Here is my analysis:\n- Point 1\n- Point 2\n- Point 3\nThank you."

SHORT_JUDGMENT = "Privacy."

# Medium quality
MEDIUM_JUDGMENT = (
    "Privacy should be prioritized here because the user has not given consent. "
    "The security concern is secondary. Therefore, deny the request."
)

_PRIVACY_VEC = {
    "safety": 0.1,
    "security": 0.2,
    "privacy": 0.9,
    "fairness": 0.3,
    "reliability": 0.1,
    "transparency": 0.6,
    "efficiency": 0.1,
}


# ---------------------------------------------------------------------------
# Dimension weights sum to 1.0
# ---------------------------------------------------------------------------


class TestDimensionWeights:
    def test_weights_sum_to_one(self):
        total = sum(_DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_five_dimensions(self):
        assert len(_DIMENSION_WEIGHTS) == 5

    def test_reasoning_depth_highest_weight(self):
        assert _DIMENSION_WEIGHTS[AuthenticityDimension.REASONING_DEPTH] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# AuthenticityDetector — basic scoring
# ---------------------------------------------------------------------------


class TestAuthenticityDetectorBasic:
    def test_score_returns_authenticity_score(self):
        det = AuthenticityDetector()
        score = det.score(GOOD_JUDGMENT, GOOD_REASONING)
        assert isinstance(score, AuthenticityScore)

    def test_overall_in_range(self):
        det = AuthenticityDetector()
        for text in [GOOD_JUDGMENT, BAD_JUDGMENT, SHORT_JUDGMENT]:
            score = det.score(text)
            assert 0.0 <= score.overall <= 1.0

    def test_good_judgment_higher_than_bad(self):
        det = AuthenticityDetector()
        good = det.score(GOOD_JUDGMENT, GOOD_REASONING)
        bad = det.score(BAD_JUDGMENT)
        assert good.overall > bad.overall

    def test_short_judgment_low_score(self):
        det = AuthenticityDetector(min_word_count=30)
        score = det.score(SHORT_JUDGMENT)
        assert score.overall < 0.5

    def test_five_dimension_scores(self):
        det = AuthenticityDetector()
        score = det.score(GOOD_JUDGMENT)
        assert len(score.dimension_scores) == 5

    def test_dimension_scores_in_range(self):
        det = AuthenticityDetector()
        score = det.score(GOOD_JUDGMENT)
        for ds in score.dimension_scores:
            assert 0.0 <= ds.score <= 1.0

    def test_is_authentic_above_threshold(self):
        det = AuthenticityDetector(authenticity_threshold=0.3)
        score = det.score(GOOD_JUDGMENT, GOOD_REASONING)
        assert score.is_authentic is True

    def test_is_not_authentic_below_threshold(self):
        det = AuthenticityDetector(authenticity_threshold=0.99)
        score = det.score(SHORT_JUDGMENT)
        assert score.is_authentic is False

    def test_word_count_reported(self):
        det = AuthenticityDetector()
        score = det.score(GOOD_JUDGMENT)
        assert score.judgment_word_count > 0

    def test_flags_populated(self):
        det = AuthenticityDetector()
        score = det.score(GOOD_JUDGMENT, GOOD_REASONING)
        # Good judgment has constitutional refs and tradeoff language
        assert any(
            "constitutional" in f or "tradeoff" in f or "stakeholder" in f for f in score.flags
        )

    def test_as_dict_structure(self):
        det = AuthenticityDetector()
        d = det.score(GOOD_JUDGMENT).as_dict
        assert "overall" in d
        assert "is_authentic" in d
        assert "dimensions" in d
        assert "flags" in d
        assert len(d["dimensions"]) == 5


# ---------------------------------------------------------------------------
# Individual dimensions
# ---------------------------------------------------------------------------


class TestReasoningDepth:
    def _get_dim(self, score: AuthenticityScore) -> DimensionScore:
        return next(
            ds
            for ds in score.dimension_scores
            if ds.dimension == AuthenticityDimension.REASONING_DEPTH
        )

    def test_longer_text_higher_depth(self):
        det = AuthenticityDetector()
        short = det.score("Privacy matters.")
        long = det.score(GOOD_JUDGMENT)
        assert self._get_dim(long).score > self._get_dim(short).score

    def test_logical_connectives_boost_score(self):
        det = AuthenticityDetector()
        with_connectives = det.score(
            "Privacy matters because the user has not consented. "
            "Therefore, we must deny. However, security is also important. "
            "Thus, we must balance these concerns."
        )
        without = det.score("Privacy matters. Deny the request. Security matters.")
        assert self._get_dim(with_connectives).score >= self._get_dim(without).score

    def test_tradeoff_language_in_flags(self):
        det = AuthenticityDetector()
        score = det.score("While privacy is important, security outweighs it here.")
        assert "tradeoff_language_present" in score.flags

    def test_short_text_low_word_count_flag(self):
        det = AuthenticityDetector(min_word_count=50)
        score = det.score("Short text.")
        assert any("low_word_count" in f for f in score.flags)


class TestStakeholderCoverage:
    def _get_dim(self, score: AuthenticityScore) -> DimensionScore:
        return next(
            ds
            for ds in score.dimension_scores
            if ds.dimension == AuthenticityDimension.STAKEHOLDER_COVERAGE
        )

    def test_multiple_stakeholders_higher_score(self):
        det = AuthenticityDetector()
        multi = det.score(
            "The data subject has not consented. The controller seeks access. "
            "Third parties may be affected. The regulator requires compliance."
        )
        single = det.score("Privacy matters.")
        assert self._get_dim(multi).score > self._get_dim(single).score

    def test_no_stakeholders_low_score(self):
        det = AuthenticityDetector()
        score = det.score("Deny the request based on the score.")
        dim = self._get_dim(score)
        assert dim.score < 0.5


class TestConstitutionalConsistency:
    def _get_dim(self, score: AuthenticityScore) -> DimensionScore:
        return next(
            ds
            for ds in score.dimension_scores
            if ds.dimension == AuthenticityDimension.CONSTITUTIONAL_CONSISTENCY
        )

    def test_article_references_boost(self):
        det = AuthenticityDetector()
        with_refs = det.score(
            "Under Article 8 ECHR and GDPR Article 6, the fairness and privacy "
            "principles require consent. The compliance standard mandates disclosure."
        )
        without = det.score("Deny the request.")
        assert self._get_dim(with_refs).score > self._get_dim(without).score

    def test_constitutional_flags(self):
        det = AuthenticityDetector()
        score = det.score("GDPR and Article 8 ECHR apply here.")
        assert any("constitutional_refs" in f for f in score.flags)


class TestDeliberativeAuthenticity:
    def _get_dim(self, score: AuthenticityScore) -> DimensionScore:
        return next(
            ds
            for ds in score.dimension_scores
            if ds.dimension == AuthenticityDimension.DELIBERATIVE_AUTHENTICITY
        )

    def test_first_person_boosts_score(self):
        det = AuthenticityDetector()
        fp = det.score(
            "In my judgment, privacy is paramount. My assessment is that "
            "the data subject's rights outweigh the controller's interests."
        )
        no_fp = det.score(
            "Privacy is paramount. The data subject's rights outweigh "
            "the controller's interests. The decision is to deny."
        )
        assert self._get_dim(fp).score >= self._get_dim(no_fp).score

    def test_ai_bullet_list_penalized(self):
        det = AuthenticityDetector()
        bullets = det.score(
            "My analysis:\n- Privacy matters\n- Security matters\n- Fairness matters\n"
            "- Transparency matters\n- Reliability matters\nConclusion: deny."
        )
        no_bullets = det.score(
            "In my judgment, privacy matters and security matters. "
            "I weigh fairness against transparency and conclude we should deny."
        )
        assert self._get_dim(bullets).score <= self._get_dim(no_bullets).score

    def test_ai_bullet_list_flag(self):
        det = AuthenticityDetector()
        score = det.score("Analysis:\n- Point A\n- Point B\n- Point C\n- Point D\n- Point E")
        assert "ai_list_pattern" in score.flags

    def test_formulaic_opener_penalized(self):
        det = AuthenticityDetector()
        formulaic = det.score("Certainly! I'll help analyze this governance decision.")
        normal = det.score(
            "In my judgment, this decision requires careful analysis of the privacy implications."
        )
        assert self._get_dim(formulaic).score <= self._get_dim(normal).score


class TestPrecedentCompatibility:
    def _get_dim(self, score: AuthenticityScore) -> DimensionScore:
        return next(
            ds
            for ds in score.dimension_scores
            if ds.dimension == AuthenticityDimension.PRECEDENT_COMPATIBILITY
        )

    def test_no_store_returns_neutral(self):
        det = AuthenticityDetector()
        score = det.score(GOOD_JUDGMENT, precedent_store=None, query_vector=None)
        dim = self._get_dim(score)
        assert dim.score == pytest.approx(0.5)
        assert "neutral" in dim.evidence

    def test_empty_store_returns_neutral(self):
        det = AuthenticityDetector()
        store = PrecedentStore(CONST_HASH, min_votes_for_precedent=1)
        score = det.score(GOOD_JUDGMENT, precedent_store=store, query_vector=_PRIVACY_VEC)
        dim = self._get_dim(score)
        assert dim.score == pytest.approx(0.5)

    def test_similar_precedent_boosts_score(self):
        det = AuthenticityDetector()
        store = PrecedentStore(CONST_HASH, min_votes_for_precedent=1)
        rec = PrecedentRecord.create(
            case_id="c1",
            task_id="t1",
            miner_uid="m",
            judgment="Privacy takes precedence",
            reasoning="ECHR applies",
            votes_for=2,
            votes_against=0,
            proof_root_hash="abc",
            escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            impact_vector=_PRIVACY_VEC,
            constitutional_hash=CONST_HASH,
        )
        store.add(rec)

        # Near-identical query vector
        near_vec = {k: v * 1.01 for k, v in _PRIVACY_VEC.items()}
        score = det.score(GOOD_JUDGMENT, precedent_store=store, query_vector=near_vec)
        dim = self._get_dim(score)
        assert dim.score > 0.5

    def test_high_similarity_flag(self):
        det = AuthenticityDetector()
        store = PrecedentStore(CONST_HASH, min_votes_for_precedent=1)
        rec = PrecedentRecord.create(
            case_id="c1",
            task_id="t1",
            miner_uid="m",
            judgment="Privacy wins",
            reasoning="reason",
            votes_for=2,
            votes_against=0,
            proof_root_hash="abc",
            escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            impact_vector=_PRIVACY_VEC,
            constitutional_hash=CONST_HASH,
        )
        store.add(rec)
        score = det.score(GOOD_JUDGMENT, precedent_store=store, query_vector=_PRIVACY_VEC)
        dim = self._get_dim(score)
        if dim.score >= 0.85:
            assert any("precedent_match" in f for f in score.flags)


# ---------------------------------------------------------------------------
# End-to-end scoring consistency
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_consistent_scoring(self):
        """Same inputs → same score (deterministic)."""
        det = AuthenticityDetector()
        s1 = det.score(GOOD_JUDGMENT, GOOD_REASONING)
        s2 = det.score(GOOD_JUDGMENT, GOOD_REASONING)
        assert s1.overall == s2.overall

    def test_score_ranking(self):
        """Good > Medium > Short in authenticity."""
        det = AuthenticityDetector()
        good = det.score(GOOD_JUDGMENT, GOOD_REASONING)
        medium = det.score(MEDIUM_JUDGMENT)
        short = det.score(SHORT_JUDGMENT)
        assert good.overall > medium.overall > short.overall

    def test_threshold_default(self):
        det = AuthenticityDetector()
        assert det._threshold == 0.55
