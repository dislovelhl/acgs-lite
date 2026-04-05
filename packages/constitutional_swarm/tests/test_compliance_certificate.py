"""Tests for ComplianceCertificate — Phase 2.2."""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.compliance_certificate import (
    AuditPeriod,
    CertificateIssuer,
    ComplianceSnapshot,
    HMACProver,
    ProofType,
    ZKPStubProver,
)

CONST_HASH = "608508a9bd224290"


def _good_snapshot(compliance_rate: float = 0.9980) -> ComplianceSnapshot:
    total = 10_000
    passed = int(total * compliance_rate)
    return ComplianceSnapshot(
        total_decisions=total,
        passed_decisions=passed,
        escalated_decisions=300,
        auto_resolved_decisions=200,
        constitutional_hash=CONST_HASH,
        framework="eu_ai_act",
    )


def _period() -> AuditPeriod:
    return AuditPeriod.last_n_days(90, label="Q1-2026")


# ---------------------------------------------------------------------------
# AuditPeriod
# ---------------------------------------------------------------------------


class TestAuditPeriod:
    def test_last_n_days(self):
        p = AuditPeriod.last_n_days(90)
        assert abs(p.duration_days - 90) < 0.01

    def test_label(self):
        p = AuditPeriod.last_n_days(30, label="Q1")
        assert p.label == "Q1"

    def test_default_label(self):
        p = AuditPeriod.last_n_days(30)
        assert "last-30d" in p.label

    def test_current_month(self):
        p = AuditPeriod.current_month()
        assert p.start_at < p.end_at
        assert p.label  # non-empty


# ---------------------------------------------------------------------------
# ComplianceSnapshot
# ---------------------------------------------------------------------------


class TestComplianceSnapshot:
    def test_compliance_rate(self):
        s = _good_snapshot(0.997)
        assert s.compliance_rate == pytest.approx(0.997, abs=0.001)

    def test_escalation_rate(self):
        s = ComplianceSnapshot(
            total_decisions=1000,
            passed_decisions=970,
            escalated_decisions=30,
            auto_resolved_decisions=20,
            constitutional_hash=CONST_HASH,
        )
        assert s.escalation_rate == pytest.approx(0.03)

    def test_zero_decisions(self):
        s = ComplianceSnapshot(0, 0, 0, 0, CONST_HASH)
        assert s.compliance_rate == 1.0
        assert s.escalation_rate == 0.0

    def test_to_dict(self):
        s = _good_snapshot()
        d = s.to_dict()
        assert "compliance_rate" in d
        assert "constitutional_hash" in d
        assert d["constitutional_hash"] == CONST_HASH


# ---------------------------------------------------------------------------
# HMACProver
# ---------------------------------------------------------------------------


class TestHMACProver:
    def test_prove_returns_hex(self):
        prover = HMACProver("secret")
        s = _good_snapshot()
        proof = prover.prove(s, 0.997, CONST_HASH)
        assert len(proof) == 64  # SHA-256 hex

    def test_verify_valid(self):
        prover = HMACProver("secret")
        s = _good_snapshot()
        proof = prover.prove(s, 0.997, CONST_HASH)
        assert prover.verify(proof, s, 0.997, CONST_HASH)

    def test_verify_wrong_key(self):
        p1 = HMACProver("key1")
        p2 = HMACProver("key2")
        s = _good_snapshot()
        proof = p1.prove(s, 0.997, CONST_HASH)
        assert not p2.verify(proof, s, 0.997, CONST_HASH)

    def test_verify_tampered_snapshot(self):
        prover = HMACProver("secret")
        s = _good_snapshot()
        proof = prover.prove(s, 0.997, CONST_HASH)
        tampered = ComplianceSnapshot(
            total_decisions=s.total_decisions,
            passed_decisions=s.passed_decisions - 1,  # tampered
            escalated_decisions=s.escalated_decisions,
            auto_resolved_decisions=s.auto_resolved_decisions,
            constitutional_hash=CONST_HASH,
        )
        assert not prover.verify(proof, tampered, 0.997, CONST_HASH)

    def test_deterministic(self):
        prover = HMACProver("secret")
        s = _good_snapshot()
        assert prover.prove(s, 0.997, CONST_HASH) == prover.prove(s, 0.997, CONST_HASH)


# ---------------------------------------------------------------------------
# ZKPStubProver
# ---------------------------------------------------------------------------


