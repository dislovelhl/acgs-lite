---
title: API Gateway liveness probe returns live
description: GET /health/live returns the liveness status for Kubernetes probes
criticality: high
scenario: standard
flow: health-checks
category: happy-path
priority: High
---

# HC-004: API Gateway liveness probe returns live

## Setup

- Use skill: `api-health-check`
- The ACGS-2 API Gateway is running

## Steps

1. Send a GET request to `/health/live`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"live": true`

## Expected Result

The liveness probe confirms the API Gateway process is alive and responsive.

## Bug Description

If the liveness probe fails, Kubernetes will restart the pod, causing service disruption.
