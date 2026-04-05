---
title: Security rule SEC-001 detects credential leak pattern
description: Submit an action containing an API key pattern and verify SEC-001 fires with both keyword and regex matching
criticality: critical
scenario: standard
flow: governance-validation
category: happy-path
priority: Critical
---

# GV-007: Security rule SEC-001 detects credential leak pattern

## Setup

- Use skill: `api-validate-action`
- The acgs-lite governance server is running with the standard constitution containing rule `SEC-001` (severity: critical, keywords: ["api_key", "secret", "password", "credential"], patterns: ["(?i)(api[_-]?key|secret|password)\\s*[:=]\\s*\\S+"])

## Steps

1. Send a POST request to `/validate` with body:
   ```json
   {
     "action": "output includes api_key: sk-abc123",
     "agent_id": "leaky-agent",
     "context": {}
   }
   ```
2. Verify the response HTTP status is **200**
3. Verify the response body contains `"valid": false`
4. Verify the `violations` array contains `"SEC-001"`
5. Verify the response contains `"constitutional_hash": "608508a9bd224290"`

## Expected Result

The governance engine detects both the keyword "api_key" and the regex pattern matching `api_key: sk-abc123`, firing rule SEC-001 to block the credential leak.

## Bug Description

If credential leak patterns are not detected, the governance engine fails to prevent secrets from being exposed in agent outputs, creating a critical security vulnerability.
