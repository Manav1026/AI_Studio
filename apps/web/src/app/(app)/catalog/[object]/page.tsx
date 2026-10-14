"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Badge, Card, ErrorNote, Input, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { ObjectDetail } from "@/lib/types";

export default function ObjectPage() {
  const { object } = useParams<{ object: string }>();
  const [d, setD] = useState<ObjectDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => { api<ObjectDetail>(`/catalog/objects/${object}`).then(setD).catch(setError); }, [object]);
  const fields = useMemo(() => (d?.fields ?? []).filter((f) =>
    !filter || f.api_name.toLowerCase().includes(filter.toLowerCase()) || f.label.toLowerCase().includes(filter.toLowerCase())), [d, filter]);

  if (error) return <ErrorNote error={error} />;
  if (!d) return <p className="text-muted">Loading…</p>;
  return (
    <>
      <p className="mb-2 text-xs"><Link href="/catalog" className="text-brand hover:underline">← Catalog</Link></p>
      <PageHeader title={d.label} description={<span className="font-mono text-xs">{d.api_name} · key prefix {d.key_prefix ?? "—"} · version {d.metadata_version}</span>} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title={`Fields (${d.fields.length})`} className="lg:col-span-2" actions={<Input placeholder="Filter fields" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-44 py-1" aria-label="Filter fields" />}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr><th className="py-2 pr-3 font-medium">Field</th><th className="py-2 pr-3 font-medium">Type</th><th className="py-2 pr-3 font-medium">Capabilities</th></tr>
              </thead>
              <tbody>
                {fields.map((f) => (
                  <tr key={f.api_name} className="border-t border-line align-top">
                    <td className="py-2 pr-3"><p className="font-medium">{f.label}</p><p className="font-mono text-xs text-muted">{f.api_name}</p></td>
                    <td className="py-2 pr-3"><Badge tone={f.data_type === "reference" ? "brand" : "neutral"}>{f.data_type}</Badge>
                      {f.reference_to.length > 0 && <p className="mt-1 text-xs text-muted">→ {f.reference_to.join(", ")} via <span className="font-mono">{f.relationship_name}</span></p>}
                      {f.picklist_values.length > 0 && <p className="mt-1 max-w-xs text-xs text-muted">{f.picklist_values.slice(0, 6).join(", ")}{f.picklist_values.length > 6 ? "…" : ""}</p>}
                    </td>
                    <td className="py-2 pr-3"><div className="flex flex-wrap gap-1">
                      {f.is_filterable && <Badge>filter</Badge>}{f.is_groupable && <Badge>group</Badge>}
                      {f.is_sortable && <Badge>sort</Badge>}{f.is_aggregatable && <Badge>aggregate</Badge>}{f.is_custom && <Badge tone="brand">custom</Badge>}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Relationships">
          {d.relationships.length === 0 ? <p className="text-muted">No relationships cataloged.</p> : (
            <ul className="space-y-3">
              {d.relationships.map((r) => (
                <li key={`${r.direction}-${r.relationship_name}`} className="border-b border-line pb-3 last:border-0">
                  <div className="flex items-center gap-2">
                    <Badge tone={r.direction === "parent" ? "brand" : "neutral"}>{r.direction === "parent" ? "parent" : "child"}</Badge>
                    <span className="font-mono text-xs">{r.relationship_name}</span>
                  </div>
                  <p className="mt-1 text-muted">
                    {r.direction === "parent" ? "Looks up " : "Has many "}
                    {r.in_catalog ? <Link className="text-brand hover:underline" href={`/catalog/${r.related_object}`}>{r.related_object}</Link> : r.related_object}
                    {r.relationship_type === "master_detail" && " (master-detail)"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
