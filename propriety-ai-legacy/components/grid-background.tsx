import { useRef } from "react"
import { motion, useScroll, useTransform } from "framer-motion"

interface GridBackgroundProps {
  className?: string
}

export function GridBackground({ className = "" }: GridBackgroundProps) {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  })
  const y = useTransform(scrollYProgress, [0, 1], ["0%", "15%"])

  return (
    <div ref={ref} className={`absolute inset-0 overflow-hidden ${className}`}>
      <motion.div className="absolute inset-0" style={{ y }}>
        <svg
          className="absolute inset-0 w-full h-full"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <pattern
              id="grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(255,255,255,0.07)"
                strokeWidth="0.5"
              />
            </pattern>
            <radialGradient
              id="grid-mask-radial"
              cx="50%"
              cy="50%"
              r="50%"
            >
              <stop offset="0%" stopColor="white" />
              <stop offset="100%" stopColor="black" />
            </radialGradient>
            <linearGradient
              id="grid-mask-linear"
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="0%" stopColor="white" />
              <stop offset="70%" stopColor="white" />
              <stop offset="100%" stopColor="black" />
            </linearGradient>
            <mask id="grid-mask">
              <rect
                width="100%"
                height="100%"
                fill="url(#grid-mask-radial)"
                style={{ maskType: "luminance" }}
              />
            </mask>
          </defs>
          <rect
            width="100%"
            height="100%"
            fill="url(#grid)"
            mask="url(#grid-mask)"
          />
        </svg>
      </motion.div>
    </div>
  )
}
