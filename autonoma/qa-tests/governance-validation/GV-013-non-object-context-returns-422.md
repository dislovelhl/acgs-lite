---
title: Non-object context returns HTTP 422 validation error
description: Submit a validation request with a string context instead of an object and verify the server returns a 422 error
criticality: high
scenario: standard
flow: governance-validation
category: validation
priority: High
---

# GV-013: Non-object context returns HTTP 422 validation error

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "test action",
     "agent_id": "test-agent",
     "context": "not-an-object"
   }
   ```
2. Verify the response HTTP status is **422**
3. Verify the response body contains an error message mentioning `"'context' must be an object"`

## Expected Result

The server rejects the request with HTTP 422 because the context field must be a JSON object, not a string.

## Bug Description

If the server accepts non-object context values, conditional rules that rely on context fields may silently fail to evaluate or throw runtime errors.
