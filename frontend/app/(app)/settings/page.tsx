"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, useApi } from "@/lib/api";
import { can, useMe } from "@/components/app/shell";
import { OrgFields, orgPayload } from "@/components/app/org-form";
import { ErrorBox, Loading, PageHeader } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

function OrgSettings({ editable }: { editable: boolean }) {
  const { data: org, mutate } = useApi("/organizations/current");
  if (!org) return <Loading />;
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try { await api("/organizations/current", { method: "PATCH", json: { ...orgPayload(new FormData(e.currentTarget)), onboarding_completed: true } }); toast.success("Saved"); mutate(); }
    catch (err) { toast.error((err as Error).message); }
  }
  return (
    <form onSubmit={save} className="space-y-4">
      <OrgFields org={org} disabled={!editable} />
      {editable ? <Button type="submit">Save profile</Button> : <p className="text-xs text-muted-foreground">Only owners and admins can edit the organization profile.</p>}
    </form>
  );
}

function Pricing({ editable }: { editable: boolean }) {
  const { data, error, mutate } = useApi<any[]>("/price-items");
  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api("/price-items", { json: { name: f.get("name"), unit: f.get("unit") || "unit", unit_price: f.get("unit_price"), currency: String(f.get("currency")).toUpperCase(), description: "" } });
      e.currentTarget?.reset();
      mutate();
    } catch (err) { toast.error((err as Error).message); }
  }
  const toggle = async (i: any) => {
    try { await api(`/price-items/${i.id}`, { method: "PUT", json: { ...i, active: !i.active } }); mutate(); } catch (err) { toast.error((err as Error).message); }
  };
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">Proposals can only price from this list. Every change is recorded in the audit log.</p>
      <ErrorBox error={error} />
      {data && data.length > 0 && (
        <div className="rounded-lg border"><Table>
          <TableHeader><TableRow><TableHead>Item</TableHead><TableHead>Unit</TableHead><TableHead className="text-right">Price</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>{data.map((i) => (
            <TableRow key={i.id}><TableCell>{i.name}</TableCell><TableCell>{i.unit}</TableCell>
              <TableCell className="text-right tabular-nums">{i.unit_price} {i.currency}</TableCell>
              <TableCell>{editable ? <Button size="xs" variant="ghost" onClick={() => toggle(i)}>{i.active ? "Active · deactivate" : "Inactive · activate"}</Button> : i.active ? "Active" : "Inactive"}</TableCell></TableRow>
          ))}</TableBody>
        </Table></div>
      )}
      {editable && (
        <form onSubmit={add} className="flex flex-wrap items-end gap-2">
          <Input aria-label="Item name" name="name" placeholder="Item name" required className="w-56" />
          <Input aria-label="Unit" name="unit" placeholder="Unit (e.g. month)" className="w-36" />
          <Input aria-label="Unit price" name="unit_price" type="number" min="0" step="0.01" placeholder="Price" required className="w-28" />
          <Input aria-label="Currency" name="currency" defaultValue="USD" maxLength={3} className="w-20" />
          <Button type="submit" variant="outline"><Plus /> Add</Button>
        </form>
      )}
    </div>
  );
}

function Rubric({ editable }: { editable: boolean }) {
  const { data, mutate } = useApi("/rubric");
  const [criteria, setCriteria] = useState<any[]>([]);
  useEffect(() => { if (data) setCriteria(data.criteria); }, [data]);
  if (!data) return <Loading rows={3} />;
  const set = (i: number, k: string, v: unknown) => setCriteria(criteria.map((c, j) => (j === i ? { ...c, [k]: v } : c)));
  async function save() {
    try { await api("/rubric", { method: "PUT", json: { criteria } }); toast.success("Saved as a new rubric version"); mutate(); }
    catch (err) { toast.error((err as Error).message); }
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">Version {data.version}. Saving creates a new version; past scores keep the version they were scored with.</p>
      {criteria.map((c, i) => (
        <div key={i} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[160px_1fr_80px_auto]">
          <Input aria-label="Label" value={c.label} disabled={!editable} onChange={(e) => set(i, "label", e.target.value)} />
          <Input aria-label="Description" value={c.description} disabled={!editable} onChange={(e) => set(i, "description", e.target.value)} />
          <Input aria-label="Weight" type="number" min={0} max={100} value={c.weight} disabled={!editable} onChange={(e) => set(i, "weight", Number(e.target.value))} />
          {editable && <Button variant="ghost" size="icon" aria-label="Remove criterion" onClick={() => setCriteria(criteria.filter((_, j) => j !== i))}><Trash2 /></Button>}
        </div>
      ))}
      {editable && (
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setCriteria([...criteria, { key: `custom_${criteria.length + 1}`, label: "New criterion", description: "Describe what evidence counts", weight: 10 }])}><Plus /> Add criterion</Button>
          <Button onClick={save}>Save rubric</Button>
        </div>
      )}
    </div>
  );
}

export default function Settings() {
  const me = useMe();
  return (
    <>
      <PageHeader title="Settings" description="Organization profile, approved pricing and qualification rubric." />
      <div className="space-y-10">
        <section><h2 className="mb-4 font-medium">Company profile</h2><OrgSettings editable={can(me, "org.manage")} /></section>
        <section id="pricing"><h2 className="mb-4 font-medium">Approved price list</h2><Pricing editable={can(me, "pricing.manage")} /></section>
        <section><h2 className="mb-4 font-medium">Qualification rubric</h2><Rubric editable={can(me, "rubric.manage")} /></section>
      </div>
    </>
  );
}
