"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { AuthCard } from "@/components/app/auth-card";
import { ErrorBox, Field } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ResetPassword() {
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const token = new URLSearchParams(window.location.search).get("token") ?? "";
    try {
      await api("/auth/password-reset/confirm", { json: { token, password: new FormData(e.currentTarget).get("password") } });
      setDone(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <AuthCard title="Choose a new password">
      {done ? (
        <p className="text-sm">Password updated. <Link className="text-primary hover:underline" href="/login">Sign in</Link></p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="New password" htmlFor="password" hint="At least 10 characters. You will be signed out everywhere.">
            <Input id="password" name="password" type="password" minLength={10} autoComplete="new-password" required />
          </Field>
          <ErrorBox error={error} />
          <Button type="submit" className="w-full">Update password</Button>
        </form>
      )}
    </AuthCard>
  );
}
