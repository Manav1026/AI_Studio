"use client";

import { useEffect, useState } from "react";

import { Badge, ErrorNote, Input, PageHeader, statusTone } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { AuditItem, Page } from "@/lib/types";

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [data, setData] = useState<Page<AuditItem> | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const t = setTimeout(() => api<Page<AuditItem>>(`/audit?limit=200${action ? `&action=${encodeURIComponent(action)}` : ""}`)
      .then(setData).catch(setError), 200);
    return () => clearTimeout(t);
  }, [action]);
  return (
    <>
      <PageHeader title="Audit log" description="Connection, sync, query, save and MCP events. Each carries the correlation ID that also appears in API logs and traces." />
      <div className="mb-4 max-w-xs"><Input placeholder="Filter by action prefix (e.g. query.)" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter actions" /></div>
      <ErrorNote error={error} />
      {data && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-bg text-xs uppercase tracking-wide text-muted">
              <tr>{["When", "Action", "Result", "Resource", "Correlation ID", "Details"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.id} className="border-t border-line align-top">
                  <td className="whitespace-nowrap px-3 py-2 text-muted">{fmt.date(e.created_at)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{e.action}</td>
                  <td className="px-3 py-2"><Badge tone={statusTone(e.result)}>{e.result}</Badge></td>
                  <td className="px-3 py-2 text-xs">{e.resource_type}{e.resource_id && <span className="block font-mono text-muted">{e.resource_id.slice(0, 18)}</span>}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted">{e.correlation_id?.slice(0, 16)}</td>
                  <td className="max-w-sm truncate px-3 py-2 font-mono text-xs text-muted">{JSON.stringify(e.metadata)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
