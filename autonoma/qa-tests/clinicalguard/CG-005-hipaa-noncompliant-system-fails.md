---
title: Non-compliant system description fails HIPAA check
description: Submit a system description lacking HIPAA safeguards and verify it is marked non-compliant
criticality: critical
scenario: standard
flow: clinicalguard-clinical-validation
category: happy-path
priority: Critical
---

# CG-005: Non-compliant system description fails HIPAA check

## Setup

- Use skill: `clinicalguard-hipaa-check`
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
             "text": "check_hipaa_compliance: This agent processes real patient records with no encryption and shares data freely."
           }
         ]
       }
     }
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify `result.status` is `"completed"`
4. Verify `result.result.compliant` is `false`
5. Verify `result.result.checklist` contains items showing which specific safeguards are missing

## Expected Result

A system description that lacks encryption and shares data freely is correctly identified as HIPAA non-compliant, with specific checklist items indicating the gaps.

## Bug Description

If an insecure system passes the HIPAA check, the compliance validation is broken, giving false assurance about healthcare data protection.
