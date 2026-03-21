interface DotMatrixProps {
  cols?: number
  rows?: number
  gap?: number
  className?: string
}

export function DotMatrix({ cols = 14, rows = 6, gap = 20, className = "" }: DotMatrixProps) {
  return (
    <div
      className={`pointer-events-none select-none ${className}`}
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, ${gap}px)`,
        gridTemplateRows: `repeat(${rows}, ${gap}px)`,
        gap: "0px",
      }}
    >
      {Array.from({ length: cols * rows }).map((_, i) => {
        const col = i % cols
        const row = Math.floor(i / cols)
        const delay = (col * 0.12 + row * 0.08).toFixed(2)
        const duration = col % 2 === 0 ? "3.2s" : "2.8s"
        return (
          <div
            key={i}
            style={{
              width: 3,
              height: 3,
              borderRadius: "50%",
              backgroundColor: "oklch(0.65 0.18 160)",
              animationName: "dot-pulse",
              animationDuration: duration,
              animationDelay: `${delay}s`,
              animationTimingFunction: "steps(1, end)",
              animationIterationCount: "infinite",
              opacity: 0.3,
            }}
          />
        )
      })}
      <style>{`
        @keyframes dot-pulse {
          0%, 100% { opacity: 0.12; }
          50% { opacity: 0.7; }
        }
      `}</style>
    </div>
  )
}
