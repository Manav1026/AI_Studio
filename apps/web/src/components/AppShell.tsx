"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/connections", label: "Connections" },
  { href: "/catalog", label: "Metadata catalog" },
  { href: "/query", label: "Query workspace" },
  { href: "/saved", label: "Saved queries" },
  { href: "/history", label: "History" },
  { href: "/audit", label: "Audit log", admin: true },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    api<Me>("/me").then(setMe).catch(() => router.replace("/login"));
  }, [router]);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  if (!me) return <div className="grid min-h-screen place-items-center text-muted">Loading…</div>;
  const isAdmin = me.role === "owner" || me.role === "admin";

  return (
    <MeContext.Provider value={me}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface md:flex">
          <div className="flex items-center gap-2 px-5 py-5">
            <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
              <rect width="32" height="32" rx="7" fill="#0b5cab" />
              <path d="M9 20c0-4 3-7 7-7s7 3 7 7" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" />
              <circle cx="16" cy="11" r="2.4" fill="#fff" />
            </svg>
            <div className="leading-tight">
              <p className="text-sm font-semibold">SF AI Workspace</p>
              <p className="text-xs text-muted">Prototype</p>
            </div>
          </div>
          <nav className="flex-1 space-y-0.5 px-3" aria-label="Main">
            {NAV.filter((n) => !n.admin || isAdmin).map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
              return (
                <Link key={n.href} href={n.href}
                  className={`block rounded-md px-3 py-2 ${active ? "bg-brand-soft font-medium text-brand" : "text-ink hover:bg-bg"}`}>
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <div className="border-t border-line px-5 py-4 text-xs">
            <p className="truncate font-medium">{me.email}</p>
            <p className="text-muted">{me.tenant_name} · {me.role}</p>
            <p className="mt-2 text-muted">Salesforce: {me.salesforce_mode} · AI: {me.ai_provider}</p>
            <button onClick={logout} className="mt-3 text-brand hover:underline">Sign out</button>
          </div>
        </aside>
        <main className="min-w-0 flex-1 px-5 py-6 md:px-10 md:py-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </MeContext.Provider>
  );
}
