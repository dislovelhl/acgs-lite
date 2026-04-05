---
title: Request body exceeding 64KB returns HTTP 413
description: Send a ClinicalGuard request with a body larger than 64KB and verify the server rejects it
criticality: high
scenario: standard
flow: clinicalguard-clinical-validation
category: validation
priority: High
---

# CG-008: Request body exceeding 64KB returns HTTP 413

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running
- If `CLINICALGUARD_API_KEY` is set, include `X-API-Key: acgs_hci_test_key_dave` header

## Steps

1. Construct a JSON-RPC request body where the text field contains more than 64KB of data (e.g., a 70,000-character string)
2. Send the POST request to `/`
3. Verify the response HTTP status is **413**
4. Verify the response body contains `"Request body too large"`

## Expected Result

The server rejects oversized payloads with HTTP 413 to prevent resource exhaustion attacks.

## Bug Description

If the server accepts arbitrarily large payloads, it is vulnerable to denial-of-service attacks via memory exhaustion.
