---
title: Unknown JSON-RPC method returns method-not-found error
description: Send a JSON-RPC request with an unsupported method and verify the error response
criticality: high
scenario: standard
flow: clinicalguard-clinical-validation
category: validation
priority: High
---

# CG-011: Unknown JSON-RPC method returns method-not-found error

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running
- If `CLINICALGUARD_API_KEY` is set, include `X-API-Key: acgs_hci_test_key_dave` header

## Steps

1. Send a POST request to `/` with body:
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tasks/get",
     "params": {}
   }
   ```
2. Verify the response HTTP status is **200** (JSON-RPC errors are returned in the response body)
3. Verify the response contains a JSON-RPC error object with `error.code` equal to `-32601`
4. Verify `error.message` contains `"Method not found"`

## Expected Result

The server returns a JSON-RPC error for unsupported methods, following the JSON-RPC 2.0 specification for method-not-found errors.

## Bug Description

If the server returns a generic error or crashes on unknown methods, it does not comply with the JSON-RPC 2.0 specification.
