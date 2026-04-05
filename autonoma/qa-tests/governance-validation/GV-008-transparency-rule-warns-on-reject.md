---
title: Transparency rule TRANS-001 fires on rejection without explanation
description: Submit an action that rejects without explanation and verify the medium-severity transparency rule fires
criticality: high
scenario: standard
flow: governance-validation
category: happy-path
priority: High
---

# GV-008: Transparency rule TRANS-001 fires on rejection without explanation

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution containing rule `TRANS-001` (severity: medium, keywords: ["reject", "deny", "terminate", "suspend"], workflow_action: "warn")

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "reject the insurance claim without explanation",
     "agent_id": "claims-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": false`
4. Verify the `violations` array contains `"TRANS-001"`
5. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The governance engine detects the keyword "reject" in the action and fires rule TRANS-001, which requires explanation for consequential automated decisions.

## Bug Description

If the transparency rule does not fire, consequential automated decisions can be made without required explanations, violating EU AI Act transparency requirements.
