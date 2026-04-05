---
title: Governance server health check returns ok with engine ready
description: GET /health on acgs-lite returns status ok and engine ready
criticality: critical
scenario: standard
flow: health-checks
category: happy-path
priority: Critical
---

# HC-001: Governance server health check returns ok with engine ready

## Setup

- Use skill: `api-health-check`
- The acgs-lite governance server is running

## Steps

1. Send a GET request to `/health`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"status": "ok"`
4. Verify the response contains `"engine": "ready"`

## Expected Result

The governance server health check confirms the service is running and the validation engine is ready to accept requests.

## Bug Description

If the health check fails or the engine is not ready, the governance service is not operational, blocking all validation requests.
