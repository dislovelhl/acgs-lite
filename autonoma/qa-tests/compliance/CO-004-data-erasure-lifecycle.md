---
title: Data erasure request lifecycle completes end-to-end
description: Submit an erasure request, check status, process it, and obtain a certificate
criticality: high
scenario: standard
flow: compliance
category: multi-entity
priority: High
---

# CO-004: Data erasure request lifecycle completes end-to-end

## Setup

- Use skill: `api-data-subject-rights`
- The ACGS-2 API Gateway is running with authentication and GDPR erasure service available

## Steps

1. Send a POST request to `/api/v1/data-subject/erasure` with body:
   ```json
   {
     "data_subject_id": "user-12345",
     "scope": "all_data",
     "reason": "User requested account deletion"
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response contains `request_id` and `status`
4. Record the `request_id`
5. Send a GET request to `/api/v1/data-subject/erasure/{request_id}`
6. Verify the response contains `status`, `systems_processed`, `total_records_erased`
7. Send a POST to `/api/v1/data-subject/erasure/{request_id}/process?identity_verified=true`
8. Verify the response shows completion status
9. Send a GET to `/api/v1/data-subject/erasure/{request_id}/certificate`
10. Verify the response contains `certificate_id`, `gdpr_article_17_compliant`, `certificate_hash`

## Expected Result

The full erasure lifecycle completes: request creation, status check, processing with identity verification, and certificate generation.

## Bug Description

If any step in the erasure lifecycle fails, the platform cannot fulfill GDPR Article 17 right-to-erasure requests, exposing the organization to regulatory penalties.
