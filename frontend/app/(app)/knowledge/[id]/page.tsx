"use client";

import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Download, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, download, fmtDate, useApi } from "@/lib/api";
import { ACCEPT, CATEGORIES } from "@/components/app/categories";
import { ErrorBox, Field, Loading, NativeSelect, PageHeader, StatusBadge } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function DocumentDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [saving, setSaving] = useState(false);
  const { data: d, error, mutate } = useApi(`/documents/${id}`, {
    refreshInterval: (x) => (x && ["uploaded", "processing"].includes(x.status) ? 2000 : 0),
  });

  if (error) return <ErrorBox error={error} retry={() => mutate()} />;
  if (!d) return <Loading />;

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); mutate(); } catch (e) { toast.error((e as Error).message); }
  };

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setSaving(true);
    await act(() => api(`/documents/${id}`, { method: "PATCH", json: {
      title: f.get("title"), category: f.get("category"),
      tags: String(f.get("tags")).split(",").map((t) => t.trim()).filter(Boolean),
    } }), "Saved");
    setSaving(false);
  }

  async function replace(file: File) {
    const form = new FormData();
    form.append("file", file);
    await act(() => api(`/documents/${id}/replace`, { form }), "New version uploaded. Re-processing…");
  }

  async function remove() {
    if (!confirm(`Delete "${d.title}"? It will no longer be used in answers or proposals.`)) return;
    try { await api(`/documents/${id}`, { method: "DELETE" }); router.push("/knowledge"); } catch (e) { toast.error((e as Error).message); }
  }

  return (
    <>
      <PageHeader title={d.title} description={`${d.filename} · version ${d.version} · ${(d.size_bytes / 1024).toFixed(0)} KB · uploaded ${fmtDate(d.created_at)}`}
        actions={<>
          <Button variant="outline" onClick={() => download(`/documents/${id}/download`)}><Download /> Download</Button>
          <Button variant="outline" onClick={() => fileRef.current?.click()}><RefreshCw /> Replace</Button>
          <input ref={fileRef} type="file" accept={ACCEPT} hidden onChange={(e) => e.target.files?.[0] && replace(e.target.files[0])} />
          <Button variant="destructive" onClick={remove}><Trash2 /> Delete</Button>
        </>} />
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <section>
          <div className="mb-3 flex items-center gap-2 text-sm">
            <StatusBadge status={d.status} />
            {d.status === "ready" && <span className="text-muted-foreground">{d.chunk_count} passages indexed</span>}
            {d.status === "failed" && <Button size="sm" variant="outline" onClick={() => act(() => api(`/documents/${id}/retry`, { method: "POST" }), "Retrying")}>Retry processing</Button>}
          </div>
          {d.error && <ErrorBox error={d.error} />}
          <h2 className="mb-2 mt-4 text-sm font-medium">Extracted text preview</h2>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/30 p-4 font-sans text-sm text-muted-foreground">
            {d.text_preview || (d.status === "ready" ? "No text." : "Available once processing finishes.")}
          </pre>
        </section>
        <form onSubmit={save} className="space-y-4 rounded-lg border p-4">
          <Field label="Title" htmlFor="title"><Input id="title" name="title" defaultValue={d.title} required /></Field>
          <Field label="Category" htmlFor="category">
            <NativeSelect id="category" name="category" defaultValue={d.category}>
              {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Tags" htmlFor="tags" hint="Comma separated."><Input id="tags" name="tags" defaultValue={d.tags.join(", ")} /></Field>
          <Button type="submit" disabled={saving}>Save details</Button>
        </form>
      </div>
    </>
  );
}
