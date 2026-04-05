# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.5.x   | Yes                |
| 2.4.x   | Security fixes only|
| < 2.4   | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in acgs-lite, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, email **security@acgs.ai** with:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact assessment
4. Any suggested fix (optional)

We will acknowledge receipt within 48 hours and provide an initial assessment within
5 business days.

## Security Principles

acgs-lite is governance infrastructure for AI agents. Security is foundational.
Licensed under Apache-2.0.

- **MACI separation**: no agent can validate its own output. Proposer, Validator,
  Executor, and Observer are structurally separated roles.
- **Fail-closed**: governance decisions default to deny on any error.
- **Tamper-evident audit trails**: SHA-256 chain verification on all decision records.
- **Constitutional hash verification**: the canonical hash `608508a9bd224290` ensures
  constitution integrity.
- **No secrets in source**: all credentials via environment variables only.

## Scope

The following are in scope for security reports:

- Constitutional validation bypass
- MACI role separation violations
- Audit trail tampering
- Secret leakage in logs or error messages
- Dependency vulnerabilities with exploitable paths
- Injection attacks through rule definitions

## Disclosure Timeline

- **Day 0**: Report received, acknowledgment sent
- **Day 5**: Initial assessment shared with reporter
- **Day 30**: Target fix deadline for critical issues
- **Day 90**: Public disclosure (coordinated with reporter)

## Recognition

We maintain a security acknowledgments section in our releases for responsible
disclosures.
