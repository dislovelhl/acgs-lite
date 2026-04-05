# Query ClinicalGuard Audit Trail

## Destination
The ClinicalGuard A2A endpoint `POST /` with the `query_audit_trail` skill

## Prerequisites

- ClinicalGuard is running (default: `http://localhost:8080`)
- If `CLINICALGUARD_API_KEY` is set, include the `X-API-Key` header
- At least one clinical validation has been performed (to have audit entries)

## Steps

### Query Recent Entries

1. Send a POST request to `/` with:
   ```
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tasks/send",
     "params": {
       "message": {
         "parts": [
           {
             "text": "query_audit_trail: recent 10"
           }
         ]
       }
     }
   }
   ```
2. Verify the response status is 200
3. Verify `result.result` contains:
   - `entries` (array of audit entry objects)
   - `chain_valid` (boolean indicating hash chain integrity)
   - `total` (integer count)

### Query by Audit ID

1. First, perform a clinical validation to get an audit ID (e.g., "HC-20260404-A7F2B3")
2. Send a POST with text: `"query_audit_trail: HC-20260404-A7F2B3"`
3. Verify the response returns the specific audit entry matching that ID
4. Verify the entry contains: `id`, `type`, `agent_id`, `action`, `valid`, `violations`, `constitutional_hash`, `timestamp`

### Keyword-Based Routing

The skill can be triggered by keyword detection:
- Text containing "audit", "trail", or an ID starting with "HC-" will automatically route to this skill even without the `query_audit_trail:` prefix

### Limits

- Maximum query limit is 500 entries
- Default limit (when not specified) is 20 entries
