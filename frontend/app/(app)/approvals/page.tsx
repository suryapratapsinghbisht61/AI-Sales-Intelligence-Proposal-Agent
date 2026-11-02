"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckSquare } from "lucide-react";
import { toast } from "sonner";
import { api, fmtDate, useApi } from "@/lib/api";
import { can, useMe } from "@/components/app/shell";
import { EmptyState, ErrorBox, Loading, NativeSelect, PageHeader, StatusBadge } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

function Item({ a, canDecide, onDone }: { a: any; canDecide: boolean; onDone: () => void }) {
  const [comment, setComment] = useState("");
  const [history, setHistory] = useState<any[] | null>(null);
  const decide = async (action: string) => {
    try { await api(`/approvals/${a.id}/${action}`, { json: { comment } }); toast.success("Decision recorded"); onDone(); }
    catch (e) { toast.error((e as Error).message); }
  };
  const s = a.summary;
  return (
    <li className="space-y-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link href={`/proposals/${a.target_id}`} className="font-medium hover:underline">{s.title}</Link>
          <p className="text-xs text-muted-foreground">Proposal approval · version {a.target_version} · requested by {a.requested_by} · {fmtDate(a.created_at)}</p>
        </div>
        <StatusBadge status={a.status} />
      </div>
      <p className="text-sm">Total: <b className="tabular-nums">{s.total && s.total !== "0.00" ? `${s.currency} ${s.total}` : "To be confirmed"}</b></p>
      {(s.flags?.length > 0 || s.warnings?.length > 0) && (
        <ul className="space-y-0.5 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs">
          {[...(s.warnings ?? []), ...(s.flags ?? [])].map((f: string, i: number) => <li key={i}>⚠ {f}</li>)}
        </ul>
      )}
      {a.status !== "pending" && <p className="text-sm text-muted-foreground">Decided by {a.decided_by} · {fmtDate(a.decided_at)}{a.comment && `: “${a.comment}”`}</p>}
      {a.status === "pending" && canDecide && (
        <div className="space-y-2">
          <label htmlFor={`c-${a.id}`} className="sr-only">Comment</label>
          <Textarea id={`c-${a.id}`} placeholder="Comment (required to reject or request changes)" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => decide("approve")}>Approve</Button>
            <Button size="sm" variant="outline" onClick={() => decide("request-changes")}>Request changes</Button>
            <Button size="sm" variant="destructive" onClick={() => decide("reject")}>Reject</Button>
          </div>
        </div>
      )}
      <button className="text-xs text-primary hover:underline" onClick={async () => setHistory((await api(`/approvals/${a.id}`)).history)}>View history</button>
      {history && (
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          {history.map((h, i) => <li key={i}>{fmtDate(h.at)} · {h.action}{h.detail?.version && ` (v${h.detail.version})`}{h.detail?.comment && `: ${h.detail.comment}`}</li>)}
        </ul>
      )}
    </li>
  );
}

export default function Approvals() {
  const me = useMe();
  const [status, setStatus] = useState("pending");
  const { data, error, mutate } = useApi<any[]>(`/approvals?status=${status}`);
  return (
    <>
      <PageHeader title="Approvals" description={can(me, "approvals.decide") ? "Review AI-generated work before it reaches a customer." : "Track the status of your submitted work. Managers and admins make decisions."}
        actions={<NativeSelect aria-label="Status" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">Pending</option><option value="approved">Approved</option>
          <option value="changes_requested">Changes requested</option><option value="rejected">Rejected</option><option value="">All</option>
        </NativeSelect>} />
      <ErrorBox error={error} retry={() => mutate()} />
      {!data ? <Loading /> : data.length === 0 ? <EmptyState icon={CheckSquare} title="Nothing here">Submitted proposals will appear in this queue.</EmptyState> : (
        <ul className="space-y-3">{data.map((a) => <Item key={a.id} a={a} canDecide={can(me, "approvals.decide")} onDone={() => mutate()} />)}</ul>
      )}
    </>
  );
}
