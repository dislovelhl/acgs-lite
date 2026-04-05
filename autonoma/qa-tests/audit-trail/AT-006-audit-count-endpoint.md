---
title: Audit count endpoint returns correct total
description: GET /audit/count returns the exact number of audit entries
criticality: high
scenario: standard
flow: audit-trail-inspection
category: happy-path
priority: High
---

# AT-006: Audit count endpoint returns correct total

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the standard scenario (8 audit entries)

## Steps

1. Send a GET request to `/audit/count`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"count": 8`

## Expected Result

The count endpoint returns the exact number of audit entries, matching the total from the chain verification.

## Bug Description

If the count does not match the actual number of entries, the count endpoint is out of sync with the audit store, providing misleading metrics.
