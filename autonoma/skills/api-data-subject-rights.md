# Exercise GDPR/CCPA Data Subject Rights

## Destination
The ACGS-2 API Gateway endpoints under `/api/v1/data-subject`

## Prerequisites

- The ACGS-2 API Gateway is running
- Authentication is required (all endpoints require `get_current_user`)
- GDPR erasure service must be available for erasure endpoints

## Steps

### Data Subject Access Request (GDPR Art. 15)

1. Send a POST request to `/api/v1/data-subject/access` with:
   ```
   {
     "data_subject_id": "user-12345",
     "categories": ["personal_identifiers", "contact_info"],
     "format": "json"
   }
   ```
2. Verify the response status is 200
3. Verify the response contains:
   - `request_id` (UUID string)
   - `data_subject_id` matching the input
   - `data_categories` (array of strings)
   - `data_count` (integer)
   - `processing_purposes` (array describing why data is processed)
   - `recipients` (array of data recipients)
   - `retention_period` (string describing how long data is kept)
   - `automated_decision_making` (boolean)
   - `constitutional_hash` (should be "608508a9bd224290")

### Request Data Erasure (GDPR Art. 17)

1. Send a POST to `/api/v1/data-subject/erasure` with:
   ```
   {
     "data_subject_id": "user-12345",
     "scope": "all_data",
     "reason": "User requested account deletion"
   }
   ```
2. Verify the response status is 200
3. Verify the response contains `request_id`, `status`, `deadline` (30-day GDPR deadline)

### Check Erasure Status

1. Send GET `/api/v1/data-subject/erasure/{request_id}` using the request_id from above
2. Verify the response contains `status`, `systems_processed`, `total_records_erased`

### Process Erasure

1. Send POST `/api/v1/data-subject/erasure/{request_id}/process?identity_verified=true`
2. Verify the response shows completion status

### Get Erasure Certificate

1. After processing, send GET `/api/v1/data-subject/erasure/{request_id}/certificate`
2. Verify the response contains `certificate_id`, `gdpr_article_17_compliant`, `certificate_hash`

### Classify Data for PII

1. Send POST `/api/v1/data-subject/classify` with:
   ```
   {
     "data": {
       "name": "John Doe",
       "email": "john@example.com",
       "ssn": "123-45-6789"
     }
   }
   ```
2. Verify the response contains `tier`, `pii_categories`, `overall_confidence`, `requires_encryption`

### Error Cases

- Erasure endpoints return 503 if GDPR erasure service is unavailable
- PII classification returns 503 if PII detector is unavailable
- Non-existent erasure request returns 404
