---
title: List all audit entries returns 8 standard entries
description: GET /audit/entries returns all 8 pre-seeded audit trail entries with correct structure
criticality: critical
scenario: standard
flow: audit-trail-inspection
category: happy-path
priority: Critical
---

# AT-001: List all audit entries returns 8 standard entries

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the standard scenario (8 pre-seeded audit entries)

## Steps

1. Send a GET request to `/audit/entries`
2. Verify the response HTTP status is **200**
3. Verify the response is a JSON array with exactly **8** elements
4. Verify each entry contains the fields: `id`, `type`, `agent_id`, `action`, `valid`, `violations`, `constitutional_hash`, `timestamp`
5. Verify entry with `id: "AUD-STD-001"` has `agent_id: "test-agent"` and `valid: true`
6. Verify entry with `id: "AUD-STD-002"` has `valid: false` and `violations` containing `"SAFE-001"`
7. Verify each entry has a non-empty `timestamp` in ISO-8601 format

## Expected Result

All 8 pre-seeded audit entries are returned with correct structure and values matching the standard scenario specification.

## Bug Description

If the entry count is wrong or field values do not match, the audit trail is not correctly recording validation decisions.
