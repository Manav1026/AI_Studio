"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  ErrorNote,
  Input,
  PageHeader,
  Textarea,
} from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type {
  ExecuteResponse,
  PlanResponse,
  SavedQuery,
  Validation,
} from "@/lib/types";

const SAMPLES = [
  "Show me the top 10 customers by opportunity revenue this year",
  "How many open cases by priority",
  "Open pipeline by stage",
  "Opportunities over 200k closing next month",
  "List contacts at Acme Corp",
  "Count of projects by status",
];

function Checks({ v }: { v: Validation }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {v.checks.map((c) => (
          <Badge key={c} tone="ok">
            ✓ {c.replace(/_/g, " ")}
          </Badge>
        ))}
      </div>
      {v.issues.length > 0 && (
        <ul className="space-y-1">
          {v.issues.map((i, n) => (
            <li
              key={n}
              className={i.severity === "error" ? "text-bad" : "text-warn"}>
              <span className="font-mono text-xs">{i.code}</span> — {i.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Workspace() {
  const params = useSearchParams();
  const [question, setQuestion] = useState(params.get("q") ?? "");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [soql, setSoql] = useState("");
  const [edited, setEdited] = useState<Validation | null>(null);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<
    "plan" | "exec" | "validate" | "save" | null
  >(null);
  const [saveName, setSaveName] = useState("");
  const [saved, setSaved] = useState<SavedQuery | null>(null);
  const auto = useRef(false);

  async function doPlan(q = question) {
    if (!q.trim()) return;
    setBusy("plan");
    setError(null);
    setResult(null);
    setSaved(null);
    setEdited(null);
    try {
      const p = await api<PlanResponse>("/query/plan", {
        method: "POST",
        json: { question: q },
      });
      setPlan(p);
      setSoql(p.soql ?? "");
      setSaveName(q.slice(0, 80));
    } catch (e) {
      setError(e);
      setPlan(null);
    } finally {
      setBusy(null);
    }
  }
  useEffect(() => {
    if (!auto.current && params.get("q")) {
      auto.current = true;
      doPlan(params.get("q")!);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isEdited = plan != null && soql.trim() !== (plan.soql ?? "").trim();
  const executable =
    plan && (isEdited ? edited?.valid : plan.status === "validated");

  async function validateEdited() {
    setBusy("validate");
    setError(null);
    try {
      setEdited(
        await api<Validation>("/query/validate", {
          method: "POST",
          json: { soql },
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }
  async function execute() {
    if (!plan) return;
    setBusy("exec");
    setError(null);
    try {
      const body = isEdited ? { soql } : { execution_id: plan.execution_id };
      setResult(
        await api<ExecuteResponse>("/query/execute", {
          method: "POST",
          json: body,
          headers: { "Idempotency-Key": crypto.randomUUID() },
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }
  async function save() {
    if (!plan) return;
    setBusy("save");
    setError(null);
    try {
      const body = isEdited
        ? { name: saveName, soql, question_examples: [question] }
        : { name: saveName, execution_id: plan.execution_id };
      setSaved(
        await api<SavedQuery>("/saved-queries", {
          method: "POST",
          json: { ...body, visibility: "tenant" },
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Query workspace"
        description="The system builds a structured plan, compiles SOQL, validates it against the catalog and policy, and only runs it when you click Execute."
      />
      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            doPlan();
          }}
          className="space-y-3">
          <label htmlFor="q" className="text-xs font-medium text-muted">
            Question
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="q"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Show me the top 10 customers by opportunity revenue this year"
            />
            <Button
              type="submit"
              disabled={busy !== null || !question.trim()}
              className="shrink-0">
              {busy === "plan" ? "Planning…" : "Generate query"}
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {SAMPLES.map((s) => (
              <button
                type="button"
                key={s}
                onClick={() => {
                  setQuestion(s);
                  doPlan(s);
                }}
                className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-brand hover:text-brand">
                {s}
              </button>
            ))}
          </div>
        </form>
      </Card>

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {plan && (
        <div className="mt-4 grid gap-4 lg:grid-cols-5">
          <Card
            className="lg:col-span-3"
            title={
              <span className="flex items-center gap-2">
                Generated query
                <Badge tone={plan.status === "validated" ? "ok" : "bad"}>
                  {plan.status}
                </Badge>
                <Badge tone="brand">
                  {plan.source === "template" ? "saved template" : "AI plan"}
                </Badge>
              </span>
            }
            actions={
              <span className="font-mono text-xs text-muted">
                ref {plan.correlation_id.slice(0, 12)}
              </span>
            }>
            {plan.explanation && <p className="mb-3">{plan.explanation}</p>}
            <label htmlFor="soql" className="text-xs font-medium text-muted">
              SOQL (read-only — you may edit, edits are re-validated)
            </label>
            <Textarea
              id="soql"
              rows={4}
              value={soql}
              onChange={(e) => {
                setSoql(e.target.value);
                setEdited(null);
              }}
              className="mt-1 font-mono text-xs"
              spellCheck={false}
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {isEdited && (
                <Button
                  variant="secondary"
                  onClick={validateEdited}
                  disabled={busy !== null}>
                  {busy === "validate" ? "Validating…" : "Validate edits"}
                </Button>
              )}
              <Button onClick={execute} disabled={!executable || busy !== null}>
                {busy === "exec" ? "Running…" : "Execute"}
              </Button>
            </div>
            {isEdited && !edited && (
              <p className="mt-2 text-xs text-warn">
                Edited SOQL must pass validation before it can run.
              </p>
            )}
          </Card>
          <Card className="lg:col-span-2" title="Validation">
            <Checks v={isEdited && edited ? edited : plan.validation} />
            <dl className="mt-4 space-y-1 text-xs text-muted">
              {plan.context_objects.length > 0 && (
                <div>
                  Context sent to AI:{" "}
                  <span className="text-ink">
                    {plan.context_objects.join(", ")}
                  </span>
                </div>
              )}
              {plan.template && (
                <div>
                  Template:{" "}
                  <span className="text-ink">{plan.template.name}</span> (
                  {Math.round(plan.template.score * 100)}% match)
                </div>
              )}
              <div>
                Model:{" "}
                <span className="text-ink">
                  {plan.model ?? "none (template)"}
                </span>
              </div>
              <div>
                Tokens:{" "}
                <span className="text-ink">
                  {fmt.num(
                    (plan.token_usage?.input_tokens ?? 0) +
                      (plan.token_usage?.output_tokens ?? 0),
                  )}
                </span>
              </div>
            </dl>
          </Card>
        </div>
      )}

      {result && (
        <Card
          className="mt-4"
          title={
            <span className="flex items-center gap-2">
              Results <Badge tone="ok">{result.row_count} rows</Badge>
              {result.cached && <Badge>cached</Badge>}
            </span>
          }
          actions={
            <span className="text-xs text-muted">
              {result.duration_ms} ms · ref {result.correlation_id.slice(0, 12)}
            </span>
          }>
          {result.warnings.length > 0 && (
            <p className="mb-3 text-xs text-warn">
              {result.warnings.map((w) => w.message).join(" · ")}
            </p>
          )}
          <DataTable columns={result.columns} rows={result.rows} />
          <div className="mt-4 flex flex-col gap-2 border-t border-line pt-4 sm:flex-row sm:items-center">
            {saved ? (
              <p className="text-ok">
                Saved as “{saved.name}” (v{saved.version}). Parameters:{" "}
                {Object.keys(saved.parameters_schema).join(", ") || "none"}.
                Similar questions will now reuse it without an AI call.
              </p>
            ) : (
              <>
                <Input
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  aria-label="Template name"
                  className="sm:max-w-md"
                />
                <Button
                  variant="secondary"
                  onClick={save}
                  disabled={busy !== null || saveName.length < 2}>
                  {busy === "save" ? "Saving…" : "Save as reusable query"}
                </Button>
              </>
            )}
          </div>
        </Card>
      )}
    </>
  );
}

export default function QueryPage() {
  return (
    <Suspense>
      <Workspace />
    </Suspense>
  );
}
