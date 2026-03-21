import { useRef, useEffect, useState } from "react"
import { motion, useScroll, useSpring } from "framer-motion"

interface TracingBeamProps {
  children: React.ReactNode
  className?: string
}

export function TracingBeam({ children, className = "" }: TracingBeamProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [svgHeight, setSvgHeight] = useState(0)

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 20%", "end 80%"],
  })

  const pathLength = useSpring(scrollYProgress, {
    stiffness: 400,
    damping: 80,
  })

  useEffect(() => {
    if (ref.current) {
      setSvgHeight(ref.current.offsetHeight)
    }
  }, [])

  return (
    <div ref={ref} className={`relative ${className}`}>
      <div className="absolute left-0 top-3 -translate-x-1/2">
        <svg
          viewBox={`0 0 20 ${svgHeight}`}
          width={20}
          height={svgHeight}
          className="overflow-visible"
        >
          <path
            d={`M 10 0 L 10 ${svgHeight}`}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="1.5"
          />
          <motion.path
            d={`M 10 0 L 10 ${svgHeight}`}
            fill="none"
            stroke="oklch(0.65 0.18 160)"
            strokeWidth="1.5"
            strokeLinecap="round"
            style={{ pathLength }}
          />
          <motion.circle
            cx="10"
            cy={svgHeight}
            r="4"
            fill="oklch(0.65 0.18 160)"
            style={{
              filter: "drop-shadow(0 0 6px oklch(0.65 0.18 160))",
              offsetDistance: pathLength,
            }}
          />
        </svg>
      </div>
      <div className="pl-10">{children}</div>
    </div>
  )
}
