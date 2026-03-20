workspace "ACGS-2" "Advanced Constitutional Governance System — constitutional governance infrastructure for AI agents." {

    !identifiers hierarchical

    model {

        // ── People ──────────────────────────────────────────────────────────────
        aiDeveloper = person "AI Developer" "Integrates acgs-lite into AI applications and agent workflows." "Developer"
        platformOperator = person "Platform Operator" "Deploys and configures the agent bus, manages constitutional amendments, monitors governance health." "Operator"
        endUser = person "End User" "Interacts with governed AI agents through downstream applications." "User"
        securityAuditor = person "Security Auditor" "Reviews audit logs, compliance reports, and constitutional integrity." "Auditor"

        // ── External Systems ─────────────────────────────────────────────────────
        openaiApi = softwareSystem "OpenAI API" "GPT-4 and o-series models for agent reasoning." "External"
        anthropicApi = softwareSystem "Anthropic API" "Claude models via direct API." "External"
        huggingfaceHub = softwareSystem "HuggingFace Hub" "Open-source model hosting and inference." "External"
        workosIdp = softwareSystem "WorkOS" "Enterprise SSO — SAML 2.0 and OIDC identity provider integration." "External"
        opaServer = softwareSystem "Open Policy Agent" "Policy evaluation engine for constitutional rule enforcement." "External"
        prometheusServer = softwareSystem "Prometheus" "Metrics scraping and alerting." "External"
        gitlabInstance = softwareSystem "GitLab" "Source control — webhook integration for MR governance." "External"

        // ── Primary Software System ──────────────────────────────────────────────
        acgs = softwareSystem "ACGS-2" "Constitutional governance infrastructure providing runtime validation, MACI enforcement, compliance frameworks, and adaptive self-evolution for AI agent systems." {

            // ── acgs-lite (embeddable library) ──
            acgsLite = container "acgs-lite" "Standalone governance library. Validates agent actions against constitutional rules at 560ns P50. Embeds in any Python AI application." "Python 3.11+ / PyO3 Rust" "Library" {
                constitutionEngine = component "GovernanceEngine" "Validates actions against a Constitution. Produces ValidationResult with violations and severity." "Python / Rust"
                constitutionModel = component "Constitution" "Rule set with YAML loader, versioning, snapshots, and lazy-loaded policy modules (77+)." "Python"
                maciEnforcer = component "MACIEnforcer" "Enforces Proposer → Validator → Executor separation of powers. Rejects self-validation." "Python"
                auditLog = component "AuditLog" "SHA-256 chained tamper-evident audit trail of governance decisions." "Python"
                complianceFrameworks = component "Compliance Frameworks" "9 regulatory mappings: GDPR, HIPAA, ISO 42001, NIST AI RMF, NYC LL144, OECD AI, SOC 2, EU AI Act, US Fair Lending." "Python"
                integrationsLayer = component "LLM Integrations" "Governance wrappers for OpenAI, Anthropic, LangChain, LiteLLM, LlamaIndex, AutoGen, CrewAI, A2A, MCP." "Python"
                rustValidator = component "Rust Validator (PyO3)" "Native Rust validation engine. Hot-path: 560ns P50. Optional — Python fallback when not built." "Rust / PyO3"
            }

            // ── Enhanced Agent Bus ──
            agentBus = container "Enhanced Agent Bus" "Platform engine providing MACI enforcement, constitutional governance, deliberation, observability, and enterprise features for multi-agent systems." "Python 3.11+ / FastAPI" "Service" {

                busCore = component "EnhancedAgentBus" "Core message router. Receives agent messages, applies batch governance middleware, dispatches to handlers." "Python / asyncio"
                maciMiddleware = component "MACI Middleware" "Enforces role separation at the middleware layer. Proposer cannot be Validator. Rejects self-validation attempts." "Python"
                constitutionalGov = component "Constitutional Governance" "Self-evolving constitutions: amendments, version control, diff engine, rollback, HITL integration, OPA policy sync." "Python"
                adaptiveGov = component "Adaptive Governance" "DTMC-based learner. Adjusts thresholds from governance traces. Recommends amendments." "Python / ONNX"
                deliberationLayer = component "Deliberation Layer" "Event-driven multi-stakeholder voting via Redis pub/sub. ONNX/PyTorch impact scoring. Consensus engine." "Python / Redis"
                agentHealth = component "Agent Health Monitor" "Anomaly detection, autonomous healing (restart/reroute/quarantine), governed recovery via MACI." "Python"
                observability = component "Observability" "OpenTelemetry traces, Prometheus metrics, structlog JSON logging, timeout budgeting, capacity planning." "Python / OTel"
                persistenceEngine = component "Persistence & Saga" "Durable workflow execution with replay, checkpoints, saga compensation. Multi-backend: Redis + PostgreSQL." "Python"
                contextMemory = component "Context Memory" "Mamba-2 hybrid processor for 4M+ token context. Constitutional context cache. Long-term memory." "Python"
                llmAdapters = component "LLM Adapters" "Multi-provider framework: OpenAI, Anthropic, Bedrock, HuggingFace, Azure. Capability matrix, cost optimisation, failover." "Python"
                enterpriseSSO = component "Enterprise SSO" "SAML 2.0/OIDC with MACI role mapping. Tenant-aware sessions. Gap analysis and policy conversion." "Python"
                multiTenancy = component "Multi-Tenancy" "PostgreSQL Row-Level Security, tenant context isolation, quota management, lifecycle management." "Python / PostgreSQL"
                mcpServerComp = component "MCP Server" "Model Context Protocol server exposing governance tools to external AI systems." "Python / MCP"
            }

            // ── API Gateway ──
            apiGateway = container "API Gateway" "Unified auth, rate limiting, MACI tier enforcement, PQC mode, and reverse proxy to agent bus." "Python 3.11+ / FastAPI" "Service" {
                authRoutes = component "Auth Routes" "OIDC, SAML 2.0, WorkOS login/logout/callback handlers." "Python"
                governanceRoutes = component "Governance Routes" "Decision explanation (FR-12), data subject rights (GDPR/CCPA), compliance assessment." "Python"
                autonomyRoutes = component "Autonomy Routes" "Tier management, self-evolution control (pause/resume/stop), bounded experiment gating." "Python"
                pqcRoutes = component "PQC Routes" "Post-quantum cryptography phase 5 activation and status." "Python"
                x402Routes = component "x402 Routes" "Pay-per-call governance via micropayment protocol." "Python"
                proxyRoute = component "Catch-all Proxy" "Reverse proxy forwarding all unmatched requests to agent bus on port 8000." "Python"
                rateLimiter = component "Rate Limiter" "Per-endpoint limits: Auth=10/min, SSO=5/min, Health=6000/min, Default=1000/min. Redis-backed." "Python / Redis"
                autonomyTierMw = component "Autonomy Tier Middleware" "HITL gates based on agent tier assignment. Enforces human-in-the-loop for high-autonomy operations." "Python"
            }

            // ── Analytics API ──
            analyticsApi = container "Analytics API" "Governance analytics and reporting service." "Python / FastAPI" "Service"

            // ── EU AI Act Compliance Tool ──
            euAiActService = container "EU AI Act Service" "EU AI Act compliance tool with 125-item checklist, risk classification, transparency requirements." "Python / FastAPI" "Service"

            // ── x402 Micropayment API ──
            x402Api = container "x402 API" "Micropayment-gated governance access with per-call pricing." "Python / FastAPI" "Service"

            // ── Architecture Fitness ──
            archFitness = container "Architecture Fitness" "Weekly architectural fitness function reports (dependency health, coverage trends, governance metrics)." "Python" "Service"

            // ── Self-hosted LLM ──
            mistralService = container "Mistral LLM" "Self-hosted LLM for governance reasoning (constitutional amendment suggestions, policy copilot)." "Python / Mistral" "Service"

            // ── Infrastructure ──
            postgresDb = container "PostgreSQL" "Primary data store: tier assignments, saga state, multi-tenant data, audit records, migrations." "PostgreSQL 15" "Database"
            redisStore = container "Redis" "Pub/sub for deliberation, rate limiting, caching, circuit breaker state, distributed locks." "Redis 7" "Cache"

        }

        // ── Relationships: People → System ──────────────────────────────────────
        aiDeveloper -> acgs "Integrates acgs-lite, calls governance APIs" "Python SDK / REST"
        platformOperator -> acgs "Configures constitutions, manages tiers, reviews governance" "REST / PM2"
        endUser -> acgs "Actions validated by governed agents" "Indirect"
        securityAuditor -> acgs "Reads audit logs, compliance reports" "REST / Direct"

        // ── Relationships: People → Containers ──────────────────────────────────
        aiDeveloper -> acgs.acgsLite "Embeds in agent code, calls validate()" "Python import"
        platformOperator -> acgs.apiGateway "Manages autonomy tiers, SSO config" "HTTPS"
        platformOperator -> acgs.agentBus "Monitors governance pipeline, amends constitution" "HTTPS / PM2"
        securityAuditor -> acgs.analyticsApi "Queries governance metrics" "HTTPS"

        // ── Relationships: acgs-lite → External ─────────────────────────────────
        acgs.acgsLite -> acgs.agentBus "Publishes messages for governed processing" "HTTP / async"
        acgs.acgsLite.integrationsLayer -> openaiApi "Wraps with governance (GovernedCallable)" "HTTPS"
        acgs.acgsLite.integrationsLayer -> anthropicApi "Wraps with governance (GovernedCallable)" "HTTPS"

        // ── Relationships: API Gateway → Agent Bus ───────────────────────────────
        acgs.apiGateway -> acgs.agentBus "Proxies all agent requests" "HTTP / REST"
        acgs.apiGateway -> acgs.redisStore "Rate limiting, session state" "TCP"
        acgs.apiGateway -> acgs.postgresDb "Tier assignments, audit records" "TCP / async"
        acgs.apiGateway -> workosIdp "SSO callbacks, directory sync" "HTTPS / SAML/OIDC"

        // ── Relationships: Agent Bus → Infrastructure ────────────────────────────
        acgs.agentBus -> acgs.postgresDb "Saga state, tenant data, governance records" "TCP / asyncpg"
        acgs.agentBus -> acgs.redisStore "Deliberation pub/sub, caching, circuit breaker" "TCP"
        acgs.agentBus -> opaServer "Constitutional rule evaluation" "HTTP / Rego"
        acgs.agentBus -> prometheusServer "Exposes /metrics endpoint" "HTTP"
        acgs.agentBus -> acgs.mistralService "Policy copilot, amendment suggestions" "HTTP"
        acgs.agentBus.llmAdapters -> openaiApi "LLM inference with governance wrapping" "HTTPS"
        acgs.agentBus.llmAdapters -> anthropicApi "LLM inference with governance wrapping" "HTTPS"
        acgs.agentBus.llmAdapters -> huggingfaceHub "Open-source model inference" "HTTPS"
        acgs.agentBus.mcpServerComp -> acgs.acgsLite "Exposes governance tools via MCP" "stdio / HTTP"

        // ── Relationships: acgs-lite components ──────────────────────────────────
        acgs.acgsLite.constitutionEngine -> acgs.acgsLite.rustValidator "Delegates hot-path validation (fallback to Python)" "FFI"
        acgs.acgsLite.constitutionEngine -> acgs.acgsLite.constitutionModel "Loads rule set" "Python"
        acgs.acgsLite.maciEnforcer -> acgs.acgsLite.constitutionEngine "Wraps validation with role checks" "Python"
        acgs.acgsLite.integrationsLayer -> acgs.acgsLite.maciEnforcer "Tags LLM calls with MACI role" "Python"
        acgs.acgsLite.integrationsLayer -> acgs.acgsLite.auditLog "Records every governance decision" "Python"
        acgs.acgsLite.complianceFrameworks -> acgs.acgsLite.constitutionModel "Maps regulatory requirements to rules" "Python"

        // ── Relationships: Agent Bus components ──────────────────────────────────
        acgs.agentBus.busCore -> acgs.agentBus.maciMiddleware "Routes messages through governance pipeline" "Python"
        acgs.agentBus.maciMiddleware -> acgs.agentBus.constitutionalGov "Validates against current constitution" "Python"
        acgs.agentBus.constitutionalGov -> acgs.agentBus.deliberationLayer "Escalates contested decisions" "Python / Redis"
        acgs.agentBus.constitutionalGov -> acgs.agentBus.adaptiveGov "Feeds traces for ML threshold adjustment" "Python"
        acgs.agentBus.agentHealth -> acgs.agentBus.busCore "Triggers reroute / quarantine on anomaly" "Python"
        acgs.agentBus.persistenceEngine -> acgs.agentBus.contextMemory "Persists long-horizon context checkpoints" "Python"
        acgs.agentBus.enterpriseSSO -> acgs.agentBus.multiTenancy "Sets tenant context on authenticated session" "Python"

        // ── Additional component relationships for dynamic views ─────────────────
        acgs.agentBus.constitutionalGov -> acgs.agentBus.observability "Records governance decisions as OTel spans" "Python"
        acgs.agentBus.constitutionalGov -> acgs.agentBus.persistenceEngine "Checkpoints governance and saga state" "Python"
        acgs.agentBus.agentHealth -> acgs.agentBus.busCore "Triggers reroute or quarantine on anomaly" "Python"
        acgs.agentBus.adaptiveGov -> acgs.agentBus.constitutionalGov "Proposes threshold and rule amendments" "Python"
        acgs.agentBus.deliberationLayer -> acgs.agentBus.constitutionalGov "Returns consensus decision to governor" "Python"

        // ── acgs-lite → API Gateway (governed apps call gateway first) ──────────
        acgs.acgsLite -> acgs.apiGateway "Submits agent actions for platform-level governance" "HTTPS / REST"

        // ── GitLab webhook ───────────────────────────────────────────────────────
        acgs.acgsLite -> gitlabInstance "Validates MRs on push events" "HTTPS webhook"

        // ── Deployment ───────────────────────────────────────────────────────────
        deploymentEnvironment "Production" {
            deploymentNode "Linux Host" "Physical or VM running PM2 process manager" "Linux / PM2" {
                deploymentNode "PM2 Process Group" "7 managed processes" "PM2" {
                    acgsBusInst = containerInstance acgs.agentBus
                    apiGwInst   = containerInstance acgs.apiGateway
                    analyticsInst = containerInstance acgs.analyticsApi
                    x402Inst    = containerInstance acgs.x402Api
                    euAiInst    = containerInstance acgs.euAiActService
                    fitnessInst = containerInstance acgs.archFitness
                    mistralInst = containerInstance acgs.mistralService
                }
                deploymentNode "Docker Compose" "Containerised infrastructure" "Docker" {
                    deploymentNode "Redis Node" "In-memory data store" "Docker" {
                        redisInst = containerInstance acgs.redisStore
                    }
                    deploymentNode "PostgreSQL Node" "Relational database" "Docker" {
                        pgInst = containerInstance acgs.postgresDb
                    }
                    deploymentNode "OPA Node" "Policy engine" "Docker" {
                        infrastructureNode "Open Policy Agent" "Evaluates Rego constitutional policies" "OPA 0.60+"
                    }
                }
            }
        }
    }

    views {

        // Level 1: System Context
        systemContext acgs "SystemContext" "ACGS-2 in its operational environment — AI developers, operators, auditors, and external services." {
            include *
            autoLayout tb 400 200
        }

        // Level 2: Container — all services
        container acgs "Containers" "Internal structure of ACGS-2: services, libraries, databases, and their interactions." {
            include *
            autoLayout tb 300 150
        }

        // Level 3a: Component — acgs-lite
        component acgs.acgsLite "AcgsLiteComponents" "Internal structure of the acgs-lite governance library." {
            include *
            autoLayout tb 250 150
        }

        // Level 3b: Component — Enhanced Agent Bus
        component acgs.agentBus "AgentBusComponents" "Internal governance pipeline components of the Enhanced Agent Bus." {
            include *
            autoLayout tb 250 150
        }

        // Level 3c: Component — API Gateway
        component acgs.apiGateway "ApiGatewayComponents" "Route handlers and middleware inside the API Gateway." {
            include *
            autoLayout tb 250 150
        }

        // Dynamic: End-to-end governed action (container level)
        dynamic acgs "GovernanceFlow" "End-to-end flow for a governed agent action through ACGS-2 (container level)." {
            acgs.acgsLite -> acgs.apiGateway "POST /api/v1/agent/action"
            acgs.apiGateway -> acgs.agentBus "Proxy with auth + tier context"
            acgs.agentBus -> opaServer "Evaluate Rego constitutional policies"
            acgs.agentBus -> acgs.postgresDb "Persist governance decision record"
            acgs.agentBus -> acgs.redisStore "Update metrics and circuit breaker state"
            autoLayout
        }

        // Dynamic: Agent bus governance pipeline (component level)
        dynamic acgs.agentBus "GovernancePipeline" "Internal pipeline routing within the Enhanced Agent Bus." {
            acgs.agentBus.busCore -> acgs.agentBus.maciMiddleware "Route message through governance middleware"
            acgs.agentBus.maciMiddleware -> acgs.agentBus.constitutionalGov "Validate against current constitution"
            acgs.agentBus.constitutionalGov -> acgs.agentBus.adaptiveGov "Feed decision trace for threshold learning"
            acgs.agentBus.constitutionalGov -> acgs.agentBus.observability "Emit OTel span + Prometheus counter"
            acgs.agentBus.constitutionalGov -> acgs.agentBus.persistenceEngine "Checkpoint saga state"
            acgs.agentBus.agentHealth -> acgs.agentBus.busCore "Trigger reroute or quarantine on detected anomaly"
            autoLayout
        }

        // Dynamic: Constitutional amendment flow (component level)
        dynamic acgs.agentBus "AmendmentFlow" "Bounded self-evolution cycle: propose → deliberate → execute." {
            acgs.agentBus.adaptiveGov -> acgs.agentBus.constitutionalGov "Propose amendment (Proposer role)"
            acgs.agentBus.constitutionalGov -> acgs.agentBus.deliberationLayer "Escalate for multi-stakeholder vote"
            acgs.agentBus.deliberationLayer -> acgs.agentBus.constitutionalGov "Return consensus decision (Validator role)"
            acgs.agentBus.constitutionalGov -> acgs.agentBus.persistenceEngine "Persist amendment record and diff (Executor role)"
            autoLayout
        }

        // Deployment
        deployment acgs "Production" "ProductionDeployment" "Production deployment on a Linux host with PM2 + Docker Compose." {
            include *
            autoLayout tb 300 150
        }

        styles {
            element "Person" {
                shape Person
                background #08427B
                color #ffffff
            }
            element "Developer" {
                background #1168BD
                color #ffffff
            }
            element "Operator" {
                background #0a5c3a
                color #ffffff
            }
            element "Auditor" {
                background #5c340a
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
                background #438DD5
                color #ffffff
            }
            element "Cache" {
                shape Cylinder
                background #e8a000
                color #000000
            }
            element "Library" {
                background #2e7d32
                color #ffffff
            }
            element "Service" {
                background #438DD5
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
            relationship "Relationship" {
                routing Orthogonal
            }
        }
    }
}
