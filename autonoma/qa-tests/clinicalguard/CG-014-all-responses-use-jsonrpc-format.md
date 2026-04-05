---
title: All clinical validation responses use JSON-RPC 2.0 format
description: Verify that all successful ClinicalGuard responses follow the JSON-RPC 2.0 specification
criticality: critical
scenario: standard
flow: clinicalguard-clinical-validation
category: state-persistence
priority: Critical
---

# CG-014: All clinical validation responses use JSON-RPC 2.0 format

## Setup

- Use skill: `clinicalguard-validate`
- ClinicalGuard is running
- If `CLINICALGUARD_API_KEY` is set, include `X-API-Key: acgs_hci_test_key_dave` header

## Steps

1. Send a clinical validation request (Warfarin + Aspirin case):
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tasks/send",
     "params": {
       "message": {
         "parts": [{"text": "validate_clinical_action: Patient on Warfarin. Propose Aspirin 325mg daily."}]
       }
     }
   }
   ```
2. Verify the response contains `"jsonrpc": "2.0"`
3. Verify the response contains `"id": 1` matching the request ID
4. Verify the response contains a `result` object (not an `error` object)
5. Send a HIPAA check request with `id: 2`
6. Verify that response also contains `"jsonrpc": "2.0"` and `"id": 2`

## Expected Result

All ClinicalGuard responses strictly follow JSON-RPC 2.0 format with matching request IDs, enabling standard JSON-RPC clients to parse them correctly.

## Bug Description

If responses do not follow JSON-RPC 2.0 format, A2A interoperability is broken, as other agents cannot parse ClinicalGuard's responses using standard JSON-RPC libraries.
