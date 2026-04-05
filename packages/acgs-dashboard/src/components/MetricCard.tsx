import { clsx } from "clsx";
import type { ReactNode } from "react";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
  color?: "blue" | "green" | "red" | "yellow" | "purple";
}

const COLOR_MAP = {
  blue: "bg-blue-50 text-blue-600",
  green: "bg-emerald-50 text-emerald-600",
  red: "bg-red-50 text-red-600",
  yellow: "bg-amber-50 text-amber-600",
  purple: "bg-purple-50 text-purple-600",
};

export function MetricCard({
  title,
  value,
  subtitle,
  icon,
  color = "blue",
}: MetricCardProps) {
  return (
    <div className="card flex items-start gap-4">
      {icon && (
        <div
          className={clsx(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            COLOR_MAP[color],
          )}
        >
          {icon}
        </div>
      )}
      <div className="min-w-0">
        <p className="text-sm text-gray-500">{title}</p>
        <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
        {subtitle && <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>}
      </div>
    </div>
  );
}
