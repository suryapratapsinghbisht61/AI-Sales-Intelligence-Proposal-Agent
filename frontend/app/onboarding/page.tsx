"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, useApi, type Me } from "@/lib/api";
import { OrgFields, orgPayload } from "@/components/app/org-form";
import { ErrorBox } from "@/components/app/ui";
import { Button } from "@/components/ui/button";

export default function Onboarding() {
  const router = useRouter();
  const { data: me, error: meErr } = useApi<Me>("/me");
  const [isNew, setIsNew] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data: org } = useApi(me?.active_organization && !isNew ? "/organizations/current" : null);

  useEffect(() => {
    if ((meErr as any)?.status === 401) router.replace("/login");
    if (me) setIsNew(!me.active_organization || new URLSearchParams(window.location.search).has("new"));
  }, [me, meErr, router]);

  async function save(form: HTMLFormElement, complete: boolean) {
    setBusy(true);
    setError(null);
    try {
      const body = { ...orgPayload(new FormData(form)), onboarding_completed: complete };
      if (isNew) await api("/organizations", { json: body });
      else await api("/organizations/current", { method: "PATCH", json: body });
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  if (!me || (!isNew && !org)) return null;
  return (
    <div className="min-h-screen bg-muted/40 px-4 py-10">
      <div className="mx-auto max-w-2xl rounded-xl border bg-card p-6 shadow-sm">
        <h1 className="text-lg font-semibold">{isNew ? "Set up your organization" : "Finish your company profile"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Only the name is required. The rest helps SalesPilot qualify prospects and draft proposals; you can finish it later in Settings.
        </p>
        <form className="mt-6 space-y-5" onSubmit={(e) => { e.preventDefault(); save(e.currentTarget, true); }}>
          <OrgFields org={org} disabled={busy} />
          <ErrorBox error={error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" disabled={busy}
              onClick={(e) => { const f = e.currentTarget.form!; if (f.reportValidity()) save(f, false); }}>Skip for now</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Continue"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
