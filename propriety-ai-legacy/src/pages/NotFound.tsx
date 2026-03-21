import { ArrowRight } from "lucide-react"

export default function NotFound() {
  return (
    <main className="min-h-screen crosshatch-bg pt-14 flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground/60 mb-4">
          // 404
        </p>
        <h1 className="font-display font-light text-5xl tracking-[-0.02em] leading-[0.92] mb-4">
          Page not found
        </h1>
        <p className="text-muted-foreground mb-8">This page does not exist or has been moved.</p>
        <a
          href="/"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-governance/10 border border-governance/25 text-governance text-sm font-medium hover:bg-governance/15 transition-colors"
        >
          Back to home
          <ArrowRight className="w-4 h-4" />
        </a>
      </div>
    </main>
  )
}
