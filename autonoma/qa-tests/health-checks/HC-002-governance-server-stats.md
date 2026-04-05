---
title: Governance server stats include audit metrics
description: GET /stats returns audit entry count and chain validity
criticality: high
scenario: standard
flow: health-checks
category: happy-path
priority: High
---

# HC-002: Governance server stats include audit metrics

## Setup

- Use skill: `api-health-check`
- The acgs-lite governance server is running with the standard scenario (8 audit entries)

## Steps

1. Send a GET request to `/stats`
2. Verify the response HTTP status is **200**
3. Verify the response contains `"audit_entry_count": 8`
4. Verify the response contains `"audit_chain_valid": true`

## Expected Result

The stats endpoint provides operational metrics including the current audit entry count and chain validity status.

## Bug Description

If stats report incorrect counts or chain validity, operational monitoring dashboards will display misleading information.
