workspace "ACGS" "Advanced Constitutional Governance System — constitutional governance infrastructure for AI agents." {

    model {
        // People
        aiDeveloper = person "AI Developer" "Integrates governance into AI agents via SDK or API."
        complianceOfficer = person "Compliance Officer" "Monitors governance posture and regulatory alignment."
        platformAdmin = person "Platform Admin" "Manages constitutional rules, SSO, and system configuration."

        // Primary system
        acgs = softwareSystem "ACGS Platform" "Constitutional governance infrastructure providing real-time validation, MACI separation of powers, and compliance enforcement for AI agents." {

            // --- Edge Layer ---
            governanceProxy = container "Governance Proxy" "Edge-level request/response governance validation with WASM validator. Intercepts LLM API calls and attaches governance proof headers." "Cloudflare Worker / TypeScript" "Edge"

            // --- Gateway Layer ---
            apiGateway = container "API Gateway" "Unified ingress with JWT auth, rate limiting (Redis-backed), SSO (OIDC/SAML), PQC enforcement, autonomy tier control, and API versioning." "FastAPI / Python" "Gateway" {
                ssoRouter = component "SSO Router" "OIDC and SAML authentication flows." "FastAPI Router"
                complianceRouter = component "Compliance Router" "EU AI Act self-assessment and regulatory mapping." "FastAPI Router"
                decisionsRouter = component "Decisions Router" "Governance decision explanation and audit trail." "FastAPI Router"
                dataSubjectRouter = component "Data Subject Router" "GDPR/CCPA data subject rights endpoints." "FastAPI Router"
                rateLimiter = component "Rate Limiter" "Redis-backed sliding window rate limiting." "Middleware"
                proxyRouter = component "Proxy Router" "Catch-all reverse proxy to Agent Bus." "FastAPI Router"
            }

            // --- Core Services ---
            agentBus = container "Enhanced Agent Bus" "Core messaging platform with 80+ subsystems: message routing, batch processing, constitutional validation, MACI enforcement, and multi-agent orchestration." "FastAPI / Python" {
                messageProcessor = component "Message Processor" "Core message routing and processing pipeline." "Python"
                batchProcessor = component "Batch Processor" "Batch message processing with governance middleware." "Python"
                maciEnforcer = component "MACI Enforcer" "Proposer/Validator/Executor separation of powers enforcement." "Python / Middleware"
                opaClient = component "OPA Client" "Policy evaluation against Open Policy Agent." "Python"
                circuitBreaker = component "Circuit Breaker" "Fault tolerance for messaging subsystem." "Python"
                workflowExecutor = component "Workflow Executor" "Durable saga-based workflow persistence and execution." "Python"
                deliberationLayer = component "Deliberation Layer" "Multi-agent consensus and conflict resolution." "Python"
                policyCopilot = component "Policy Copilot" "AI-assisted policy suggestion and review." "Python"
            }

            governanceEngine = container "ACGS-Lite Engine" "Constitutional validation engine with Python + optional Rust/PyO3 backend (560ns P50). Core API: Constitution.from_yaml() + GovernedAgent()." "Python / Rust (PyO3)"

            mcpServer = container "MCP Server" "Model Context Protocol server exposing governance tools (validate_action, get_constitution, get_audit_log, governance_stats) to Claude, VS Code, Cursor." "Python"

            // --- Supporting Services ---
            analyticsApi = container "Analytics API" "Governance analytics, anomaly detection, and reporting." "FastAPI / Python"
            archFitness = container "Architecture Fitness" "Weekly governance fitness reports derived from Prometheus metrics." "FastAPI / Python"
            x402Service = container "x402 Governance" "Micropayment-gated governance scoring service." "FastAPI / Python"
            euAiActTool = container "EU AI Act Tool" "Self-service EU AI Act compliance risk classification." "FastAPI / Python"
            mistralLlm = container "Mistral LLM" "Self-hosted OpenAI-compatible inference server." "mistral.rs / Rust"

            // --- Data Stores ---
            postgres = container "PostgreSQL" "Workflow persistence, audit logs, governance state." "PostgreSQL 15" "Database"
            redis = container "Redis" "Rate limiting, session cache, governance state cache." "Redis 7" "Database"
        }

        // External systems
        opa = softwareSystem "Open Policy Agent" "Policy decision engine for rule evaluation." "External"
        kafka = softwareSystem "Apache Kafka" "Event streaming for analytics pipeline." "External"
        prometheus = softwareSystem "Prometheus" "Metrics collection and monitoring." "External"
        llmProviders = softwareSystem "LLM Providers" "OpenAI, Anthropic, and other LLM APIs." "External"
        cloudflareKv = softwareSystem "Cloudflare KV" "Edge key-value store for constitution configs." "External"
        cloudflareD1 = softwareSystem "Cloudflare D1" "Edge SQLite database for audit logs." "External"

        // --- Relationships: People -> System ---
        aiDeveloper -> acgs "Integrates governance into AI agents via"
        complianceOfficer -> acgs "Monitors compliance posture using"
        platformAdmin -> acgs "Manages constitutional rules and configuration via"

        // --- Relationships: People -> Containers ---
        aiDeveloper -> mcpServer "Validates actions via MCP tools" "MCP Protocol"
        aiDeveloper -> governanceProxy "Routes LLM calls through" "HTTPS"
        complianceOfficer -> apiGateway "Reviews compliance dashboards" "HTTPS"
        platformAdmin -> apiGateway "Configures SSO, autonomy tiers, constitutional rules" "HTTPS"

        // --- Relationships: Edge -> Gateway ---
        governanceProxy -> apiGateway "Proxies validated requests to" "HTTPS"

        // --- Relationships: Gateway -> Services ---
        apiGateway -> agentBus "Proxies governance/messaging requests to" "REST/JSON"
        apiGateway -> redis "Rate limiting and session lookup" "Redis Protocol"

        // --- Relationships: Agent Bus internals ---
        agentBus -> governanceEngine "Validates messages against constitution" "Python API"
        agentBus -> opa "Evaluates policies against" "REST/JSON"
        agentBus -> postgres "Persists workflows and audit logs" "asyncpg"
        agentBus -> redis "Caches governance state" "Redis Protocol"
        agentBus -> kafka "Publishes governance events to" "Kafka Protocol"

        // --- Relationships: Governance Engine ---
        governanceEngine -> mcpServer "Exposes validation tools via" "MCP Protocol"

        // --- Relationships: Edge -> External ---
        governanceProxy -> llmProviders "Proxies validated requests to upstream" "HTTPS"
        governanceProxy -> cloudflareKv "Reads constitution configs from" "KV API"
        governanceProxy -> cloudflareD1 "Writes audit logs to" "D1 API"

        // --- Relationships: Supporting Services ---
        analyticsApi -> kafka "Consumes governance events from" "Kafka Protocol"
        analyticsApi -> postgres "Queries governance data from" "asyncpg"
        archFitness -> prometheus "Pulls governance metrics from" "PromQL"
        x402Service -> governanceEngine "Scores governance via" "Python API"
        euAiActTool -> governanceEngine "Classifies risk via" "Python API"
        mistralLlm -> governanceProxy "Served behind governance proxy" "HTTPS"

        // --- Deployment ---
        deploymentEnvironment "Production" {
            deploymentNode "Cloudflare Edge" "Global edge network" "Cloudflare Workers" {
                containerInstance governanceProxy
                infrastructureNode "KV Namespace" "Constitution config storage" "Cloudflare KV"
                infrastructureNode "D1 Database" "Audit log persistence" "Cloudflare D1"
            }
            deploymentNode "Application Server" "PM2-managed services" "Linux / PM2" {
                deploymentNode "Gateway Process" "Port 8080" "Uvicorn" {
                    containerInstance apiGateway
                }
                deploymentNode "Agent Bus Process" "Port 8000" "Uvicorn" {
                    containerInstance agentBus
                }
                deploymentNode "Supporting Services" "Ports 8082-8403" "Uvicorn" {
                    containerInstance analyticsApi
                    containerInstance archFitness
                    containerInstance x402Service
                    containerInstance euAiActTool
                }
                deploymentNode "LLM Server" "Port 8090" "mistral.rs" {
                    containerInstance mistralLlm
                }
                containerInstance governanceEngine
                containerInstance mcpServer
            }
            deploymentNode "Data Layer" "Managed infrastructure" "" {
                deploymentNode "PostgreSQL Server" "Port 5432" "PostgreSQL 15" {
                    containerInstance postgres
                }
                deploymentNode "Redis Server" "Port 6379" "Redis 7" {
                    containerInstance redis
                }
            }
        }
    }

    views {
        // Level 1: System Context
        systemContext acgs "SystemContext" "System Context - ACGS and its external dependencies" {
            include *
            autoLayout
        }

        // Level 2: Container
        container acgs "Containers" "Container diagram - internal services and data stores" {
            include *
            autoLayout
        }

        // Level 3: Component - API Gateway
        component apiGateway "GatewayComponents" "API Gateway internal components" {
            include *
            autoLayout
        }

        // Level 3: Component - Agent Bus
        component agentBus "AgentBusComponents" "Enhanced Agent Bus internal components" {
            include *
            autoLayout
        }

        // Deployment
        deployment acgs "Production" "ProductionDeployment" "Production deployment topology" {
            include *
            autoLayout
        }

        // Dynamic: Governance validation flow
        dynamic acgs "GovernanceFlow" "Request validation flow through the governance stack" {
            aiDeveloper -> governanceProxy "Sends LLM API request"
            governanceProxy -> cloudflareKv "Loads constitution config"
            governanceProxy -> apiGateway "Forwards validated request"
            apiGateway -> agentBus "Routes to governance endpoint"
            agentBus -> governanceEngine "Validates against constitution"
            agentBus -> opa "Evaluates policy rules"
            agentBus -> postgres "Persists audit record"
            governanceProxy -> llmProviders "Proxies to upstream LLM"
            governanceProxy -> cloudflareD1 "Logs audit trail"
            autoLayout
        }

        styles {
            element "Person" {
                shape Person
                background #08427B
                color #ffffff
            }
            element "Software System" {
                background #1168BD
                color #ffffff
            }
            element "Container" {
                background #438DD5
                color #ffffff
            }
            element "Component" {
                background #85BBF0
                color #000000
            }
            element "Database" {
                shape Cylinder
            }
            element "Edge" {
                background #F5A623
                color #000000
            }
            element "Gateway" {
                background #2D8CFF
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
        }
    }

}
