---
title: Regex pattern in PRIV-001 detects SSN format
description: Submit an action containing an SSN pattern and verify the regex-based rule matching fires
criticality: critical
scenario: standard
flow: governance-validation
category: happy-path
priority: Critical
---

# GV-006: Regex pattern in PRIV-001 detects SSN format

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution containing rule `PRIV-001` which has pattern `["\\b\\d{3}-\\d{2}-\\d{4}\\b"]`

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "SSN is 123-45-6789",
     "agent_id": "data-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": false`
4. Verify the `violations` array contains `"PRIV-001"`
5. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The governance engine's regex pattern matcher detects the SSN format (NNN-NN-NNNN) in the action text and fires the PRIV-001 privacy rule.

## Bug Description

If the SSN pattern is not detected, the regex-based rule matching is broken, allowing sensitive personal identifiers to pass through the governance engine undetected.
