"""Tests for NMC Protocol — Phase 2.4."""

from __future__ import annotations

import hashlib
import uuid

import pytest

from constitutional_swarm.bittensor.nmc_protocol import (
    ConsensusJudgment,
    NMCCoordinator,
    NMCSession,
    NMCSessionState,
    SybilFlag,
    SynthesisMethod,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _commitment(judgment: str, nonce: str) -> str:
    return hashlib.sha256(f"{judgment}:{nonce}".encode()).hexdigest()


def _make_session(
    required_miners: set[str] | None = None,
    min_reveals: int = 2,
    deadline: float = 300.0,
    exclude_sybils: bool = True,
) -> NMCSession:
    return NMCSession(
        case_id="ESC-001",
        required_miners=required_miners,
        min_reveals=min_reveals,
        deadline_seconds=deadline,
        exclude_sybils=exclude_sybils,
    )


def _three_miner_session(
    j1: str = "allow",
    j2: str = "deny",
    j3: str = "allow",
    w1: float = 1.0,
    w2: float = 1.0,
    w3: float = 1.0,
    exclude_sybils: bool = True,
) -> tuple[NMCSession, dict]:
    miners = {"m1", "m2", "m3"}
    session = NMCSession(
        case_id="ESC-test",
        required_miners=miners,
        min_reveals=2,
        exclude_sybils=exclude_sybils,
    )
    nonces = {m: uuid.uuid4().hex for m in miners}
    judgments = {"m1": j1, "m2": j2, "m3": j3}
    weights = {"m1": w1, "m2": w2, "m3": w3}

    # Commit phase
    for m in miners:
        session.accept_commitment(m, _commitment(judgments[m], nonces[m]))

    # Reveal phase (auto-transitioned)
    for m in miners:
        session.accept_reveal(m, judgments[m], nonces[m], weight=weights[m])

    return session, nonces


# ---------------------------------------------------------------------------
# NMCCommitment & reveal verification
# ---------------------------------------------------------------------------


class TestCommitReveal:
    def test_commitment_hash_matches(self):
        session = _make_session()
        nonce = uuid.uuid4().hex
        judgment = "allow_with_conditions"
        h = _commitment(judgment, nonce)
        session.accept_commitment("m1", h)
        session.close_commits()
        session.accept_reveal("m1", judgment, nonce)  # should not raise

    def test_wrong_nonce_raises(self):
        session = _make_session()
        nonce = uuid.uuid4().hex
        judgment = "allow"
        h = _commitment(judgment, nonce)
        session.accept_commitment("m1", h)
        session.close_commits()
        with pytest.raises(ValueError, match="does not match commitment"):
            session.accept_reveal("m1", judgment, "WRONG_NONCE")

    def test_tampered_judgment_raises(self):
        session = _make_session()
        nonce = uuid.uuid4().hex
        judgment = "allow"
        h = _commitment(judgment, nonce)
        session.accept_commitment("m1", h)
        session.close_commits()
        with pytest.raises(ValueError, match="does not match commitment"):
            session.accept_reveal("m1", "deny", nonce)


# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------


class TestSessionState:
    def test_initial_state_open(self):
        session = _make_session()
        assert session.state == NMCSessionState.OPEN

    def test_auto_transition_to_revealing(self):
        session = _make_session(required_miners={"m1", "m2"})
        session.accept_commitment("m1", _commitment("allow", "n1"))
        assert session.state == NMCSessionState.OPEN
        session.accept_commitment("m2", _commitment("deny", "n2"))
        assert session.state == NMCSessionState.REVEALING

    def test_manual_close_commits(self):
        session = _make_session()
        session.accept_commitment("m1", _commitment("allow", "n1"))
        count = session.close_commits()
        assert count == 1
        assert session.state == NMCSessionState.REVEALING

    def test_commit_after_reveal_phase_raises(self):
        session = _make_session()
        session.accept_commitment("m1", _commitment("allow", "n1"))
        session.close_commits()
        with pytest.raises(ValueError, match="not OPEN"):
            session.accept_commitment("m2", _commitment("allow", "n2"))

    def test_reveal_without_commitment_raises(self):
        session = _make_session()
        session.accept_commitment("m1", _commitment("allow", "n1"))
        session.close_commits()
        with pytest.raises(ValueError, match="never committed"):
            session.accept_reveal("ghost", "allow", "nonce")

    def test_double_commit_raises(self):
        session = _make_session()
        h = _commitment("allow", "n1")
        session.accept_commitment("m1", h)
        with pytest.raises(ValueError, match="already committed"):
            session.accept_commitment("m1", h)

    def test_double_reveal_raises(self):
        session = _make_session()
        nonce = "n1"
        h = _commitment("allow", nonce)
        session.accept_commitment("m1", h)
        session.close_commits()
        session.accept_reveal("m1", "allow", nonce)
        with pytest.raises(ValueError, match="already revealed"):
            session.accept_reveal("m1", "allow", nonce)

    def test_synthesized_state_after_synthesis(self):
        session, _ = _three_miner_session()
        session.synthesize()
        assert session.state == NMCSessionState.SYNTHESIZED

    def test_is_complete_after_synthesis(self):
        session, _ = _three_miner_session()
        session.synthesize()
        assert session.is_complete is True

    def test_pending_reveal_miners(self):
        session = _make_session(required_miners={"m1", "m2"})
        session.accept_commitment("m1", _commitment("allow", "n1"))
        session.accept_commitment("m2", _commitment("deny", "n2"))
        # All committed → REVEALING; no reveals yet
        session.accept_reveal("m1", "allow", "n1")
        assert "m2" in session.pending_reveal_miners
        assert "m1" not in session.pending_reveal_miners


# ---------------------------------------------------------------------------
# Synthesis strategies
# ---------------------------------------------------------------------------


class TestSynthesis:
    def test_majority_vote_wins(self):
        # Exclude_sybils=False so all 3 reveals count for confidence
        session, _ = _three_miner_session(
            j1="allow", j2="allow", j3="deny", exclude_sybils=False
        )
        consensus = session.synthesize(SynthesisMethod.MAJORITY_VOTE)
        assert consensus.judgment_text == "allow"
        assert consensus.confidence == pytest.approx(2 / 3)

    def test_unanimous_all_agree(self):
        session, _ = _three_miner_session(j1="allow", j2="allow", j3="allow")
        consensus = session.synthesize(SynthesisMethod.UNANIMOUS)
        assert consensus.judgment_text == "allow"
        assert consensus.confidence == pytest.approx(1.0)

    def test_unanimous_no_agreement(self):
        session, _ = _three_miner_session(j1="allow", j2="deny", j3="abstain")
        consensus = session.synthesize(SynthesisMethod.UNANIMOUS)
        # No unanimity → low confidence
        assert consensus.confidence == pytest.approx(0.0)

    def test_weighted_vote(self):
        # m1 (2.5x) and m3 (2.5x) vote "allow"; m2 (1.0x) votes "deny"
        # exclude_sybils=False so all 3 contribute to weighted sum
        session, _ = _three_miner_session(
            j1="allow", j2="deny", j3="allow",
            w1=2.5, w2=1.0, w3=2.5,
            exclude_sybils=False,
        )
        consensus = session.synthesize(SynthesisMethod.WEIGHTED_VOTE)
        assert consensus.judgment_text == "allow"
        # total weight = 6.0; "allow" weight = 5.0
        assert consensus.confidence == pytest.approx(5.0 / 6.0, abs=0.01)

    def test_confidence_two_thirds_threshold(self):
        session, _ = _three_miner_session(j1="allow", j2="allow", j3="allow")
        consensus = session.synthesize()
        assert consensus.is_high_confidence is True

    def test_below_min_reveals_raises(self):
        session = NMCSession("ESC-x", min_reveals=3)
        # Commit 2 miners (need 3 reveals), close, reveal both, try to synthesize
        data = {"m1": ("allow", "n1"), "m2": ("deny", "n2")}
        for m, (j, n) in data.items():
            session.accept_commitment(m, _commitment(j, n))
        session.close_commits()  # only 2 committed
        for m, (j, n) in data.items():
            session.accept_reveal(m, j, n)
        with pytest.raises(ValueError, match="Insufficient"):
            session.synthesize()

    def test_consensus_fields(self):
        session, _ = _three_miner_session()
        consensus = session.synthesize()
        assert consensus.case_id == "ESC-test"
        assert consensus.committed_count == 3
        assert consensus.reveal_count == 3

    def test_synthesize_returns_immutable(self):
        session, _ = _three_miner_session()
        consensus = session.synthesize()
        with pytest.raises(AttributeError):
            consensus.judgment_text = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Sybil detection
# ---------------------------------------------------------------------------


class TestSybilDetection:
    def test_no_sybil_unique_judgments(self):
        session, _ = _three_miner_session(j1="allow", j2="deny", j3="abstain")
        consensus = session.synthesize()
        assert not consensus.has_sybil_activity

    def test_exact_duplicate_flagged(self):
        session, _ = _three_miner_session(
            j1="allow", j2="allow", j3="deny",
            exclude_sybils=False,  # don't exclude — just detect
        )
        consensus = session.synthesize()
        assert consensus.has_sybil_activity
        assert len(consensus.sybil_flags) == 1
        flag = consensus.sybil_flags[0]
        assert flag.is_exact_duplicate
        assert flag.confidence == pytest.approx(1.0)

    def test_sybil_excluded_from_consensus(self):
        # m2 copies m1's judgment → only m1 + m3 contribute
        session, _ = _three_miner_session(
            j1="allow", j2="allow", j3="deny",
            exclude_sybils=True,
        )
        consensus = session.synthesize()
        # One pair is duplicate: either m1 or m2 is excluded
        # After exclusion: remaining miners vote allow + deny
        assert consensus.valid_reveal_count == 2  # one excluded

    def test_excluded_miners_recorded(self):
        session, _ = _three_miner_session(
            j1="allow", j2="allow", j3="deny",
            exclude_sybils=True,
        )
        consensus = session.synthesize()
        assert len(consensus.excluded_miners) == 1

    def test_all_miners_identical_no_exclusion(self):
        """If all miners submit the same judgment, none are excluded."""
        session, _ = _three_miner_session(
            j1="allow", j2="allow", j3="allow",
            exclude_sybils=True,
        )
        consensus = session.synthesize()
        # All duplicates → NMC falls back to including all (no valid subset)
        assert consensus.judgment_text == "allow"

    def test_sybil_flag_immutable(self):
        session, _ = _three_miner_session(j1="X", j2="X", j3="Y", exclude_sybils=False)
        consensus = session.synthesize()
        assert len(consensus.sybil_flags) == 1
        flag = consensus.sybil_flags[0]
        with pytest.raises(AttributeError):
            flag.confidence = 0.0  # type: ignore[misc]

    def test_sybil_to_dict(self):
        session, _ = _three_miner_session(j1="X", j2="X", j3="Y", exclude_sybils=False)
        consensus = session.synthesize()
        d = consensus.to_dict()
        assert len(d["sybil_flags"]) == 1
        assert d["has_sybil_activity"] is True


# ---------------------------------------------------------------------------
# NMCCoordinator
# ---------------------------------------------------------------------------


class TestNMCCoordinator:
    def test_create_session(self):
        coord = NMCCoordinator()
        session = coord.create_session("ESC-001")
        assert session.case_id == "ESC-001"

    def test_duplicate_case_raises(self):
        coord = NMCCoordinator()
        coord.create_session("ESC-001")
        with pytest.raises(ValueError, match="already exists"):
            coord.create_session("ESC-001")

    def test_get_session(self):
        coord = NMCCoordinator()
        coord.create_session("ESC-002")
        assert coord.get_session("ESC-002") is not None
        assert coord.get_session("ESC-999") is None

    def test_outcome_before_synthesis_is_none(self):
        coord = NMCCoordinator()
        coord.create_session("ESC-003")
        assert coord.get_session_outcome("ESC-003") is None

    def test_outcome_after_synthesis(self):
        coord = NMCCoordinator(default_min_reveals=2)
        session = coord.create_session(
            "ESC-004",
            required_miners={"m1", "m2"},
        )
        data = {"m1": ("allow", "n1"), "m2": ("deny", "n2")}
        # Phase 1: all commits
        for m, (j, n) in data.items():
            session.accept_commitment(m, _commitment(j, n))
        # Phase 2: all reveals (auto-transitioned after both committed)
        for m, (j, n) in data.items():
            session.accept_reveal(m, j, n)
        session.synthesize()

        outcome = coord.get_session_outcome("ESC-004")
        assert outcome is not None
        assert isinstance(outcome, ConsensusJudgment)

    def test_active_vs_completed(self):
        coord = NMCCoordinator()
        session = coord.create_session("ESC-A", required_miners={"m1", "m2"})
        coord.create_session("ESC-B")  # still open
        # Complete ESC-A: commits first, then reveals
        data = {"m1": ("allow", "na1"), "m2": ("allow", "na2")}
        for m, (j, n) in data.items():
            session.accept_commitment(m, _commitment(j, n))
        for m, (j, n) in data.items():
            session.accept_reveal(m, j, n)
        session.synthesize()
        assert len(coord.completed_sessions()) == 1
        assert len(coord.active_sessions()) == 1

    def test_sybil_report(self):
        coord = NMCCoordinator()
        session = coord.create_session("ESC-S", required_miners={"m1", "m2"})
        # Commits first
        for m in ["m1", "m2"]:
            session.accept_commitment(m, _commitment("same", "nonce-" + m))
        # Then reveals (auto-transitioned after both committed)
        for m in ["m1", "m2"]:
            session.accept_reveal(m, "same", "nonce-" + m)
        session.synthesize(SynthesisMethod.MAJORITY_VOTE)
        report = coord.sybil_report()
        assert len(report) == 1
        assert report[0]["case_id"] == "ESC-S"

    def test_summary(self):
        coord = NMCCoordinator()
        coord.create_session("ESC-1")
        s = coord.summary()
        assert s["total_sessions"] == 1
        assert s["synthesized"] == 0

    def test_session_summary(self):
        session = _make_session()
        s = session.summary()
        assert s["state"] == "open"
        assert s["committed"] == 0
