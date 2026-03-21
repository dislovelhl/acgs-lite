import { useRef } from "react"
import { motion, useInView } from "framer-motion"

type MarginValue = `${number}${"px" | "%"}`
type Margin =
  | MarginValue
  | `${MarginValue} ${MarginValue}`
  | `${MarginValue} ${MarginValue} ${MarginValue}`
  | `${MarginValue} ${MarginValue} ${MarginValue} ${MarginValue}`

interface AnimateInProps {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
  delay?: number
  direction?: "up" | "left"
  offset?: number
  margin?: Margin
  duration?: number
}

export function AnimateIn({
  children,
  className,
  style,
  delay = 0,
  direction = "up",
  offset = 20,
  margin = "-40px",
  duration = 0.5,
}: AnimateInProps) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref as React.RefObject<Element>, { once: true, margin })
  const axis = direction === "up" ? "y" : "x"

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, [axis]: offset }}
      animate={isInView ? { opacity: 1, [axis]: 0 } : {}}
      transition={{ duration, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
      style={style}
    >
      {children}
    </motion.div>
  )
}
