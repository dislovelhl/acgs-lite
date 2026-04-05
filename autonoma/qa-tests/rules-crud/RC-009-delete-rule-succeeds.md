---
title: Delete an existing rule removes it from the constitution
description: DELETE /rules/{id} removes the rule, confirmed by subsequent GET returning 404
criticality: critical
scenario: standard
flow: rules-crud
category: happy-path
priority: Critical
---

# RC-009: Delete an existing rule removes it from the constitution

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running
- Create a rule `E2E-DEL-001` first:
  POST `/rules` with `{"id": "E2E-DEL-001", "text": "Deletable rule", "severity": "low", "keywords": ["deleteme"]}`

## Steps

1. Verify the rule exists: GET `/rules/E2E-DEL-001` returns HTTP **200**
2. Send a DELETE request to `/rules/E2E-DEL-001`
3. Verify the response HTTP status is **204**
4. Send a GET request to `/rules/E2E-DEL-001`
5. Verify it now returns HTTP **404**
6. Send a GET to `/rules` and verify `E2E-DEL-001` is no longer in the list

## Expected Result

The rule is permanently removed from the constitution. Subsequent reads confirm its absence. The engine rebuilds without the deleted rule.

## Bug Description

If a deleted rule persists or continues to affect validation, the delete operation is not fully propagated, leaving stale rules in the engine.
