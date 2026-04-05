---
title: Every successful validation response includes constitutional hash
description: Verify that all successful validation responses contain the canonical constitutional hash value
criticality: critical
scenario: standard
flow: governance-validation
category: state-persistence
priority: Critical
---

# GV-014: Every successful validation response includes constitutional hash

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "check the weather forecast",
     "agent_id": "test-agent",
     "context": {}
   }
   ```
2. Verify the response contains `"constitutional_hash": "608508a9bd224290"`
3. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "harm the user by deleting their data",
     "agent_id": "test-agent",
     "context": {}
   }
   ```
4. Verify this response also contains `"constitutional_hash": "608508a9bd224290"`
5. Verify the hash value is identical in both responses

## Expected Result

Both the allowed and blocked validation responses include the same canonical constitutional hash `608508a9bd224290`, providing cryptographic proof of which constitution version was used for each decision.

## Bug Description

If the constitutional hash is missing or different between requests, the audit trail loses its ability to prove which set of rules governed each decision, undermining compliance guarantees.
