"""ClinicalGuard: Healthcare-specific custom validators for GovernanceEngine.

These validators detect PHI patterns, clinical safety issues, and adverse events
using regex-based detection. They plug into GovernanceEngine via add_validator().

Usage::

    from clinicalguard.skills.healthcare_validators import (
        phi_detector,
        clinical_decision_auditor,
        adverse_event_logger,
    )
    engine.add_validator(phi_detector)
    engine.add_validator(clinical_decision_auditor)
    engine.add_validator(adverse_event_logger)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import re
from typing import Any

from acgs_lite.constitution import Severity
from acgs_lite.engine.core import Violation

# ---------------------------------------------------------------------------
# PHI Detector — catches HIPAA-defined identifiers in free text
# ---------------------------------------------------------------------------

# 10 of 18 HIPAA Safe Harbor identifiers (45 CFR 164.514(b)(2))
# Covers: SSN, MRN, DOB, phone, email, insurance ID, IP, account#, device/UDI, license#
# NOT yet covered: geographic data, dates (other than DOB), fax, URLs, VIN, biometric, photos
_PHI_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "PHI-SSN",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "Social Security Number pattern detected",
    ),
    (
        "PHI-MRN",
        re.compile(r"\b(?:MRN|Medical Record)\s*[#:]?\s*\d{5,}\b", re.IGNORECASE),
        "Medical Record Number pattern detected",
    ),
    (
        "PHI-DOB",
        re.compile(
            r"\b(?:DOB|date of birth|born)\s*[:\-]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
            re.IGNORECASE,
        ),
        "Date of birth pattern detected",
    ),
    (
        "PHI-PHONE",
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
        "Phone number pattern detected",
    ),
    (
        "PHI-EMAIL",
        re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
        "Email address pattern detected",
    ),
    (
        "PHI-INSURANCE",
        re.compile(
            r"\b(?:insurance|policy|member)\s*(?:id|number|#)\s*[:\-]?\s*[A-Z0-9]{6,}\b",
            re.IGNORECASE,
        ),
        "Insurance/policy ID pattern detected",
    ),
    (
        "PHI-IP",
        re.compile(r"\bIP\s*(?:address)?\s*[:\-]?\s*\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", re.IGNORECASE),
        "IP address pattern detected",
    ),
    (
        "PHI-ACCOUNT",
        re.compile(
            r"\b(?:account|acct)\s*(?:number|#|no)\s*[:\-]?\s*\d{8,}\b",
            re.IGNORECASE,
        ),
        "Account number pattern detected",
    ),
    (
        "PHI-DEVICE",
        re.compile(
            r"\b(?:UDI|device identifier|serial number)\s*[:\-]?\s*[A-Z0-9\-]{8,}\b",
            re.IGNORECASE,
        ),
        "Device/UDI identifier pattern detected",
    ),
    (
        "PHI-LICENSE",
        re.compile(
            r"\b(?:license|certificate|DEA)\s*(?:number|#|no)\s*[:\-]?\s*[A-Z0-9]{6,}\b",
            re.IGNORECASE,
        ),
        "License/certificate number pattern detected",
    ),
]


def phi_detector(text: str, context: dict[str, Any]) -> list[Violation]:
    """Detect PHI patterns in text per HIPAA Safe Harbor (45 CFR 164.514(b)(2)).

    Returns CRITICAL violations for each PHI type detected. Any single detection
    should block the output from being transmitted unencrypted.
    """
    violations: list[Violation] = []
    for rule_id, pattern, description in _PHI_PATTERNS:
        match = pattern.search(text)
        if match:
            violations.append(
                Violation(
                    rule_id=rule_id,
                    rule_text=description,
                    severity=Severity.CRITICAL,
                    matched_content=match.group()[:50],
                    category="phi_protection",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Clinical Decision Auditor — flags unsubstantiated clinical claims
# ---------------------------------------------------------------------------

_CLINICAL_CONCERNS: list[tuple[str, re.Pattern[str], str, Severity]] = [
    (
        "CLIN-NOEVIDENCE",
        re.compile(
            r"\b(?:no evidence|not evidence.based|without evidence|unproven)\b",
            re.IGNORECASE,
        ),
        "Clinical claim without evidence basis",
        Severity.HIGH,
    ),
    (
        "CLIN-CERTAINTY",
        re.compile(
            r"\b(?:definitely|certainly|guaranteed|100%|always works|never fails)\b",
            re.IGNORECASE,
        ),
        "Inappropriate certainty in clinical context — diagnostic uncertainty must be disclosed",
        Severity.MEDIUM,
    ),
    (
        "CLIN-SELFDIAGNOSE",
        re.compile(
            r"\b(?:you (?:have|definitely have|probably have)|your diagnosis is|diagnosed with)\b",
            re.IGNORECASE,
        ),
        "AI providing direct diagnosis without physician oversight",
        Severity.HIGH,
    ),
    (
        "CLIN-NOMONITOR",
        re.compile(
            r"\b(?:no (?:need to |need for )?monitor|skip (?:follow.up|monitoring)|"
            r"don'?t (?:need|bother) (?:to )?(?:check|monitor|follow))\b",
            re.IGNORECASE,
        ),
        "Recommendation to skip monitoring for clinical intervention",
        Severity.HIGH,
    ),
    (
        "CLIN-STOPMED",
        re.compile(
            r"\b(?:stop (?:taking (?:your )?|your )(?:medication|medicine|treatment)|"
            r"discontinue (?:all |your )?(?:medication|treatment))\b",
            re.IGNORECASE,
        ),
        "AI recommending medication discontinuation without physician oversight",
        Severity.CRITICAL,
    ),
]


def clinical_decision_auditor(text: str, context: dict[str, Any]) -> list[Violation]:
    """Flag clinical claims that lack evidence, express inappropriate certainty,
    or recommend actions that require physician oversight.
    """
    violations: list[Violation] = []
    for rule_id, pattern, description, severity in _CLINICAL_CONCERNS:
        match = pattern.search(text)
        if match:
            violations.append(
                Violation(
                    rule_id=rule_id,
                    rule_text=description,
                    severity=severity,
                    matched_content=match.group()[:50],
                    category="clinical_safety",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Adverse Event Logger — detects signals that require FDA MedWatch reporting
# ---------------------------------------------------------------------------

_ADVERSE_EVENT_SIGNALS: list[tuple[str, re.Pattern[str], str, Severity]] = [
    (
        "AE-DEATH",
        re.compile(
            r"\b(?:patient (?:died|death|deceased|expired|fatal)|"
            r"cause of death|mortality)\b",
            re.IGNORECASE,
        ),
        "Adverse event signal: patient death — requires MedWatch reporting",
        Severity.CRITICAL,
    ),
    (
        "AE-HOSPITALIZE",
        re.compile(
            r"\b(?:hospitali[sz](?:ed|ation)|(?:emergency|ER|ED) (?:visit|admission)|"
            r"ICU (?:admission|transfer)|life.threatening)\b",
            re.IGNORECASE,
        ),
        "Adverse event signal: hospitalization/life-threatening — may require reporting",
        Severity.HIGH,
    ),
    (
        "AE-DISABILITY",
        re.compile(
            r"\b(?:permanent (?:disability|impairment|damage)|"
            r"irreversible (?:damage|injury|harm))\b",
            re.IGNORECASE,
        ),
        "Adverse event signal: permanent disability — requires MedWatch reporting",
        Severity.CRITICAL,
    ),
    (
        "AE-OVERDOSE",
        re.compile(
            r"\b(?:overdose|toxic (?:level|dose)|supratherapeutic|"
            r"serotonin syndrome|neuroleptic malignant)\b",
            re.IGNORECASE,
        ),
        "Adverse event signal: overdose/toxicity",
        Severity.CRITICAL,
    ),
    (
        "AE-ALLERGY",
        re.compile(
            r"\b(?:anaphyla(?:xis|ctic)|severe (?:allergic|hypersensitivity)|"
            r"stevens.johnson|angioedema)\b",
            re.IGNORECASE,
        ),
        "Adverse event signal: severe allergic reaction",
        Severity.CRITICAL,
    ),
    (
        "AE-FALLRISK",
        re.compile(
            r"\b(?:fall(?:s| risk)|fracture(?:s| risk)|syncope|orthostatic)\b",
            re.IGNORECASE,
        ),
        "Adverse event signal: fall/fracture risk — requires documentation",
        Severity.MEDIUM,
    ),
]


def adverse_event_logger(text: str, context: dict[str, Any]) -> list[Violation]:
    """Detect signals of adverse events that may require FDA MedWatch reporting
    (21 CFR 314.80, 314.98) or institutional incident reporting.
    """
    violations: list[Violation] = []
    for rule_id, pattern, description, severity in _ADVERSE_EVENT_SIGNALS:
        match = pattern.search(text)
        if match:
            violations.append(
                Violation(
                    rule_id=rule_id,
                    rule_text=description,
                    severity=severity,
                    matched_content=match.group()[:50],
                    category="adverse_event",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Convenience: register all validators at once
# ---------------------------------------------------------------------------

ALL_VALIDATORS = [phi_detector, clinical_decision_auditor, adverse_event_logger]


def register_all(engine: Any) -> None:
    """Register all healthcare validators on a GovernanceEngine.

    Args:
        engine: GovernanceEngine instance with add_validator() method.
    """
    for validator in ALL_VALIDATORS:
        engine.add_validator(validator)
