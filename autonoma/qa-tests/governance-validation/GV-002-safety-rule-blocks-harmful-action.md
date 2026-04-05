---
title: Safety rule SAFE-001 blocks harmful action
description: Submit an action containing the keyword "harm" and verify it is blocked by the critical safety rule SAFE-001
criticality: critical
scenario: standard
flow: governance-validation
category: happy-path
priority: Critical
---

# GV-002: Safety rule SAFE-001 blocks harmful action

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution containing rule `SAFE-001` (severity: critical, keywords: ["harm", "injure", "kill", "weapon", "attack"])

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "harm the user by deleting their data",
     "agent_id": "test-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": false`
4. Verify the `violations` array contains `"SAFE-001"`
5. Verify the response contains a non-empty `audit_id` field
6. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The governance engine detects the keyword "harm" in the action text, fires rule SAFE-001, and blocks the action. The violation is attributed to SAFE-001 in the response.

## Bug Description

If the harmful action is allowed through (`valid: true`), the governance engine fails to enforce its most critical safety rule, creating a dangerous gap in AI agent oversight.
