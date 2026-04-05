---
title: Empty scenario returns empty or default rules list
description: In a fresh installation, GET /rules returns an empty array or only built-in defaults
criticality: high
scenario: empty
flow: rules-crud
category: happy-path
priority: High
---

# RC-012: Empty scenario returns empty or default rules list

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running with an empty/default constitution (no user-created rules)

## Steps

1. Send a GET request to `/rules`
2. Verify the response HTTP status is **200**
3. Verify the response is a JSON array (length 0 or only built-in default rules)
4. Verify no rules with `category: "custom"` exist

## Expected Result

A fresh installation returns an empty rules list or only built-in system defaults. The endpoint handles the zero-rule state gracefully.

## Bug Description

If the endpoint errors on an empty constitution, the first-use experience is broken, preventing developers from starting with a clean slate.
