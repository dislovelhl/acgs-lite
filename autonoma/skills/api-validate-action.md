# Validate an Action via the Governance API

## Destination
The acgs-lite governance server endpoint `POST /validate`

## Prerequisites

- The acgs-lite governance server is running (default: `http://localhost:8000`)
- At least one constitutional rule exists in the engine (default constitution has built-in rules)

## Steps

### Submit a Valid Action

1. Send a POST request to `/validate` with the following JSON body:
   ```
   {
     "action": "check the weather forecast",
     "agent_id": "test-agent",
     "context": {}
   }
   ```
2. Verify the response status is 200
3. Verify the response contains `"valid": true`
4. Verify the response contains an empty or minimal `violations` list
5. Verify the response contains an `audit_id` field

### Submit a Violating Action

1. Send a POST request to `/validate` with an action that triggers a constitutional rule (for example, an action containing keywords matching a critical rule)
2. Verify the response status is 200
3. Verify the response contains `"valid": false`
4. Verify the `violations` list contains at least one rule ID
5. Verify the response contains an `audit_id` field

### Error Cases

- Send a POST with `{"action": ""}` -- expect HTTP 422 with detail "'action' must be a non-empty string"
- Send a POST with `{"action": "test", "agent_id": 123}` -- expect HTTP 422 with detail "'agent_id' must be a string"
- Send a POST with `{"action": "test", "context": "not-an-object"}` -- expect HTTP 422 with detail "'context' must be an object"

## Response Format

A successful response looks like:
```
{
  "valid": true,
  "violations": [],
  "audit_id": "...",
  "constitutional_hash": "608508a9bd224290",
  ...
}
```
