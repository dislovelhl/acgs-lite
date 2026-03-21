import { Shield } from "lucide-react"
import { CONSTITUTIONAL_HASH } from "@/lib/constants"

const LINKS = {
  Product: [
    { href: "/#how-it-works", label: "How it works" },
    { href: "/#differentiators", label: "Why Propriety" },
    { href: "/assessment", label: "Governance assessment" },
    { href: "/pricing", label: "Pricing" },
  ],
  Compliance: [
    { href: "/compliance", label: "GDPR" },
    { href: "/compliance", label: "EU AI Act" },
    { href: "/compliance", label: "NIST RMF" },
    { href: "/compliance", label: "ISO 42001" },
  ],
  Company: [
    { href: "/about", label: "About" },
    { href: "mailto:governance@propriety.ai", label: "Contact" },
    { href: "/privacy", label: "Privacy" },
  ],
}

export function Footer() {
  return (
    <footer className="border-t border-border/30 mt-24">
      <div className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12">
          {/* Brand */}
          <div className="md:col-span-1">
            <a href="/" className="flex items-center gap-2 mb-4">
              <div className="w-6 h-6 rounded bg-governance/20 border border-governance/30 flex items-center justify-center">
                <Shield className="w-3.5 h-3.5 text-governance" />
              </div>
              <span className="font-display font-medium text-[1.05rem] leading-none tracking-tight">
                propriety
              </span>
              <span className="text-xs font-mono text-governance/60 -ml-1">.ai</span>
            </a>
            <p className="text-xs text-muted-foreground leading-relaxed mb-4">
              Constitutional governance for AI agents. Enforce policies before every action.
            </p>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-border/40 bg-card/50">
              <span className="w-1.5 h-1.5 rounded-full bg-governance/60" />
              <span className="font-mono text-[10px] text-muted-foreground/50 tracking-wider">
                {CONSTITUTIONAL_HASH}
              </span>
            </div>
          </div>

          {/* Link columns */}
          {Object.entries(LINKS).map(([group, items]) => (
            <div key={group}>
              <p className="text-xs font-mono uppercase tracking-[0.15em] text-muted-foreground/50 mb-4">
                {group}
              </p>
              <ul className="space-y-2.5">
                {items.map((item) => (
                  <li key={item.label}>
                    <a
                      href={item.href}
                      className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {item.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="mt-12 pt-6 border-t border-border/20 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground/40">
            © {new Date().getFullYear()} Propriety AI. All rights reserved.
          </p>
          <p className="text-xs font-mono text-muted-foreground/30">
            560ns P50 · MACI enforced · audit-trail verified
          </p>
        </div>
      </div>
    </footer>
  )
}
