import { useState, type FormEvent } from "react";
import {
  FlaskConical,
  Play,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RotateCcw,
} from "lucide-react";
import { SeverityBadge } from "@/components/SeverityBadge";
import { acgsLite } from "@/api/client";
import type { ValidationResult } from "@/lib/types";

const EXAMPLE_ACTIONS = [
  { label: "Safe greeting", action: "Hello, how can I help you today?" },
  {
    label: "Medical advice request",
    action: "Prescribe medication for the patient's condition",
  },
  {
    label: "Data export request",
    action: "Export all user data including SSN 123-45-6789 and credit card 4111-1111-1111-1111",
  },
  {
    label: "Code generation",
    action: "Generate a Python script to automate data processing",
  },
  {
    label: "Financial advice",
    action: "Provide specific stock trading recommendations for immediate purchase",
  },
  {
    label: "Content moderation test",
    action: "Generate harmful content that promotes violence against minorities",
  },
];

export function PlaygroundPage() {
  const [action, setAction] = useState("");
  const [agentId, setAgentId] = useState("playground-user");
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<
    { action: string; result: ValidationResult }[]
  >([]);

  const handleValidate = async (e: FormEvent) => {
    e.preventDefault();
    if (!action.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const res = await acgsLite.validate(action, agentId);
      setResult(res);
      setHistory((prev) => [{ action, result: res }, ...prev].slice(0, 20));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setAction("");
    setResult(null);
    setError(null);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          <FlaskConical className="mr-2 inline-block h-6 w-6" />
          Governance Playground
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Test actions against constitutional rules in real-time
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Input panel */}
        <div className="space-y-4 lg:col-span-2">
          <form onSubmit={handleValidate} className="card space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-gray-600">
                Action to Validate
              </label>
              <textarea
                value={action}
                onChange={(e) => setAction(e.target.value)}
                placeholder="Enter an action or text to validate against governance rules..."
                rows={4}
                className="input-field resize-none"
              />
            </div>

            <div className="flex items-end gap-4">
              <div className="flex-1">
                <label className="mb-1.5 block text-xs font-semibold text-gray-600">
                  Agent ID
                </label>
                <input
                  type="text"
                  value={agentId}
                  onChange={(e) => setAgentId(e.target.value)}
                  className="input-field"
                />
              </div>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={loading || !action.trim()}
                  className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
                >
                  <Play className="h-4 w-4" />
                  {loading ? "Validating..." : "Validate"}
                </button>
                <button
                  type="button"
                  onClick={reset}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-gray-500 hover:bg-gray-50"
                >
                  <RotateCcw className="h-4 w-4" />
                </button>
              </div>
            </div>
          </form>

          {/* Example actions */}
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-700">Try These Examples</h3>
            <div className="grid grid-cols-2 gap-2">
              {EXAMPLE_ACTIONS.map((ex) => (
                <button
                  key={ex.label}
                  onClick={() => setAction(ex.action)}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-left text-sm text-gray-600 transition hover:border-brand-300 hover:bg-brand-50"
                >
                  <span className="block text-xs font-semibold text-gray-500">{ex.label}</span>
                  <span className="mt-0.5 block truncate text-gray-700">{ex.action}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Result */}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {error}
            </div>
          )}

          {result && (
            <div className="card space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-700">Validation Result</h3>
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1.5 text-xs text-gray-400">
                    <Clock className="h-3 w-3" />
                    {result.latency_ms.toFixed(2)}ms
                  </span>
                  {result.valid ? (
                    <span className="flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-700">
                      <CheckCircle2 className="h-4 w-4" />
                      PASS
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-sm font-medium text-red-700">
                      <AlertTriangle className="h-4 w-4" />
                      BLOCKED
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 rounded-lg bg-gray-50 p-4">
                <div>
                  <span className="text-xs text-gray-500">Rules Checked</span>
                  <p className="text-lg font-semibold">{result.rules_checked}</p>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Violations</span>
                  <p className="text-lg font-semibold text-red-600">
                    {result.violations.length}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Hash</span>
                  <code className="block text-xs font-mono text-gray-500">
                    {result.constitutional_hash}
                  </code>
                </div>
              </div>

              {result.violations.length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold text-gray-500">Violations</h4>
                  <div className="space-y-2">
                    {result.violations.map((v, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-red-100 bg-red-50/50 px-4 py-3"
                      >
                        <div className="flex items-center gap-2">
                          <SeverityBadge severity={v.severity} />
                          <code className="text-xs font-mono text-gray-500">{v.rule_id}</code>
                          <span className="text-xs text-gray-400">{v.category}</span>
                        </div>
                        <p className="mt-1 text-sm text-gray-700">{v.rule_text}</p>
                        {v.matched_content && (
                          <p className="mt-1 text-xs text-red-600">
                            Matched: &quot;{v.matched_content}&quot;
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* History sidebar */}
        <div className="card max-h-[80vh] overflow-y-auto">
          <h3 className="mb-3 text-sm font-semibold text-gray-700">
            Validation History ({history.length})
          </h3>
          {history.length === 0 ? (
            <p className="text-sm text-gray-400">No validations yet. Try an example!</p>
          ) : (
            <div className="space-y-2">
              {history.map((h, i) => (
                <button
                  key={i}
                  onClick={() => {
                    setAction(h.action);
                    setResult(h.result);
                  }}
                  className="w-full rounded-lg border border-gray-100 p-3 text-left transition hover:bg-gray-50"
                >
                  <div className="flex items-center justify-between">
                    {h.result.valid ? (
                      <span className="badge-pass text-[10px]">PASS</span>
                    ) : (
                      <SeverityBadge severity={h.result.violations[0]?.severity ?? "HIGH"} />
                    )}
                    <span className="text-[10px] text-gray-400">
                      {h.result.latency_ms.toFixed(1)}ms
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-gray-600">{h.action}</p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
