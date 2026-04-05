---
title: Conditional rule COND-001 fires when context matches production
description: Submit a deploy action with production context and verify COND-001 blocks it, then submit with staging context and verify it passes
criticality: critical
scenario: standard
flow: governance-validation
category: happy-path
priority: Critical
---

# GV-005: Conditional rule COND-001 fires when context matches production

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution containing rule `COND-001` (severity: high, keywords: ["deploy", "release"], condition: {"env": "production"})

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "deploy the model to production",
     "agent_id": "deploy-agent",
     "context": {"env": "production"}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": false`
4. Verify the `violations` array contains `"COND-001"`
5. Now send a POST request to `/validate` with body:
   ```json
   {
     "action": "deploy the model to staging",
     "agent_id": "deploy-agent",
     "context": {"env": "staging"}
   }
   ```
6. Verify the response HTTP status is **200**
7. Verify the response body contains `"valid": true`
8. Verify the `violations` array is empty `[]`

## Expected Result

The conditional rule COND-001 only fires when the context environment is "production". The same action in a "staging" context passes validation.

## Bug Description

If the conditional rule fires regardless of context, or fails to fire in the matching context, the context-dependent rule evaluation is broken, leading to either over-blocking or under-blocking of deployments.
