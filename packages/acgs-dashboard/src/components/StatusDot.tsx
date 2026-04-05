import { clsx } from "clsx";

interface StatusDotProps {
  status: "ok" | "warn" | "error" | "unknown";
  label?: string;
}

const DOT_COLORS = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  error: "bg-red-500",
  unknown: "bg-gray-400",
};

export function StatusDot({ status, label }: StatusDotProps) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={clsx("inline-block h-2 w-2 rounded-full", DOT_COLORS[status])}
      />
      {label && <span className="text-sm text-gray-600">{label}</span>}
    </span>
  );
}
