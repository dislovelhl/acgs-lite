import { useState, useEffect, useCallback } from "react"
import { motion } from "framer-motion"
import { FileText, ChevronLeft, ChevronRight, Filter } from "lucide-react"
import { fetchAuditTrail, type AuditEntry, type AuditTrailResponse } from "@/lib/api-client"

const PAGE_SIZE = 20

const SEVERITY_COLORS: Record<AuditEntry["severity"], string> = {
  CRITICAL: "text-destructive",
  HIGH: "text-warning",
  MEDIUM: "text-amber-400",
  LOW: "text-governance",
}

const RESULT_BADGE: Record<AuditEntry["result"], string> = {
  PASS: "bg-governance/15 text-governance border-governance/25",
  FAIL: "bg-destructive/15 text-destructive border-destructive/25",
  WARN: "bg-warning/15 text-warning border-warning/25",
}

const GRID_COLS = "grid-cols-[80px_1fr_1fr_70px_80px_140px]"

type SeverityFilter = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | ""

const SEVERITY_OPTIONS: Array<{ value: SeverityFilter; label: string }> = [
  { value: "", label: "All severities" },
  { value: "CRITICAL", label: "Critical" },
  { value: "HIGH", label: "High" },
  { value: "MEDIUM", label: "Medium" },
  { value: "LOW", label: "Low" },
]

// ── Fallback data for offline / demo mode ──────────────────────────────────

const FALLBACK_ENTRIES: AuditEntry[] = [
  { id: "a1", timestamp: "2026-03-18T10:14:22Z", action: "policy_eval", actor: "agent-cx-91", result: "PASS", severity: "LOW", hash: "cdd01ef066bc6cf2a1b3" },
  { id: "a2", timestamp: "2026-03-18T10:14:19Z", action: "bulk_export", actor: "agent-cx-98", result: "FAIL", severity: "HIGH", hash: "e4f2a81c9d03bb7e52c1" },
  { id: "a3", timestamp: "2026-03-18T10:14:15Z", action: "policy_eval", actor: "agent-cx-93", result: "PASS", severity: "LOW", hash: "7ba3c92def15aa0184e2" },
  { id: "a4", timestamp: "2026-03-18T10:14:10Z", action: "proximity_check", actor: "agent-cx-94", result: "WARN", severity: "MEDIUM", hash: "3f9e21b04ca8dd6701f5" },
  { id: "a5", timestamp: "2026-03-18T10:13:58Z", action: "amendment_vote", actor: "validator-01", result: "PASS", severity: "CRITICAL", hash: "a12bc3d4e5f6789012ab" },
  { id: "a6", timestamp: "2026-03-18T10:13:45Z", action: "transfer_funds", actor: "agent-cx-97", result: "PASS", severity: "LOW", hash: "9d8c7b6a5f4e3d2c1b0a" },
  { id: "a7", timestamp: "2026-03-18T10:13:30Z", action: "read_record", actor: "agent-cx-95", result: "PASS", severity: "LOW", hash: "1a2b3c4d5e6f7890abcd" },
  { id: "a8", timestamp: "2026-03-18T10:13:12Z", action: "refoundation_proposal", actor: "system", result: "PASS", severity: "CRITICAL", hash: "ff0011223344556677ee" },
]

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function truncateHash(hash: string): string {
  if (hash.length <= 12) return hash
  return `${hash.slice(0, 8)}...${hash.slice(-4)}`
}

export function AuditTrail() {
  const [entries, setEntries] = useState<AuditEntry[]>(FALLBACK_ENTRIES)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(FALLBACK_ENTRIES.length)
  const [severity, setSeverity] = useState<SeverityFilter>("")
  const [loading, setLoading] = useState(false)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const load = useCallback(async (p: number, sev: SeverityFilter) => {
    setLoading(true)
    try {
      const result: AuditTrailResponse = await fetchAuditTrail({
        page: p,
        limit: PAGE_SIZE,
        severity: sev,
      })
      setEntries(result.items)
      setTotal(result.total)
      setPage(result.page)
    } catch {
      // Keep existing data on error
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(page, severity)
  }, [page, severity, load])

  function handlePrev() {
    if (page > 1) setPage((p) => p - 1)
  }

  function handleNext() {
    if (page < totalPages) setPage((p) => p + 1)
  }

  return (
    <div className="rounded-xl border border-border/40 glass-edge overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-border/30">
        <FileText className="w-4 h-4 text-governance" />
        <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground/40 uppercase">
          audit trail
        </span>

        {/* Severity filter */}
        <div className="ml-auto flex items-center gap-2">
          <Filter className="w-3 h-3 text-muted-foreground/40" />
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value as SeverityFilter)
              setPage(1)
            }}
            className="bg-card/60 border border-border/30 rounded-md px-2 py-1 text-[11px] font-mono text-muted-foreground appearance-none cursor-pointer focus:outline-none focus:border-governance/40"
            aria-label="Filter by severity"
          >
            {SEVERITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto" role="table" aria-label="Audit trail entries">
        <div className="min-w-[720px]">
          {/* Table header */}
          <div
            className={`grid ${GRID_COLS} gap-3 px-5 py-2 border-b border-border/20 text-[10px] font-mono text-muted-foreground/40 uppercase tracking-wider`}
            role="row"
          >
            <span role="columnheader">Time</span>
            <span role="columnheader">Action</span>
            <span role="columnheader">Actor</span>
            <span role="columnheader">Result</span>
            <span role="columnheader">Severity</span>
            <span role="columnheader">Hash</span>
          </div>

          {/* Table body */}
          <div className={loading ? "opacity-50 transition-opacity" : "transition-opacity"}>
            {entries.map((entry, i) => (
              <motion.div
                key={entry.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2, delay: i * 0.02 }}
                className={`grid ${GRID_COLS} gap-3 px-5 py-2.5 border-b border-border/10 hover:bg-card/40 transition-colors`}
                role="row"
              >
                <span className="font-mono text-[11px] text-muted-foreground/50 tabular-nums" role="cell">
                  {formatTimestamp(entry.timestamp)}
                </span>
                <span className="text-xs text-foreground/80 truncate" role="cell">
                  {entry.action}
                </span>
                <span className="font-mono text-[11px] text-muted-foreground/60 truncate" role="cell">
                  {entry.actor}
                </span>
                <span role="cell">
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${RESULT_BADGE[entry.result]}`}>
                    {entry.result}
                  </span>
                </span>
                <span className={`font-mono text-[11px] font-semibold ${SEVERITY_COLORS[entry.severity]}`} role="cell">
                  {entry.severity}
                </span>
                <span className="font-mono text-[11px] text-muted-foreground/40" role="cell" title={entry.hash}>
                  {truncateHash(entry.hash)}
                </span>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between px-5 py-3 border-t border-border/30">
        <span className="font-mono text-[10px] text-muted-foreground/40">
          {total} total entries
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrev}
            disabled={page <= 1}
            className="p-1 rounded border border-border/30 text-muted-foreground/50 hover:text-foreground hover:border-border/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <span className="font-mono text-[11px] text-muted-foreground/50 tabular-nums">
            {page} / {totalPages}
          </span>
          <button
            onClick={handleNext}
            disabled={page >= totalPages}
            className="p-1 rounded border border-border/30 text-muted-foreground/50 hover:text-foreground hover:border-border/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            aria-label="Next page"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
