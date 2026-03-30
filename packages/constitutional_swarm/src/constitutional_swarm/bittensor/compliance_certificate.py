"""Compliance Certificate — Phase 2.2: ZKP-ready governance attestation.

Enterprises need to prove their AI systems were governed constitutionally
during a given time window — without revealing what decisions were made.

Two-layer architecture:
  Layer 1 (now):  HMAC-SHA256 signed certificate — production-ready,
                  no external dependency. Verifiable by any party with
                  the shared secret. Used for governance certification
                  and Revenue Stream 2 from day one.

  Layer 2 (Phase 2.3):  ZKP prover (Noir/circom) — proves
                  "compliance_rate ≥ threshold" without revealing
                  individual decisions. Plugged in via ZKProver Protocol.

The ComplianceCertificate is the artifact issued to enterprises after
a governance audit. It records: period, constitutional hash, decision
counts, compliance rate, and the cryptographic proof.

Design:
  • Pluggable prover — swap HMAC for ZKP without changing the API
  • Certificate is immutable once issued
  • Verifier works for both HMAC and ZKP certificates
  • AuditPeriod defines the time window being certified

Roadmap: 08-subnet-implementation-roadmap.md § Phase 2.2
Q&A:     07-subnet-concept-qa-responses.md § 3B
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Certificate types and status
# ---------------------------------------------------------------------------


class ProofType(Enum):
    HMAC_SHA256 = "hmac_sha256"   # current — HMAC signed, no ZKP
    ZKP_NOIR    = "zkp_noir"      # future — Noir ZK-SNARK
    ZKP_CIRCOM  = "zkp_circom"    # future — circom/snarkjs


class CertificateStatus(Enum):
    VALID     = "valid"
    EXPIRED   = "expired"
    REVOKED   = "revoked"
    PENDING   = "pending"


# ---------------------------------------------------------------------------
# Audit period
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditPeriod:
    """Time window being certified."""

    start_at: float
    end_at: float
    label: str = ""      # e.g. "Q1-2026", "2026-03"

    @property
    def duration_days(self) -> float:
        return (self.end_at - self.start_at) / 86_400

    @classmethod
    def last_n_days(cls, n: int, label: str = "") -> "AuditPeriod":
        end = time.time()
        return cls(start_at=end - n * 86_400, end_at=end, label=label or f"last-{n}d")

    @classmethod
    def current_month(cls) -> "AuditPeriod":
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return cls(
            start_at=start.timestamp(),
            end_at=now.timestamp(),
            label=now.strftime("%Y-%m"),
        )


# ---------------------------------------------------------------------------
# Compliance snapshot (what the certificate attests to)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComplianceSnapshot:
    """Summary of governance decisions in the audit period.

    This is the plaintext behind the proof — revealed for HMAC certs,
    hidden for ZKP certs (only the compliance_rate is proven).
    """

    total_decisions: int
    passed_decisions: int
    escalated_decisions: int
    auto_resolved_decisions: int
    constitutional_hash: str
    framework: str = "general"          # e.g. "eu_ai_act", "nist_ai_rmf"

    @property
    def compliance_rate(self) -> float:
        if self.total_decisions == 0:
            return 1.0
        return self.passed_decisions / self.total_decisions

    @property
    def escalation_rate(self) -> float:
        if self.total_decisions == 0:
            return 0.0
        return self.escalated_decisions / self.total_decisions

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "passed_decisions": self.passed_decisions,
            "escalated_decisions": self.escalated_decisions,
            "auto_resolved_decisions": self.auto_resolved_decisions,
            "compliance_rate": round(self.compliance_rate, 6),
            "escalation_rate": round(self.escalation_rate, 6),
            "constitutional_hash": self.constitutional_hash,
            "framework": self.framework,
        }


# ---------------------------------------------------------------------------
# Certificate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComplianceCertificate:
    """Immutable governance compliance certificate.

    Issued by the CertificateIssuer after verifying a ComplianceSnapshot.
    The proof field contains the HMAC or ZKP proving the attestation.

    For HMAC certificates: snapshot data is included and the proof is
    the HMAC of the canonical representation.

    For ZKP certificates: snapshot data may be omitted (private); the
    proof proves "compliance_rate ≥ threshold" without revealing counts.
    """

    cert_id: str
    issued_at: float
    expires_at: float
    issuer_id: str
    subject_id: str           # enterprise/client being certified
    period: AuditPeriod
    snapshot: ComplianceSnapshot
    proof_type: ProofType
    proof: str                # HMAC hex or ZKP proof blob
    threshold: float          # compliance_rate must be ≥ this
    status: CertificateStatus = CertificateStatus.VALID

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return self.status == CertificateStatus.VALID and not self.is_expired

    @property
    def attests_compliance(self) -> bool:
        """True if the snapshot meets the stated threshold."""
        return self.snapshot.compliance_rate >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "cert_id": self.cert_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "issuer_id": self.issuer_id,
            "subject_id": self.subject_id,
            "period": {
                "start": self.period.start_at,
                "end": self.period.end_at,
                "label": self.period.label,
            },
            "snapshot": self.snapshot.to_dict(),
            "proof_type": self.proof_type.value,
            "proof": self.proof,
            "threshold": self.threshold,
            "status": self.status.value,
            "is_valid": self.is_valid,
            "attests_compliance": self.attests_compliance,
        }


# ---------------------------------------------------------------------------
# Prover interface (pluggable)
# ---------------------------------------------------------------------------


class ComplianceProver(Protocol):
    """Protocol for generating compliance proofs.

    Implement for ZKP backends:
        class NoirProver:
            def prove(self, snapshot, threshold, constitutional_hash) -> str:
                # generate Noir ZK-SNARK proof
                return proof_blob

            def verify(self, proof, threshold, constitutional_hash) -> bool:
                # verify Noir proof
                ...
    """

    def prove(
        self,
        snapshot: ComplianceSnapshot,
        threshold: float,
        constitutional_hash: str,
    ) -> str:
        """Generate a proof string for the given snapshot."""
        ...

    def verify(
        self,
        proof: str,
        snapshot: ComplianceSnapshot,
        threshold: float,
        constitutional_hash: str,
    ) -> bool:
        """Verify a proof. Returns True if valid."""
        ...


class HMACProver:
    """HMAC-SHA256 prover — production-ready, no ZKP dependency.

    Proof = HMAC(key, canonical_payload) where:
      canonical_payload = f"{constitutional_hash}:{compliance_rate:.6f}:{threshold:.4f}"

    Reveals: compliance_rate and all snapshot counts (included in cert).
    Does NOT reveal: individual decision content (only aggregate counts).
    """

    def __init__(self, secret_key: str) -> None:
        self._key = secret_key.encode()

    def prove(
        self,
        snapshot: ComplianceSnapshot,
        threshold: float,
        constitutional_hash: str,
    ) -> str:
        payload = (
            f"{constitutional_hash}:{snapshot.compliance_rate:.6f}:"
            f"{threshold:.4f}:{snapshot.total_decisions}:{snapshot.passed_decisions}"
        )
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()

    def verify(
        self,
        proof: str,
        snapshot: ComplianceSnapshot,
        threshold: float,
        constitutional_hash: str,
    ) -> bool:
        expected = self.prove(snapshot, threshold, constitutional_hash)
        return hmac.compare_digest(proof, expected)


class ZKPStubProver:
    """ZKP stub — records circuit inputs for when Noir SDK is available.

    Generates a deterministic placeholder proof from the circuit inputs.
    NOT cryptographically sound — for API compatibility testing only.
    Replace with NoirProver when Noir SDK is integrated.
    """

    def prove(
        self,
        snapshot: ComplianceSnapshot,
        threshold: float,
        constitutional_hash: str,
    ) -> str:
        # Deterministic stub: hash of circuit inputs (not a real ZKP)
        payload = (
            f"zkp_stub:{constitutional_hash}:{snapshot.compliance_rate:.6f}:{threshold:.4f}"
        )
        return "zkp_stub:" + hashlib.sha256(payload.encode()).hexdigest()

    def verify(
        self,
        proof: str,
        snapshot: ComplianceSnapshot,
        threshold: float,
        constitutional_hash: str,
    ) -> bool:
        expected = self.prove(snapshot, threshold, constitutional_hash)
        return proof == expected


# ---------------------------------------------------------------------------
# Certificate Issuer
# ---------------------------------------------------------------------------


class CertificateIssuer:
    """Issues ComplianceCertificates for governance audit periods.

    Usage::

        issuer = CertificateIssuer(
            issuer_id="acgs-subnet-owner",
            secret_key="production-secret",      # for HMAC prover
        )

        snapshot = ComplianceSnapshot(
            total_decisions=10_000,
            passed_decisions=9_970,
            escalated_decisions=300,
            auto_resolved_decisions=200,
            constitutional_hash="608508a9bd224290",
            framework="eu_ai_act",
        )
        period = AuditPeriod.last_n_days(90, label="Q1-2026")

        cert = issuer.issue(
            subject_id="enterprise-42",
            period=period,
            snapshot=snapshot,
            threshold=0.997,         # 99.7% compliance required
            valid_for_days=365,
        )
        print(cert.attests_compliance)   # True (99.70% >= 99.70%)

        # Verify
        assert issuer.verify(cert)
    """

    def __init__(
        self,
        issuer_id: str = "acgs-subnet-owner",
        secret_key: str = "change-me-in-production",
        prover: ComplianceProver | None = None,
        proof_type: ProofType = ProofType.HMAC_SHA256,
    ) -> None:
        self._issuer_id = issuer_id
        self._proof_type = proof_type
        if prover is not None:
            self._prover = prover
        else:
            self._prover = HMACProver(secret_key)
        self._issued: dict[str, ComplianceCertificate] = {}
        self._revoked: set[str] = set()

    def issue(
        self,
        subject_id: str,
        period: AuditPeriod,
        snapshot: ComplianceSnapshot,
        threshold: float = 0.997,
        valid_for_days: int = 365,
    ) -> ComplianceCertificate:
        """Issue a compliance certificate.

        Raises ValueError if compliance_rate < threshold (cannot certify).
        """
        if snapshot.compliance_rate < threshold:
            raise ValueError(
                f"Cannot issue certificate: compliance_rate "
                f"{snapshot.compliance_rate:.4%} < threshold {threshold:.4%}"
            )

        proof = self._prover.prove(snapshot, threshold, snapshot.constitutional_hash)
        now = time.time()
        cert = ComplianceCertificate(
            cert_id=uuid.uuid4().hex[:16],
            issued_at=now,
            expires_at=now + valid_for_days * 86_400,
            issuer_id=self._issuer_id,
            subject_id=subject_id,
            period=period,
            snapshot=snapshot,
            proof_type=self._proof_type,
            proof=proof,
            threshold=threshold,
        )
        self._issued[cert.cert_id] = cert
        return cert

    def verify(self, cert: ComplianceCertificate) -> bool:
        """Verify a certificate's proof and status."""
        if cert.cert_id in self._revoked:
            return False
        if cert.is_expired:
            return False
        return self._prover.verify(
            cert.proof,
            cert.snapshot,
            cert.threshold,
            cert.snapshot.constitutional_hash,
        )

    def revoke(self, cert_id: str, reason: str = "") -> None:
        """Revoke a certificate (e.g. if constitutional hash changed)."""
        self._revoked.add(cert_id)
        if cert_id in self._issued:
            import dataclasses
            cert = self._issued[cert_id]
            self._issued[cert_id] = dataclasses.replace(
                cert, status=CertificateStatus.REVOKED
            )

    def get(self, cert_id: str) -> ComplianceCertificate | None:
        return self._issued.get(cert_id)

    def issued_for(self, subject_id: str) -> list[ComplianceCertificate]:
        return [c for c in self._issued.values() if c.subject_id == subject_id]

    def summary(self) -> dict[str, Any]:
        return {
            "issuer_id": self._issuer_id,
            "proof_type": self._proof_type.value,
            "total_issued": len(self._issued),
            "total_revoked": len(self._revoked),
        }
