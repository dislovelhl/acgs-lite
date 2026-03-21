import { useRef } from "react"
import { motion, useInView } from "framer-motion"

type El = "h1" | "h2" | "h3" | "p"

interface WordRevealProps {
  text: string
  el?: El
  className?: string
  delay?: number
}

const wordVariants = {
  hidden: { opacity: 0, y: 16, filter: "blur(4px)" },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: {
      duration: 0.6,
      delay: i * 0.08,
      ease: [0.16, 1, 0.3, 1] as [number, number, number, number],
    },
  }),
}

export function WordReveal({ text, el: El = "h2", className = "", delay = 0 }: WordRevealProps) {
  const ref = useRef<HTMLElement>(null)
  const isInView = useInView(ref as React.RefObject<Element>, {
    once: true,
    margin: "-60px",
  })

  const words = text.split(" ")

  return (
    <El ref={ref as React.RefObject<HTMLHeadingElement>} className={`overflow-visible ${className}`}>
      {words.map((word, i) => (
        <motion.span
          key={`${word}-${i}`}
          custom={i + delay / 0.08}
          initial="hidden"
          animate={isInView ? "visible" : "hidden"}
          variants={wordVariants}
          className="inline-block mr-[0.25em]"
          style={{ willChange: "opacity, transform" }}
        >
          {word}
        </motion.span>
      ))}
    </El>
  )
}
