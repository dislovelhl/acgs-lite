---
title: Update an existing rule changes its fields
description: PUT /rules/SAFE-001 updates the rule text and severity, confirmed by subsequent GET
criticality: critical
scenario: standard
flow: rules-crud
category: happy-path
priority: Critical
---

# RC-007: Update an existing rule changes its fields

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running with the standard constitution containing rule `SAFE-001`

## Steps

1. Send a PUT request to `/rules/SAFE-001` with body:
   ```json
   {
     "text": "Updated: Reject all actions that could cause physical harm",
     "severity": "critical"
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body shows the updated `text` field
4. Send a GET request to `/rules/SAFE-001`
5. Verify the rule's `text` matches `"Updated: Reject all actions that could cause physical harm"`
6. Verify `severity` remains `"critical"`

## Expected Result

The rule is updated successfully and the changes persist. The engine rebuilds with the updated rule.

## Bug Description

If rule updates fail or do not persist, constitution management is broken, preventing administrators from evolving their governance rules over time.
