// ACGS PM2 Ecosystem Configuration
// Constitutional Hash: cdd01ef066bc6cf2
//
// This file is intentionally limited to services that have checked-in launchable
// entrypoints in the current repository state.

const path = require("path");
const fs = require("fs");

const PROJECT_ROOT = __dirname;
const PYTHON_BIN = process.env.PYTHON_BIN || "python3";
const PYTHONPATH = [
  path.join(PROJECT_ROOT, "packages"),
  PROJECT_ROOT,
  path.join(PROJECT_ROOT, "src"),
].join(":");
const DEV_JWT_PRIVATE_KEY_PATH = path.join(PROJECT_ROOT, "config/dev-jwt/private.pem");
const DEV_JWT_PUBLIC_KEY_PATH = path.join(PROJECT_ROOT, "config/dev-jwt/public.pem");
const DEV_JWT_PRIVATE_KEY = fs.existsSync(DEV_JWT_PRIVATE_KEY_PATH)
  ? fs.readFileSync(DEV_JWT_PRIVATE_KEY_PATH, "utf8")
  : "";
const DEV_JWT_PUBLIC_KEY = fs.existsSync(DEV_JWT_PUBLIC_KEY_PATH)
  ? fs.readFileSync(DEV_JWT_PUBLIC_KEY_PATH, "utf8")
  : "";

module.exports = {
  apps: [
    {
      name: "agent-bus-8000",
      script: "start_agent_bus.py",
      interpreter: PYTHON_BIN,
      cwd: PROJECT_ROOT,
      instances: 1,
      exec_mode: "fork",
      env: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        ACGS_ENV: "development",
        REDIS_URL: process.env.REDIS_URL || "redis://localhost:6379/0",
        OPA_URL: process.env.OPA_URL || "http://localhost:8181",
        DATABASE_URL:
          process.env.DATABASE_URL || "postgresql://postgres:postgres@localhost:5432/postgres",
        JWT_ALGORITHM: process.env.JWT_ALGORITHM || "RS256",
        JWT_PRIVATE_KEY: process.env.JWT_PRIVATE_KEY || DEV_JWT_PRIVATE_KEY,
        JWT_PUBLIC_KEY: process.env.JWT_PUBLIC_KEY || DEV_JWT_PUBLIC_KEY,
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        MACI_STRICT_MODE: process.env.MACI_STRICT_MODE || "true",
        LOG_LEVEL: process.env.LOG_LEVEL || "INFO",
      },
      env_production: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        ACGS_ENV: "production",
        REDIS_URL: process.env.REDIS_URL || "redis://localhost:6379/0",
        OPA_URL: process.env.OPA_URL || "http://localhost:8181",
        DATABASE_URL:
          process.env.DATABASE_URL || "postgresql://postgres:postgres@localhost:5432/postgres",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        MACI_STRICT_MODE: process.env.MACI_STRICT_MODE || "true",
        LOG_LEVEL: process.env.LOG_LEVEL || "INFO",
      },
    },

    {
      name: "api-gateway-8080",
      script: "start_api_gateway.py",
      interpreter: PYTHON_BIN,
      cwd: PROJECT_ROOT,
      instances: 1,
      exec_mode: "fork",
      env: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "development",
        AGENT_BUS_URL: process.env.AGENT_BUS_URL || "http://localhost:8000",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: process.env.LOG_LEVEL || "INFO",
        JWT_SECRET: process.env.JWT_SECRET,
        CSRF_ALLOW_EPHEMERAL_SECRET: process.env.CSRF_ALLOW_EPHEMERAL_SECRET || "true",
        CORS_ORIGINS: '["http://localhost:8080","http://127.0.0.1:8080"]',
      },
      env_production: {
        PYTHONPATH,
        PYTHONUNBUFFERED: "1",
        ENVIRONMENT: "production",
        AGENT_BUS_URL: process.env.AGENT_BUS_URL || "http://localhost:8000",
        CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2", // pragma: allowlist secret
        LOG_LEVEL: process.env.LOG_LEVEL || "INFO",
        JWT_SECRET: process.env.JWT_SECRET,
      },
    },
  ],
};
