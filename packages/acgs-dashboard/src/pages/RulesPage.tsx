import { useCallback, useState } from "react";
import { ShieldCheck, Search, Filter, ChevronDown, ChevronRight } from "lucide-react";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useApi } from "@/hooks/useApi";
import { acgsLite } from "@/api/client";
import type { Rule, Severity } from "@/lib/types";

const ALL_SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export function RulesPage() {
  const rulesFetcher = useCallback(() => acgsLite.getRules(), []);
  const { data: rules, loading, error } = useApi(rulesFetcher);

  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<Severity | "ALL">("ALL");
  const [expandedRule, setExpandedRule] = useState<string | null>(null);

  const filtered = (rules ?? []).filter((r) => {
    if (severityFilter !== "ALL" && r.severity !== severityFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        r.id.toLowerCase().includes(q) ||
        r.text.toLowerCase().includes(q) ||
        r.category.toLowerCase().includes(q) ||
        r.tags.some((t) => t.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          <ShieldCheck className="mr-2 inline-block h-6 w-6" />
          Constitutional Rules
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {rules?.length ?? 0} rules loaded &middot; Browse, search, and inspect governance rules
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search rules by ID, text, category, or tag..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-400" />
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as Severity | "ALL")}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
          >
            <option value="ALL">All Severities</option>
            {ALL_SEVERITIES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Rules list */}
      {loading ? (
        <div className="flex h-40 items-center justify-center text-sm text-gray-500">
          Loading rules...
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((rule) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              expanded={expandedRule === rule.id}
              onToggle={() =>
                setExpandedRule(expandedRule === rule.id ? null : rule.id)
              }
            />
          ))}
          {filtered.length === 0 && (
            <div className="py-12 text-center text-sm text-gray-400">
              No rules match your filters.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RuleRow({
  rule,
  expanded,
  onToggle,
}: {
  rule: Rule;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="card !p-0 overflow-hidden">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-gray-400" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <code className="text-xs font-mono text-gray-500">{rule.id}</code>
            <SeverityBadge severity={rule.severity} />
            {!rule.enabled && (
              <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] text-gray-500">
                DISABLED
              </span>
            )}
            {rule.deprecated && (
              <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] text-red-600">
                DEPRECATED
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-sm text-gray-700">{rule.text}</p>
        </div>
        <div className="shrink-0 text-xs text-gray-400">
          {rule.workflow_action}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-6 py-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <Detail label="Category" value={`${rule.category} / ${rule.subcategory}`} />
            <Detail label="Workflow Action" value={rule.workflow_action} />
            <Detail label="Priority" value={String(rule.priority)} />
            <Detail label="Hardcoded" value={rule.hardcoded ? "Yes" : "No"} />
          </div>

          {rule.keywords.length > 0 && (
            <div className="mt-3">
              <span className="text-xs font-semibold text-gray-500">Keywords:</span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {rule.keywords.map((kw) => (
                  <span
                    key={kw}
                    className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {rule.patterns.length > 0 && (
            <div className="mt-3">
              <span className="text-xs font-semibold text-gray-500">Patterns:</span>
              <div className="mt-1 space-y-1">
                {rule.patterns.map((p, i) => (
                  <code
                    key={i}
                    className="block rounded bg-gray-200 px-2 py-1 text-xs font-mono text-gray-700"
                  >
                    {p}
                  </code>
                ))}
              </div>
            </div>
          )}

          {rule.tags.length > 0 && (
            <div className="mt-3">
              <span className="text-xs font-semibold text-gray-500">Tags:</span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {rule.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-600"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {rule.depends_on.length > 0 && (
            <div className="mt-3">
              <span className="text-xs font-semibold text-gray-500">Depends On:</span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {rule.depends_on.map((dep) => (
                  <code
                    key={dep}
                    className="rounded bg-purple-100 px-2 py-0.5 text-xs font-mono text-purple-700"
                  >
                    {dep}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs font-semibold text-gray-500">{label}</span>
      <p className="text-sm text-gray-700">{value}</p>
    </div>
  );
}
