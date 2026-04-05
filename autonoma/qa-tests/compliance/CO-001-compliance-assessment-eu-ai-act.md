---
title: Compliance assessment for EU AI Act returns non-empty result
description: POST /api/v1/compliance/assess with framework eu_ai_act returns a meaningful compliance assessment
criticality: high
scenario: standard
flow: compliance
category: happy-path
priority: High
---

# CO-001: Compliance assessment for EU AI Act returns non-empty result

## Setup

- Use skill: `api-data-subject-rights`
- The ACGS-2 API Gateway is running with the standard scenario

## Steps

1. Send a POST request to `/api/v1/compliance/assess` with body:
   ```json
   {
     "framework": "eu_ai_act"
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response contains a non-empty assessment result
4. Verify the response includes rule-to-framework mappings (e.g., `SAFE-001` maps to `Art.9-RiskMgmt`)

## Expected Result

The compliance module returns a meaningful assessment of the current constitution against the EU AI Act, including rule mappings and coverage gaps.

## Bug Description

If the assessment is empty or fails, compliance officers cannot evaluate EU AI Act readiness, which is critical given the August 2026 deadline.
