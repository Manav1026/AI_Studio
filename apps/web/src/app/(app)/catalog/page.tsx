"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Empty, ErrorNote, Input, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { CatalogObject, Page } from "@/lib/types";

export default function CatalogPage() {
  const [q, setQ] = useState("");
  const [data, setData] = useState<Page<CatalogObject> | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api<Page<CatalogObject>>(`/catalog/objects?limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}`)
        .then((d) => { setData(d); setError(null); }).catch(setError);
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <>
      <PageHeader title="Metadata catalog"
        description="Objects, fields and relationships discovered from Salesforce and stored in the product catalog. The AI only ever sees the relevant slice of this." />
      <div className="mb-4 max-w-sm"><Input placeholder="Search objects…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search objects" /></div>
      <ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty title="No objects found" /> : (
        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-bg text-xs uppercase tracking-wide text-muted">
              <tr><th className="px-4 py-2 font-medium">Object</th><th className="px-4 py-2 font-medium">API name</th><th className="px-4 py-2 font-medium">Fields</th><th className="px-4 py-2 font-medium">Type</th></tr>
            </thead>
            <tbody>
              {data.items.map((o) => (
                <tr key={o.api_name} className="border-t border-line hover:bg-bg">
                  <td className="px-4 py-2.5"><Link className="font-medium text-brand hover:underline" href={`/catalog/${o.api_name}`}>{o.label}</Link></td>
                  <td className="px-4 py-2.5 font-mono text-xs">{o.api_name}</td>
                  <td className="px-4 py-2.5 tabular-nums">{o.field_count}</td>
                  <td className="px-4 py-2.5">{o.is_custom ? <Badge tone="brand">custom</Badge> : <Badge>standard</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}
