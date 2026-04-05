---
title: Positive security testing context does not trigger false positive
description: Submit an action that mentions security credentials in a testing context and verify it is not falsely blocked
criticality: high
scenario: standard
flow: governance-validation
category: happy-path
priority: High
---

# GV-010: Positive security testing context does not trigger false positive

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard 10-rule constitution loaded

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "testing security controls for credential leaks",
     "agent_id": "auditor-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": true`
4. Verify the `violations` field is an empty array `[]`
5. Verify the response contains a non-empty `audit_id` field

## Expected Result

Despite containing words like "credential" and "security", the positive testing context of the action prevents false positives. The engine correctly distinguishes between actual credential leaks and security testing discussions.

## Bug Description

If a security audit action is incorrectly blocked, the engine's keyword matching is too aggressive and produces false positives that would prevent legitimate security testing activities.
