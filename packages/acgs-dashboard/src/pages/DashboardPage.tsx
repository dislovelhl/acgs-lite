import { useCallback } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from "recharts";
import {
  ShieldCheck,
  AlertTriangle,
  Clock,
  Activity,
  CheckCircle2,
  Database,
} from "lucide-react";
import { MetricCard } from "@/components/MetricCard";
import { StatusDot } from "@/components/StatusDot";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useApi } from "@/hooks/useApi";
import { acgsLite } from "@/api/client";
import type { Severity } from "@/lib/types";

const SEVERITY_COLORS: Record<Severity, string> = {
  CRITICAL: "#ef4444",
  HIGH: "#f97316",
  MEDIUM: "#eab308",
  LOW: "#3b82f6",
};

const DEMO_LATENCY_DATA = Array.from({ length: 20 }, (_, i) => ({
  t: `${i}s`,
  latency: 0.3 + Math.random() * 0.5,
}));

export function DashboardPage() {
  const statsFetcher = useCallback(() => acgsLite.stats(), []);
  const healthFetcher = useCallback(() => acgsLite.health(), []);

  const { data: stats, loading: statsLoading, error: statsError } = useApi(statsFetcher, 5000);
  const { data: health, error: healthError } = useApi(healthFetcher, 10000);

  const engineStatus = health?.status === "ok" ? "ok" : health ? "error" : "unknown";
  const isDemo = health?.engine === "demo";

  const recentValidations = stats?.recent_validations ?? [];

  // Derive severity distribution from recent validations
  const severityCounts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  for (const v of recentValidations) {
    for (const viol of v.violations) {
      severityCounts[viol.severity]++;
    }
  }
  const pieData = (Object.entries(severityCounts) as [Severity, number][])
    .filter(([, count]) => count > 0)
    .map(([severity, count]) => ({ name: severity, value: count }));

  // Recent validations as bar chart data
  const recentBars = recentValidations.slice(-10).map((v, i) => ({
    name: `#${i + 1}`,
    rules: v.rules_checked,
    violations: v.violations.length,
  }));

  if (statsLoading && !stats) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-sm text-gray-500">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Governance Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Real-time constitutional governance monitoring
            {isDemo && (
              <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                Demo Mode
              </span>
            )}
          </p>
        </div>
        <StatusDot status={engineStatus} label={`Engine: ${health?.engine ?? "connecting..."}`} />
      </div>

      {(statsError || healthError) && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {statsError ?? healthError}
        </div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Total Validations"
          value={stats?.total_validations?.toLocaleString() ?? "---"}
          icon={<ShieldCheck className="h-5 w-5" />}
          color="blue"
          subtitle="All-time checks"
        />
        <MetricCard
          title="Compliance Rate"
          value={stats ? `${(stats.compliance_rate * 100).toFixed(1)}%` : "---"}
          icon={<CheckCircle2 className="h-5 w-5" />}
          color="green"
          subtitle="Actions passing governance"
        />
        <MetricCard
          title="Avg Latency"
          value={stats ? `${stats.avg_latency_ms.toFixed(2)}ms` : "---"}
          icon={<Clock className="h-5 w-5" />}
          color="purple"
          subtitle="Validation response time"
        />
        <MetricCard
          title="Rules Active"
          value={stats?.rules_count ?? stats?.unique_agents ?? "---"}
          icon={<Database className="h-5 w-5" />}
          color="yellow"
          subtitle={stats?.audit_mode ? `Audit: ${stats.audit_mode}` : "Constitutional rules"}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent validations bar chart */}
        <div className="card lg:col-span-2">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">
            <Activity className="mr-1.5 inline-block h-4 w-4" />
            Recent Validations
          </h3>
          {recentBars.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={recentBars}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="rules" fill="#3b82f6" name="Rules Checked" radius={[4, 4, 0, 0]} />
                <Bar dataKey="violations" fill="#ef4444" name="Violations" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-60 items-center justify-center text-sm text-gray-400">
              No validation data yet. Use the Playground to run validations.
            </div>
          )}
        </div>

        {/* Severity pie chart */}
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">
            <AlertTriangle className="mr-1.5 inline-block h-4 w-4" />
            Violation Severity
          </h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={4}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {pieData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={SEVERITY_COLORS[entry.name as Severity]}
                    />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-60 items-center justify-center text-sm text-gray-400">
              No violations detected
            </div>
          )}
        </div>
      </div>

      {/* Latency trend + Audit health */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">
            <Clock className="mr-1.5 inline-block h-4 w-4" />
            Validation Latency Trend
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={DEMO_LATENCY_DATA}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="t" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit="ms" />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="latency"
                stroke="#8b5cf6"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">Audit Health</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-3">
              <span className="text-sm text-gray-600">Audit Entries</span>
              <span className="text-sm font-semibold">
                {stats?.audit_entry_count?.toLocaleString() ?? "---"}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-3">
              <span className="text-sm text-gray-600">Chain Integrity</span>
              <span>
                {stats?.audit_chain_valid ? (
                  <span className="badge-pass">Valid</span>
                ) : stats ? (
                  <SeverityBadge severity="CRITICAL" />
                ) : (
                  <span className="text-sm text-gray-400">---</span>
                )}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-3">
              <span className="text-sm text-gray-600">Constitutional Hash</span>
              <code className="text-xs font-mono text-gray-500">
                {stats?.constitutional_hash ?? "608508a9bd224290"}
              </code>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-3">
              <span className="text-sm text-gray-600">Audit Mode</span>
              <span className="text-sm font-semibold capitalize">
                {stats?.audit_mode ?? "---"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent validation table */}
      {recentValidations.length > 0 && (
        <div className="card overflow-hidden">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">Recent Validation Requests</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Agent</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Rules</th>
                  <th className="px-4 py-3">Violations</th>
                  <th className="px-4 py-3">Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentValidations.slice(-8).reverse().map((v) => (
                  <tr key={v.request_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      {v.valid ? (
                        <span className="badge-pass">PASS</span>
                      ) : (
                        <SeverityBadge
                          severity={v.violations[0]?.severity ?? "HIGH"}
                        />
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{v.agent_id}</td>
                    <td className="max-w-xs truncate px-4 py-3">{v.action}</td>
                    <td className="px-4 py-3">{v.rules_checked}</td>
                    <td className="px-4 py-3">{v.violations.length}</td>
                    <td className="px-4 py-3">{v.latency_ms.toFixed(2)}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
