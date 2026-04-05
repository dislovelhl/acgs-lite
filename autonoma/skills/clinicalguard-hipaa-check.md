# Run HIPAA Compliance Check via ClinicalGuard

## Destination
The ClinicalGuard A2A endpoint `POST /` with the `check_hipaa_compliance` skill

## Prerequisites

- ClinicalGuard is running (default: `http://localhost:8080`)
- If `CLINICALGUARD_API_KEY` is set, include the `X-API-Key` header

## Steps

### Submit a HIPAA Compliance Check

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
             "text": "check_hipaa_compliance: This agent processes synthetic patient data, maintains an audit log, encrypts data at rest and in transit, and limits access to authorized personnel only."
           }
         ]
       }
     }
   }
   ```
2. Verify the response status is 200
3. Verify the JSON-RPC response has `result.status` equal to "completed"
4. Verify `result.result` contains:
   - `compliant` (boolean)
   - `items_checked` (integer, count of checklist items evaluated)
   - `checklist` (array of objects, each with status and description)
   - `constitutional_hash` (should be "608508a9bd224290")

### Test with Non-Compliant Description

1. Submit a description that lacks key HIPAA safeguards (e.g., "This agent processes real patient records with no encryption and shares data freely")
2. Verify the result shows `compliant: false`
3. Verify the checklist items show which specific safeguards are missing

### Keyword-Based Routing

The skill can also be triggered by keyword detection:
- Text containing "hipaa", "compliance", "phi", or "privacy" will automatically route to this skill even without the `check_hipaa_compliance:` prefix
