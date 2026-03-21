import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts"

interface DataPoint {
  time: string
  p50: number
  p95: number
  p99: number
}

interface Props {
  data: DataPoint[]
  budgetMs: number
  title?: string
}

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString)
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  } catch {
    return isoString
  }
}

function TooltipContent({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-edge rounded-lg px-3 py-2 text-xs space-y-1">
      <div className="font-mono text-[10px] text-muted-foreground/60">
        {label ? formatTime(label) : ""}
      </div>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full flex-shrink-0"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-mono text-foreground">{entry.value.toFixed(3)}ms</span>
        </div>
      ))}
    </div>
  )
}

export function LatencyChart({ data, budgetMs, title }: Props) {
  return (
    <div>
      {title && (
        <div className="font-mono text-[10px] tracking-[0.2em] text-muted-foreground/50 uppercase mb-3">
          {title}
        </div>
      )}
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="gradP50" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="oklch(0.88 0.20 155)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="oklch(0.88 0.20 155)" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradP95" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="oklch(0.78 0.14 75)" stopOpacity={0.2} />
              <stop offset="100%" stopColor="oklch(0.78 0.14 75)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            tickFormatter={formatTime}
            tick={{ fontSize: 9, fill: "oklch(0.70 0.01 250)" }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 9, fill: "oklch(0.70 0.01 250)" }}
            axisLine={false}
            tickLine={false}
            width={40}
            tickFormatter={(v: number) => `${v.toFixed(1)}`}
          />
          <Tooltip content={<TooltipContent />} />
          <ReferenceLine
            y={budgetMs}
            stroke="oklch(0.60 0.20 25)"
            strokeDasharray="4 4"
            strokeOpacity={0.6}
            label={{
              value: `Budget: ${budgetMs}ms`,
              position: "right",
              fontSize: 9,
              fill: "oklch(0.60 0.20 25)",
            }}
          />
          <Area
            type="monotone"
            dataKey="p50"
            name="P50"
            stroke="oklch(0.88 0.20 155)"
            fill="url(#gradP50)"
            strokeWidth={1.5}
            dot={false}
            animationDuration={300}
          />
          <Area
            type="monotone"
            dataKey="p95"
            name="P95"
            stroke="oklch(0.78 0.14 75)"
            fill="url(#gradP95)"
            strokeWidth={1.5}
            dot={false}
            animationDuration={300}
          />
          <Area
            type="monotone"
            dataKey="p99"
            name="P99"
            stroke="oklch(0.60 0.20 25)"
            fill="none"
            strokeWidth={1.5}
            strokeDasharray="4 2"
            dot={false}
            animationDuration={300}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
