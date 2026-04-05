# Query the Audit Trail

## Destination
The acgs-lite governance server endpoints under `/audit`

## Prerequisites

- The acgs-lite governance server is running (default: `http://localhost:8000`)
- At least one validation has been performed (to have audit entries)

## Steps

### Generate Audit Entries

1. First, submit one or more validation requests to `/validate` so there are entries in the audit log
2. For example: POST `/validate` with `{"action": "safe action", "agent_id": "audit-test-agent"}`

### List Audit Entries

1. Send a GET request to `/audit/entries`
2. Verify the response status is 200
3. Verify the response is a JSON array of audit entries
4. Each entry contains fields like: `id`, `type`, `agent_id`, `action`, `valid`, `violations`, `constitutional_hash`, `timestamp`

### Paginate Audit Entries

1. Send GET `/audit/entries?limit=5&offset=0`
2. Verify the response contains at most 5 entries
3. Send GET `/audit/entries?limit=5&offset=5`
4. Verify the response contains the next batch of entries (no overlap with the first batch)

### Filter by Agent ID

1. Send GET `/audit/entries?agent_id=audit-test-agent`
2. Verify all returned entries have `agent_id` equal to "audit-test-agent"
3. Send GET `/audit/entries?agent_id=nonexistent-agent`
4. Verify the response is an empty array

### Verify Chain Integrity

1. Send a GET request to `/audit/chain`
2. Verify the response status is 200
3. Verify the response contains `"valid": true`
4. Verify the response contains `"entry_count"` as a non-negative integer

### Get Audit Count

1. Send a GET request to `/audit/count`
2. Verify the response status is 200
3. Verify the response contains `"count"` as a non-negative integer
4. Verify the count matches or is greater than the number of entries you created
