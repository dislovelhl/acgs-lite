/**
 * ACGS API client — connects to acgs-lite server and API gateway.
 *
 * In dev mode, Vite proxy forwards /validate, /health, /stats to acgs-lite (port 8100)
 * and /api/* to the gateway (port 8000).
 *
 * When the backend is unreachable, methods fall back to demo data so the
 * dashboard remains usable for exploration and testing.
 */

import type {
  HealthResponse,
  Rule,
  StatsResponse,
  ValidationResult,
  GovernanceState,
  StabilityMetrics,
} from "@/lib/types";

const ACGS_LITE_BASE = import.meta.env.VITE_ACGS_LITE_URL ?? "";
const GATEWAY_BASE = import.meta.env.VITE_GATEWAY_URL ?? "";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

/** Wrap a fetcher so network errors resolve to a fallback instead of throwing. */
function withFallback<T>(fetcher: () => Promise<T>, fallback: T): () => Promise<T> {
  return () => fetcher().catch(() => fallback);
}

// ---------------------------------------------------------------------------
// Demo data — used when the acgs-lite backend is not running
// ---------------------------------------------------------------------------

const DEMO_RULES: Rule[] = [
  {
    id: "safety-harmful-content",
    text: "Block content that promotes violence, self-harm, or illegal activities",
    severity: "CRITICAL",
    keywords: ["violence", "self-harm", "illegal", "harm", "weapon"],
    patterns: [],
    category: "safety",
    subcategory: "content-safety",
    depends_on: [],
    enabled: true,
    workflow_action: "block",
    hardcoded: true,
    tags: ["content-safety", "critical"],
    priority: 100,
    condition: {},
    deprecated: false,
    replaced_by: "",
    valid_from: "",
    valid_until: "",
    metadata: {},
  },
  {
    id: "privacy-pii-detection",
    text: "Warn when output contains personal identifiable information patterns",
    severity: "HIGH",
    keywords: ["SSN", "social security", "credit card", "passport"],
    patterns: ["\\b\\d{3}-\\d{2}-\\d{4}\\b", "\\b\\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}\\b"],
    category: "privacy",
    subcategory: "pii",
    depends_on: [],
    enabled: true,
    workflow_action: "escalate",
    hardcoded: false,
    tags: ["pii", "privacy", "compliance"],
    priority: 90,
    condition: {},
    deprecated: false,
    replaced_by: "",
    valid_from: "",
    valid_until: "",
    metadata: {},
  },
  {
    id: "fairness-bias-detection",
    text: "Flag outputs containing demographic stereotypes or biased generalizations",
    severity: "MEDIUM",
    keywords: ["stereotype", "discrimination", "bias"],
    patterns: [],
    category: "fairness",
    subcategory: "bias",
    depends_on: [],
    enabled: true,
    workflow_action: "warn",
    hardcoded: false,
    tags: ["bias", "fairness", "dei"],
    priority: 70,
    condition: {},
    deprecated: false,
    replaced_by: "",
    valid_from: "",
    valid_until: "",
    metadata: {},
  },
  {
    id: "transparency-explanation",
    text: "Require AI-generated content to be clearly labeled and explained",
    severity: "MEDIUM",
    keywords: ["generated", "AI-produced", "automated"],
    patterns: [],
    category: "transparency",
    subcategory: "labeling",
    depends_on: [],
    enabled: true,
    workflow_action: "warn",
    hardcoded: false,
    tags: ["transparency", "labeling"],
    priority: 60,
    condition: {},
    deprecated: false,
    replaced_by: "",
    valid_from: "",
    valid_until: "",
    metadata: {},
  },
  {
    id: "security-prompt-injection",
    text: "Detect and block prompt injection attempts in user input",
    severity: "CRITICAL",
    keywords: ["ignore previous", "disregard instructions", "system prompt"],
    patterns: ["ignore\\s+(all\\s+)?previous", "you\\s+are\\s+now"],
    category: "security",
    subcategory: "prompt-injection",
    depends_on: [],
    enabled: true,
    workflow_action: "block",
    hardcoded: true,
    tags: ["security", "injection", "critical"],
    priority: 95,
    condition: {},
    deprecated: false,
    replaced_by: "",
    valid_from: "",
    valid_until: "",
    metadata: {},
  },
  {
    id: "compliance-medical-advice",
    text: "Block unauthorized medical diagnosis or prescription recommendations",
    severity: "HIGH",
    keywords: ["prescribe", "diagnose", "medication", "treatment plan"],
    patterns: [],
    category: "compliance",
    subcategory: "medical",
    depends_on: ["safety-harmful-content"],
    enabled: true,
    workflow_action: "block",
    hardcoded: false,
    tags: ["medical", "compliance", "regulated"],
    priority: 85,
    condition: {},
    deprecated: false,
    replaced_by: "",
    valid_from: "",
    valid_until: "",
    metadata: {},
  },
];

