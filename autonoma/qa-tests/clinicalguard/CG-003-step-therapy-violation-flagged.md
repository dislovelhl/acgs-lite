---
title: Step therapy violation is flagged for off-protocol prescription
description: Submit a biologic prescription without prior Methotrexate trial and verify step therapy violation is detected
criticality: critical
scenario: standard
flow: clinicalguard-clinical-validation
category: happy-path
priority: Critical
---

# CG-003: Step therapy violation is flagged for off-protocol prescription

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running with the Healthcare AI Constitution
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
             "text": "validate_clinical_action: Patient SYNTH-099. Prescribe Adalimumab without prior Methotrexate trial. No prior treatment documented."
           }
         ]
       }
     }
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify `result.status` is `"completed"`
4. Verify `result.result.decision` is one of `"CONDITIONALLY_APPROVED"` or `"REJECTED"`
5. Verify `result.result.risk_tier` is `"high"`
6. Verify `result.result.audit_id` matches the pattern `HC-\d{8}-[A-F0-9]{6}`

## Expected Result

The ClinicalGuard agent detects the step therapy violation (prescribing a biologic without first trying the standard first-line therapy) and flags it as high risk.

## Bug Description

If the step therapy violation is not detected, the agent fails to enforce treatment protocol ordering, which could lead to unnecessary use of expensive biologics and potential patient harm.
