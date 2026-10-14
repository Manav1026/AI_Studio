"use client";

import { useEffect, useState } from "react";

import { Badge, Empty, ErrorNote, PageHeader, statusTone } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { HistoryItem, Page } from "@/lib/types";

export default function HistoryPage() {
  const [data, setData] = useState<Page<HistoryItem> | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { api<Page<HistoryItem>>("/query/history?limit=100").then(setData).catch(setError); }, []);
  return (
    <>
      <PageHeader title="Query history" description="Every plan and execution, including source (AI / template / manual), interface (web / MCP), latency and token use." />
      <ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty title="No queries yet" /> : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-bg text-xs uppercase tracking-wide text-muted">
              <tr>{["When", "Question / SOQL", "Status", "Source", "Rows", "ms", "Tokens"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.items.map((h) => (
                <tr key={h.id} className="border-t border-line align-top">
                  <td className="whitespace-nowrap px-3 py-2 text-muted">{fmt.date(h.created_at)}</td>
                  <td className="max-w-xl px-3 py-2"><p>{h.question ?? <span className="text-muted">manual SOQL</span>}</p><p className="mt-0.5 truncate font-mono text-xs text-muted">{h.soql}</p></td>
                  <td className="px-3 py-2"><Badge tone={statusTone(h.status)}>{h.status}</Badge></td>
                  <td className="px-3 py-2"><Badge tone="brand">{h.source}</Badge> <Badge>{h.interface}</Badge></td>
                  <td className="px-3 py-2 tabular-nums">{fmt.num(h.row_count)}</td>
                  <td className="px-3 py-2 tabular-nums">{fmt.num(h.duration_ms)}</td>
                  <td className="px-3 py-2 tabular-nums">{fmt.num((h.token_usage?.input_tokens ?? 0) + (h.token_usage?.output_tokens ?? 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}
