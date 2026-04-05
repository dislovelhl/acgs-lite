---
title: Governance vector schema has exactly 7 dimensions
description: GET /api/v1/decisions/governance-vector/schema returns all 7 governance dimensions
criticality: high
scenario: standard
flow: compliance
category: happy-path
priority: High
---

# CO-002: Governance vector schema has exactly 7 dimensions

## Setup

- The ACGS-2 API Gateway is running

## Steps

1. Send a GET request to `/api/v1/decisions/governance-vector/schema`
2. Verify the response HTTP status is **200**
3. Verify the schema contains exactly **7** dimensions
4. Verify the dimensions include: `safety`, `security`, `privacy`, `fairness`, `reliability`, `transparency`, `efficiency`

## Expected Result

The governance vector schema defines all 7 dimensions used for multi-dimensional decision scoring.

## Bug Description

If dimensions are missing or extra, the governance vector model is inconsistent, leading to incomplete or incorrect decision attribution.
