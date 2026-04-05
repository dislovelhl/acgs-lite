---
title: PII classification detects sensitive data categories
description: POST /api/v1/data-subject/classify identifies PII categories and sensitivity tier
criticality: mid
scenario: standard
flow: compliance
category: happy-path
priority: Medium
---

# CO-005: PII classification detects sensitive data categories

## Setup

- Use skill: `api-data-subject-rights`
- The ACGS-2 API Gateway is running with PII detector available

## Steps

1. Send a POST request to `/api/v1/data-subject/classify` with body:
   ```json
   {
     "data": {
       "name": "John Doe",
       "email": "john@example.com",
       "ssn": "123-45-6789"
     }
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response contains `tier` indicating sensitivity level
4. Verify the response contains `pii_categories` as an array
5. Verify the response contains `overall_confidence` as a numeric score
6. Verify the response contains `requires_encryption` as a boolean (should be `true` for SSN data)

## Expected Result

The PII classifier identifies all sensitive data fields and assigns an appropriate sensitivity tier. SSN data triggers the encryption requirement flag.

## Bug Description

If PII is not correctly classified, the platform cannot properly handle sensitive data, leading to potential data protection violations.
