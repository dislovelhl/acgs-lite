import { motion } from "framer-motion"
import { GridBackground } from "./grid-background"

interface PageHeroProps {
  label?: string
  title: string
  description?: string
  children?: React.ReactNode
}

export function PageHero({ label, title, description, children }: PageHeroProps) {
  return (
    <section
      className="relative py-24 px-6 overflow-hidden"
      style={{
        boxShadow:
          "0 0 120px 0 oklch(0.65 0.18 160 / 0.07) inset, 0 1px 0 rgba(255,255,255,0.04) inset",
      }}
    >
      <GridBackground />
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 40% at 50% 0%, oklch(0.65 0.18 160 / 0.08), transparent)",
        }}
      />
      <div className="relative z-10 max-w-4xl mx-auto text-center">
        {label && (
          <div className="article-notation justify-center mb-6">{label}</div>
        )}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="font-display font-light text-5xl sm:text-6xl tracking-[-0.02em] leading-[0.92] mb-5"
        >
          {title}
        </motion.h1>
        {description && (
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="text-muted-foreground text-lg leading-relaxed"
          >
            {description}
          </motion.p>
        )}
        {children}
      </div>
    </section>
  )
}