function makeDemoValidation(i: number): ValidationResult {
  const actions = [
    "Generate a summary of the quarterly report",
    "Send email notification to team members",
    "Export user data including SSN 123-45-6789",
    "Create automated response for customer inquiry",
    "Deploy model update to production environment",
    "Prescribe medication for patient condition",
    "Analyze market trends for Q3 forecast",
    "Generate harmful content that promotes violence",
  ];
  const valid = i % 3 !== 0;
  return {
    valid,
    constitutional_hash: "608508a9bd224290",
    violations: valid
      ? []
      : [
          {
            rule_id: DEMO_RULES[i % DEMO_RULES.length].id,
            rule_text: DEMO_RULES[i % DEMO_RULES.length].text,
            severity: DEMO_RULES[i % DEMO_RULES.length].severity,
            matched_content: actions[i % actions.length].slice(0, 50),
            category: DEMO_RULES[i % DEMO_RULES.length].category,
          },
        ],
    rules_checked: DEMO_RULES.length,
    latency_ms: 0.15 + Math.random() * 0.4,
    request_id: `demo-${Date.now()}-${i}`,
    timestamp: new Date(Date.now() - i * 60_000).toISOString(),
    action: actions[i % actions.length],
    agent_id: ["agent-alpha", "agent-beta", "agent-gamma", "dashboard-user"][i % 4],
  };
}

const DEMO_STATS: StatsResponse = {
  total_validations: 1247,
  compliance_rate: 0.934,
  avg_latency_ms: 0.28,
  unique_agents: 4,
  recent_validations: Array.from({ length: 12 }, (_, i) => makeDemoValidation(i)),
  audit_entry_count: 1247,
  audit_chain_valid: true,
};

const DEMO_HEALTH: HealthResponse = { status: "ok", engine: "demo" };

const DEMO_GOVERNANCE_STATE: GovernanceState = {
  state_id: "demo-state",
  rules: DEMO_RULES,
  version: "1.0.0",
  name: "Demo Constitution",
  description: "Demonstration governance rules for the dashboard",
  metadata: {},
};

// ---------------------------------------------------------------------------
// acgs-lite endpoints (with demo fallback)
// ---------------------------------------------------------------------------

export const acgsLite = {
  health: withFallback(
    () => fetchJson<HealthResponse>(`${ACGS_LITE_BASE}/health`),
    DEMO_HEALTH,
  ),

  stats: withFallback(
    () => fetchJson<StatsResponse>(`${ACGS_LITE_BASE}/stats`),
    DEMO_STATS,
  ),

  validate: (action: string, agentId = "dashboard-user", context: Record<string, unknown> = {}) =>
    fetchJson<ValidationResult>(`${ACGS_LITE_BASE}/validate`, {
      method: "POST",
      body: JSON.stringify({ action, agent_id: agentId, context }),
    }),

  getGovernanceState: withFallback(
    () => fetchJson<GovernanceState>(`${ACGS_LITE_BASE}/governance/state`),
    DEMO_GOVERNANCE_STATE,
  ),

  getRules: withFallback(
    () =>
      fetchJson<GovernanceState>(`${ACGS_LITE_BASE}/governance/state`).then(
        (s) => s.rules,
      ),
    DEMO_RULES,
  ),

  updateGovernanceState: (state: Partial<GovernanceState>) =>
    fetchJson<GovernanceState>(`${ACGS_LITE_BASE}/governance/state`, {
      method: "PUT",
      body: JSON.stringify(state),
    }),
};

/** API gateway endpoints */
export const gateway = {
  stabilityMetrics: () =>
    fetchJson<StabilityMetrics>(
      `${GATEWAY_BASE}/api/v1/governance/stability/metrics`,
    ),

  busHealth: () =>
    fetchJson<{ status: string; version: string }>(
      `${GATEWAY_BASE}/v1/health`,
    ),

  busStats: () =>
    fetchJson<{
      total_validations: number;
      compliance_rate: number;
      avg_latency_ms: number;
      unique_agents: number;
    }>(`${GATEWAY_BASE}/v1/stats`),
};
