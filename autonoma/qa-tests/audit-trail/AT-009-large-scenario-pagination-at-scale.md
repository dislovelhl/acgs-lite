---
title: Large scenario pagination works correctly with 1000 entries
description: In the large scenario, verify pagination across 1000 entries with no duplicates or gaps
criticality: high
scenario: large
flow: audit-trail-inspection
category: async-patterns
priority: High
---

# AT-009: Large scenario pagination works correctly with 1000 entries

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the large scenario (1000 audit entries)

## Steps

1. Send a GET request to `/audit/count`
2. Verify the response contains `"count": 1000`
3. Send a GET request to `/audit/entries?limit=100&offset=0`
4. Verify the response returns exactly **100** entries
5. Send a GET request to `/audit/entries?limit=100&offset=900`
6. Verify the response returns exactly **100** entries
7. Send a GET request to `/audit/entries?limit=100&offset=1000`
8. Verify the response returns an empty array `[]` (past the end)
9. Send a GET request to `/audit/chain`
10. Verify the response contains `"valid": true` and `"entry_count": 1000`

## Expected Result

Pagination works correctly at scale, returning exact page sizes and handling the boundary condition when offset exceeds total entries.

## Bug Description

If pagination fails at scale or the chain verification breaks with 1000 entries, the system cannot support production audit trail volumes.
