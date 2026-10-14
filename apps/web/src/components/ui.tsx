import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function Button({ variant = "primary", className, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  return (
    <button
      {...p}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-brand text-brand-ink hover:bg-[#094d8f]",
        variant === "secondary" && "border border-line bg-surface text-ink hover:bg-bg",
        variant === "ghost" && "text-brand hover:bg-brand-soft",
        variant === "danger" && "border border-line bg-surface text-bad hover:bg-bad-soft",
        className,
      )}
    />
  );
}

export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cx("w-full rounded-md border border-line bg-surface px-3 py-2 text-sm placeholder:text-muted/70", p.className)} />;
}

export function Textarea(p: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...p} className={cx("w-full rounded-md border border-line bg-surface px-3 py-2 text-sm", p.className)} />;
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-4 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "bad" | "brand"; children: ReactNode }) {
  return (
    <span className={cx(
      "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
      tone === "neutral" && "bg-bg text-muted",
      tone === "ok" && "bg-ok-soft text-ok",
      tone === "warn" && "bg-warn-soft text-warn",
      tone === "bad" && "bg-bad-soft text-bad",
      tone === "brand" && "bg-brand-soft text-brand",
    )}>{children}</span>
  );
}

export function statusTone(s: string): "ok" | "warn" | "bad" | "neutral" | "brand" {
  if (["active", "succeeded", "success", "validated"].includes(s)) return "ok";
  if (["rejected", "failure", "failed", "error", "revoked"].includes(s)) return "bad";
  if (["queued", "running", "partial", "planned"].includes(s)) return "warn";
  return "neutral";
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <pre className="overflow-x-auto rounded-md border border-line bg-[#0f1722] p-3 font-mono text-xs leading-relaxed text-[#e6edf3] whitespace-pre-wrap break-words">{children}</pre>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 text-muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as { message?: string; code?: string; correlationId?: string };
  return (
    <div role="alert" className="rounded-md border border-bad/30 bg-bad-soft px-3 py-2 text-bad">
      <span className="font-medium">{e.message ?? "Something went wrong"}</span>
      {e.correlationId && <span className="ml-2 font-mono text-xs opacity-80">ref {e.correlationId.slice(0, 12)}</span>}
    </div>
  );
}

export function DataTable({ columns, rows, empty = "No rows" }: { columns: string[]; rows: Record<string, unknown>[]; empty?: string }) {
  if (!rows.length) return <Empty title={empty} />;
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-bg text-xs uppercase tracking-wide text-muted">
          <tr>{columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {columns.map((c) => (
                <td key={c} className={cx("whitespace-nowrap px-3 py-2", typeof r[c] === "number" && "text-right tabular-nums")}>
                  {r[c] == null ? <span className="text-muted">—</span> : typeof r[c] === "number" ? (r[c] as number).toLocaleString() : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link href={href} className="font-medium text-brand hover:underline">{children}</Link>;
}
