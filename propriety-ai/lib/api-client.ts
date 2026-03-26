const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8080"

// ── Types ──────────────────────────────────────────────────────────────────

export interface ComplianceFramework {
  name: string
  score: number
  status: "compliant" | "partial" | "non_compliant"
  passing: number
  total: number
}

export interface GovernanceStatus {
  frameworks: ComplianceFramework[]
  overall_score: number
  last_updated: string
}

export interface AuditEntry {
  id: string
  timestamp: string
  action: string
  actor: string
  result: "PASS" | "FAIL" | "WARN"
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
  hash: string
}

export interface AuditTrailResponse {
  items: AuditEntry[]
  total: number
  page: number
  limit: number
}

export interface ServiceHealth {
  name: string
  status: "healthy" | "degraded" | "down"
  port: number
  uptime: string
}

export interface HealthDashboard {
  services: ServiceHealth[]
  overall: "healthy" | "degraded" | "down"
}

export interface GovernanceEvent {
  id: string
  timestamp: string
  type: string
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
  message: string
  agent?: string
}

// ── Fetch helpers ──────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${response.statusText}`)
  }

  return response.json() as Promise<T>
}

export async function fetchGovernanceStatus(): Promise<GovernanceStatus> {
  return apiFetch<GovernanceStatus>("/api/v1/governance/status")
}

export interface AuditTrailParams {
  page?: number
  limit?: number
  severity?: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | ""
}

export async function fetchAuditTrail(
  params: AuditTrailParams = {},
): Promise<AuditTrailResponse> {
  const search = new URLSearchParams()
  if (params.page) search.set("page", String(params.page))
  if (params.limit) search.set("limit", String(params.limit))
  if (params.severity) search.set("severity", params.severity)

  const query = search.toString()
  return apiFetch<AuditTrailResponse>(
    `/api/v1/audit/trail${query ? `?${query}` : ""}`,
  )
}

export async function fetchHealthDashboard(): Promise<HealthDashboard> {
  return apiFetch<HealthDashboard>("/api/v1/health/dashboard")
}

// ── SSE subscription ───────────────────────────────────────────────────────

export function subscribeGovernanceEvents(
  onEvent: (event: GovernanceEvent) => void,
  onError?: (error: Event) => void,
): () => void {
  const source = new EventSource(`${API_BASE}/api/v1/governance/events`)

  source.onmessage = (msg) => {
    try {
      const parsed = JSON.parse(msg.data) as GovernanceEvent
      onEvent(parsed)
    } catch {
      // Ignore malformed messages
    }
  }

  source.onerror = (err) => {
    onError?.(err)
  }

  return () => source.close()
}
