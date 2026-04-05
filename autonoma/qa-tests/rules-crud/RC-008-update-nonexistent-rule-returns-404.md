---
title: Update non-existent rule returns HTTP 404
description: PUT /rules/nonexistent-id returns a 404 error
criticality: high
scenario: standard
flow: rules-crud
category: validation
priority: High
---

# RC-008: Update non-existent rule returns HTTP 404

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running

## Steps

1. Send a PUT request to `/rules/nonexistent-id` with body:
   ```json
   {
     "text": "Updated text"
   }
   ```
2. Verify the response HTTP status is **404**

## Expected Result

The server returns a 404 when attempting to update a rule that does not exist.

## Bug Description

If the server returns 200 or creates a new rule instead of returning 404, the update semantics are wrong, potentially creating unintended rules.
