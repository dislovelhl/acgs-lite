---
title: Empty scenario audit trail query returns empty entries
description: In a fresh ClinicalGuard installation with no validations, verify audit trail query returns empty results
criticality: high
scenario: empty
flow: clinicalguard-clinical-validation
category: happy-path
priority: High
---

# CG-015: Empty scenario audit trail query returns empty entries

## Setup

- Use skill: `clinicalguard-audit-query`
- ClinicalGuard is running with no prior clinical validations performed

## Steps

1. Send a POST request to `/` with body:
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tasks/send",
     "params": {
       "message": {
         "parts": [
           {
             "text": "query_audit_trail: recent 10"
           }
         ]
       }
     }
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify `result.result.entries` is an empty array
4. Verify `result.result.chain_valid` is `true` (empty chain is valid)

## Expected Result

The audit trail query handles the empty state gracefully, returning an empty entries array and valid chain status.

## Bug Description

If the audit query errors on an empty trail, the zero-state handling is broken, causing errors for new ClinicalGuard deployments.
