import { useCallback, useMemo, useState } from "react";
import { GitBranch, Maximize2 } from "lucide-react";
import {
  Treemap,
  ResponsiveContainer,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useApi } from "@/hooks/useApi";
import { acgsLite } from "@/api/client";
import type { Rule, Severity } from "@/lib/types";

const SEVERITY_COLORS: Record<Severity, string> = {
  CRITICAL: "#ef4444",
  HIGH: "#f97316",
  MEDIUM: "#eab308",
  LOW: "#3b82f6",
};

const CATEGORY_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

export function RuleGraphPage() {
  const rulesFetcher = useCallback(() => acgsLite.getRules(), []);
  const { data: rules, loading, error } = useApi(rulesFetcher);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  // Category distribution
  const categoryData = useMemo(() => {
    if (!rules) return [];
    const counts: Record<string, number> = {};
    for (const r of rules) {
      counts[r.category] = (counts[r.category] ?? 0) + 1;
    }
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .map(([name, value], i) => ({
        name,
        value,
        fill: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
      }));
  }, [rules]);

  // Severity distribution
  const severityData = useMemo(() => {
    if (!rules) return [];
    const counts: Record<Severity, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const r of rules) counts[r.severity]++;
    return (Object.entries(counts) as [Severity, number][]).map(([severity, count]) => ({
      name: severity,
      value: count,
      fill: SEVERITY_COLORS[severity],
    }));
  }, [rules]);

  // Workflow action distribution
  const actionData = useMemo(() => {
    if (!rules) return [];
    const counts: Record<string, number> = {};
    for (const r of rules) {
      counts[r.workflow_action] = (counts[r.workflow_action] ?? 0) + 1;
    }
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [rules]);

  // Treemap data by category -> rule
  const treemapData = useMemo(() => {
    if (!rules) return [];
    const groups: Record<string, Rule[]> = {};
    for (const r of rules) {
      if (!groups[r.category]) groups[r.category] = [];
      groups[r.category].push(r);
    }
    return Object.entries(groups).map(([name, ruleList], i) => ({
      name,
      children: ruleList.map((r) => ({
        name: r.id,
        size: r.priority || 1,
        severity: r.severity,
      })),
      fill: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
    }));
  }, [rules]);

  // Dependency edges
  const dependencyEdges = useMemo(() => {
    if (!rules) return [];
    const edges: { from: string; to: string }[] = [];
    for (const r of rules) {
      for (const dep of r.depends_on) {
        edges.push({ from: r.id, to: dep });
      }
    }
    return edges;
  }, [rules]);

  // Rules in selected category
  const categoryRules = useMemo(() => {
    if (!rules || !selectedCategory) return [];
    return rules.filter((r) => r.category === selectedCategory);
  }, [rules, selectedCategory]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-500">
        Loading rule graph...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          <GitBranch className="mr-2 inline-block h-6 w-6" />
          Rule Visualization
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {rules?.length ?? 0} rules &middot; {dependencyEdges.length} dependencies &middot;{" "}
          {categoryData.length} categories
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Overview stats */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Severity pie */}
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">By Severity</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={severityData}
                cx="50%"
                cy="50%"
                innerRadius={45}
                outerRadius={75}
                paddingAngle={3}
                dataKey="value"
                label={({ name, value }) => `${name}: ${value}`}
              >
                {severityData.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Category bar chart */}
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">By Category</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={categoryData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 10 }}
                width={80}
              />
              <Tooltip />
              <Bar dataKey="value" name="Rules">
                {categoryData.map((entry, i) => (
                  <Cell
                    key={entry.name}
                    fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                    cursor="pointer"
                    onClick={() => setSelectedCategory(entry.name)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Workflow actions */}
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">By Workflow Action</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={actionData}
                cx="50%"
                cy="50%"
                innerRadius={45}
                outerRadius={75}
                paddingAngle={3}
                dataKey="value"
                label={({ name, value }) => `${name}: ${value}`}
              >
                <Cell fill="#ef4444" />
                <Cell fill="#f59e0b" />
                <Cell fill="#8b5cf6" />
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Treemap */}
      <div className="card">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">
            <Maximize2 className="mr-1.5 inline-block h-4 w-4" />
            Rule Treemap (by category and priority)
          </h3>
          <div className="text-xs text-gray-400">
            Click a category bar above to filter
          </div>
        </div>
        <ResponsiveContainer width="100%" height={350}>
          <Treemap
            data={treemapData}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke="#fff"
          >
            <Tooltip
              formatter={(value: number, name: string) => [`Priority: ${value}`, name]}
            />
          </Treemap>
        </ResponsiveContainer>
      </div>

      {/* Dependency graph (SVG-based) */}
      {dependencyEdges.length > 0 && (
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">
            <GitBranch className="mr-1.5 inline-block h-4 w-4" />
            Rule Dependencies ({dependencyEdges.length} edges)
          </h3>
          <div className="overflow-x-auto">
            <div className="flex flex-wrap gap-2">
              {dependencyEdges.map((edge, i) => (
                <div
                  key={i}
                  className="flex items-center gap-1 rounded-lg bg-gray-50 px-3 py-2 text-xs"
                >
                  <code className="font-mono text-purple-600">{edge.from}</code>
                  <span className="text-gray-400">&rarr;</span>
                  <code className="font-mono text-blue-600">{edge.to}</code>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Category drill-down */}
      {selectedCategory && (
        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">
              Category: {selectedCategory} ({categoryRules.length} rules)
            </h3>
            <button
              onClick={() => setSelectedCategory(null)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Clear filter
            </button>
          </div>
          <div className="space-y-2">
            {categoryRules.map((r) => (
              <div
                key={r.id}
                className="flex items-center gap-3 rounded-lg bg-gray-50 px-4 py-2"
              >
                <SeverityBadge severity={r.severity} />
                <code className="text-xs font-mono text-gray-500">{r.id}</code>
                <span className="flex-1 truncate text-sm text-gray-700">{r.text}</span>
                <span className="text-xs text-gray-400">{r.workflow_action}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
