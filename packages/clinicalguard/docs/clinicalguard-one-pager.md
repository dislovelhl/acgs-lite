# ClinicalGuard
## Constitutional AI Governance for Healthcare

ClinicalGuard adds constitutional control, MACI separation of powers, and tamper-evident auditability to healthcare AI workflows before recommendations reach clinicians or patients.

### The Problem
- HIPAA violations can expose healthcare organizations to penalties up to $1.5M per violation when PHI is mishandled.
- FDA AI/ML scrutiny is rising for systems that influence clinical recommendations without explainable controls and escalation.
- Unauditable AI decisions create liability because teams cannot reconstruct what the model proposed, why it passed, or who approved it.

### Solution
- MACI separation of powers prevents an agent from proposing and approving the same clinical action.
- A 20-rule healthcare constitution enforces evidence tiering, PHI restrictions, escalation paths, dosing constraints, and audit requirements.
- Tamper-evident audit logging records constitutional hash, timestamp, decision path, and chain integrity for post-incident review.

### Compliance
- HIPAA: 9/15 auto-covered governance controls for healthcare AI workflows.
- FDA aligned: Supports evidence-tiering, human review for critical risk, dosing controls, and adverse-event detection.
- SOC 2 ready: Control mapping support for access control, traceability, logging, and deployment hardening.

### Technical
- Two-layer validation combines LLM clinical reasoning with deterministic constitutional rules.
- PHI detection covers 10 HIPAA Safe Harbor identifiers, including SSN, MRN, DOB, phone, email, insurance, account, IP, device, and license patterns.
- Drug interaction and contraindication review flags major interactions, narrow therapeutic index risks, and step-therapy gaps.

### Deployment
- Runs in Docker, on Fly.io, or in any cloud environment that can host a Python ASGI service.
- Supports API-key authentication for protected access to validation endpoints.
- Persistent audit storage enables chain validation and long-term evidence retention.

### Pricing
- Community: AGPL license for open development, evaluation, and self-managed experimentation.
- Enterprise: Commercial license with production rights, SLA options, and support for regulated deployment programs.
