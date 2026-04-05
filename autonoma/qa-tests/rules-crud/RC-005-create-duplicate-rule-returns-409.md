---
title: Create rule with duplicate ID returns HTTP 409
description: POST /rules with an existing rule ID returns a 409 conflict error
criticality: critical
scenario: standard
flow: rules-crud
category: validation
priority: Critical
---

# RC-005: Create rule with duplicate ID returns HTTP 409

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running with the standard constitution containing rule `SAFE-001`

## Steps

1. Send a POST request to `/rules` with body:
   ```json
   {
     "id": "SAFE-001",
     "text": "Duplicate rule attempt",
     "severity": "high",
     "keywords": ["test"]
   }
   ```
2. Verify the response HTTP status is **409**
3. Verify the response body contains an error message mentioning `"Rule 'SAFE-001' already exists"`

## Expected Result

The server rejects the duplicate rule creation with a 409 Conflict status, preserving the existing rule.

## Bug Description

If the server allows duplicate rule IDs, rules will be silently overwritten, losing previous rule definitions without the user's intent.
