#!/bin/bash
# ACGS Cloudflare Workers Deployment Script
# Constitutional Hash: 608508a9bd224290

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🚀 Starting ACGS Cloudflare Workers deployment...${NC}"

# 1. Check for wrangler
if ! command -v wrangler &> /dev/null; then
    echo -e "${RED}❌ wrangler CLI not found. Please install it with 'npm install -g wrangler'.${NC}"
    exit 1
fi

# 2. Login check
echo -e "${BLUE}🔑 Checking Cloudflare authentication...${NC}"
wrangler whoami || { echo -e "${RED}❌ Please run 'wrangler login' first.${NC}"; exit 1; }

# 3. Create KV Namespace (if it doesn't exist)
echo -e "${BLUE}📦 Checking KV namespace...${NC}"
KV_OUTPUT=$(wrangler kv:namespace create CONSTITUTIONS 2>&1 || true)
KV_ID=$(echo "$KV_OUTPUT" | grep -oE 'id = "[^"]+"' | cut -d'"' -f2 | head -n 1)

if [ -n "$KV_ID" ]; then
    echo -e "${GREEN}✅ KV Namespace created: $KV_ID${NC}"
    sed -i "s/<your-kv-namespace-id>/$KV_ID/g" wrangler.toml
else
    echo -e "${BLUE}ℹ️  Using existing KV namespace from wrangler.toml.${NC}"
fi

# 4. Create D1 Database (if it doesn't exist)
echo -e "${BLUE}💾 Checking D1 database...${NC}"
D1_OUTPUT=$(wrangler d1 create acgs_audit_log 2>&1 || true)
D1_ID=$(echo "$D1_OUTPUT" | grep -oE 'database_id = "[^"]+"' | cut -d'"' -f2 | head -n 1)

if [ -n "$D1_ID" ]; then
    echo -e "${GREEN}✅ D1 Database created: $D1_ID${NC}"
    sed -i "s/<your-d1-database-id>/$D1_ID/g" wrangler.toml
    
    # Initialize D1 schema
    echo -e "${BLUE}📜 Initializing D1 schema...${NC}"
    # Create a temporary schema file if it doesn't exist
    cat > schema.sql <<EOF
CREATE TABLE IF NOT EXISTS audit_records (
    request_id TEXT PRIMARY KEY,
    phase TEXT NOT NULL,
    valid BOOLEAN NOT NULL,
    violations_json TEXT,
    constitutional_hash TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    model TEXT NOT NULL,
    latency_ms REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON audit_records (tenant_id, timestamp);
EOF
    wrangler d1 execute acgs_audit_log --file=schema.sql --remote
    rm schema.sql
else
    echo -e "${BLUE}ℹ️  Using existing D1 database from wrangler.toml.${NC}"
fi

# 5. Build and Deploy
echo -e "${BLUE}🏗️  Deploying worker...${NC}"
wrangler deploy

echo -e "${GREEN}🎉 ACGS Governance Proxy deployed successfully!${NC}"
echo -e "${BLUE}🔗 Health check: https://acgs-governance-proxy.<your-subdomain>.workers.dev/health${NC}"
echo -e "${BLUE}📋 Next step: Set your ADMIN_SECRET with 'wrangler secret put ADMIN_SECRET'${NC}"
