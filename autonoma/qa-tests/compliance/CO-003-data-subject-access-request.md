---
title: GDPR data subject access request returns structured response
description: POST /api/v1/data-subject/access returns request details with processing purposes and retention info
criticality: high
scenario: standard
flow: compliance
category: happy-path
priority: High
---

# CO-003: GDPR data subject access request returns structured response

## Setup

- Use skill: `api-data-subject-rights`
- The ACGS-2 API Gateway is running with authentication

## Steps

1. Send a POST request to `/api/v1/data-subject/access` with body:
   ```json
   {
     "data_subject_id": "user-12345",
     "categories": ["personal_identifiers", "contact_info"],
     "format": "json"
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response contains `request_id` as a UUID string
4. Verify the response contains `data_subject_id` matching `"user-12345"`
5. Verify the response contains `data_categories` as an array
6. Verify the response contains `processing_purposes` as an array
7. Verify the response contains `retention_period` as a string
8. Verify the response contains `constitutional_hash` equal to `"608508a9bd224290"`

## Expected Result

The GDPR Article 15 access request returns a comprehensive data subject profile including processing purposes, retention periods, and automated decision-making flags.

## Bug Description

If the access request fails or returns incomplete data, the platform is non-compliant with GDPR Article 15 right of access requirements.
