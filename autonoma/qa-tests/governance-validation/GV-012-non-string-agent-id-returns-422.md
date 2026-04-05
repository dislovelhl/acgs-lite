---
title: Non-string agent_id returns HTTP 422 validation error
description: Submit a validation request with a numeric agent_id and verify the server returns a 422 error
criticality: high
scenario: standard
flow: governance-validation
category: validation
priority: High
---

# GV-012: Non-string agent_id returns HTTP 422 validation error

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "test action",
     "agent_id": 123,
     "context": {}
   }
   ```
2. Verify the response HTTP status is **422**
3. Verify the response body contains an error message mentioning `"'agent_id' must be a string"`

## Expected Result

The server rejects the request with HTTP 422 because `agent_id` must be a string, not an integer.

## Bug Description

If the server accepts non-string agent IDs, it could cause type errors in downstream processing or corrupt audit trail records.
