---
title: API Gateway health check returns ok with constitutional hash
description: GET /health on the API Gateway returns status ok and the canonical constitutional hash
criticality: critical
scenario: standard
flow: health-checks
category: happy-path
priority: Critical
---

# HC-003: API Gateway health check returns ok with constitutional hash

## Setup

- Use skill: `api-health-check`
- The ACGS-2 API Gateway is running

## Steps

1. Send a GET request to `/health`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"status": "ok"`
4. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The API Gateway is operational and reports the correct canonical constitutional hash.

## Bug Description

If the health check fails or the hash is different from `608508a9bd224290`, the gateway is either down or running with a stale constitution.
