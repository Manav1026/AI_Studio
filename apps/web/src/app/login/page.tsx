"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, ErrorNote, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/dev-login", { method: "POST", json: { email } });
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-line bg-surface p-6">
        <h1 className="text-lg font-semibold">Sign in</h1>
        <p className="mt-1 text-muted">
          Prototype sign-in for controlled users. Production replaces this with your OIDC identity provider.
          You will never be asked for your Salesforce password.
        </p>
        <label htmlFor="email" className="mt-5 block text-xs font-medium text-muted">Work email</label>
        <Input id="email" type="email" required autoComplete="email" value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="mt-1" />
        <div className="mt-4"><ErrorNote error={error} /></div>
        <Button type="submit" disabled={busy} className="mt-4 w-full">{busy ? "Signing in…" : "Continue"}</Button>
      </form>
    </div>
  );
}
