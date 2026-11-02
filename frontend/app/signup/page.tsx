"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { AuthCard } from "@/components/app/auth-card";
import { ErrorBox, Field } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function Signup() {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api("/auth/signup", { json: { name: f.get("name"), email: f.get("email"), password: f.get("password") } });
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = next?.startsWith("/") && !next.startsWith("//") ? next : "/onboarding";
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Create your account" subtitle="Set up SalesPilot for your sales team."
      footer={<>Already have an account? <Link className="text-primary hover:underline" href="/login">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Full name" htmlFor="name"><Input id="name" name="name" autoComplete="name" /></Field>
        <Field label="Work email" htmlFor="email"><Input id="email" name="email" type="email" autoComplete="email" required /></Field>
        <Field label="Password" htmlFor="password" hint="At least 10 characters.">
          <Input id="password" name="password" type="password" minLength={10} autoComplete="new-password" required />
        </Field>
        <ErrorBox error={error} />
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating account…" : "Create account"}</Button>
      </form>
    </AuthCard>
  );
}
