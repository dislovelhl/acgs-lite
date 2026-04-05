---
title: Delete non-existent rule returns HTTP 404
description: DELETE /rules/nonexistent-id returns a 404 error
criticality: high
scenario: standard
flow: rules-crud
category: validation
priority: High
---

# RC-010: Delete non-existent rule returns HTTP 404

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running

## Steps

1. Send a DELETE request to `/rules/nonexistent-id`
2. Verify the response HTTP status is **404**

## Expected Result

The server returns 404 when attempting to delete a rule that does not exist.

## Bug Description

If the server returns 204 for a non-existent rule, the client cannot distinguish between successful deletion and no-op, leading to misleading success responses.
