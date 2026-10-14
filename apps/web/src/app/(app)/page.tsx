"use client";

import { useEffect, useState } from "react";

import { useMe } from "@/components/AppShell";
import { Badge, Card, Empty, PageHeader, Stat, TextLink, statusTone } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { Connection, Metrics } from "@/lib/types";

const pct = (n: number) => `${Math.round(n * 100)}%`;

export default function Overview() {
  const me = useMe();
  const [conns, setConns] = useState<Connection[] | null>(null);
  const [m, setM] = useState<Metrics | null>(null);
  const isAdmin = me?.role === "owner" || me?.role === "admin";

  useEffect(() => {
    api<Connection[]>("/salesforce/connections").then(setConns).catch(() => setConns([]));
    if (isAdmin) api<Metrics>("/metrics/summary").then(setM).catch(() => undefined);
  }, [isAdmin]);

  const conn = conns?.find((c) => c.status === "active");
  return (
    <>
      <PageHeader title="Overview"
        description="Connect Salesforce → discover metadata → ask a question → validate → execute with your Salesforce permissions → save and reuse." />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Salesforce connection" className="lg:col-span-1">
          {conns === null ? <p className="text-muted">Loading…</p> : conn ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2"><span className="font-medium">{conn.org_name ?? conn.org_id}</span>
                <Badge tone={statusTone(conn.status)}>{conn.status}</Badge>{conn.mode === "mock" && <Badge>mock org</Badge>}</div>
              <p className="text-muted">{conn.sf_username}</p>
              <p className="text-muted">Catalog synced {fmt.date(conn.last_sync_at)}</p>
              <p className="pt-2"><TextLink href="/query">Ask a question →</TextLink></p>
            </div>
          ) : (
            <Empty title="No org connected"><TextLink href="/connections">Connect Salesforce</TextLink></Empty>
          )}
        </Card>
        <Card title="Try asking" className="lg:col-span-2">
          <ul className="space-y-2">
            {["Show me the top 10 customers by opportunity revenue this year", "How many open cases by priority",
              "Open pipeline by stage", "List contacts at Acme Corp"].map((q) => (
              <li key={q}><TextLink href={`/query?q=${encodeURIComponent(q)}`}>{q}</TextLink></li>
            ))}
          </ul>
        </Card>
      </div>
      {m && (
        <>
          <h2 className="mb-3 mt-8 text-sm font-semibold">Last 30 days</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Questions planned" value={fmt.num(m.queries.total)} hint={`${pct(m.queries.validation_rejection_rate)} rejected by validation`} />
            <Stat label="Saved-query reuse" value={pct(m.saved_query_reuse_rate)} hint="Answers served from templates, no AI call" />
            <Stat label="AI tokens" value={fmt.num(m.ai.input_tokens + m.ai.output_tokens)} hint={`$${m.ai.estimated_cost_usd.toFixed(4)} est. · ${m.ai.requests} calls`} />
            <Stat label="Salesforce latency" value={`${Math.round(m.queries.avg_execution_ms)} ms`} hint={`p95 ${Math.round(m.queries.p95_execution_ms)} ms`} />
            <Stat label="OAuth" value={`${m.oauth.success} / ${m.oauth.failure}`} hint="success / failure" />
            <Stat label="Metadata syncs" value={m.metadata_sync.runs} hint={`${m.metadata_sync.avg_duration_s}s avg · ${m.metadata_sync.errors} errors`} />
            <Stat label="MCP tool calls" value={fmt.num(Object.values(m.mcp_tool_calls).reduce((a, b) => a + b, 0))} hint={`${m.mcp_tool_calls.failure ?? 0} failed`} />
            <Stat label="Salesforce API calls today" value={fmt.num(Object.values(m.salesforce_api_calls_today).reduce((a, b) => a + b, 0))} />
          </div>
        </>
      )}
    </>
  );
}
