---
title: Rule creation immediately affects validation decisions
description: Create a rule, verify it blocks a matching action, delete the rule, verify the action now passes
criticality: critical
scenario: standard
flow: rules-crud
category: multi-entity
priority: Critical
---

# RC-011: Rule creation immediately affects validation decisions

## Setup

- Use skill: `api-manage-rules` and `api-validate-action`
- The acgs-lite governance server is running
- Rule `E2E-001` does not exist yet

## Steps

1. Send a POST to `/rules` with body:
   ```json
   {
     "id": "E2E-001",
     "text": "Block forbidden word",
     "severity": "critical",
     "keywords": ["forbidden-word"]
   }
   ```
2. Verify the rule was created (HTTP 201)
3. Send a POST to `/validate` with body:
   ```json
   {
     "action": "this contains forbidden-word",
     "agent_id": "test-agent",
     "context": {}
   }
   ```
4. Verify the response shows `"valid": false` with `violations` containing `"E2E-001"`
5. Send a DELETE to `/rules/E2E-001`
6. Verify deletion succeeded (HTTP 204)
7. Send the same POST to `/validate` with `"this contains forbidden-word"`
8. Verify the response now shows `"valid": true` with empty `violations`

## Expected Result

Rule changes take effect immediately. Creating a rule blocks matching actions; deleting it allows them again. The engine rebuilds automatically after each change.

## Bug Description

If rule changes do not immediately affect validation, the engine is using a stale rule set, creating a window where the constitution is out of sync with the validation behavior.
