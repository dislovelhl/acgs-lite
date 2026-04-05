---
title: Pagination with limit and offset returns correct pages
description: Paginate audit entries and verify no overlap between pages
criticality: critical
scenario: standard
flow: audit-trail-inspection
category: happy-path
priority: Critical
---

# AT-004: Pagination with limit and offset returns correct pages

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the standard scenario (8 audit entries)

## Steps

1. Send a GET request to `/audit/entries?limit=3&offset=0`
2. Verify the response HTTP status is **200**
3. Verify the response is a JSON array with exactly **3** entries
4. Record the IDs of the 3 returned entries
5. Send a GET request to `/audit/entries?limit=3&offset=3`
6. Verify the response returns exactly **3** entries
7. Verify none of the IDs from step 5 overlap with IDs from step 4
8. Send a GET request to `/audit/entries?limit=3&offset=6`
9. Verify the response returns exactly **2** entries (remaining entries)

## Expected Result

Pagination correctly partitions the audit trail into non-overlapping pages using limit and offset parameters.

## Bug Description

If pagination produces overlapping or missing entries, compliance officers reviewing audit trails could miss entries or see duplicates, compromising audit integrity.
