"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { useMe } from "@/components/AppShell";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, statusTone } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { Connection, SyncRun } from "@/lib/types";

function ConnectionsInner() {
  const me = useMe();
  const params = useSearchParams();
  const [conns, setConns] = useState<Connection[] | null>(null);
  const [runs, setRuns] = useState<Record<string, SyncRun[]>>({});
  const [error, setError] = useState<unknown>(params.get("error") ? { message: `Connection failed: ${params.get("error")}` } : null);
  const canManage = me?.role === "owner" || me?.role === "admin";

  const load = useCallback(async () => {
    const list = await api<Connection[]>("/salesforce/connections");
    setConns(list);
    const entries = await Promise.all(list.map(async (c) => [c.id, await api<SyncRun[]>(`/salesforce/connections/${c.id}/sync-runs?limit=5`)] as const));
    setRuns(Object.fromEntries(entries));
    return list;
  }, []);

  useEffect(() => { load().catch(setError); }, [load]);
  // poll while a sync is in progress
  useEffect(() => {
    const busy = conns?.some((c) => c.latest_sync && ["queued", "running"].includes(c.latest_sync.status));
    if (!busy) return;
    const t = setInterval(() => load().catch(() => undefined), 1500);
    return () => clearInterval(t);
  }, [conns, load]);

  async function connect() {
    setError(null);
    try {
      const { authorization_url } = await api<{ authorization_url: string }>("/salesforce/connections", { method: "POST" });
      window.location.href = authorization_url; // full-page redirect to Salesforce (or the mock authorizer)
    } catch (e) { setError(e); }
  }
  async function sync(id: string) {
    try { await api(`/salesforce/connections/${id}/sync`, { method: "POST" }); await load(); } catch (e) { setError(e); }
  }
  async function disconnect(id: string) {
    if (!confirm("Disconnect this org? Stored credentials are deleted and revoked.")) return;
    try { await api(`/salesforce/connections/${id}`, { method: "DELETE" }); await load(); } catch (e) { setError(e); }
  }

  return (
    <>
      <PageHeader title="Salesforce connections"
        description="OAuth 2.0 via an External Client App. Tokens are stored encrypted on the server and never sent to the browser."
        actions={canManage && <Button onClick={connect}>Connect Salesforce</Button>} />
      <div className="mb-4"><ErrorNote error={error} /></div>
      {params.get("connected") && <p className="mb-4 rounded-md bg-ok-soft px-3 py-2 text-ok">Connected. Metadata sync has been queued.</p>}
      {conns === null ? <p className="text-muted">Loading…</p> : conns.length === 0 ? (
        <Empty title="No Salesforce org connected yet">{canManage ? "Use Connect Salesforce to authorize an org." : "Ask an admin to connect an org."}</Empty>
      ) : (
        <div className="space-y-4">
          {conns.map((c) => (
            <Card key={c.id} title={<span className="flex items-center gap-2">{c.org_name ?? c.org_id}<Badge tone={statusTone(c.status)}>{c.status}</Badge>{c.mode === "mock" && <Badge>mock</Badge>}</span>}
              actions={canManage && c.status === "active" && (<>
                <Button variant="secondary" onClick={() => sync(c.id)}>Sync metadata</Button>
                <Button variant="danger" onClick={() => disconnect(c.id)}>Disconnect</Button></>)}>
              <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-3">
                <div><dt className="text-xs text-muted">Org ID</dt><dd className="font-mono text-xs">{c.org_id}</dd></div>
                <div><dt className="text-xs text-muted">Salesforce user</dt><dd>{c.sf_username}</dd></div>
                <div><dt className="text-xs text-muted">Instance</dt><dd className="truncate">{c.instance_url}</dd></div>
                <div><dt className="text-xs text-muted">API version</dt><dd>{c.api_version}</dd></div>
                <div><dt className="text-xs text-muted">Scopes</dt><dd>{c.scopes.join(", ")}</dd></div>
                <div><dt className="text-xs text-muted">Catalog version</dt><dd className="font-mono text-xs">{c.catalog_version ?? "—"}</dd></div>
              </dl>
              <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-muted">Recent sync runs</h3>
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted"><tr><th className="py-1">Status</th><th>Objects</th><th>Fields</th><th>Relationships</th><th>Errors</th><th>Completed</th></tr></thead>
                <tbody>
                  {(runs[c.id] ?? []).map((r) => (
                    <tr key={r.id} className="border-t border-line">
                      <td className="py-1.5"><Badge tone={statusTone(r.status)}>{r.status}</Badge></td>
                      <td className="tabular-nums">{r.objects_seen}</td><td className="tabular-nums">{r.fields_seen}</td>
                      <td className="tabular-nums">{r.relationships_seen}</td><td className="tabular-nums">{r.error_count}</td>
                      <td>{fmt.date(r.completed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

export default function ConnectionsPage() {
  return <Suspense><ConnectionsInner /></Suspense>;
}
