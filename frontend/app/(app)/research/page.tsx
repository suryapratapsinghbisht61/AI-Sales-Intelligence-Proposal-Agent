"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Search } from "lucide-react";
import { api, fmtDate, useApi } from "@/lib/api";
import { EmptyState, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export default function Research() {
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data } = useApi<{ items: any[] }>("/prospects?sort=last_researched_at&limit=20");

  async function start(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const p = await api("/prospects", { json: { name: f.get("name"), domain: f.get("domain"), industry: f.get("industry") } });
      await api(`/prospects/${p.id}/research`, { json: { target_offering: f.get("target_offering"), notes: f.get("notes") } });
      router.push(`/prospects/${p.id}`);
    } catch (err) { setError(err); setBusy(false); }
  }

  const researched = data?.items.filter((p) => p.research_status !== "new") ?? [];
  return (
    <>
      <PageHeader title="Research" description="Research a company from its public website and your notes, then qualify it against your rubric." />
      <form onSubmit={start} className="mb-8 grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
        <Field label="Company name" htmlFor="name"><Input id="name" name="name" required /></Field>
        <Field label="Website / domain" htmlFor="domain"><Input id="domain" name="domain" placeholder="example.com" /></Field>
        <Field label="Industry (optional)" htmlFor="industry"><Input id="industry" name="industry" /></Field>
        <Field label="Offering to focus on (optional)" htmlFor="target_offering"><Input id="target_offering" name="target_offering" /></Field>
        <div className="sm:col-span-2"><Field label="Notes or pasted public information (optional)" htmlFor="notes"
          hint="Without a website, research uses only what you paste here."><Textarea id="notes" name="notes" rows={3} /></Field></div>
        <div className="sm:col-span-2"><ErrorBox error={error} /></div>
        <div><Button type="submit" disabled={busy}><Search /> {busy ? "Starting…" : "Start research"}</Button></div>
      </form>
      <h2 className="mb-3 text-sm font-medium">Recent research</h2>
      {!data ? <Loading /> : researched.length === 0 ? <EmptyState icon={Search} title="No research yet" /> : (
        <ul className="divide-y rounded-lg border">
          {researched.map((p) => (
            <li key={p.id}><Link href={`/prospects/${p.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm hover:bg-muted/40">
              <span className="font-medium">{p.name} <span className="font-normal text-muted-foreground">{p.domain}</span></span>
              <span className="flex items-center gap-3"><span className="tabular-nums">{p.score ?? "—"}</span><StatusBadge status={p.research_status} />
                <span className="text-xs text-muted-foreground">{fmtDate(p.last_researched_at)}</span></span>
            </Link></li>
          ))}
        </ul>
      )}
    </>
  );
}
