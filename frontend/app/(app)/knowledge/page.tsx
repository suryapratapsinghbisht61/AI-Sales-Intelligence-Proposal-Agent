"use client";

import Link from "next/link";
import { useState } from "react";
import { BookOpen, RotateCw, Search, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, fmtDate, useApi } from "@/lib/api";
import { ACCEPT, CATEGORIES } from "@/components/app/categories";
import { EmptyState, ErrorBox, Field, Loading, NativeSelect, PageHeader, StatusBadge } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

function UploadDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/documents", { form: new FormData(e.currentTarget) });
      toast.success("Uploaded. Processing has started.");
      onDone();
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Upload a document</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <Field label="File" htmlFor="file" hint="PDF, DOCX, XLSX, TXT, Markdown or CSV, up to 20 MB.">
            <Input id="file" name="file" type="file" accept={ACCEPT} required />
          </Field>
          <Field label="Title" htmlFor="title" hint="Defaults to the file name."><Input id="title" name="title" /></Field>
          <Field label="Category" htmlFor="category">
            <NativeSelect id="category" name="category" defaultValue="product_docs">
              {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Tags" htmlFor="tags" hint="Comma separated."><Input id="tags" name="tags" /></Field>
          <ErrorBox error={error} />
          <DialogFooter><Button type="submit" disabled={busy}>{busy ? "Uploading…" : "Upload"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function Knowledge() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any>(null);
  const [searchErr, setSearchErr] = useState<unknown>(null);
  const { data, error, mutate } = useApi<{ items: any[]; total: number }>(
    `/documents?q=${encodeURIComponent(q)}&category=${category}`,
    { refreshInterval: (d) => (d?.items.some((x: any) => x.status === "uploaded" || x.status === "processing") ? 2000 : 0) },
  );

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return setResults(null);
    setSearchErr(null);
    try { setResults(await api("/knowledge/search", { json: { query } })); } catch (err) { setSearchErr(err); }
  }

  async function retry(id: string) {
    try { await api(`/documents/${id}/retry`, { method: "POST" }); mutate(); } catch (e) { toast.error((e as Error).message); }
  }

  return (
    <>
      <PageHeader title="Knowledge Base" description="The source of truth for answers and proposals."
        actions={<Button onClick={() => setUploading(true)}><Upload /> Upload</Button>} />
      <UploadDialog open={uploading} onClose={() => setUploading(false)} onDone={() => mutate()} />

      <form onSubmit={search} className="mb-6 flex gap-2" role="search">
        <label htmlFor="kb-search" className="sr-only">Search document contents</label>
        <Input id="kb-search" placeholder="Search inside your documents…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button type="submit" variant="outline"><Search /> Search</Button>
      </form>
      <ErrorBox error={searchErr} />
      {results && (
        <section className="mb-8 space-y-2" aria-label="Search results">
          <p className="text-xs text-muted-foreground">{results.results.length} passages · {results.mode} search</p>
          {results.results.length === 0 && <p className="text-sm">No matching passages.</p>}
          {results.results.map((r: any) => (
            <Link key={r.chunk_id} href={`/knowledge/${r.document_id}`} className="block rounded-lg border p-3 hover:bg-muted/40">
              <p className="text-sm font-medium">{r.title} <span className="font-normal text-muted-foreground">{[r.page && `p. ${r.page}`, r.section].filter(Boolean).join(" · ")}</span></p>
              <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{r.excerpt}</p>
            </Link>
          ))}
        </section>
      )}

      <div className="mb-3 flex flex-wrap gap-2">
        <Input aria-label="Filter by title" placeholder="Filter by title…" className="max-w-xs" value={q} onChange={(e) => setQ(e.target.value)} />
        <NativeSelect aria-label="Category" className="w-52" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </NativeSelect>
      </div>
      <ErrorBox error={error} retry={() => mutate()} />
      {!data ? <Loading /> : data.items.length === 0 ? (
        <EmptyState icon={BookOpen} title={q || category ? "No documents match" : "No documents yet"}>
          Upload product documentation, pricing sheets, case studies and playbooks.
        </EmptyState>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Title</TableHead><TableHead className="hidden md:table-cell">Category</TableHead>
              <TableHead>Status</TableHead><TableHead className="hidden md:table-cell">Updated</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {data.items.map((d) => (
                <TableRow key={d.id}>
                  <TableCell><Link href={`/knowledge/${d.id}`} className="font-medium hover:underline">{d.title}</Link>
                    <span className="block text-xs text-muted-foreground">{d.filename} · v{d.version}</span></TableCell>
                  <TableCell className="hidden md:table-cell">{CATEGORIES[d.category]}</TableCell>
                  <TableCell><StatusBadge status={d.status} />
                    {d.error && <span className="mt-1 block max-w-xs whitespace-normal text-xs text-destructive">{d.error}</span>}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{fmtDate(d.updated_at)}</TableCell>
                  <TableCell className="text-right">
                    {d.status === "failed" && <Button size="sm" variant="outline" onClick={() => retry(d.id)}><RotateCw /> Retry</Button>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
