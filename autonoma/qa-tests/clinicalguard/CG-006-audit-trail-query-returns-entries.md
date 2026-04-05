---
title: ClinicalGuard audit trail query returns recent entries
description: Use the query_audit_trail skill to retrieve recent audit entries and verify chain integrity
criticality: critical
scenario: standard
flow: clinicalguard-clinical-validation
category: happy-path
priority: Critical
---

# CG-006: ClinicalGuard audit trail query returns recent entries

## Setup

- Use skill: `clinicalguard-audit-query`
- ClinicalGuard is running with at least one prior clinical validation performed
- If `CLINICALGUARD_API_KEY` is set, include `X-API-Key: acgs_hci_test_key_dave` header

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
3. Verify `result.status` is `"completed"`
4. Verify `result.result.entries` is an array
5. Verify `result.result.chain_valid` is a boolean
6. Verify `result.result.total` is an integer

## Expected Result

The audit trail query returns recent entries with chain integrity status. Each entry contains audit information about past clinical validations.

## Bug Description

If the audit trail query fails or returns no structure, ClinicalGuard's audit capabilities are broken, preventing healthcare compliance officers from reviewing past decisions.
