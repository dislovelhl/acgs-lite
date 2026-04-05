---
title: ClinicalGuard health check returns rule count and chain validity
description: GET /health on ClinicalGuard returns status ok with 20 rules and valid chain
criticality: critical
scenario: standard
flow: health-checks
category: happy-path
priority: Critical
---

# HC-006: ClinicalGuard health check returns rule count and chain validity

## Setup

- Use skill: `api-health-check`
- ClinicalGuard is running with the Healthcare AI Constitution

## Steps

1. Send a GET request to `/health`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"status": "ok"`
4. Verify the response contains `"rules": 20`
5. Verify the response contains `"chain_valid": true`
6. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

ClinicalGuard is operational with all 20 healthcare rules loaded, a valid audit chain, and the correct constitutional hash.

## Bug Description

If the rule count is not 20 or the hash is wrong, ClinicalGuard is running with an incomplete or incorrect healthcare constitution, putting clinical safety at risk.
