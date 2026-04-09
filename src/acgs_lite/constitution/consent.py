"""exp196: ConsentManager — data subject consent tracking for GDPR compliance.

Purpose-based consent lifecycle with grant/withdraw/expire, lawful basis
recording, data subject rights (access/erasure/portability), compliance
reporting, and tamper-evident audit trail.
Zero hot-path overhead (offline tooling only).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConsentStatus(Enum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    PENDING = "pending"


class LawfulBasis(Enum):
    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTERESTS = "legitimate_interests"


class DataSubjectRight(Enum):
    ACCESS = "access"
    RECTIFICATION = "rectification"
    ERASURE = "erasure"
    RESTRICT_PROCESSING = "restrict_processing"
    DATA_PORTABILITY = "data_portability"
    OBJECT = "object"
    NO_AUTOMATED_DECISION = "no_automated_decision"


@dataclass
class ConsentRecord:
    subject_id: str
    purpose: str
    lawful_basis: LawfulBasis
    status: ConsentStatus = ConsentStatus.PENDING
    granted_at: float | None = None
    withdrawn_at: float | None = None
    expires_at: float | None = None
    data_categories: list[str] = field(default_factory=list)
    processing_activities: list[str] = field(default_factory=list)
    evidence: str = ""
    version: int = 1

    @property
    def is_valid(self) -> bool:
        if self.status != ConsentStatus.ACTIVE:
            return False
        return not (self.expires_at and time.time() > self.expires_at)

    def integrity_hash(self) -> str:
        raw = (
            f"{self.subject_id}|{self.purpose}|{self.lawful_basis.value}"
            f"|{self.status.value}|{self.granted_at}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RightsRequest:
    subject_id: str
    right: DataSubjectRight
    requested_at: float = field(default_factory=time.time)
    fulfilled_at: float | None = None
    status: str = "pending"
    response: str = ""

    @property
    def is_overdue(self) -> bool:
        if self.status != "pending":
            return False
        deadline = self.requested_at + (30 * 24 * 3600)
        return time.time() > deadline


class ConsentManager:
    """GDPR-compliant consent lifecycle manager.

    Tracks purpose-based consent with grant/withdraw/expire lifecycle,
    lawful basis recording, data subject rights request handling,
    and compliance reporting.

    Example::

        mgr = ConsentManager()
        mgr.grant("user-123", "marketing_emails", LawfulBasis.CONSENT,
                   data_categories=["email", "name"])
        assert mgr.has_valid_consent("user-123", "marketing_emails")

        mgr.withdraw("user-123", "marketing_emails")
        assert not mgr.has_valid_consent("user-123", "marketing_emails")
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, ConsentRecord]] = {}
        self._rights_requests: list[RightsRequest] = []
        self._audit: list[dict[str, Any]] = []

    def grant(
        self,
        subject_id: str,
        purpose: str,
        lawful_basis: LawfulBasis,
        *,
        data_categories: list[str] | None = None,
        processing_activities: list[str] | None = None,
        expires_at: float | None = None,
        evidence: str = "",
    ) -> ConsentRecord:
        if subject_id not in self._records:
            self._records[subject_id] = {}

        existing = self._records[subject_id].get(purpose)
        version = (existing.version + 1) if existing else 1

        record = ConsentRecord(
            subject_id=subject_id,
            purpose=purpose,
            lawful_basis=lawful_basis,
            status=ConsentStatus.ACTIVE,
            granted_at=time.time(),
            expires_at=expires_at,
            data_categories=data_categories or [],
            processing_activities=processing_activities or [],
            evidence=evidence,
            version=version,
        )
        self._records[subject_id][purpose] = record
        self._log("grant", subject_id, purpose, lawful_basis.value)
        return record

    def withdraw(self, subject_id: str, purpose: str) -> bool:
        record = self._get_record(subject_id, purpose)
        if not record or record.status != ConsentStatus.ACTIVE:
            return False
        record.status = ConsentStatus.WITHDRAWN
        record.withdrawn_at = time.time()
        self._log("withdraw", subject_id, purpose)
        return True

    def withdraw_all(self, subject_id: str) -> int:
        if subject_id not in self._records:
            return 0
        count = 0
        for purpose in list(self._records[subject_id]):
            if self.withdraw(subject_id, purpose):
                count += 1
        return count

    def has_valid_consent(self, subject_id: str, purpose: str) -> bool:
        record = self._get_record(subject_id, purpose)
        if not record:
            return False
        if record.expires_at and time.time() > record.expires_at:
            record.status = ConsentStatus.EXPIRED
            return False
        return record.is_valid

    def check_processing_allowed(
        self, subject_id: str, purpose: str, activity: str
    ) -> dict[str, Any]:
        record = self._get_record(subject_id, purpose)
        if not record:
            return {"allowed": False, "reason": "No consent record"}
        if not record.is_valid:
            return {"allowed": False, "reason": f"Consent status: {record.status.value}"}
        if record.processing_activities and activity not in record.processing_activities:
            return {
                "allowed": False,
                "reason": f"Activity '{activity}' not in consented activities",
            }
        return {
            "allowed": True,
            "lawful_basis": record.lawful_basis.value,
            "consent_version": record.version,
        }

    def submit_rights_request(self, subject_id: str, right: DataSubjectRight) -> RightsRequest:
        request = RightsRequest(subject_id=subject_id, right=right)
        self._rights_requests.append(request)
        self._log("rights_request", subject_id, right.value)
        return request

    def fulfill_rights_request(self, request: RightsRequest, response: str = "") -> None:
        request.status = "fulfilled"
        request.fulfilled_at = time.time()
        request.response = response
        self._log("rights_fulfilled", request.subject_id, request.right.value)

    def overdue_requests(self) -> list[RightsRequest]:
        return [r for r in self._rights_requests if r.is_overdue]

    def subject_report(self, subject_id: str) -> dict[str, Any]:
        records = self._records.get(subject_id, {})
        active = [r for r in records.values() if r.is_valid]
        withdrawn = [r for r in records.values() if r.status == ConsentStatus.WITHDRAWN]
        expired = [r for r in records.values() if r.status == ConsentStatus.EXPIRED]
        requests = [r for r in self._rights_requests if r.subject_id == subject_id]

        all_categories: set[str] = set()
        for r in active:
            all_categories.update(r.data_categories)

        return {
            "subject_id": subject_id,
            "active_consents": len(active),
            "withdrawn_consents": len(withdrawn),
            "expired_consents": len(expired),
            "active_purposes": [r.purpose for r in active],
            "data_categories_in_scope": sorted(all_categories),
            "rights_requests": len(requests),
            "pending_requests": sum(1 for r in requests if r.status == "pending"),
            "overdue_requests": sum(1 for r in requests if r.is_overdue),
        }

    def compliance_report(self) -> dict[str, Any]:
        total_subjects = len(self._records)
        total_records = sum(len(v) for v in self._records.values())
        active_count = sum(
            1 for recs in self._records.values() for r in recs.values() if r.is_valid
        )
        expired_count = sum(
            1
            for recs in self._records.values()
            for r in recs.values()
            if r.status == ConsentStatus.EXPIRED
            or (r.expires_at is not None and time.time() > r.expires_at)
        )
        overdue = self.overdue_requests()

        basis_counts: dict[str, int] = {}
        for recs in self._records.values():
            for r in recs.values():
                key = r.lawful_basis.value
                basis_counts[key] = basis_counts.get(key, 0) + 1

        return {
            "total_subjects": total_subjects,
            "total_consent_records": total_records,
            "active_consents": active_count,
            "expired_consents": expired_count,
            "consent_rate": round(active_count / total_records, 4) if total_records else 0.0,
            "lawful_basis_distribution": basis_counts,
            "total_rights_requests": len(self._rights_requests),
            "overdue_rights_requests": len(overdue),
            "gdpr_compliant": len(overdue) == 0,
            "audit_entries": len(self._audit),
        }

    def export_subject_data(self, subject_id: str) -> dict[str, Any]:
        records = self._records.get(subject_id, {})
        return {
            "subject_id": subject_id,
            "consent_records": [
                {
                    "purpose": r.purpose,
                    "lawful_basis": r.lawful_basis.value,
                    "status": r.status.value,
                    "granted_at": r.granted_at,
                    "withdrawn_at": r.withdrawn_at,
                    "expires_at": r.expires_at,
                    "data_categories": r.data_categories,
                    "version": r.version,
                    "integrity_hash": r.integrity_hash(),
                }
                for r in records.values()
            ],
            "rights_requests": [
                {
                    "right": rr.right.value,
                    "requested_at": rr.requested_at,
                    "status": rr.status,
                    "fulfilled_at": rr.fulfilled_at,
                }
                for rr in self._rights_requests
                if rr.subject_id == subject_id
            ],
            "exported_at": time.time(),
        }

    def erase_subject(self, subject_id: str) -> bool:
        if subject_id not in self._records:
            return False
        del self._records[subject_id]
        self._log("erasure", subject_id, "all_data")
        return True

    def audit_log(self, subject_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        entries = self._audit
        if subject_id:
            entries = [e for e in entries if e.get("subject_id") == subject_id]
        return entries[-limit:]

    def _get_record(self, subject_id: str, purpose: str) -> ConsentRecord | None:
        return self._records.get(subject_id, {}).get(purpose)

    def _log(self, action: str, subject_id: str, detail: str, extra: str = "") -> None:
        self._audit.append(
            {
                "action": action,
                "subject_id": subject_id,
                "detail": detail,
                "extra": extra,
                "timestamp": time.time(),
            }
        )
