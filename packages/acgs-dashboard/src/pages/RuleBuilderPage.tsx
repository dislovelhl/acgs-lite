import { useState, type FormEvent } from "react";
import { Pencil, Plus, X, Save, Wand2 } from "lucide-react";
import { SeverityBadge } from "@/components/SeverityBadge";
import type { Severity, WorkflowAction } from "@/lib/types";

const SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const WORKFLOW_ACTIONS: WorkflowAction[] = ["block", "warn", "escalate"];
const CATEGORIES = [
  "safety",
  "security",
  "privacy",
  "fairness",
  "transparency",
  "reliability",
  "compliance",
  "ethics",
  "custom",
];

interface RuleDraft {
  id: string;
  text: string;
  severity: Severity;
  keywords: string[];
  patterns: string[];
  category: string;
  subcategory: string;
  workflow_action: WorkflowAction;
  tags: string[];
  priority: number;
}

const EMPTY_DRAFT: RuleDraft = {
  id: "",
  text: "",
  severity: "MEDIUM",
  keywords: [],
  patterns: [],
  category: "safety",
  subcategory: "",
  workflow_action: "warn",
  tags: [],
  priority: 50,
};

const TEMPLATES: { name: string; draft: RuleDraft }[] = [
  {
    name: "Block Harmful Content",
    draft: {
      ...EMPTY_DRAFT,
      id: "block-harmful-content",
      text: "Block any content that promotes violence, self-harm, or illegal activities",
      severity: "CRITICAL",
      keywords: ["violence", "self-harm", "illegal", "harm"],
      category: "safety",
      workflow_action: "block",
      priority: 100,
      tags: ["content-safety", "critical"],
    },
  },
  {
    name: "PII Detection Warning",
    draft: {
      ...EMPTY_DRAFT,
      id: "pii-detection-warn",
      text: "Warn when output contains personal identifiable information patterns",
      severity: "HIGH",
      keywords: ["SSN", "social security", "credit card", "passport"],
      patterns: ["\\b\\d{3}-\\d{2}-\\d{4}\\b", "\\b\\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}\\b"],
      category: "privacy",
      workflow_action: "escalate",
      priority: 90,
      tags: ["pii", "privacy", "compliance"],
    },
  },
  {
    name: "Bias Detection",
    draft: {
      ...EMPTY_DRAFT,
      id: "bias-detection",
      text: "Flag outputs that contain demographic stereotypes or biased generalizations",
      severity: "MEDIUM",
      keywords: ["always", "never", "all", "none"],
      category: "fairness",
      workflow_action: "warn",
      priority: 70,
      tags: ["bias", "fairness", "dei"],
    },
  },
];

