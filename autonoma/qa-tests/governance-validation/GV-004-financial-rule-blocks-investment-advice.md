---
title: Financial rule FIN-001 blocks investment recommendations
description: Submit an action containing financial advice keywords and verify it is blocked by FIN-001
criticality: critical
scenario: standard
flow: governance-validation
category: happy-path
priority: Critical
---

# GV-004: Financial rule FIN-001 blocks investment recommendations

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution containing rule `FIN-001` (severity: critical, keywords: ["invest", "buy stocks", "financial advice"])

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "recommend buying stocks in Tesla",
     "agent_id": "finance-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": false`
4. Verify the `violations` array contains `"FIN-001"`
5. Verify the response contains a non-empty `audit_id` field
6. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The governance engine detects the phrase "buying stocks" in the action, fires rule FIN-001, and blocks the financial advice action.

## Bug Description

If financial advice is allowed through, the governance engine fails to prevent regulatory violations related to unlicensed financial recommendations.
