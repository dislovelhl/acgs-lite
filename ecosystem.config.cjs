// ACGS-2 PM2 Ecosystem Configuration
// Constitutional Hash: cdd01ef066bc6cf2
//
// Usage:
//   pm2 start ecosystem.config.cjs          # Start all services
//   pm2 start ecosystem.config.cjs --only agent-bus-8000  # Start single service
//   pm2 stop all / pm2 restart all
//   pm2 logs / pm2 monit / pm2 status
//
// Service groups:
//   Core:        agent-bus-8000, api-gateway-8080
//   Analytics:   analytics-api-8082
//   Monetization: x402-api-8402, eu-ai-act-8403
//   AI Inference: mistral-8090 (OpenAI-compat LLM), impact-scorer (Candle DistilBERT via acgs_lite_rust)

const path = require("path");
const PROJECT_ROOT = __dirname;
const PYTHONPATH = [PROJECT_ROOT, path.join(PROJECT_ROOT, "src")].join(":");

module.exports = {
  apps: [
    // =========================================================================
    // PYTHON BACKEND SERVICES
    // =========================================================================

    // Enhanced Agent Bus — Core messaging, MACI enforcement, constitutional validation
    {
      name: "agent-bus-8000",
      script: "start.cjs",
      interpreter: "node",
      cwd: path.join(PROJECT_ROOT, "scripts/pm2"),
      instances: 1,
      exec_mode: "fork",
      args: "agent-bus",
      env: {
        PM2_SERVICE: "agent-bus",
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        REDIS_URL: process.env.REDIS_URL || "redis://localhost:6379/0",
        OPA_URL: "http://localhost:8181",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        MACI_STRICT_MODE: "true",
        LOG_LEVEL: "INFO",
      },
      env_production: {
        PM2_SERVICE: "agent-bus",
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        PM2_UVICORN_WORKERS: "2",
        OPA_URL: "http://localhost:8181",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        MACI_STRICT_MODE: "true",
        LOG_LEVEL: "INFO",
      },
    },

    // API Gateway — Unified ingress, auth, rate limiting
    {
      name: "api-gateway-8080",
      script: "start.cjs",
      interpreter: "node",
      cwd: path.join(PROJECT_ROOT, "scripts/pm2"),
      instances: 1,
      exec_mode: "fork",
      args: "api-gateway",
      env: {
        PM2_SERVICE: "api-gateway",
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        AGENT_BUS_URL: "http://localhost:8000",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
        JWT_SECRET: process.env.JWT_SECRET,
        CORS_ORIGINS: '["http://localhost:8080","http://127.0.0.1:8080"]',
      },
      env_production: {
        PM2_SERVICE: "api-gateway",
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        PM2_UVICORN_WORKERS: "2",
        AGENT_BUS_URL: "http://localhost:8000",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
      },
    },

    // Architecture Fitness Report Service — Weekly governance fitness reports
    {
      name: "arch-fitness-8085",
      script: "src/core/services/arch_fitness/start.py",
      interpreter: ".venv/bin/python",
      cwd: PROJECT_ROOT,
      instances: 1,
      exec_mode: "fork",
      env: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        ARCH_FITNESS_PORT: "8085",
        ARCH_FITNESS_CONFIG: "config/arch-fitness.yaml",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        PROMETHEUS_URL: process.env.PROMETHEUS_URL || "http://localhost:9090",
        EAB_URL: process.env.EAB_URL || "http://localhost:8000",
        LOG_LEVEL: "INFO",
      },
      env_production: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        ARCH_FITNESS_PORT: "8085",
        ARCH_FITNESS_CONFIG: "config/arch-fitness.yaml",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
      },
    },

    // x402 Governance API — Micropayment-gated governance scoring
    {
      name: "x402-api-8402",
      script: ".venv/bin/python",
      args: "-m agent_earn serve --port 8402 --no-payment --wallet dev-wallet-placeholder",
      cwd: PROJECT_ROOT,
      instances: 1,
      exec_mode: "fork",
      env: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
      },
      env_production: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
      },
    },

    // EU AI Act Assessment Tool — Self-service compliance web tool
    {
      name: "eu-ai-act-8403",
      script: ".venv/bin/python",
      args: "-m eu_ai_act_tool.app",
      cwd: PROJECT_ROOT,
      instances: 1,
      exec_mode: "fork",
      env: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
      },
      env_production: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
      },
    },

    // mistral.rs — Self-hosted LLM serving (OpenAI-compatible API)
    // Constitutional reasoning, policy generation, governance Q&A
    // Port 8090 — replace/augment OpenAI API calls in constitutional reasoning
    // Requires: cargo install mistralrs-server --features gguf
    //           + model download (see services/mistral/start.sh)
    {
      name: "mistral-8090",
      script: "services/mistral/start.sh",
      interpreter: "bash",
      cwd: PROJECT_ROOT,
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      restart_delay: 5000,
      env: {
        MISTRAL_PORT: "8090",
        MISTRAL_DEVICE: process.env.MISTRAL_DEVICE || "cpu",
        MISTRALRS_BIN: process.env.MISTRALRS_BIN || "",
      },
      env_production: {
        MISTRAL_PORT: "8090",
        MISTRAL_DEVICE: process.env.MISTRAL_DEVICE || "cuda",
        MISTRALRS_BIN: process.env.MISTRALRS_BIN || "",
      },
    },

    // Analytics API — Governance analytics, insights, anomaly detection
    {
      name: "analytics-api-8082",
      script: "start.cjs",
      interpreter: "node",
      cwd: path.join(PROJECT_ROOT, "scripts/pm2"),
      instances: 1,
      exec_mode: "fork",
      args: "analytics-api",
      env: {
        PM2_SERVICE: "analytics-api",
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        REDIS_URL: process.env.REDIS_URL || "redis://localhost:6379/0",
        KAFKA_BOOTSTRAP: process.env.KAFKA_BOOTSTRAP || "localhost:19092",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
        TENANT_ID: "acgs-dev",
      },
      env_production: {
        PM2_SERVICE: "analytics-api",
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        PM2_UVICORN_WORKERS: "2",
        KAFKA_BOOTSTRAP: "localhost:19092",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: "INFO",
      },
    },
  ],
};
