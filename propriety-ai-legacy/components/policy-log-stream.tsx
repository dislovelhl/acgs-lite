import { useState, useEffect, useRef } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { CONSTITUTIONAL_HASH } from "@/lib/constants"

type LogLevel = "INIT" | "PASS" | "WARN" | "ERROR" | "INFO"

interface LogEntry {
  id: number
  timestamp: string
  level: LogLevel
  message: string
}

const LOG_TEMPLATES: Array<{ level: LogLevel; message: string }> = [
  { level: "INIT", message: `constitutional_hash=${CONSTITUTIONAL_HASH} loaded` },
  { level: "PASS", message: "agent cx-91 → transfer_funds [$240] — 0.31ms" },
  { level: "PASS", message: "agent cx-93 → read_patient_record — 0.28ms" },
  { level: "WARN", message: "agent cx-94 proximity GDPR Art.22 risk=0.71" },
  { level: "PASS", message: "agent cx-95 → generate_report — 0.19ms" },
  { level: "WARN", message: "agent cx-96 proximity NIST RMF score=0.68" },
  { level: "PASS", message: "agent cx-97 → approve_loan [$12k] — 0.44ms" },
  { level: "ERROR", message: "agent cx-98 → bulk_export BLOCKED EU AI Act Art.10" },
  { level: "PASS", message: "agent cx-91 → send_notification — 0.22ms" },
  { level: "INFO", message: "audit trail block #4821 anchored" },
]

const LEVEL_CLASSES: Record<LogLevel, string> = {
  INIT: "text-muted-foreground/40",
  INFO: "text-muted-foreground/40",
  PASS: "text-governance",
  WARN: "text-amber",
  ERROR: "text-destructive",
}

function makeTime(): string {
  const d = new Date()
  return [
    d.getHours().toString().padStart(2, "0"),
    d.getMinutes().toString().padStart(2, "0"),
    d.getSeconds().toString().padStart(2, "0"),
  ].join(":")
}

interface PolicyLogStreamProps {
  maxVisible?: number
  intervalMs?: number
  className?: string
}

export function PolicyLogStream({
  maxVisible = 7,
  intervalMs = 1200,
  className = "",
}: PolicyLogStreamProps) {
  const [entries, setEntries] = useState<LogEntry[]>([
    { id: 0, timestamp: makeTime(), level: "INIT", message: LOG_TEMPLATES[0].message },
  ])
  const templateIdxRef = useRef(1)

  useEffect(() => {
    const timer = setInterval(() => {
      const idx = templateIdxRef.current
      const template = LOG_TEMPLATES[idx % LOG_TEMPLATES.length]
      setEntries((prev) => [
        ...prev.slice(-(maxVisible - 1)),
        { id: Date.now(), timestamp: makeTime(), level: template.level, message: template.message },
      ])
      templateIdxRef.current = idx + 1
    }, intervalMs)
    return () => clearInterval(timer)
  }, [maxVisible, intervalMs])

  return (
    <div
      className={`rounded-xl border border-border/40 bg-black/40 backdrop-blur-sm overflow-hidden ${className}`}
    >
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/30">
        <span className="w-2.5 h-2.5 rounded-full bg-governance animate-pulse" />
        <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground/40 uppercase">
          // live policy evaluation
        </span>
      </div>

      <div
        className="relative px-4 py-3 space-y-1.5"
        style={{
          maskImage: "linear-gradient(to bottom, transparent 0%, black 18%)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 18%)",
        }}
      >
        <AnimatePresence initial={false}>
          {entries.map((entry) => (
            <motion.div
              key={entry.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex gap-3 font-mono text-[11px] leading-relaxed"
            >
              <span className="text-muted-foreground/25 flex-shrink-0 tabular-nums">
                {entry.timestamp}
              </span>
              <span className={`flex-shrink-0 font-semibold w-[38px] ${LEVEL_CLASSES[entry.level]}`}>
                {entry.level}
              </span>
              <span className="text-muted-foreground/70 overflow-hidden text-ellipsis whitespace-nowrap">
                {entry.message}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
