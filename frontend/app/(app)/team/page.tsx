"use client";

import { useState } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";
import { api, fmtDate, useApi } from "@/lib/api";
import { can, useMe } from "@/components/app/shell";
import { ErrorBox, Field, Loading, NativeSelect, PageHeader } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ROLES = { owner: "Owner", admin: "Admin", sales_manager: "Sales manager", sales_rep: "Sales representative" };

export default function Team() {
  const me = useMe();
  const manage = can(me, "members.manage");
  const { data: members, error, mutate } = useApi<any[]>("/members");
  const { data: invites, mutate: refreshInv } = useApi<any[]>(manage ? "/invitations" : null);
  const [link, setLink] = useState("");
  const [inviteErr, setInviteErr] = useState<unknown>(null);

  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); mutate(); refreshInv(); } catch (e) { toast.error((e as Error).message); mutate(); }
  };

  async function invite(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setInviteErr(null);
    try {
      const r = await api("/invitations", { json: { email: f.get("email"), role: f.get("role") } });
      setLink(r.link);
      refreshInv();
      e.currentTarget?.reset();
    } catch (err) { setInviteErr(err); }
  }

  return (
    <>
      <PageHeader title="Team" description="Members of this organization and their roles. Permissions are enforced by the server." />
      <ErrorBox error={error} retry={() => mutate()} />
      {!members ? <Loading /> : (
        <ul className="divide-y rounded-lg border">
          {members.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
              <div><p className="font-medium">{m.name || m.email}{m.user_id === me.user.id && " (you)"}</p>
                <p className="text-xs text-muted-foreground">{m.email} · joined {fmtDate(m.joined_at)}</p></div>
              <div className="flex items-center gap-2">
                {manage && m.user_id !== me.user.id ? (
                  <>
                    <NativeSelect aria-label={`Role for ${m.email}`} className="w-48" value={m.role}
                      onChange={(e) => act(() => api(`/members/${m.id}`, { method: "PATCH", json: { role: e.target.value } }))}>
                      {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </NativeSelect>
                    <Button size="sm" variant="ghost" onClick={() => confirm(`Remove ${m.email}?`) && act(() => api(`/members/${m.id}`, { method: "DELETE" }))}>Remove</Button>
                  </>
                ) : <span className="text-muted-foreground">{ROLES[m.role as keyof typeof ROLES]}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {manage && (
        <section className="mt-8 max-w-2xl space-y-4">
          <h2 className="text-sm font-medium">Invite a teammate</h2>
          <form onSubmit={invite} className="grid gap-3 sm:grid-cols-[1fr_200px_auto] sm:items-end">
            <Field label="Email" htmlFor="email"><Input id="email" name="email" type="email" required /></Field>
            <Field label="Role" htmlFor="role"><NativeSelect id="role" name="role" defaultValue="sales_rep">
              {Object.entries(ROLES).filter(([k]) => k !== "owner" || me.active_organization!.role === "owner").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect></Field>
            <Button type="submit">Create invite</Button>
          </form>
          <ErrorBox error={inviteErr} />
          {link && (
            <div className="rounded-md border bg-muted/40 p-3 text-sm">
              <p className="mb-1">Email delivery isn&apos;t configured. Share this link with your teammate (valid 7 days):</p>
              <div className="flex gap-2"><Input readOnly value={link} aria-label="Invitation link" />
                <Button variant="outline" size="icon" aria-label="Copy link" onClick={() => { navigator.clipboard.writeText(link); toast.success("Copied"); }}><Copy /></Button></div>
            </div>
          )}
          {!!invites?.length && (
            <ul className="divide-y rounded-lg border text-sm">
              {invites.map((i) => (
                <li key={i.id} className="flex items-center justify-between px-4 py-2">
                  <span>{i.email} · {ROLES[i.role as keyof typeof ROLES]} <span className="text-xs text-muted-foreground">expires {fmtDate(i.expires_at)}</span></span>
                  <Button size="sm" variant="ghost" onClick={() => act(() => api(`/invitations/${i.id}`, { method: "DELETE" }))}>Revoke</Button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}
