---
title: Benign action passes in empty scenario with no rules
description: In a fresh installation with no user-created rules, verify that a benign action passes validation
criticality: high
scenario: empty
flow: governance-validation
category: happy-path
priority: High
---

# GV-015: Benign action passes in empty scenario with no rules

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with an empty/default constitution (no user-created rules)

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "hello world",
     "agent_id": "test",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": true`

## Expected Result

In a fresh installation with no user-created rules, all actions pass validation since there are no rules to violate.

## Bug Description

If the engine rejects actions when no rules are configured, the empty-state behavior is broken, preventing developers from starting with a clean slate.
