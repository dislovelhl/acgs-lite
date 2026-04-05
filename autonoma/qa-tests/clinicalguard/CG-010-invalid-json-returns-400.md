---
title: Invalid JSON body returns HTTP 400 parse error
description: Send malformed JSON to ClinicalGuard and verify parse error response
criticality: high
scenario: standard
flow: clinicalguard-clinical-validation
category: validation
priority: High
---

# CG-010: Invalid JSON body returns HTTP 400 parse error

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running
- If `CLINICALGUARD_API_KEY` is set, include `X-API-Key: acgs_hci_test_key_dave` header

## Steps

1. Send a POST request to `/` with body set to `{invalid json`
2. Verify the response HTTP status is **400**
3. Verify the response body contains `"Parse error -- invalid JSON"`

## Expected Result

The server returns a clear parse error when receiving malformed JSON.

## Bug Description

If the server crashes or returns 500 on invalid JSON, the error handling is insufficient and could cause service instability.