class TestZKPStubProver:
    def test_prove_returns_prefix(self):
        prover = ZKPStubProver()
        s = _good_snapshot()
        proof = prover.prove(s, 0.997, CONST_HASH)
        assert proof.startswith("zkp_stub:")

    def test_verify_valid(self):
        prover = ZKPStubProver()
        s = _good_snapshot()
        proof = prover.prove(s, 0.997, CONST_HASH)
        assert prover.verify(proof, s, 0.997, CONST_HASH)

    def test_verify_wrong_proof(self):
        prover = ZKPStubProver()
        s = _good_snapshot()
        assert not prover.verify("garbage", s, 0.997, CONST_HASH)


# ---------------------------------------------------------------------------
# CertificateIssuer
# ---------------------------------------------------------------------------


class TestCertificateIssuer:
    def _issuer(self) -> CertificateIssuer:
        return CertificateIssuer(issuer_id="test-issuer", secret_key="test-secret")

    def test_default_secret_requires_env_var(self, monkeypatch):
        monkeypatch.delenv("CONSTITUTIONAL_SWARM_COMPLIANCE_CERTIFICATE_SECRET", raising=False)

        with pytest.raises(ValueError, match="CONSTITUTIONAL_SWARM_COMPLIANCE_CERTIFICATE_SECRET"):
            CertificateIssuer(issuer_id="test-issuer")

    def test_issue_valid_snapshot(self):
        issuer = self._issuer()
        cert = issuer.issue("enterprise-1", _period(), _good_snapshot(), threshold=0.997)
        assert cert.cert_id
        assert cert.issuer_id == "test-issuer"
        assert cert.subject_id == "enterprise-1"
        assert cert.proof_type == ProofType.HMAC_SHA256
        assert cert.attests_compliance is True

    def test_issue_below_threshold_raises(self):
        issuer = self._issuer()
        low_snapshot = _good_snapshot(compliance_rate=0.90)
        with pytest.raises(ValueError, match="Cannot issue certificate"):
            issuer.issue("enterprise-1", _period(), low_snapshot, threshold=0.997)

    def test_verify_valid_cert(self):
        issuer = self._issuer()
        cert = issuer.issue("e1", _period(), _good_snapshot(), threshold=0.997)
        assert issuer.verify(cert) is True

    def test_cert_is_immutable(self):
        issuer = self._issuer()
        cert = issuer.issue("e1", _period(), _good_snapshot())
        with pytest.raises(AttributeError):
            cert.cert_id = "changed"  # type: ignore[misc]

    def test_revoke_cert(self):
        issuer = self._issuer()
        cert = issuer.issue("e1", _period(), _good_snapshot())
        issuer.revoke(cert.cert_id, reason="hash changed")
        assert issuer.verify(cert) is False

    def test_expired_cert_invalid(self):
        issuer = self._issuer()
        cert = issuer.issue("e1", _period(), _good_snapshot(), valid_for_days=0)
        # Expires immediately (0 days)
        assert cert.is_expired is True
        assert issuer.verify(cert) is False

    def test_issued_for_subject(self):
        issuer = self._issuer()
        issuer.issue("enterprise-A", _period(), _good_snapshot())
        issuer.issue("enterprise-A", _period(), _good_snapshot())
        issuer.issue("enterprise-B", _period(), _good_snapshot())
        certs = issuer.issued_for("enterprise-A")
        assert len(certs) == 2
        assert all(c.subject_id == "enterprise-A" for c in certs)

    def test_to_dict_structure(self):
        issuer = self._issuer()
        cert = issuer.issue("e1", _period(), _good_snapshot())
        d = cert.to_dict()
        assert "cert_id" in d
        assert "snapshot" in d
        assert "proof" in d
        assert "attests_compliance" in d
        assert d["attests_compliance"] is True

    def test_zkp_stub_prover(self):
        issuer = CertificateIssuer(
            issuer_id="test",
            prover=ZKPStubProver(),
            proof_type=ProofType.ZKP_NOIR,
        )
        cert = issuer.issue("e1", _period(), _good_snapshot())
        assert cert.proof_type == ProofType.ZKP_NOIR
        assert cert.proof.startswith("zkp_stub:")
        assert issuer.verify(cert) is True

    def test_summary(self):
        issuer = self._issuer()
        issuer.issue("e1", _period(), _good_snapshot())
        s = issuer.summary()
        assert s["total_issued"] == 1
        assert s["total_revoked"] == 0

    def test_compliance_rate_threshold_boundary(self):
        """Exactly at threshold → certificate issued."""
        issuer = self._issuer()
        # compliance_rate = 0.997 exactly
        snapshot = ComplianceSnapshot(
            total_decisions=1000,
            passed_decisions=997,
            escalated_decisions=3,
            auto_resolved_decisions=0,
            constitutional_hash=CONST_HASH,
        )
        cert = issuer.issue("e1", _period(), snapshot, threshold=0.997)
        assert cert.attests_compliance is True
