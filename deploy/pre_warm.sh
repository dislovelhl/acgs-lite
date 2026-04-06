#!/usr/bin/env bash
# Pre-warm ClinicalGuard endpoint before demo recording.
# Run this 30 seconds before starting OBS.
# Usage: ./deploy/pre_warm.sh [url]

set -eo pipefail

URL="${1:-https://clinicalguard.fly.dev}"

echo "Pre-warming ClinicalGuard at $URL..."

# Health check first
HEALTHY=false
for i in 1 2 3 4 5; do
    HEALTH=$(curl -sf "$URL/health" 2>/dev/null || true)
    if [ -n "$HEALTH" ]; then
        echo "✓ Health check OK: $HEALTH"
        HEALTHY=true
        break
    fi
    echo "  Attempt $i/5 — waiting for cold start..."
    sleep 5
done

if [ "$HEALTHY" = false ]; then
    echo "✗ Health check failed after 5 attempts. Service is not responding."
    exit 1
fi

# Send a warm-up validation request
echo ""
echo "Sending warm-up request (primes LLM connection)..."
HTTP_CODE=$(curl -sf -o /tmp/warmup_response.json -w "%{http_code}" -X POST "$URL/" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${CLINICALGUARD_API_KEY:-}" \
    -d '{
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "id": "warmup",
        "params": {
            "id": "warmup-task",
            "message": {
                "parts": [{"type": "text", "text": "validate_clinical_action: Warm-up request for SYNTH-000."}]
            }
        }
    }' 2>/dev/null) || HTTP_CODE="000"

if [ "$HTTP_CODE" -ge 200 ] 2>/dev/null && [ "$HTTP_CODE" -lt 300 ] 2>/dev/null; then
    python3 -m json.tool /tmp/warmup_response.json 2>/dev/null | head -5 || true
    echo ""
    echo "✓ ClinicalGuard is warm. Start recording now."
else
    echo "✗ Warm-up request failed (HTTP $HTTP_CODE)."
    [ -f /tmp/warmup_response.json ] && cat /tmp/warmup_response.json 2>/dev/null
    exit 1
fi
