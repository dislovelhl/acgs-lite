"""Domain template data for Constitution.from_template().

Each key is a governance domain name; the value is a dict suitable for
passing to ``Constitution.from_dict()``.
"""

from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "gitlab": {
        "name": "gitlab-governance",
        "version": "1.0.0",
        "description": (
            "Constitutional governance for GitLab SDLC — enforces MACI "
            "separation of powers, protects credentials, and ensures "
            "merge request integrity."
        ),
        "rules": [
            {
                "id": "GL-001",
                "text": (
                    "MR author cannot approve their own merge request (MACI separation of powers)"
                ),
                "severity": "critical",
                "keywords": ["self-approve", "auto-approve", "self-merge"],
                "category": "maci",
                "subcategory": "separation-of-powers",
                "workflow_action": "block",
            },
            {
                "id": "GL-002",
                "text": "No credentials or secrets committed to repository",
                "severity": "critical",
                "keywords": ["api_key", "secret key", "private key", "password"],
                "patterns": [
                    r"(?i)(sk-[a-zA-Z0-9]{20,})",
                    r"(?i)(ghp_[a-zA-Z0-9]{36})",
                    r"(?i)(glpat-[a-zA-Z0-9\-]{20})",
                    r"[A-Za-z0-9+/]{40}",
                ],
                "category": "data-protection",
                "subcategory": "credential-exposure",
                "workflow_action": "block_and_notify",
            },
            {
                "id": "GL-003",
                "text": "No PII (SSN, credit cards) in source code or commit messages",
                "severity": "critical",
                "keywords": ["ssn", "social security", "credit card", "pii"],
                "patterns": [
                    r"\d{3}-\d{2}-\d{4}",
                    r"4[0-9]{12}(?:[0-9]{3})?",
                ],
                "category": "data-protection",
                "subcategory": "pii-exposure",
                "workflow_action": "block_and_notify",
            },
            {
                "id": "GL-004",
                "text": "Destructive production operations require human review",
                "severity": "high",
                "keywords": [
                    "drop table",
                    "delete all",
                    "truncate",
                    "rm -rf",
                    "force push",
                ],
                "category": "operations",
                "subcategory": "destructive-action",
                "workflow_action": "require_human_review",
            },
            {
                "id": "GL-005",
                "text": "CI/CD pipelines must not skip constitutional validation",
                "severity": "high",
                "keywords": [
                    "skip validation",
                    "disable governance",
                    "no-verify",
                    "bypass check",
                ],
                "category": "integrity",
                "subcategory": "governance-bypass",
                "workflow_action": "block",
            },
            {
                "id": "GL-006",
                "text": "Agent actions must produce an audit trail entry",
                "severity": "medium",
                "keywords": ["no-audit", "skip audit", "disable logging"],
                "category": "audit",
                "subcategory": "trail-completeness",
                "workflow_action": "warn",
            },
        ],
    },
    "healthcare": {
        "name": "healthcare-governance",
        "version": "1.0.0",
        "description": (
            "HIPAA-aligned constitutional governance for healthcare AI — "
            "protects PHI, prevents unauthorised treatment decisions, and "
            "ensures human oversight of clinical recommendations."
        ),
        "rules": [
            {
                "id": "HC-001",
                "text": (
                    "AI must not make autonomous treatment decisions without clinician review"
                ),
                "severity": "critical",
                "keywords": [
                    "prescribe",
                    "diagnose",
                    "treatment decision",
                    "clinical recommendation",
                    "approve treatment",
                    "deny treatment",
                ],
                "category": "clinical-safety",
                "subcategory": "autonomous-decision",
                "workflow_action": "require_human_review",
            },
            {
                "id": "HC-002",
                "text": (
                    "Protected Health Information must not be exposed outside authorised scope"
                ),
                "severity": "critical",
                "keywords": [
                    "patient data",
                    "medical record",
                    "health record",
                    "phi",
                    "ehr",
                ],
                "patterns": [r"\d{3}-\d{2}-\d{4}"],
                "category": "data-protection",
                "subcategory": "phi-exposure",
                "workflow_action": "block_and_notify",
            },
            {
                "id": "HC-003",
                "text": (
                    "AI must not provide individualised medical advice"
                    " without appropriate disclaimers"
                ),
                "severity": "high",
                "keywords": [
                    "take this medication",
                    "your diagnosis",
                    "you have",
                    "medical advice",
                ],
                "category": "clinical-safety",
                "subcategory": "unqualified-advice",
                "workflow_action": "escalate_to_senior",
            },
            {
                "id": "HC-004",
                "text": (
                    "Patient consent must be obtained before processing sensitive health data"
                ),
                "severity": "high",
                "keywords": ["without consent", "no consent check", "skip consent"],
                "category": "compliance",
                "subcategory": "hipaa-consent",
                "workflow_action": "block",
            },
            {
                "id": "HC-005",
                "text": ("All clinical AI decisions must be logged with patient ID and timestamp"),
                "severity": "high",
                "keywords": ["no audit", "skip log", "disable audit"],
                "category": "audit",
                "subcategory": "clinical-trail",
                "workflow_action": "block",
            },
        ],
    },
    "finance": {
        "name": "finance-governance",
        "version": "1.0.0",
        "description": (
            "ECOA/FCRA-aligned constitutional governance for financial AI — "
            "prevents discriminatory lending, enforces explainability, and "
            "protects against unauthorised transactions."
        ),
        "rules": [
            {
                "id": "FIN-001",
                "text": "AI must not provide individualised investment or financial advice",
                "severity": "critical",
                "keywords": [
                    "invest in",
                    "buy stocks",
                    "financial advice",
                    "portfolio recommendation",
                    "buy crypto",
                    "short sell",
                ],
                "category": "regulatory",
                "subcategory": "financial-advice",
                "workflow_action": "block",
            },
            {
                "id": "FIN-002",
                "text": "Loan/credit decisions must not use protected characteristics",
                "severity": "critical",
                "keywords": [
                    "use zip code",
                    "use race",
                    "use gender",
                    "use religion",
                    "use national origin",
                    "proxy discrimin",
                ],
                "category": "compliance",
                "subcategory": "fair-lending",
                "workflow_action": "block_and_notify",
            },
            {
                "id": "FIN-003",
                "text": "Credit decisions must provide adverse action reasons (FCRA)",
                "severity": "high",
                "keywords": ["no reason", "deny without explanation", "reject silently"],
                "category": "compliance",
                "subcategory": "adverse-action",
                "workflow_action": "require_human_review",
            },
            {
                "id": "FIN-004",
                "text": "High-value transactions require multi-party authorisation",
                "severity": "critical",
                "keywords": [
                    "transfer funds",
                    "wire transfer",
                    "large transaction",
                    "bulk payment",
                ],
                "category": "operations",
                "subcategory": "transaction-control",
                "workflow_action": "require_human_review",
            },
            {
                "id": "FIN-005",
                "text": ("PII and financial account data must not be exposed in logs or responses"),
                "severity": "critical",
                "keywords": ["ssn", "account number", "credit card", "pii"],
                "patterns": [
                    r"\d{3}-\d{2}-\d{4}",
                    r"[0-9]{13,16}",
                    r"[0-9]{9}",
                ],
                "category": "data-protection",
                "subcategory": "pii-exposure",
                "workflow_action": "block_and_notify",
            },
        ],
    },
    "security": {
        "name": "security-governance",
        "version": "1.0.0",
        "description": (
            "Cybersecurity-focused constitutional governance — prevents "
            "code injection, credential exposure, privilege escalation, "
            "and sandbox escape."
        ),
        "rules": [
            {
                "id": "SEC-001",
                "text": "AI must not generate or execute code injection payloads",
                "severity": "critical",
                "keywords": [
                    "sql injection",
                    "xss payload",
                    "exec(",
                    "eval(",
                    "os.system",
                    "subprocess.call",
                    "__import__",
                ],
                "patterns": [
                    r"(?i)(union\s+select)",
                    r"<script[^>]*>",
                    r"(?i)(eval\s*\()",
                ],
                "category": "security",
                "subcategory": "code-injection",
                "workflow_action": "block_and_notify",
            },
            {
                "id": "SEC-002",
                "text": "Credentials and secrets must not appear in outputs or logs",
                "severity": "critical",
                "keywords": [
                    "api key",
                    "secret key",
                    "private key",
                    "password",
                    "bearer token",
                ],
                "patterns": [
                    r"(?i)(sk-[a-zA-Z0-9]{20,})",
                    r"(?i)(ghp_[a-zA-Z0-9]{36})",
                    r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
                ],
                "category": "data-protection",
                "subcategory": "credential-exposure",
                "workflow_action": "block_and_notify",
            },
            {
                "id": "SEC-003",
                "text": "AI must not perform privilege escalation",
                "severity": "critical",
                "keywords": [
                    "escalate privilege",
                    "sudo su",
                    "chmod 777",
                    "setuid",
                    "add to sudoers",
                    "grant admin",
                ],
                "category": "security",
                "subcategory": "privilege-escalation",
                "workflow_action": "block",
            },
            {
                "id": "SEC-004",
                "text": "Network scanning and enumeration require explicit authorisation",
                "severity": "high",
                "keywords": [
                    "port scan",
                    "nmap",
                    "masscan",
                    "network scan",
                    "enumerate hosts",
                    "banner grab",
                ],
                "category": "security",
                "subcategory": "network-reconnaissance",
                "workflow_action": "require_human_review",
            },
            {
                "id": "SEC-005",
                "text": "Sandbox environments must not be escaped or bypassed",
                "severity": "critical",
                "keywords": [
                    "escape sandbox",
                    "bypass sandbox",
                    "container escape",
                    "docker breakout",
                    "chroot escape",
                ],
                "category": "security",
                "subcategory": "sandbox-escape",
                "workflow_action": "block_and_notify",
            },
        ],
    },
    "general": {
        "name": "general-ai-governance",
        "version": "1.0.0",
        "description": (
            "General-purpose constitutional governance for AI agents — "
            "covers financial advice, medical advice, legal advice, "
            "PII exposure, and MACI separation of powers."
        ),
        "rules": [
            {
                "id": "GEN-001",
                "text": "Agent must not provide individualised financial advice",
                "severity": "critical",
                "keywords": ["invest in", "buy stocks", "financial advice", "buy crypto"],
                "category": "regulatory",
                "subcategory": "financial-advice",
                "workflow_action": "block",
            },
            {
                "id": "GEN-002",
                "text": "Agent must not provide individualised medical advice",
                "severity": "critical",
                "keywords": [
                    "take this medication",
                    "your diagnosis",
                    "medical advice",
                    "prescribe",
                ],
                "category": "regulatory",
                "subcategory": "medical-advice",
                "workflow_action": "block",
            },
            {
                "id": "GEN-003",
                "text": "Agent must not provide specific legal advice",
                "severity": "high",
                "keywords": [
                    "legal advice",
                    "you should sue",
                    "file a lawsuit",
                    "your legal right",
                ],
                "category": "regulatory",
                "subcategory": "legal-advice",
                "workflow_action": "escalate_to_senior",
            },
            {
                "id": "GEN-004",
                "text": "Agent must not expose PII in responses",
                "severity": "critical",
                "keywords": ["ssn", "social security", "api key", "pii"],
                "patterns": [
                    r"\b\d{3}-\d{2}-\d{4}\b",
                    r"(?i)(sk-[a-zA-Z0-9]{20,})",
                ],
                "category": "data-protection",
                "subcategory": "pii-exposure",
                "workflow_action": "block_and_notify",
            },
            {
                "id": "GEN-005",
                "text": (
                    "Proposers cannot validate their own proposals (MACI separation of powers)"
                ),
                "severity": "critical",
                "keywords": ["self-approve", "auto-approve", "self-validate"],
                "category": "maci",
                "subcategory": "separation-of-powers",
                "workflow_action": "block",
            },
        ],
    },
}
