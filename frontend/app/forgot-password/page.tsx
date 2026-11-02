"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { AuthCard } from "@/components/app/auth-card";
import { ErrorBox, Field } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ForgotPassword() {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      await api("/auth/password-reset/request", { json: { email: new FormData(e.currentTarget).get("email") } });
      setSent(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <AuthCard title="Reset your password" footer={<Link className="hover:text-foreground" href="/login">Back to sign in</Link>}>
      {sent ? (
        <p className="text-sm text-muted-foreground">
          If an account exists for that email, a reset link has been issued. Email delivery is not configured yet,
          so in development the link is written to the API server log.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Work email" htmlFor="email"><Input id="email" name="email" type="email" required /></Field>
          <ErrorBox error={error} />
          <Button type="submit" className="w-full">Send reset link</Button>
        </form>
      )}
    </AuthCard>
  );
}
