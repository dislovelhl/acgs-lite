import { useRef, MouseEvent } from "react"

interface GlareCardProps {
  children: React.ReactNode
  className?: string
}

export function GlareCard({ children, className = "" }: GlareCardProps) {
  const cardRef = useRef<HTMLDivElement>(null)

  function handleMouseMove(e: MouseEvent<HTMLDivElement>) {
    const card = cardRef.current
    if (!card) return
    const rect = card.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    card.style.setProperty("--glare-x", `${x}%`)
    card.style.setProperty("--glare-y", `${y}%`)
  }

  function handleMouseLeave() {
    const card = cardRef.current
    if (!card) return
    card.style.setProperty("--glare-x", "50%")
    card.style.setProperty("--glare-y", "50%")
  }

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={`relative overflow-hidden ${className}`}
      style={
        {
          "--glare-x": "50%",
          "--glare-y": "50%",
        } as React.CSSProperties
      }
    >
      {children}
      <div
        className="pointer-events-none absolute inset-0 rounded-[inherit]"
        style={{
          background:
            "radial-gradient(400px circle at var(--glare-x) var(--glare-y), rgba(255,255,255,0.055), transparent 40%)",
        }}
      />
    </div>
  )
}
