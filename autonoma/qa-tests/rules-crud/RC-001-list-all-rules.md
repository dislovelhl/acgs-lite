---
title: List all constitutional rules returns full inventory
description: GET /rules returns all 10 standard rules with correct fields
criticality: critical
scenario: standard
flow: rules-crud
category: happy-path
priority: Critical
---

# RC-001: List all constitutional rules returns full inventory

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running with the standard 10-rule constitution loaded

## Steps

1. Send a GET request to `/rules`
2. Verify the response HTTP status is **200**
3. Verify the response is a JSON array with exactly **10** elements
4. Verify each rule object contains the fields: `id`, `text`, `severity`, `keywords`, `patterns`, `category`, `subcategory`, `workflow_action`, `enabled`, `tags`, `priority`
5. Verify rule with `id: "SAFE-001"` has `severity: "critical"` and `category: "safety"`
6. Verify rule with `id: "DEPR-001"` has `enabled: false` and `deprecated: true`
7. Verify rule with `id: "COND-001"` has a non-empty `condition` field

## Expected Result

The endpoint returns all 10 constitutional rules with their complete field set. Each rule has the correct severity, category, and metadata.

## Bug Description

If the rule count is wrong or fields are missing, the constitution is not fully loaded, which would cause validation to produce incorrect results.
