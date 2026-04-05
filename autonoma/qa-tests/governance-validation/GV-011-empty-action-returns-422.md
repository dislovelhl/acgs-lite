---
title: Empty action string returns HTTP 422 validation error
description: Submit a validation request with an empty action string and verify the server returns a 422 error
criticality: critical
scenario: standard
flow: governance-validation
category: validation
priority: Critical
---

# GV-011: Empty action string returns HTTP 422 validation error

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "",
     "agent_id": "test-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **422**
3. Verify the response body contains an error message mentioning `"'action' must be a non-empty string"`

## Expected Result

The server rejects the request with HTTP 422 because the action field is an empty string. No audit trail entry is created.

## Bug Description

If the server accepts an empty action, it may process undefined behavior in the rule engine, or create meaningless audit trail entries that pollute the log.
