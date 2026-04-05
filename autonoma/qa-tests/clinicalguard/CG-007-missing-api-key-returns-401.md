---
title: Missing API key returns HTTP 401 when authentication is required
description: Send a ClinicalGuard request without X-API-Key header when CLINICALGUARD_API_KEY is set and verify 401 response
criticality: critical
scenario: standard
flow: clinicalguard-clinical-validation
category: validation
priority: Critical
---

# CG-007: Missing API key returns HTTP 401 when authentication is required

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running with `CLINICALGUARD_API_KEY` environment variable set

## Steps

1. Send a POST request to `/` WITHOUT the `X-API-Key` header, with body:
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tasks/send",
     "params": {
       "message": {
         "parts": [
           {
             "text": "validate_clinical_action: Patient on Warfarin."
           }
         ]
       }
     }
   }
   ```
2. Verify the response HTTP status is **401**
3. Verify the response body contains `"Unauthorized -- provide X-API-Key header"`

## Expected Result

The server rejects unauthenticated requests with a 401 status when API key authentication is configured.

## Bug Description

If unauthenticated requests are processed, the healthcare agent lacks access control, allowing any caller to validate clinical actions without authorization.
