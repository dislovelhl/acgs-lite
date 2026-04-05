---
title: Validation request creates a corresponding audit trail entry
description: Perform a validation and verify the audit trail count increments and a new entry appears
criticality: critical
scenario: standard
flow: audit-trail-inspection
category: multi-entity
priority: Critical
---

# AT-010: Validation request creates a corresponding audit trail entry

## Setup

- Use skill: `api-validate-action` and `api-query-audit`
- The acgs-lite governance server is running with the standard scenario

## Steps

1. Send a GET request to `/audit/count` and record the current count as `N`
2. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "audit trail test action",
     "agent_id": "audit-test-agent",
     "context": {}
   }
   ```
3. Record the `audit_id` from the validation response
4. Send a GET request to `/audit/count`
5. Verify the count is now `N + 1`
6. Send a GET request to `/audit/entries?agent_id=audit-test-agent`
7. Verify the response contains an entry with action text `"audit trail test action"`
8. Verify the entry's `constitutional_hash` equals `"608508a9bd224290"`
9. Send a GET request to `/audit/chain`
10. Verify the chain is still `"valid": true`

## Expected Result

Each successful validation creates exactly one audit trail entry with the correct agent ID, action, and constitutional hash. The chain remains valid after the new entry.

## Bug Description

If validations do not create audit entries, or create multiple entries, or break the chain, the audit trail is unreliable for compliance reporting.
