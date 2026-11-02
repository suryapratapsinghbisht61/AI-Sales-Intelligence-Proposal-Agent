"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Copy, FileText, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, fmtDate, useApi } from "@/lib/api";
import { ProspectFields, prospectPayload } from "@/components/app/prospect-form";
import { ResearchView } from "@/components/app/research-view";
import { ErrorBox, Field, Loading, PageHeader, StatusBadge } from "@/components/app/ui";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

function Draft({ d, onChange }: { d: any; onChange: () => void }) {
  const [subject, setSubject] = useState(d.subject);
  const [body, setBody] = useState(d.body);
  const save = async (extra = {}) => {
    try { await api(`/drafts/${d.id}`, { method: "PATCH", json: { subject, body, ...extra } }); toast.success("Saved"); onChange(); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center justify-between"><StatusBadge status={d.status} /><span className="text-xs text-muted-foreground">{fmtDate(d.created_at)}</span></div>
      <Field label="Subject" htmlFor={`s-${d.id}`}><Input id={`s-${d.id}`} value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
      <Field label="Message" htmlFor={`b-${d.id}`}><Textarea id={`b-${d.id}`} rows={8} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
      <p className="text-xs text-muted-foreground"><b>Why it&apos;s personalised:</b> {d.rationale}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => save()}>Save</Button>
        <Button size="sm" variant="outline" onClick={() => { navigator.clipboard.writeText(`${subject}\n\n${body}`); toast.success("Copied"); }}><Copy /> Copy</Button>
        {d.status !== "sent" && <Button size="sm" variant="outline" onClick={() => save({ status: "sent" })}>Mark as sent</Button>}
      </div>
    </div>
  );
}

export default function ProspectDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const { data: p, error: loadErr, mutate } = useApi(`/prospects/${id}`, {
    refreshInterval: (x) => (x && ["queued", "running"].includes(x.research_status) ? 2500 : 0),
  });

  if (loadErr) return <ErrorBox error={loadErr} retry={() => mutate()} />;
  if (!p) return <Loading />;
  const busy = ["queued", "running"].includes(p.research_status);

  async function research(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setError(null);
    try {
      const r = await api(`/prospects/${id}/research`, { json: { target_offering: f.get("target_offering"), notes: f.get("notes"), force: f.get("force") === "on" } });
      if (r.cached) toast.info("Showing recent research. Tick “Run fresh research” to redo it.");
      mutate();
    } catch (err) { setError(err); }
  }

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try { await api(`/prospects/${id}`, { method: "PATCH", json: prospectPayload(new FormData(e.currentTarget)) }); toast.success("Saved"); mutate(); }
    catch (err) { toast.error((err as Error).message); }
  }

  async function remove() {
    if (!confirm(`Delete ${p.name} and all its research?`)) return;
    await api(`/prospects/${id}`, { method: "DELETE" });
    router.push("/prospects");
  }

  return (
    <>
      <PageHeader title={p.name} description={[p.domain, p.industry, p.location].filter(Boolean).join(" · ")}
        actions={<>
          <Link href={`/proposals/new?prospect=${id}`} className={buttonVariants()}><FileText /> New proposal</Link>
          <Button variant="outline" size="icon" aria-label="Delete prospect" onClick={remove}><Trash2 /></Button>
        </>} />
      {p.description && <p className="mb-6 max-w-3xl text-sm text-muted-foreground">{p.description}</p>}
      <Tabs defaultValue="research">
        <TabsList>
          <TabsTrigger value="research">Research</TabsTrigger>
          <TabsTrigger value="outreach">Outreach ({p.drafts.length})</TabsTrigger>
          <TabsTrigger value="details">Details</TabsTrigger>
        </TabsList>
        <TabsContent value="research" className="mt-4 space-y-6">
          <form onSubmit={research} className="space-y-3 rounded-lg border p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Offering to focus on (optional)" htmlFor="target_offering"><Input id="target_offering" name="target_offering" /></Field>
              <div className="flex items-end gap-2 text-sm"><input id="force" name="force" type="checkbox" className="mb-2" /><label htmlFor="force" className="mb-1.5">Run fresh research (ignore recent results)</label></div>
            </div>
            <Field label="Notes or pasted public information (optional)" htmlFor="notes"
              hint={p.domain ? `SalesPilot reads public pages on ${p.domain} (respecting robots.txt) plus anything you paste here.` : "No website set: research will use only what you paste here."}>
              <Textarea id="notes" name="notes" rows={3} />
            </Field>
            <ErrorBox error={error} />
            <Button type="submit" disabled={busy}><Search /> {busy ? "Researching…" : "Research company"}</Button>
          </form>
          {busy && <p className="animate-pulse text-sm text-muted-foreground">Research is {p.research_status}. This usually takes under a minute.</p>}
          {p.research?.status === "failed" && <ErrorBox error={`Research failed: ${p.research.error}`} />}
          {p.research?.status === "done" ? <ResearchView r={p.research} /> : !busy && !p.research && (
            <p className="text-sm text-muted-foreground">Not researched yet.</p>
          )}
        </TabsContent>
        <TabsContent value="outreach" className="mt-4 space-y-4">
          <p className="text-xs text-muted-foreground">Drafts are never sent automatically. Copy them into your email client, then mark them as sent.</p>
          {p.drafts.length === 0 ? <p className="text-sm text-muted-foreground">Research the company to generate an outreach draft from verified facts.</p>
            : p.drafts.map((d: any) => <Draft key={d.id} d={d} onChange={() => mutate()} />)}
        </TabsContent>
        <TabsContent value="details" className="mt-4">
          <form onSubmit={save} className="space-y-4 rounded-lg border p-4"><ProspectFields p={p} /><Button type="submit">Save changes</Button></form>
        </TabsContent>
      </Tabs>
    </>
  );
}
