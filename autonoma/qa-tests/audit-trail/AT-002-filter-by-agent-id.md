---
title: Filter audit entries by agent_id returns correct subset
description: GET /audit/entries?agent_id=test-agent returns exactly 3 entries for that agent
criticality: critical
scenario: standard
flow: audit-trail-inspection
category: happy-path
priority: Critical
---

# AT-002: Filter audit entries by agent_id returns correct subset

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the standard scenario (8 pre-seeded audit entries)

## Steps

1. Send a GET request to `/audit/entries?agent_id=test-agent`
2. Verify the response HTTP status is **200**
3. Verify the response is a JSON array with exactly **3** elements
4. Verify all returned entries have `agent_id` equal to `"test-agent"`
5. Verify the entry IDs include `AUD-STD-001`, `AUD-STD-002`, `AUD-STD-003`
6. Send a GET request to `/audit/entries?agent_id=deploy-agent`
7. Verify the response returns exactly **2** entries (IDs `AUD-STD-006`, `AUD-STD-007`)

## Expected Result

Agent ID filtering correctly returns only the entries belonging to the specified agent.

## Bug Description

If filtering returns wrong entries or wrong count, the audit trail filtering is broken, preventing compliance officers from investigating specific agents.
