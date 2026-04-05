---
title: Agent card returns ClinicalGuard identity and 3 skills
description: GET /.well-known/agent.json returns the agent card with name, skills, and capabilities
criticality: high
scenario: standard
flow: clinicalguard-clinical-validation
category: happy-path
priority: High
---

# CG-013: Agent card returns ClinicalGuard identity and 3 skills

## Setup

- ClinicalGuard is running

## Steps

1. Send a GET request to `/.well-known/agent.json`
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"name": "ClinicalGuard"`
4. Verify the `skills` array has exactly **3** elements
5. Verify the skills include `validate_clinical_action`, `check_hipaa_compliance`, and `query_audit_trail`

## Expected Result

The agent card provides the standard A2A discovery information with the agent's identity and available skills.

## Bug Description

If the agent card is missing or has the wrong skill count, A2A agent discovery is broken, preventing other agents from knowing ClinicalGuard's capabilities.
