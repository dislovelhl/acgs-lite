---
title: Empty scenario returns no audit entries with valid chain
description: In a fresh installation, verify audit endpoints return empty state correctly
criticality: high
scenario: empty
flow: audit-trail-inspection
category: happy-path
priority: High
---

# AT-008: Empty scenario returns no audit entries with valid chain

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with an empty installation (no prior validations)

## Steps

1. Send a GET request to `/audit/entries`
2. Verify the response is an empty array `[]`
3. Send a GET request to `/audit/count`
4. Verify the response contains `"count": 0`
5. Send a GET request to `/audit/chain`
6. Verify the response contains `"valid": true` and `"entry_count": 0`
7. Send a GET request to `/audit/entries?limit=10&offset=0`
8. Verify the response is an empty array `[]`

## Expected Result

All audit endpoints handle the empty state gracefully. An empty chain is considered valid (there is nothing to tamper with).

## Bug Description

If any audit endpoint errors on empty state, new installations will fail health checks or produce misleading error responses.
