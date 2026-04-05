---
title: HIPAA-compliant system description passes compliance check
description: Submit a system description with proper safeguards and verify it is marked compliant
criticality: critical
scenario: standard
flow: clinicalguard-clinical-validation
category: happy-path
priority: Critical
---

# CG-004: HIPAA-compliant system description passes compliance check

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
             "text": "check_hipaa_compliance: This agent processes synthetic patient data, maintains an audit log, encrypts data at rest and in transit, and limits access to authorized personnel only."
           }
         ]
       }
     }
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify `result.status` is `"completed"`
4. Verify `result.result.compliant` is `true`
5. Verify `result.result` contains `items_checked` as an integer
6. Verify `result.result` contains `checklist` as an array
7. Verify `result.result` contains `constitutional_hash` equal to `"608508a9bd224290"`

## Expected Result

A system description that includes encryption, audit logging, access controls, and synthetic data is marked as HIPAA compliant.

## Bug Description

If a properly safeguarded system is marked non-compliant, the HIPAA checker is producing false negatives, undermining confidence in compliance assessments.
