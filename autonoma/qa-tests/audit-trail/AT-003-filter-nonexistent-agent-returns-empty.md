---
title: Filter by non-existent agent_id returns empty array
description: GET /audit/entries?agent_id=nonexistent-agent returns an empty array
criticality: high
scenario: standard
flow: audit-trail-inspection
category: validation
priority: High
---

# AT-003: Filter by non-existent agent_id returns empty array

## Setup

- Use skill: `api-query-audit`
- The acgs-lite governance server is running with the standard scenario

## Steps

1. Send a GET request to `/audit/entries?agent_id=nonexistent-agent`
2. Verify the response HTTP status is **200**
3. Verify the response is an empty JSON array `[]`

## Expected Result

Filtering by a non-existent agent ID returns an empty array rather than an error, following RESTful conventions for empty result sets.

## Bug Description

If the endpoint returns an error instead of an empty array, API consumers cannot distinguish between "no results" and "server error".
