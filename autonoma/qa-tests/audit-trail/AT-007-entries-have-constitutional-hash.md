---
title: All audit entries contain canonical constitutional hash
description: Verify every audit entry has the constitutional_hash field set to the canonical value
criticality: critical
scenario: standard
flow: audit-trail-inspection
category: state-persistence
priority: Critical
---

# AT-007: All audit entries contain canonical constitutional hash

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the standard scenario

## Steps

1. Send a GET request to `/audit/entries`
2. Verify the response HTTP status is **200**
3. For each of the 8 entries, verify the `constitutional_hash` field equals `"608508a9bd224290"`
4. Verify entries AUD-STD-001 through AUD-STD-008 all have the same hash value

## Expected Result

Every audit entry records the constitutional hash that was active when the validation occurred, ensuring cryptographic traceability of which rules governed each decision.

## Bug Description

If any entry is missing the hash or has a different value, the audit trail cannot prove which constitution version was used for that decision, breaking the compliance chain.
