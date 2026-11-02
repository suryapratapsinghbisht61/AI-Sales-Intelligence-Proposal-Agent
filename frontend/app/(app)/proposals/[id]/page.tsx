"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertTriangle, Download, FileText, History, Pencil, RefreshCw, Send } from "lucide-react";
import { toast } from "sonner";
import { api, download, fmtDate, useApi } from "@/lib/api";
import { ErrorBox, Loading, Md, PageHeader, StatusBadge } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const EDITABLE = ["draft", "changes_requested", "rejected"];

function Section({ s, editable, onSave, onRegen }: { s: any; editable: boolean; onSave: (c: string) => Promise<void>; onRegen: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(s.content);
  useEffect(() => setText(s.content), [s.content]);
  return (
    <section className="rounded-lg border p-4" aria-labelledby={`h-${s.key}`}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id={`h-${s.key}`} className="font-medium">{s.title}</h2>
        {editable && !editing && (
          <div className="flex gap-1">
            <Button size="xs" variant="ghost" onClick={() => setEditing(true)}><Pencil /> Edit</Button>
            {s.key !== "pricing" && <Button size="xs" variant="ghost" onClick={onRegen}><RefreshCw /> Regenerate</Button>}
          </div>
        )}
      </div>
      {!!s.flags?.length && (
        <ul className="mb-3 space-y-1 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs">
          {s.flags.map((f: string) => <li key={f} className="flex gap-1.5"><AlertTriangle className="size-3.5 shrink-0 text-amber-600" aria-hidden />{f}</li>)}
        </ul>
      )}
      {editing ? (
        <div className="space-y-2">
          <Textarea aria-label={`Edit ${s.title}`} rows={10} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex gap-2">
            <Button size="sm" onClick={async () => { await onSave(text); setEditing(false); }}>Save as new version</Button>
            <Button size="sm" variant="ghost" onClick={() => { setText(s.content); setEditing(false); }}>Cancel</Button>
          </div>
          {s.key === "pricing" && <p className="text-xs text-muted-foreground">Any amount not on the approved price list will be flagged for the approver.</p>}
        </div>
      ) : <Md>{s.content}</Md>}
      {!!s.sources?.length && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-muted-foreground">{s.sources.length} supporting source{s.sources.length > 1 && "s"}</summary>
          <ul className="mt-2 space-y-1.5">
            {s.sources.map((src: any) => (
              <li key={src.chunk_id} className="rounded border p-2">
                <a href={`/knowledge/${src.document_id}`} className="flex items-center gap-1 font-medium hover:underline"><FileText className="size-3" aria-hidden />{src.title}{src.page && ` · p. ${src.page}`}</a>
                <p className="mt-1 line-clamp-3 text-muted-foreground">{src.excerpt}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export default function ProposalEditor() {
  const { id } = useParams<{ id: string }>();
  const [viewing, setViewing] = useState<number | null>(null);
  const { data: p, error, mutate } = useApi(`/proposals/${id}`, {
    refreshInterval: (x) => (x?.status === "generating" ? 2500 : 0),
  });
  const { data: versions, mutate: refreshVersions } = useApi<any[]>(`/proposals/${id}/versions`);
  const { data: old } = useApi(viewing ? `/proposals/${id}/versions/${viewing}` : null);

  useEffect(() => { refreshVersions(); }, [p?.current_version, refreshVersions]);

  if (error) return <ErrorBox error={error} retry={() => mutate()} />;
  if (!p) return <Loading />;

  const editable = EDITABLE.includes(p.status) && !viewing;
  const v = viewing ? old : p.version;

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); mutate(); } catch (e) { toast.error((e as Error).message); mutate(); }
  };
  const save = (key: string, content: string) => run(() => api(`/proposals/${id}`, { method: "PATCH",
    json: { base_version: p.current_version, sections: [{ key, content }], note: `Edited ${key.replaceAll("_", " ")}` } }), "Saved as a new version");
  const regen = (section?: string) => run(() => api(`/proposals/${id}/regenerate`, { json: { section: section ?? null } }), "Regenerating…");

  return (
    <>
      <PageHeader title={p.title} description={`For ${p.prospect_name} · version ${p.current_version}`}
        actions={<>
          <StatusBadge status={p.status} />
          {p.current_version > 0 && <Button variant="outline" onClick={() => download(`/proposals/${id}/export`, "POST").catch((e) => toast.error(e.message))}><Download /> Export DOCX</Button>}
          {EDITABLE.includes(p.status) && p.current_version > 0 && (
            <Button onClick={() => run(() => api(`/proposals/${id}/submit`, { method: "POST" }), "Submitted for approval")}><Send /> Submit for approval</Button>
          )}
        </>} />
      {p.status === "generating" && <p className="mb-4 animate-pulse text-sm text-muted-foreground">Drafting from your Knowledge Base… this can take a minute.</p>}
      {p.error && <div className="mb-4"><ErrorBox error={p.error} retry={() => regen()} /></div>}
      {p.status === "pending_approval" && <p className="mb-4 text-sm text-muted-foreground">Waiting for approval. Editing is locked until a decision is made.</p>}

      <div className="grid gap-6 lg:grid-cols-[1fr_240px]">
        <div className="space-y-4">
          {viewing && <div className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm">Viewing version {viewing} (read-only) <Button size="sm" variant="outline" onClick={() => setViewing(null)}>Back to current</Button></div>}
          {!!v?.warnings?.length && (
            <ul className="space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
              {v.warnings.map((w: string) => <li key={w}>⚠ {w}</li>)}
            </ul>
          )}
          {!v ? (p.status !== "generating" && !p.error && <Loading />) : v.sections.map((s: any) => (
            <Section key={s.key} s={s} editable={editable} onSave={(c) => save(s.key, c)} onRegen={() => regen(s.key)} />
          ))}
        </div>
        <aside className="space-y-3">
          <h2 className="flex items-center gap-1.5 text-sm font-medium"><History className="size-4" aria-hidden /> Version history</h2>
          <ul className="space-y-1 text-sm">
            {versions?.map((x) => (
              <li key={x.version}>
                <button onClick={() => setViewing(x.version === p.current_version ? null : x.version)}
                  className={`w-full rounded-md px-2 py-1.5 text-left hover:bg-muted ${(viewing ?? p.current_version) === x.version ? "bg-muted" : ""}`}>
                  <span className="font-medium">v{x.version}</span> · {x.note}
                  <span className="block text-xs text-muted-foreground">{x.created_by ?? "AI"} · {fmtDate(x.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
          {editable && p.current_version > 0 && <Button variant="outline" size="sm" className="w-full" onClick={() => regen()}><RefreshCw /> Regenerate all sections</Button>}
        </aside>
      </div>
    </>
  );
}
