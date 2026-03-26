import { useState, useEffect, useRef, useCallback } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { Radio } from "lucide-react"
import { subscribeGovernanceEvents, type GovernanceEvent } from "@/lib/api-client"

const MAX_VISIBLE = 100

const SEVERITY_COLORS: Record<GovernanceEvent["severity"], string> = {
  CRITICAL: "text-destructive",
  HIGH: "text-warning",
  MEDIUM: "text-amber-400",
  LOW: "text-governance",
}

const SEVERITY_DOT: Record<GovernanceEvent["severity"], string> = {
  CRITICAL: "bg-destructive",
  HIGH: "bg-warning",
  MEDIUM: "bg-amber-400",
  LOW: "bg-governance",
}

type ConnectionStatus = "connected" | "connecting" | "disconnected"

const STATUS_INDICATOR: Record<ConnectionStatus, string> = {
  connected: "bg-governance animate-pulse",
  connecting: "bg-warning animate-pulse",
  disconnected: "bg-destructive",
}

// ── Demo events for offline mode ───────────────────────────────────────────

const DEMO_EVENTS: Omit<GovernanceEvent, "id" | "timestamp">[] = [
  { type: "policy_eval", severity: "LOW", message: "agent cx-91 transfer_funds [$240] PASS 0.31ms", agent: "cx-91" },
  { type: "policy_eval", severity: "LOW", message: "agent cx-93 read_patient_record PASS 0.28ms", agent: "cx-93" },
  { type: "proximity_warn", severity: "MEDIUM", message: "agent cx-94 proximity GDPR Art.22 risk=0.71", agent: "cx-94" },
  { type: "policy_eval", severity: "LOW", message: "agent cx-95 generate_report PASS 0.19ms", agent: "cx-95" },
  { type: "block", severity: "HIGH", message: "agent cx-98 bulk_export BLOCKED EU AI Act Art.10", agent: "cx-98" },
  { type: "policy_eval", severity: "LOW", message: "agent cx-97 approve_loan [$12k] PASS 0.44ms", agent: "cx-97" },
  { type: "amendment", severity: "CRITICAL", message: "constitutional amendment proposed: add Art.15 transparency clause", agent: "system" },
  { type: "audit", severity: "LOW", message: "audit trail block #4821 anchored to chain", agent: "system" },
  { type: "proximity_warn", severity: "MEDIUM", message: "agent cx-96 proximity NIST RMF score=0.68", agent: "cx-96" },
  { type: "policy_eval", severity: "LOW", message: "agent cx-91 send_notification PASS 0.22ms", agent: "cx-91" },
]

function formatTime(iso: string): string {
  const d = new Date(iso)
  return [
    d.getHours().toString().padStart(2, "0"),
    d.getMinutes().toString().padStart(2, "0"),
    d.getSeconds().toString().padStart(2, "0"),
  ].join(":")
}

export function GovernanceFeed() {
  const [events, setEvents] = useState<GovernanceEvent[]>([])
  const [status, setStatus] = useState<ConnectionStatus>("connecting")
  const scrollRef = useRef<HTMLDivElement>(null)
  const demoIdxRef = useRef(0)
  const receivedRealEvent = useRef(false)
  const userScrolledUp = useRef(false)

  const addEvent = useCallback((event: GovernanceEvent) => {
    setEvents((prev) => [...prev.slice(-(MAX_VISIBLE - 1)), event])
  }, [])

  // Track whether user has scrolled up to avoid fighting auto-scroll
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    function handleScroll() {
      if (!el) return
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      userScrolledUp.current = distanceFromBottom > 40
    }

    el.addEventListener("scroll", handleScroll, { passive: true })
    return () => el.removeEventListener("scroll", handleScroll)
  }, [])

  // Auto-scroll to bottom when new events arrive (unless user scrolled up)
  useEffect(() => {
    const el = scrollRef.current
    if (el && !userScrolledUp.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [events])

  useEffect(() => {
    let demoTimer: ReturnType<typeof setInterval> | undefined

    const cleanup = subscribeGovernanceEvents(
      (event) => {
        receivedRealEvent.current = true
        setStatus("connected")
        addEvent(event)
      },
      () => {
        setStatus("disconnected")
      },
    )

    // Start demo mode after a short delay if no real events arrived
    const fallbackTimer = setTimeout(() => {
      if (!receivedRealEvent.current) {
        setStatus("connected")
        demoTimer = setInterval(() => {
          const template = DEMO_EVENTS[demoIdxRef.current % DEMO_EVENTS.length]
          const now = new Date().toISOString()
          addEvent({
            ...template,
            id: `demo-${Date.now()}`,
            timestamp: now,
          })
          demoIdxRef.current += 1
        }, 1400)
      }
    }, 2000)

    return () => {
      cleanup()
      clearTimeout(fallbackTimer)
      if (demoTimer) clearInterval(demoTimer)
    }
  }, [addEvent])

  return (
    <div className="rounded-xl border border-border/40 glass-edge overflow-hidden flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/30">
        <span className={`w-2.5 h-2.5 rounded-full ${STATUS_INDICATOR[status]}`} />
        <Radio className="w-3.5 h-3.5 text-governance" />
        <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground/40 uppercase">
          governance events
        </span>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground/30">
          {events.length} events
        </span>
      </div>

      {/* Event list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-3 space-y-1"
        style={{
          maxHeight: 400,
          maskImage: "linear-gradient(to bottom, transparent 0%, black 4%, black 96%, transparent 100%)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 4%, black 96%, transparent 100%)",
        }}
        role="log"
        aria-label="Governance event feed"
        aria-live="polite"
      >
        <AnimatePresence initial={false}>
          {events.map((event) => (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
              className="flex gap-3 font-mono text-[11px] leading-relaxed py-0.5"
            >
              <span className="text-muted-foreground/25 flex-shrink-0 tabular-nums">
                {formatTime(event.timestamp)}
              </span>
              <span className={`flex-shrink-0 ${SEVERITY_DOT[event.severity]} w-1.5 h-1.5 rounded-full mt-1.5`} />
              <span
                className={`flex-shrink-0 w-[62px] font-semibold ${SEVERITY_COLORS[event.severity]}`}
              >
                {event.severity}
              </span>
              <span className="text-muted-foreground/70 overflow-hidden text-ellipsis whitespace-nowrap">
                {event.message}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>

        {events.length === 0 && (
          <div className="text-center text-muted-foreground/30 font-mono text-[11px] py-8">
            Waiting for events...
          </div>
        )}
      </div>
    </div>
  )
}
