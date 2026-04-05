# Manage Constitutional Rules (CRUD)

## Destination
The acgs-lite governance server endpoints under `/rules`

## Prerequisites

- The acgs-lite governance server is running (default: `http://localhost:8000`)

## Steps

### List All Rules

1. Send a GET request to `/rules`
2. Verify the response status is 200
3. Verify the response is a JSON array
4. Each rule object contains: `id`, `text`, `severity`, `keywords`, `patterns`, `category`, `subcategory`, `workflow_action`, `enabled`, `tags`, `priority`

### Get a Single Rule

1. Send a GET request to `/rules/{rule_id}` where `{rule_id}` is an existing rule ID
2. Verify the response status is 200
3. Verify the response contains the rule with matching `id`

**Error case:** GET `/rules/nonexistent-id` returns HTTP 404 with detail "Rule 'nonexistent-id' not found"

### Create a Rule

1. Send a POST request to `/rules` with the following JSON body:
   ```
   {
     "id": "TEST-001",
     "text": "No financial advice or investment recommendations",
     "severity": "critical",
     "keywords": ["invest", "buy stocks", "financial advice"],
     "patterns": [],
     "category": "safety",
     "workflow_action": "block"
   }
   ```
2. Verify the response status is 201
3. Verify the response contains the created rule with `id` equal to "TEST-001"
4. Send a GET to `/rules` and verify the new rule appears in the list

**Error cases:**
- POST `/rules` with `{"id": "TEST-001", ...}` again returns HTTP 409 with detail "Rule 'TEST-001' already exists"
- POST `/rules` with `{"id": ""}` returns HTTP 422

### Update a Rule

1. Send a PUT request to `/rules/TEST-001` with:
   ```
   {
     "text": "Updated: No financial advice whatsoever",
     "severity": "high"
   }
   ```
2. Verify the response status is 200
3. Verify the response shows the updated `text` and `severity`

**Error case:** PUT `/rules/nonexistent-id` returns HTTP 404

### Delete a Rule

1. Send a DELETE request to `/rules/TEST-001`
2. Verify the response status is 204
3. Send a GET to `/rules/TEST-001` and verify it returns HTTP 404

**Error case:** DELETE `/rules/nonexistent-id` returns HTTP 404

### Verify Rule Changes Affect Validation

1. Create a rule with `id: "E2E-001"`, `severity: "critical"`, `keywords: ["forbidden-word"]`
2. Send POST `/validate` with `{"action": "this contains forbidden-word"}`
3. Verify the response shows `valid: false` with a violation referencing "E2E-001"
4. Delete the rule "E2E-001"
5. Send the same validation request again
6. Verify the response now shows `valid: true`
