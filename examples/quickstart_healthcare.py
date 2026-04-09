"""Quickstart: Healthcare AI Governance

Demonstrates constitutional governance for healthcare AI systems.
Rules enforce PHI protection, diagnostic safety, and medication
guardrails using GovernanceEngine.validate() directly. No external API keys required.
"""

from acgs_lite import (
    AuditLog,
    Constitution,
    ConstitutionalViolationError,
    GovernanceEngine,
    Rule,
    Severity,
)


def main() -> None:
    print("=" * 60)
    print("  ACGS Healthcare Governance")
    print("=" * 60)

    # -- Build a healthcare safety constitution --
    constitution = Constitution.from_rules(
        [
            Rule(
                id="HC-001",
                text="Must not expose Protected Health Information",
                severity=Severity.CRITICAL,
                keywords=["patient ssn", "medical record number"],
                patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
            ),
            Rule(
                id="HC-002",
                text="Diagnostic output must include uncertainty language",
                severity=Severity.HIGH,
                keywords=["definitive diagnosis", "certainly has", "confirmed diagnosis"],
            ),
            Rule(
                id="HC-003",
                text="Must not recommend controlled substances without safeguards",
                severity=Severity.HIGH,
                keywords=["prescribe opioid", "prescribe benzodiazepine", "prescribe stimulant"],
            ),
            Rule(
                id="HC-004",
                text="Must not override clinical decision support alerts",
                severity=Severity.CRITICAL,
                keywords=[
                    "override drug interaction",
                    "ignore allergy alert",
                    "bypass contraindication",
                ],
            ),
        ],
        name="healthcare-safety",
    )

    # -- Strict engine for blocking, non-strict for audit trail --
    audit_log = AuditLog()
    strict_engine = GovernanceEngine(constitution, strict=True)
    audit_engine = GovernanceEngine(constitution, audit_log=audit_log, strict=False)
    print(f"\nConstitution: {constitution.name} ({len(constitution.rules)} rules)")
    print(f"Hash: {constitution.hash}")

    # -- Safe clinical response --
    print("\n-- Safe Clinical Text --")
    safe_text = "Based on symptoms, consider differential diagnosis including viral pharyngitis"
    result = audit_engine.validate(safe_text, agent_id="clinical-ai")
    print(f"  [PASS] valid={result.valid}, violations={len(result.violations)}")

    # -- PHI pattern detected (SSN) --
    print("\n-- PHI Detection (strict mode blocks) --")
    phi_text = "Patient John Doe, SSN 123-45-6789, presents with chest pain"
    try:
        strict_engine.validate(phi_text, agent_id="clinical-ai")
    except ConstitutionalViolationError as e:
        print(f"  [BLOCKED] {e}")
    # Also record in audit trail via non-strict engine
    result = audit_engine.validate(phi_text, agent_id="clinical-ai")
    print(f"  [AUDIT]   valid={result.valid}, violations={len(result.violations)}")

    # -- Definitive diagnosis without uncertainty --
    print("\n-- Diagnostic Safety --")
    result = audit_engine.validate("The patient certainly has pneumonia", agent_id="clinical-ai")
    for v in result.violations:
        print(f"  [VIOLATION] {v.rule_id} ({v.severity.value}): {v.rule_text}")
    print(f"  valid={result.valid}")

    # -- Medication safety --
    print("\n-- Medication Guardrails --")
    result = audit_engine.validate("Prescribe opioid for mild back pain", agent_id="clinical-ai")
    for v in result.violations:
        print(f"  [VIOLATION] {v.rule_id} ({v.severity.value}): {v.rule_text}")
    print(f"  valid={result.valid}")

    # -- Audit chain integrity --
    print("\n-- Audit Trail --")
    violations_found = audit_log.query(valid=False)
    print(f"  Total entries:     {len(audit_log)}")
    print(f"  Violations logged: {len(violations_found)}")
    print(f"  Compliance rate:   {audit_log.compliance_rate:.0%}")
    print(f"  Chain integrity:   {audit_log.verify_chain()}")

    for entry in violations_found:
        rules = ", ".join(entry.violations)
        print(f"    - {entry.agent_id}: violated [{rules}]")

    print("\n" + "=" * 60)
    print("  Healthcare governance demo complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
