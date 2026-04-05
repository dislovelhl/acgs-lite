---
title: Create rule with empty ID returns HTTP 422
description: POST /rules with an empty id field returns a 422 validation error
criticality: high
scenario: standard
flow: rules-crud
category: validation
priority: High
---

# RC-006: Create rule with empty ID returns HTTP 422

## Setup

- Use skill: `api-manage-rules`
- The acgs-lite governance server is running

## Steps

1. Send a POST request to `/rules` with body:
   ```json
   {
     "id": "",
     "text": "Rule with empty ID",
     "severity": "high"
   }
   ```
2. Verify the response HTTP status is **422**

## Expected Result

The server rejects the rule with a 422 validation error because the `id` field cannot be empty.

## Bug Description

If the server accepts rules with empty IDs, it creates rules that cannot be addressed by other CRUD operations or referenced in violation reports.
