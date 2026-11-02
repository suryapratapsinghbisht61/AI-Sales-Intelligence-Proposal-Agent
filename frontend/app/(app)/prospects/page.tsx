"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { Building2, Download, Plus, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, download, fmtDate, useApi } from "@/lib/api";
import { ProspectFields, prospectPayload } from "@/components/app/prospect-form";
import { EmptyState, ErrorBox, Loading, NativeSelect, PageHeader, StatusBadge } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function Prospects() {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("created_at");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { data, error: loadErr, mutate } = useApi<{ items: any[]; total: number }>(
    `/prospects?q=${encodeURIComponent(q)}&sort=${sort}&desc=${sort !== "name"}`);

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      await api("/prospects", { json: prospectPayload(new FormData(e.currentTarget)) });
      setAdding(false);
      setError(null);
      mutate();
    } catch (err) { setError(err); }
  }

  async function importCsv(file: File) {
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await api("/prospects/import", { form });
      toast.success(`Imported ${r.created}. Skipped ${r.skipped_duplicates.length} duplicates, ${r.errors.length} invalid rows.`);
      mutate();
    } catch (e) { toast.error((e as Error).message); }
  }

  return (
    <>
      <PageHeader title="Prospects" description="Companies you are selling to. Prospect data is kept separate from your company knowledge."
        actions={<>
          <Button variant="outline" onClick={() => fileRef.current?.click()}><Upload /> Import CSV</Button>
          <input ref={fileRef} type="file" accept=".csv" hidden onChange={(e) => { if (e.target.files?.[0]) importCsv(e.target.files[0]); e.target.value = ""; }} />
          <Button variant="outline" onClick={() => download("/prospects/export")}><Download /> Export</Button>
          <Button onClick={() => setAdding(true)}><Plus /> Add prospect</Button>
        </>} />
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>Add prospect</DialogTitle></DialogHeader>
          <form onSubmit={create} className="space-y-4"><ProspectFields /><ErrorBox error={error} />
            <DialogFooter><Button type="submit">Save prospect</Button></DialogFooter></form>
        </DialogContent>
      </Dialog>
      <p className="mb-3 text-xs text-muted-foreground">CSV columns: name, domain, industry, location, company_size, description, source_url, tags (semicolon separated).</p>
      <div className="mb-3 flex flex-wrap gap-2">
        <Input aria-label="Search prospects" placeholder="Search name, domain, industry…" className="max-w-xs" value={q} onChange={(e) => setQ(e.target.value)} />
        <NativeSelect aria-label="Sort by" className="w-48" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="created_at">Newest</option><option value="score">Highest score</option>
          <option value="last_researched_at">Recently researched</option><option value="name">Name</option>
        </NativeSelect>
      </div>
      <ErrorBox error={loadErr} retry={() => mutate()} />
      {!data ? <Loading /> : data.items.length === 0 ? (
        <EmptyState icon={Building2} title="No prospects yet">Add a prospect manually or import a CSV.</EmptyState>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Company</TableHead><TableHead className="hidden md:table-cell">Industry</TableHead>
              <TableHead>Score</TableHead><TableHead>Research</TableHead><TableHead className="hidden md:table-cell">Last researched</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.items.map((p) => (
                <TableRow key={p.id}>
                  <TableCell><Link className="font-medium hover:underline" href={`/prospects/${p.id}`}>{p.name}</Link>
                    <span className="block text-xs text-muted-foreground">{p.domain}</span></TableCell>
                  <TableCell className="hidden md:table-cell">{p.industry || "—"}</TableCell>
                  <TableCell className="tabular-nums">{p.score ?? "—"}</TableCell>
                  <TableCell><StatusBadge status={p.research_status} /></TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{fmtDate(p.last_researched_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
