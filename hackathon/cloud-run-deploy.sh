#!/usr/bin/env bash
# Constitutional Sentinel — Cloud Run deployment script
#
# Requirements:
#   - gcloud CLI authenticated: gcloud auth login
#   - Docker (for local build test)
#   - GitLab project with webhook capability
#
# Usage:
#   export GCP_PROJECT=my-gcp-project
#   export GITLAB_TOKEN=glpat-...
#   export GITLAB_PROJECT_ID=12345
#   export GITLAB_WEBHOOK_SECRET=my-webhook-secret
#   bash hackathon/cloud-run-deploy.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-acgs-sentinel}"
IMAGE="gcr.io/${GCP_PROJECT}/${SERVICE_NAME}"

GITLAB_TOKEN="${GITLAB_TOKEN:?Set GITLAB_TOKEN}"
GITLAB_PROJECT_ID="${GITLAB_PROJECT_ID:?Set GITLAB_PROJECT_ID}"
GITLAB_WEBHOOK_SECRET="${GITLAB_WEBHOOK_SECRET:-acgs-webhook-$(openssl rand -hex 8)}"

echo "=== Constitutional Sentinel: Cloud Run Deployment ==="
echo "GCP Project:  ${GCP_PROJECT}"
echo "Region:       ${REGION}"
echo "Service:      ${SERVICE_NAME}"
echo "GitLab PID:   ${GITLAB_PROJECT_ID}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Build and push container
# ---------------------------------------------------------------------------
echo "[1/4] Building container..."
cd "$(dirname "$0")/.."   # packages/acgs-lite/
gcloud builds submit \
    --tag "${IMAGE}" \
    --project "${GCP_PROJECT}"

# ---------------------------------------------------------------------------
# Step 2: Deploy to Cloud Run
# ---------------------------------------------------------------------------
echo "[2/4] Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --project "${GCP_PROJECT}" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "GITLAB_TOKEN=${GITLAB_TOKEN}" \
    --set-env-vars "GITLAB_PROJECT_ID=${GITLAB_PROJECT_ID}" \
    --set-env-vars "GITLAB_WEBHOOK_SECRET=${GITLAB_WEBHOOK_SECRET}" \
    --set-env-vars "GCP_PROJECT_ID=${GCP_PROJECT}" \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 60

# ---------------------------------------------------------------------------
# Step 3: Verify health
# ---------------------------------------------------------------------------
echo "[3/4] Verifying deployment..."
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" \
    --project "${GCP_PROJECT}" \
    --format "value(status.url)")

echo "Service URL: ${SERVICE_URL}"

HEALTH=$(curl -sf "${SERVICE_URL}/health" | python3 -m json.tool)
echo "Health check:"
echo "${HEALTH}"

HASH=$(echo "${HEALTH}" | python3 -c "import sys,json; print(json.load(sys.stdin)['constitutional_hash'])")
echo ""
echo "Constitutional hash: ${HASH}"

# ---------------------------------------------------------------------------
# Step 4: Register GitLab webhook
# ---------------------------------------------------------------------------
echo "[4/4] Registering GitLab webhook..."
echo ""
echo "Run this command to register the webhook in your GitLab project:"
echo ""
echo "  curl --request POST \\"
echo "    --header 'PRIVATE-TOKEN: ${GITLAB_TOKEN}' \\"
echo "    --header 'Content-Type: application/json' \\"
echo "    --data '{"
echo "      \"url\": \"${SERVICE_URL}/webhook\","
echo "      \"secret_token\": \"${GITLAB_WEBHOOK_SECRET}\","
echo "      \"merge_requests_events\": true,"
echo "      \"push_events\": false,"
echo "      \"enable_ssl_verification\": true"
echo "    }' \\"
echo "    \"https://gitlab.com/api/v4/projects/${GITLAB_PROJECT_ID}/hooks\""
echo ""
echo "=== Deployment complete ==="
echo ""
echo "Next steps:"
echo "  1. Register the webhook (command above)"
echo "  2. Open a test MR with a violation (e.g. hardcode a password)"
echo "  3. Watch the Constitutional Sentinel block it and post inline comments"
echo ""
echo "  Cloud Run URL:   ${SERVICE_URL}"
echo "  Webhook secret:  ${GITLAB_WEBHOOK_SECRET}"
echo "  Const. hash:     ${HASH}"
