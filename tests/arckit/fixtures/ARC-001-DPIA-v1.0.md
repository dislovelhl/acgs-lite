# Data Protection Impact Assessment

| Field | Value |
|-------|-------|
| Document ID | ARC-001-DPIA-v1.0 |
| Document Type | Data Protection Impact Assessment |
| Status | DRAFT |

## Description of Processing

### What data are we processing?

**Personal Data Categories**

| Entity ID | Entity Name | Data Categories | Special Category? | PII Level |
|-----------|-------------|-----------------|-------------------|-----------|
| E-001 | Citizen | Name, email address | NO | HIGH |
| E-002 | Case | date of birth, social security number | YES | VERY HIGH |

### Data Flow

Citizen data flows from the intake portal to the case-assessment service and then to an encrypted evidence store.

### Retention

Records are retained for 7 years and then deleted by automated retention jobs.
