---
title: Privacy rule PRIV-001 blocks unauthorized PII access
description: Submit an action referencing personal data access and verify it is blocked by the high-severity privacy rule PRIV-001
criticality: critical
scenario: standard
flow: governance-validation
category: happy-path
priority: Critical
---

# GV-003: Privacy rule PRIV-001 blocks unauthorized PII access

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution containing rule `PRIV-001` (severity: high, keywords: ["personal data", "PII", "SSN", "social security"])

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "access personal data without consent",
     "agent_id": "test-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": false`
4. Verify the `violations` array contains `"PRIV-001"`
5. Verify the response contains a non-empty `audit_id` field
6. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The governance engine detects the phrase "personal data" in the action, fires rule PRIV-001, and blocks the action.

## Bug Description

If the PII-accessing action is allowed through, the governance engine fails to enforce privacy protections, exposing users to GDPR and HIPAA compliance violations.
