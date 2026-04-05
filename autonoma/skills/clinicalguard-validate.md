# Validate a Clinical Action via ClinicalGuard

## Destination
The ClinicalGuard A2A endpoint `POST /`

## Prerequisites

- ClinicalGuard is running (default: `http://localhost:8080`)
- If `CLINICALGUARD_API_KEY` is set, include the `X-API-Key` header

## Steps

### Submit a Clinical Validation

1. Send a POST request to `/` with the following JSON body:
   ```
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tasks/send",
     "params": {
       "message": {
         "parts": [
           {
             "text": "validate_clinical_action: Patient SYNTH-042 on Warfarin. Propose Aspirin 325mg daily."
           }
         ]
       }
     }
   }
   ```
2. Verify the response status is 200
3. Verify the response has JSON-RPC structure: `{"jsonrpc": "2.0", "id": 1, "result": {...}}`
4. Verify `result.status` is "completed"
5. Verify `result.result` contains decision fields: `decision` (APPROVED, CONDITIONALLY_APPROVED, or REJECTED), `risk_tier`, `reasoning`, `audit_id`

### Drug Interaction Detection

1. Submit a validation with known drug interaction (e.g., Warfarin + Aspirin)
2. Verify the result mentions drug interaction risks
3. Verify the decision is CONDITIONALLY_APPROVED or REJECTED depending on severity

### Keyword-Based Skill Detection

The agent detects skills from text keywords. Without the "validate_clinical_action:" prefix:
1. Send text containing "prescribe" or "medication" -- routes to validate_clinical_action
2. Send text containing "hipaa" or "compliance" -- routes to check_hipaa_compliance
3. Send text containing "audit" or "trail" -- routes to query_audit_trail

### Error Cases

- Missing API key when required: Send POST without `X-API-Key` header. Expect 401 with `"Unauthorized -- provide X-API-Key header"`
- Body too large: Send a body larger than 64KB. Expect 413 with `"Request body too large"`
- Action text too long: Send text longer than 10,000 characters. Expect 400 with text length error
- Invalid JSON: Send malformed JSON. Expect 400 with `"Parse error -- invalid JSON"`
- Wrong method: Send `"method": "tasks/get"`. Expect a JSON-RPC error with code -32601 and `"Method not found"`
- Non-object body: Send a JSON array instead of object. Expect 400 with `"Request must be a JSON object"`
- Unknown skill: Send text like `"unknown_skill: test"`. Expect a result with `"error": "Unknown skill"` and `"available_skills"` list

### Response Format

A successful response:
```
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "id": "task-xxxxxxxx",
    "status": "completed",
    "result": {
      "decision": "CONDITIONALLY_APPROVED",
      "risk_tier": "high",
      "reasoning": "...",
      "drug_interactions": [...],
      "conditions": [...],
      "audit_id": "HC-20260404-XXXXXX"
    }
  }
}
```
