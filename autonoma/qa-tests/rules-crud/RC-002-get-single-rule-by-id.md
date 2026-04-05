---
title: Get a single rule by ID returns correct rule
description: GET /rules/SAFE-001 returns the specific rule with all expected fields
criticality: critical
scenario: standard
flow: rules-crud
category: happy-path
priority: Critical
---

# RC-002: Get a single rule by ID returns correct rule

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running with the standard constitution containing rule `SAFE-001`

## Steps

1. Send a GET request to `/rules/SAFE-001`
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"id": "SAFE-001"`
4. Verify `severity` is `"critical"`
5. Verify `category` is `"safety"`
6. Verify `keywords` contains `"harm"`, `"injure"`, `"kill"`, `"weapon"`, `"attack"`
7. Verify `enabled` is `true`
8. Verify `workflow_action` is `"block"`
9. Verify `tags` contains `"core"` and `"eu-ai-act"`
10. Verify `priority` is `10`

## Expected Result

The endpoint returns the full SAFE-001 rule with all fields matching the standard scenario specification.

## Bug Description

If the rule is returned with incorrect fields, the constitution data integrity is compromised, and validation decisions may be wrong.
