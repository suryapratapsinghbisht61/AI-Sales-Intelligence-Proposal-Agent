"use client";

import Link from "next/link";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { AuthCard } from "@/components/app/auth-card";
import { ErrorBox } from "@/components/app/ui";
import { Button } from "@/components/ui/button";

export default function Invite() {
  const { data: me, error: meError } = useApi("/me", { shouldRetryOnError: false });
  const [error, setError] = useState<unknown>(null);
  const here = typeof window === "undefined" ? "/invite" : window.location.pathname + window.location.search;

  async function accept() {
    try {
      await api("/invitations/accept", { json: { token: new URLSearchParams(window.location.search).get("token") } });
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err);
    }
  }

  return (
    <AuthCard title="Join your team on SalesPilot">
      {meError ? (
        <p className="text-sm">
          <Link className="text-primary hover:underline" href={`/signup?next=${encodeURIComponent(here)}`}>Create an account</Link> or{" "}
          <Link className="text-primary hover:underline" href={`/login?next=${encodeURIComponent(here)}`}>sign in</Link>{" "}
          with the email address the invitation was sent to.
        </p>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Signed in as {me?.user.email ?? "…"}</p>
          <ErrorBox error={error} />
          <Button className="w-full" onClick={accept} disabled={!me}>Accept invitation</Button>
        </div>
      )}
    </AuthCard>
  );
}
