---
title: Large scenario returns all 120 rules
description: In the large scenario, GET /rules returns all 120 rules and the engine rebuilds successfully
criticality: high
scenario: large
flow: rules-crud
category: happy-path
priority: High
---

# RC-013: Large scenario returns all 120 rules

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running with the large scenario constitution (120 rules)

## Steps

1. Send a GET request to `/rules`
2. Verify the response HTTP status is **200**
3. Verify the response is a JSON array with exactly **120** elements
4. Verify rules span all expected categories: `safety`, `privacy`, `fairness`, `transparency`, `security`, `oversight`, `general`, `custom`
5. Verify rule IDs follow the pattern `{CATEGORY_PREFIX}-{NNN}` (e.g., `SAFE-001` through `SAFE-020`)

## Expected Result

The governance engine handles 120 rules without errors. All rules are returned in the list response with correct structure.

## Bug Description

If the engine cannot load 120 rules or the list endpoint truncates results, the platform cannot support production-scale constitutions.
