"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Card, Code, DataTable, Empty, ErrorNote, Input, PageHeader } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { ExecuteResponse, Page, SavedQuery } from "@/lib/types";

function SavedItem({ sq }: { sq: SavedQuery }) {
  const [vals, setVals] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(sq.parameters_schema).map(([k, s]) => [k, String(s.default ?? "")])));
  const [res, setRes] = useState<ExecuteResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null);
    const parameters = Object.fromEntries(Object.entries(vals).map(([k, v]) =>
      [k, sq.parameters_schema[k]?.type === "integer" ? Number(v) : v]));
    try { setRes(await api<ExecuteResponse>(`/saved-queries/${sq.id}/execute`, { method: "POST", json: { parameters } })); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <Card title={<span className="flex items-center gap-2">{sq.name}<Badge>v{sq.version}</Badge><Badge tone={sq.visibility === "tenant" ? "brand" : "neutral"}>{sq.visibility}</Badge></span>}
      actions={<span className="text-xs text-muted">used {sq.use_count}× · updated {fmt.date(sq.updated_at)}</span>}>
      <Code>{sq.template}</Code>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        {Object.entries(sq.parameters_schema).map(([k, s]) => (
          <label key={k} className="text-xs text-muted">{k}
            {s.enum ? (
              <select value={vals[k]} onChange={(e) => setVals({ ...vals, [k]: e.target.value })}
                className="mt-1 block rounded-md border border-line bg-surface px-2 py-2 text-sm text-ink">
                {s.enum.map((o) => <option key={o}>{o}</option>)}
              </select>
            ) : (
              <Input type={s.type === "integer" ? "number" : "text"} min={s.minimum} max={s.maximum} value={vals[k]}
                onChange={(e) => setVals({ ...vals, [k]: e.target.value })} className="mt-1 w-28" />
            )}
          </label>
        ))}
        <Button onClick={run} disabled={busy}>{busy ? "Running…" : "Run"}</Button>
      </div>
      {sq.question_examples.length > 0 && <p className="mt-3 text-xs text-muted">Matches questions like: “{sq.question_examples[0]}”</p>}
      <div className="mt-3"><ErrorNote error={error} /></div>
      {res && <div className="mt-3"><p className="mb-2 text-xs text-muted">{res.row_count} rows · {res.duration_ms} ms</p><DataTable columns={res.columns} rows={res.rows} /></div>}
    </Card>
  );
}

export default function SavedPage() {
  const [data, setData] = useState<Page<SavedQuery> | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { api<Page<SavedQuery>>("/saved-queries").then(setData).catch(setError); }, []);
  return (
    <>
      <PageHeader title="Saved queries" description="Governed, versioned templates with typed parameters. Matching questions reuse them instead of calling the AI." />
      <ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty title="No saved queries yet">Run a query in the workspace and save it.</Empty> : (
        <div className="space-y-4">{data.items.map((sq) => <SavedItem key={sq.id} sq={sq} />)}</div>
      ))}
    </>
  );
}
