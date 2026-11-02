"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { AuthCard } from "@/components/app/auth-card";
import { ErrorBox, Field } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function Login() {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { json: { email: f.get("email"), password: f.get("password") } });
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = next?.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Sign in" subtitle="Welcome back to SalesPilot."
      footer={<>New here? <Link className="text-primary hover:underline" href="/signup">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Work email" htmlFor="email"><Input id="email" name="email" type="email" autoComplete="email" required /></Field>
        <Field label="Password" htmlFor="password"><Input id="password" name="password" type="password" autoComplete="current-password" required /></Field>
        <ErrorBox error={error} />
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <Link href="/forgot-password" className="block text-center text-sm text-muted-foreground hover:text-foreground">Forgot your password?</Link>
      </form>
    </AuthCard>
  );
}
