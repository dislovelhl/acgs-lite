# Check Service Health

## Destination
Health check endpoints across all services

## acgs-lite Governance Server

### Basic Health Check

1. Send a GET request to `/health`
2. Verify the response status is 200
3. Verify the response contains `"status": "ok"` and `"engine": "ready"`

### Engine Stats

1. Send a GET request to `/stats`
2. Verify the response status is 200
3. Verify the response contains `audit_entry_count` (integer) and `audit_chain_valid` (boolean)

## ACGS-2 API Gateway

### Basic Health

1. Send a GET request to `/health`
2. Verify the response status is 200
3. Verify the response contains `"status": "ok"` and `"constitutional_hash": "608508a9bd224290"`

### Liveness Probe

1. Send a GET request to `/health/live`
2. Verify the response status is 200
3. Verify the response contains `"live": true`

### Readiness Probe

1. Send a GET request to `/health/ready`
2. Verify the response status is 200 (or 503 if dependencies are down)
3. Verify the response contains `"ready"` (boolean), `"checks"` (object with database, redis, opa, constitutional_hash), and `"timestamp"` (ISO string)
4. Each check has `status` ("up", "down", or "degraded") and `latency_ms`

### Startup Probe

1. Send a GET request to `/health/startup`
2. Verify the response status is 200
3. Verify the response contains `"ready"` (boolean), `"hash_valid": true`, and `"constitutional_hash": "608508a9bd224290"`

## ClinicalGuard

### Health Check

1. Send a GET request to `/health`
2. Verify the response status is 200
3. Verify the response contains:
   - `"status": "ok"`
   - `"rules"` (integer, should be around 20 for the healthcare constitution)
   - `"audit_entries"` (integer)
   - `"chain_valid"` (boolean)
   - `"constitutional_hash": "608508a9bd224290"`
