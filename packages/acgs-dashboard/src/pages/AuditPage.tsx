import { useCallback, useMemo, useState } from "react";
import {
  ScrollText,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  Download,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useApi } from "@/hooks/useApi";
import { acgsLite } from "@/api/client";
import type { ValidationResult } from "@/lib/types";

export function AuditPage() {
  const statsFetcher = useCallback(() => acgsLite.stats(), []);
  const { data: stats, loading } = useApi(statsFetcher, 5000);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pass" | "fail">("all");

  const validations: ValidationResult[] = stats?.recent_validations ?? [];

  const filtered = useMemo(() => {
    return validations.filter((v) => {
      if (statusFilter === "pass" && !v.valid) return false;
      if (statusFilter === "fail" && v.valid) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          v.agent_id.toLowerCase().includes(q) ||
          v.action.toLowerCase().includes(q) ||
          v.request_id.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [validations, search, statusFilter]);

  // Hourly distribution for chart
  const hourlyData = useMemo(() => {
    const buckets: Record<string, { pass: number; fail: number }> = {};
    for (const v of validations) {
      const hour = v.timestamp?.slice(11, 13) ?? "??";
      const key = `${hour}:00`;
      if (!buckets[key]) buckets[key] = { pass: 0, fail: 0 };
      if (v.valid) buckets[key].pass++;
      else buckets[key].fail++;
    }
    return Object.entries(buckets)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([hour, counts]) => ({ hour, ...counts }));
  }, [validations]);

  const exportCsv = () => {
    const header = "timestamp,agent_id,action,valid,violations,rules_checked,latency_ms,request_id\n";
    const rows = filtered
      .map(
        (v) =>
          `${v.timestamp},${v.agent_id},"${v.action.replace(/"/g, '""')}",${v.valid},${v.violations.length},${v.rules_checked},${v.latency_ms},${v.request_id}`,
      )
      .join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `acgs-audit-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            <ScrollText className="mr-2 inline-block h-6 w-6" />
            Audit Trail
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {validations.length} validation records &middot; Chain integrity:{" "}
            {stats?.audit_chain_valid ? (
              <span className="text-emerald-600">Valid</span>
            ) : (
              <span className="text-red-600">Invalid</span>
            )}
          </p>
        </div>
        <button
          onClick={exportCsv}
          disabled={filtered.length === 0}
          className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-600 transition hover:bg-gray-50 disabled:opacity-50"
        >
          <Download className="h-4 w-4" />
          Export CSV
        </button>
      </div>

      {/* Distribution chart */}
      {hourlyData.length > 0 && (
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">
            Validation Distribution
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="pass" stackId="a" fill="#10b981" name="Pass" />
              <Bar dataKey="fail" stackId="a" fill="#ef4444" name="Fail" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search by agent ID, action, or request ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-400" />
          {(["all", "pass", "fail"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium capitalize transition ${
                statusFilter === s
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-gray-200 text-gray-500 hover:bg-gray-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex h-40 items-center justify-center text-sm text-gray-500">
          Loading audit trail...
        </div>
      ) : (
        <div className="card overflow-hidden !p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Agent</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Rules</th>
                  <th className="px-4 py-3">Violations</th>
                  <th className="px-4 py-3">Latency</th>
                  <th className="px-4 py-3">Request ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-12 text-center text-gray-400"
                    >
                      No matching audit records
                    </td>
                  </tr>
                ) : (
                  filtered.map((v) => (
                    <tr key={v.request_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        {v.valid ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500" />
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-gray-500">
                        {v.timestamp}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{v.agent_id}</td>
                      <td className="max-w-xs truncate px-4 py-3">{v.action}</td>
                      <td className="px-4 py-3">{v.rules_checked}</td>
                      <td className="px-4 py-3">
                        {v.violations.length > 0 ? (
                          <span className="font-semibold text-red-600">
                            {v.violations.length}
                          </span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs">
                        {v.latency_ms.toFixed(2)}ms
                      </td>
                      <td className="px-4 py-3 font-mono text-[10px] text-gray-400">
                        {v.request_id}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
