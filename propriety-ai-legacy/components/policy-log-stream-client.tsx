import { lazy, Suspense } from "react"

const LazyPolicyLogStream = lazy(() =>
  import("./policy-log-stream").then((m) => ({ default: m.PolicyLogStream })),
)

export function PolicyLogStream() {
  return (
    <Suspense
      fallback={
        <div className="h-72 rounded-xl bg-card/40 border border-border/30 animate-pulse" />
      }
    >
      <LazyPolicyLogStream />
    </Suspense>
  )
}
