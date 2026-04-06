# Security Policy: Zero-Trust for AI Agents

**Meta Description**: The ACGS-Lite security philosophy. Learn how we handle vulnerability disclosures and the core principles of MACI role separation and fail-closed governance.

---

ACGS-Lite is governance infrastructure. We take security seriously because our library is the last line of defense for your production systems.

## 🛡️ Core Security Principles

Our architecture is built on four "Ironclad" principles:

1.  **MACI Separation**: No agent can validate its own output. Proposer, Validator, Executor, and Observer are structurally separated roles to prevent self-validation attacks.
2.  **Fail-Closed Governance**: If a governance check fails to execute (due to a timeout, memory error, or crash), the action is **blocked by default**. Safety over availability.
3.  **Tamper-Evident Audit**: All decisions are recorded in a cryptographically chained audit log (SHA-256). Any attempt to retroactively modify the decision history is mathematically detectable.
4.  **Constitutional Integrity**: The canonical constitutional hash (current: `608508a9bd224290`) ensures that the safety rules haven't been modified in transit or during deployment.

## 🐛 Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly. **Do not open a public GitHub issue.**

Email **security@acgs.ai** with:
1.  A clear description of the vulnerability.
2.  Steps to reproduce (including a minimal Python script if possible).
3.  Potential impact assessment.

### Disclosure Timeline
-   **Acknowledgment**: Within 48 hours.
-   **Initial Assessment**: Within 5 business days.
-   **Fix Deadline**: 30 days for critical issues.
-   **Public Disclosure**: Coordinated with the reporter after a fix is released (typically 90 days).

## 🎯 In-Scope for Security Reports

We are particularly interested in:
-   **Validation Bypasses**: Ways to trick the `GovernanceEngine` into approving a prohibited pattern.
-   **MACI Violations**: Circumventing role separation to allow an agent to self-validate.
-   **Audit Tampering**: Modifying the audit log without breaking the hash chain.
-   **Secret Leakage**: Cases where sensitive data from the prompt is leaked into logs or error messages.
-   **Prompt Injection**: Novel ways to use the agent to bypass constitutional constraints.

## 🛠️ Security Best Practices for Users

*   **Scoped Permissions**: Always grant your agents the "Least Privilege" necessary for their task.
*   **Sandbox Execution**: Run agent-generated code in ephemeral, isolated containers.
*   **Regular Audits**: Periodically verify your `AuditLog` integrity using `acgs verify`.
*   **Update Regularly**: Ensure you are running the latest version of `acgs-lite` to receive security patches for new injection patterns.

---

**Licensed under Apache-2.0.**
