---
title: Action text longer than 10000 characters returns HTTP 400
description: Send a ClinicalGuard validation with action text exceeding 10000 characters and verify rejection
criticality: high
scenario: standard
flow: clinicalguard-clinical-validation
category: validation
priority: High
---

# CG-009: Action text longer than 10000 characters returns HTTP 400

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running
- If `CLINICALGUARD_API_KEY` is set, include `X-API-Key: acgs_hci_test_key_dave` header

## Steps

1. Construct a JSON-RPC request where the text field contains `"validate_clinical_action: "` followed by more than 10,000 characters of action text
2. Send the POST request to `/`
3. Verify the response HTTP status is **400**
4. Verify the response body contains an error about text length

## Expected Result

The server rejects action text exceeding 10,000 characters with HTTP 400 to prevent abuse and ensure reasonable processing times.

## Bug Description

If the server accepts extremely long action text, it could lead to excessive LLM token consumption and unacceptable latency.
