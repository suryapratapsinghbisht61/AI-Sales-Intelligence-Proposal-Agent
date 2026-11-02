"use client";

import Link from "next/link";
import { useMe } from "@/components/app/shell";
import { PageHeader } from "@/components/app/ui";

export default function Account() {
  const me = useMe();
  return (
    <>
      <PageHeader title="Your account" />
      <dl className="max-w-lg divide-y rounded-lg border text-sm">
        <div className="flex justify-between px-4 py-3"><dt className="text-muted-foreground">Name</dt><dd>{me.user.name || "—"}</dd></div>
        <div className="flex justify-between px-4 py-3"><dt className="text-muted-foreground">Email</dt><dd>{me.user.email}</dd></div>
        <div className="flex justify-between px-4 py-3"><dt className="text-muted-foreground">Organizations</dt>
          <dd className="text-right">{me.organizations.map((o) => <span key={o.id} className="block">{o.name} · {o.role.replace("_", " ")}</span>)}</dd></div>
      </dl>
      <p className="mt-4 text-sm"><Link className="text-primary hover:underline" href="/forgot-password">Change password</Link> (sends a reset link)</p>
    </>
  );
}