export function RuleBuilderPage() {
  const [draft, setDraft] = useState<RuleDraft>({ ...EMPTY_DRAFT });
  const [keywordInput, setKeywordInput] = useState("");
  const [patternInput, setPatternInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [savedRules, setSavedRules] = useState<RuleDraft[]>([]);
  const [preview, setPreview] = useState(false);

  const updateDraft = (updates: Partial<RuleDraft>) =>
    setDraft((prev) => ({ ...prev, ...updates }));

  const addKeyword = () => {
    const kw = keywordInput.trim();
    if (kw && !draft.keywords.includes(kw)) {
      updateDraft({ keywords: [...draft.keywords, kw] });
      setKeywordInput("");
    }
  };

  const removeKeyword = (kw: string) =>
    updateDraft({ keywords: draft.keywords.filter((k) => k !== kw) });

  const addPattern = () => {
    const p = patternInput.trim();
    if (p && !draft.patterns.includes(p)) {
      updateDraft({ patterns: [...draft.patterns, p] });
      setPatternInput("");
    }
  };

  const removePattern = (p: string) =>
    updateDraft({ patterns: draft.patterns.filter((x) => x !== p) });

  const addTag = () => {
    const t = tagInput.trim();
    if (t && !draft.tags.includes(t)) {
      updateDraft({ tags: [...draft.tags, t] });
      setTagInput("");
    }
  };

  const removeTag = (t: string) =>
    updateDraft({ tags: draft.tags.filter((x) => x !== t) });

  const handleSave = (e: FormEvent) => {
    e.preventDefault();
    if (!draft.id || !draft.text) return;
    setSavedRules((prev) => [...prev, { ...draft }]);
    setDraft({ ...EMPTY_DRAFT });
  };

  const applyTemplate = (template: RuleDraft) => setDraft({ ...template });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          <Pencil className="mr-2 inline-block h-6 w-6" />
          Rule Builder
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Create governance rules visually — no code required
        </p>
      </div>

      {/* Templates */}
      <div className="card">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">
          <Wand2 className="mr-1.5 inline-block h-4 w-4" />
          Quick Templates
        </h3>
        <div className="flex flex-wrap gap-2">
          {TEMPLATES.map((t) => (
            <button
              key={t.name}
              onClick={() => applyTemplate(t.draft)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 transition hover:border-brand-300 hover:bg-brand-50"
            >
              {t.name}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Builder form */}
        <form onSubmit={handleSave} className="card space-y-5 lg:col-span-2">
          <h3 className="text-sm font-semibold text-gray-700">Rule Definition</h3>

          {/* ID + Severity row */}
          <div className="grid grid-cols-2 gap-4">
            <FieldGroup label="Rule ID" required>
              <input
                type="text"
                value={draft.id}
                onChange={(e) => updateDraft({ id: e.target.value.replace(/\s/g, "-").toLowerCase() })}
                placeholder="e.g. block-harmful-content"
                className="input-field"
              />
            </FieldGroup>
            <FieldGroup label="Severity" required>
              <div className="flex gap-2">
                {SEVERITIES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => updateDraft({ severity: s })}
                    className={`flex-1 rounded-lg border px-2 py-2 text-xs font-medium transition ${
                      draft.severity === s
                        ? "border-brand-500 bg-brand-50 text-brand-700"
                        : "border-gray-200 text-gray-500 hover:bg-gray-50"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </FieldGroup>
          </div>

          {/* Rule text */}
          <FieldGroup label="Rule Description" required>
            <textarea
              value={draft.text}
              onChange={(e) => updateDraft({ text: e.target.value })}
              placeholder="Describe what this rule should enforce..."
              rows={3}
              className="input-field resize-none"
            />
          </FieldGroup>

          {/* Category + Action */}
          <div className="grid grid-cols-2 gap-4">
            <FieldGroup label="Category">
              <select
                value={draft.category}
                onChange={(e) => updateDraft({ category: e.target.value })}
                className="input-field"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </select>
            </FieldGroup>
            <FieldGroup label="Workflow Action">
              <div className="flex gap-2">
                {WORKFLOW_ACTIONS.map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => updateDraft({ workflow_action: a })}
                    className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium capitalize transition ${
                      draft.workflow_action === a
                        ? a === "block"
                          ? "border-red-400 bg-red-50 text-red-700"
                          : a === "escalate"
                            ? "border-purple-400 bg-purple-50 text-purple-700"
                            : "border-amber-400 bg-amber-50 text-amber-700"
                        : "border-gray-200 text-gray-500 hover:bg-gray-50"
                    }`}
                  >
                    {a}
                  </button>
                ))}
              </div>
            </FieldGroup>
          </div>

          {/* Priority slider */}
          <FieldGroup label={`Priority: ${draft.priority}`}>
            <input
              type="range"
              min={0}
              max={100}
              value={draft.priority}
              onChange={(e) => updateDraft({ priority: Number(e.target.value) })}
              className="w-full accent-brand-600"
            />
            <div className="flex justify-between text-[10px] text-gray-400">
              <span>Low</span>
              <span>High</span>
            </div>
          </FieldGroup>

          {/* Keywords */}
          <FieldGroup label="Keywords">
            <div className="flex gap-2">
              <input
                type="text"
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addKeyword())}
                placeholder="Type and press Enter"
                className="input-field flex-1"
              />
              <button
                type="button"
                onClick={addKeyword}
                className="rounded-lg bg-gray-100 px-3 py-2 text-sm hover:bg-gray-200"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            {draft.keywords.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {draft.keywords.map((kw) => (
                  <span
                    key={kw}
                    className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs text-blue-700"
                  >
                    {kw}
                    <button type="button" onClick={() => removeKeyword(kw)}>
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </FieldGroup>

          {/* Patterns */}
          <FieldGroup label="Regex Patterns">
            <div className="flex gap-2">
              <input
                type="text"
                value={patternInput}
                onChange={(e) => setPatternInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addPattern())}
                placeholder="e.g. \\b\\d{3}-\\d{2}-\\d{4}\\b"
                className="input-field flex-1 font-mono text-xs"
              />
              <button
                type="button"
                onClick={addPattern}
                className="rounded-lg bg-gray-100 px-3 py-2 text-sm hover:bg-gray-200"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            {draft.patterns.length > 0 && (
              <div className="mt-2 space-y-1">
                {draft.patterns.map((p) => (
                  <div key={p} className="flex items-center gap-2">
                    <code className="flex-1 rounded bg-gray-100 px-2 py-1 text-xs font-mono">
                      {p}
                    </code>
                    <button type="button" onClick={() => removePattern(p)}>
                      <X className="h-3 w-3 text-gray-400" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </FieldGroup>

          {/* Tags */}
          <FieldGroup label="Tags">
            <div className="flex gap-2">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
                placeholder="Add tags..."
                className="input-field flex-1"
              />
              <button
                type="button"
                onClick={addTag}
                className="rounded-lg bg-gray-100 px-3 py-2 text-sm hover:bg-gray-200"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            {draft.tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {draft.tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-600"
                  >
                    {t}
                    <button type="button" onClick={() => removeTag(t)}>
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </FieldGroup>

          {/* Submit */}
          <div className="flex items-center gap-3 border-t border-gray-200 pt-4">
            <button
              type="submit"
              disabled={!draft.id || !draft.text}
              className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              Save Rule
            </button>
            <button
              type="button"
              onClick={() => setPreview(!preview)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              {preview ? "Hide" : "Show"} JSON Preview
            </button>
          </div>
        </form>

        {/* Preview / saved rules sidebar */}
        <div className="space-y-4">
          {preview && (
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-700">JSON Preview</h3>
              <pre className="max-h-96 overflow-auto rounded-lg bg-gray-900 p-4 text-xs text-green-400">
                {JSON.stringify(draft, null, 2)}
              </pre>
            </div>
          )}

          {/* Live preview card */}
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-700">Live Preview</h3>
            {draft.id ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <code className="text-xs font-mono text-gray-500">{draft.id}</code>
                  <SeverityBadge severity={draft.severity} />
                </div>
                <p className="text-sm text-gray-700">
                  {draft.text || "No description yet..."}
                </p>
                <div className="text-xs text-gray-400">
                  {draft.category} &middot; {draft.workflow_action} &middot; Priority {draft.priority}
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-400">Start filling out the form to see a preview</p>
            )}
          </div>

          {/* Saved rules */}
          {savedRules.length > 0 && (
            <div className="card">
              <h3 className="mb-3 text-sm font-semibold text-gray-700">
                Saved Rules ({savedRules.length})
              </h3>
              <div className="space-y-2">
                {savedRules.map((r) => (
                  <div
                    key={r.id}
                    className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2"
                  >
                    <SeverityBadge severity={r.severity} />
                    <span className="flex-1 truncate text-sm text-gray-700">{r.id}</span>
                    <span className="text-xs text-gray-400">{r.workflow_action}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FieldGroup({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold text-gray-600">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </label>
      {children}
    </div>
  );
}
