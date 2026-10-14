export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown,
              public correlationId?: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api/v1${path}`, {
    credentials: "include",
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    let body: { error?: { code: string; message: string; details?: unknown; correlation_id?: string } } = {};
    try { body = await res.json(); } catch { /* non-JSON */ }
    const e = body.error;
    if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = "/login";
    }
    throw new ApiError(res.status, e?.code ?? "http_error", e?.message ?? res.statusText, e?.details, e?.correlation_id);
  }
  return res.json() as Promise<T>;
}

export const fmt = {
  date: (s: string | null | undefined) => (s ? new Date(s).toLocaleString() : "—"),
  num: (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString()),
  cell: (v: unknown) => {
    if (v == null) return "—";
    if (typeof v === "number") return v.toLocaleString();
    if (typeof v === "boolean") return v ? "true" : "false";
    return String(v);
  },
};
