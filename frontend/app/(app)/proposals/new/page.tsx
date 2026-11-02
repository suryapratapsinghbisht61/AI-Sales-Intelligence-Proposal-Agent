"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { api, useApi } from "@/lib/api";
import { useMe } from "@/components/app/shell";
import { ErrorBox, Field, NativeSelect, PageHeader } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Line = { price_item_id: string; quantity: number };

export default function NewProposal() {
  const router = useRouter();
  const me = useMe();
  const { data: prospects } = useApi<{ items: any[] }>("/prospects?limit=200&sort=name&desc=false");
  const { data: prices } = useApi<any[]>("/price-items");
  const [prospect, setProspect] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [currency, setCurrency] = useState("USD");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setProspect(new URLSearchParams(window.location.search).get("prospect") ?? ""); }, []);
  const { data: org } = useApi("/organizations/current");
  useEffect(() => { if (org?.currency) setCurrency(org.currency); }, [org]);

  const active = prices?.filter((p) => p.active && p.currency === currency) ?? [];
  const byId = Object.fromEntries((prices ?? []).map((p) => [p.id, p]));
  const total = lines.reduce((s, l) => s + Number(byId[l.price_item_id]?.unit_price ?? 0) * l.quantity, 0);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const s = (k: string) => String(f.get(k) ?? "");
    setBusy(true);
    setError(null);
    try {
      const p = await api("/proposals", { json: {
        prospect_id: prospect, title: s("title"), offerings: s("offerings"), requirements: s("requirements"),
        timeline: s("timeline"), assumptions: s("assumptions"), exclusions: s("exclusions"),
        payment_terms: s("payment_terms"), currency, price_lines: lines.filter((l) => l.price_item_id),
      } });
      router.push(`/proposals/${p.id}`);
    } catch (err) { setError(err); setBusy(false); }
  }

  return (
    <>
      <PageHeader title="New proposal" description="SalesPilot drafts each section from your Knowledge Base. Prices are computed from the approved price list only." />
      <form onSubmit={submit} className="max-w-3xl space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Prospect" htmlFor="prospect">
            <NativeSelect id="prospect" required value={prospect} onChange={(e) => setProspect(e.target.value)}>
              <option value="">Select a prospect…</option>
              {prospects?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Proposal title" htmlFor="title"><Input id="title" name="title" required maxLength={300} /></Field>
        </div>
        <Field label="Products / services to propose" htmlFor="offerings"><Textarea id="offerings" name="offerings" rows={2} /></Field>
        <Field label="Customer requirements" htmlFor="requirements" hint="Paste the brief or RFP text. Missing requirements are flagged as placeholders, never invented.">
          <Textarea id="requirements" name="requirements" rows={6} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Timeline" htmlFor="timeline"><Textarea id="timeline" name="timeline" rows={2} /></Field>
          <Field label="Payment terms" htmlFor="payment_terms" hint="Only as supplied by an authorised team member."><Textarea id="payment_terms" name="payment_terms" rows={2} /></Field>
          <Field label="Assumptions" htmlFor="assumptions"><Textarea id="assumptions" name="assumptions" rows={2} /></Field>
          <Field label="Exclusions" htmlFor="exclusions"><Textarea id="exclusions" name="exclusions" rows={2} /></Field>
        </div>

        <fieldset className="space-y-3 rounded-lg border p-4">
          <legend className="px-1 text-sm font-medium">Pricing</legend>
          <div className="flex items-center gap-2">
            <label htmlFor="currency" className="text-sm">Currency</label>
            <Input id="currency" className="w-20" maxLength={3} value={currency} onChange={(e) => { setCurrency(e.target.value.toUpperCase()); setLines([]); }} />
          </div>
          {prices && active.length === 0 && (
            <p className="text-sm text-muted-foreground">No approved {currency} price items.{" "}
              {me.permissions.includes("pricing.manage") ? <Link href="/settings#pricing" className="text-primary hover:underline">Add them in Settings</Link> : "Ask an admin to add them."}{" "}
              Pricing will be marked “to be confirmed”.</p>
          )}
          {lines.map((l, i) => (
            <div key={i} className="flex items-center gap-2">
              <NativeSelect aria-label="Price item" value={l.price_item_id} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, price_item_id: e.target.value } : x))}>
                <option value="">Select item…</option>
                {active.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.unit_price} {p.currency}/{p.unit}</option>)}
              </NativeSelect>
              <Input aria-label="Quantity" type="number" min={0.01} step="any" className="w-24" value={l.quantity}
                onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, quantity: Number(e.target.value) } : x))} />
              <Button type="button" variant="ghost" size="icon" aria-label="Remove line" onClick={() => setLines(lines.filter((_, j) => j !== i))}><Trash2 /></Button>
            </div>
          ))}
          {active.length > 0 && <Button type="button" variant="outline" size="sm" onClick={() => setLines([...lines, { price_item_id: "", quantity: 1 }])}>Add price line</Button>}
          {lines.length > 0 && <p className="text-sm">Estimated total: <b className="tabular-nums">{currency} {total.toFixed(2)}</b> <span className="text-muted-foreground">(final figures are computed by the server)</span></p>}
        </fieldset>
        <ErrorBox error={error} />
        <Button type="submit" disabled={busy || !prospect}>{busy ? "Starting…" : "Generate draft"}</Button>
      </form>
    </>
  );
}
