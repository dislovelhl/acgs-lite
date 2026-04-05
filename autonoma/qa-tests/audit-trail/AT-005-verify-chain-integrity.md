---
title: Audit chain integrity verification returns valid with correct count
description: GET /audit/chain verifies the SHA-256 hash chain is intact and returns the correct entry count
criticality: critical
scenario: standard
flow: audit-trail-inspection
category: happy-path
priority: Critical
---

# AT-005: Audit chain integrity verification returns valid with correct count

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the standard scenario (8 audit entries)

## Steps

1. Send a GET request to `/audit/chain`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"valid": true`
4. Verify the response contains `"entry_count": 8`

## Expected Result

The tamper-evident SHA-256 hash chain is verified as intact with exactly 8 entries, confirming no entries have been modified or deleted.

## Bug Description

If the chain shows as invalid or the count is wrong, the tamper-evidence mechanism is compromised, which is a critical compliance failure for audit trail integrity.
