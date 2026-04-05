---
title: Unknown skill name returns error with available skills list
description: Send a request with an unrecognized skill prefix and verify the response includes available skills
criticality: high
scenario: standard
flow: clinicalguard-clinical-validation
category: validation
priority: High
---

# CG-012: Unknown skill name returns error with available skills list

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running
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
             "text": "unknown_skill: test input"
           }
         ]
       }
     }
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify `result.result` contains `"error": "Unknown skill"`
4. Verify `result.result` contains `"available_skills"` as a list including `"validate_clinical_action"`, `"check_hipaa_compliance"`, `"query_audit_trail"`

## Expected Result

The agent returns a helpful error message listing the available skills when an unknown skill is requested.

## Bug Description

If unknown skills cause crashes or return unhelpful errors, the API discoverability is poor and integrators cannot debug routing issues.
