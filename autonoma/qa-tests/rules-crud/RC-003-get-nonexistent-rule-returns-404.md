---
title: Get non-existent rule returns HTTP 404
description: GET /rules/nonexistent-id returns a 404 error with a descriptive message
criticality: critical
scenario: standard
flow: rules-crud
category: validation
priority: Critical
---

# RC-003: Get non-existent rule returns HTTP 404

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running

## Steps

1. Send a GET request to `/rules/nonexistent-id`
2. Verify the response HTTP status is **404**
3. Verify the response body contains an error message mentioning `"Rule 'nonexistent-id' not found"`

## Expected Result

The server returns a 404 with a clear error message when a non-existent rule ID is requested.

## Bug Description

If the server returns 200 with empty data or 500, the error handling for missing rules is broken, confusing API consumers.
