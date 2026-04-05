---
title: API Gateway startup probe validates constitutional hash
description: GET /health/startup returns ready status with hash validation
criticality: critical
scenario: standard
flow: health-checks
category: happy-path
priority: Critical
---

# HC-005: API Gateway startup probe validates constitutional hash

## Setup

- Use skill: `api-health-check`
- The ACGS-2 API Gateway is running

## Steps

1. Send a GET request to `/health/startup`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"ready": true`
4. Verify the response contains `"hash_valid": true`
5. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The startup probe confirms the gateway has fully initialized and the constitutional hash is valid, meaning the governance rules are correctly loaded.

## Bug Description

If the startup probe fails or hash_valid is false, the gateway started with an invalid constitution, and all governance decisions would be unreliable.
