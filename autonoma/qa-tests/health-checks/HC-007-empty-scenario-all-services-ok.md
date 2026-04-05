---
title: All services return healthy in empty scenario
description: Verify all three services return OK health status in a fresh installation
criticality: high
scenario: empty
flow: health-checks
category: happy-path
priority: High
---

# HC-007: All services return healthy in empty scenario

## Setup

- Use skill: `api-health-check`
- All three services (acgs-lite, API Gateway, ClinicalGuard) are running in a fresh installation state

## Steps

1. Send GET `/health` to acgs-lite
2. Verify the response contains `"status": "ok"`
3. Send GET `/stats` to acgs-lite
4. Verify `"audit_entry_count": 0` and `"audit_chain_valid": true`
5. Send GET `/health` to ClinicalGuard
6. Verify `"status": "ok"` and `"audit_entries": 0` and `"chain_valid": true`
7. Send GET `/health` to the API Gateway
8. Verify `"status": "ok"`

## Expected Result

All services are healthy even in an empty state with no data. Audit counts are zero and chains are valid.

## Bug Description

If any service fails health checks in the empty state, new deployments will be flagged as unhealthy, preventing rollout.
