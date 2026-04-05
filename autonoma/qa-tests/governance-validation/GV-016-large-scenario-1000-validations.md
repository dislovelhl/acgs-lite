---
title: Large scenario handles 1000 validations with 120 rules
description: In the large scenario with 120 rules, verify that all 1000 validation requests return HTTP 200 and engine latency stays within bounds
criticality: high
scenario: large
flow: governance-validation
category: async-patterns
priority: High
---

# GV-016: Large scenario handles 1000 validations with 120 rules

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with 120 constitutional rules loaded (large scenario)

## Steps

1. Send 1000 POST requests to `/validate` (500 benign, 500 violating actions spread across all 120 rules)
2. Verify all 1000 responses have HTTP status **200**
3. Verify approximately 500 responses contain `"valid": true` and approximately 500 contain `"valid": false`
4. Verify every response contains `"constitutional_hash": "608508a9bd224290"`
5. Verify engine latency remains under 10ms per validation at P99

## Expected Result

The governance engine handles high-volume validation with a large rule set without errors or unacceptable latency degradation.

## Bug Description

If the engine fails, times out, or degrades under load with 120 rules, it cannot support production workloads where constitutions may grow large.
