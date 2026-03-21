import { useState, useEffect } from "react"
import { motion, useScroll } from "framer-motion"
import { Shield, Menu, X } from "lucide-react"

const LINKS = [
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#differentiators", label: "Why Propriety" },
  { href: "/assessment", label: "Assessment" },
  { href: "/pricing", label: "Pricing" },
  { href: "/#contact", label: "Contact" },
]

export function Nav() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const { scrollY } = useScroll()

  useEffect(() => {
    return scrollY.on("change", (v) => setScrolled(v > 20))
  }, [scrollY])

  return (
    <motion.header
      className="fixed top-0 inset-x-0 z-50 transition-all"
      animate={
        scrolled
          ? { backgroundColor: "oklch(0.08 0.005 250 / 0.85)" }
          : { backgroundColor: "oklch(0.08 0.005 250 / 0)" }
      }
      style={{ backdropFilter: scrolled ? "blur(16px)" : "none" }}
    >
      <div
        className="border-b transition-colors"
        style={{ borderColor: scrolled ? "oklch(0.22 0.008 250 / 0.4)" : "transparent" }}
      >
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Logo */}
          <a href="/" className="flex items-center gap-2 group">
            <div className="w-6 h-6 rounded bg-governance/20 border border-governance/30 flex items-center justify-center group-hover:bg-governance/30 transition-colors">
              <Shield className="w-3.5 h-3.5 text-governance" />
            </div>
            <span className="font-display font-medium text-[1.05rem] leading-none tracking-tight">
              propriety
            </span>
            <span className="text-xs font-mono text-governance/60 -ml-1">.ai</span>
          </a>

          {/* Desktop links */}
          <nav className="hidden md:flex items-center gap-8">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                {l.label}
              </a>
            ))}
          </nav>

          {/* CTA + mobile toggle */}
          <div className="flex items-center gap-3">
            <a
              href="/assessment"
              className="hidden md:inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-governance/10 border border-governance/25 text-governance text-sm font-medium hover:bg-governance/15 transition-colors"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-governance animate-pulse" />
              Start assessment
            </a>

            <button
              className="md:hidden p-1.5 text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setOpen((v) => !v)}
              aria-label="Toggle menu"
            >
              {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="md:hidden border-b border-border/40 bg-background/95 backdrop-blur-xl"
        >
          <nav className="max-w-7xl mx-auto px-6 py-4 flex flex-col gap-4">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                {l.label}
              </a>
            ))}
            <a
              href="/assessment"
              onClick={() => setOpen(false)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-governance/10 border border-governance/25 text-governance text-sm font-medium w-fit"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-governance animate-pulse" />
              Start assessment
            </a>
          </nav>
        </motion.div>
      )}
    </motion.header>
  )
}
