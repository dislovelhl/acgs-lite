---
title: Create a new constitutional rule
description: POST /rules creates a new rule and it appears in subsequent GET /rules responses
criticality: critical
scenario: standard
flow: rules-crud
category: happy-path
priority: Critical
---

# RC-004: Create a new constitutional rule

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running
- Rule `TEST-001` does not exist yet

## Steps

1. Send a POST request to `/rules` with body:
   ```json
   {
     "id": "TEST-001",
     "text": "No financial advice or investment recommendations",
     "severity": "critical",
     "keywords": ["invest", "buy stocks", "financial advice"],
     "patterns": [],
     "category": "safety",
     "workflow_action": "block"
   }
   ```
2. Verify the response HTTP status is **201**
3. Verify the response body contains `"id": "TEST-001"`
4. Send a GET request to `/rules`
5. Verify the response array now includes a rule with `id: "TEST-001"`
6. Send a GET request to `/rules/TEST-001`
7. Verify the response contains the full rule with `text`, `severity`, `keywords` matching what was submitted

## Expected Result

The rule is created successfully, persisted, and visible in both the list and single-rule endpoints. The engine rebuilds to include the new rule.

## Bug Description

If rule creation fails or the new rule is not visible in subsequent reads, the CRUD lifecycle is broken, preventing constitution management.
