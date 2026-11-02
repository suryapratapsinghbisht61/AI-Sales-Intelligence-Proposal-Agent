"use client";

import Link from "next/link";
import { useState } from "react";
import { Activity } from "lucide-react";
import { fmtDate, useApi } from "@/lib/api";
import { useMe } from "@/components/app/shell";
import { DaysFilter, EmptyState, ErrorBox, Loading, PageHeader, Stat } from "@/components/app/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function Dashboard() {
  const me = useMe();
  const [days, setDays] = useState(30);
  const { data, error, mutate } = useApi(`/analytics/overview?days=${days}`);
  const { data: activity } = useApi<any[]>("/activity?limit=12");

  return (
    <>
      <PageHeader title="Overview" description={`Activity for ${me.active_organization!.name}`} actions={<DaysFilter days={days} setDays={setDays} />} />
      <ErrorBox error={error} retry={() => mutate()} />
      {!data && !error ? <Loading rows={3} /> : data && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Documents indexed" value={`${data.documents_indexed} / ${data.documents_total}`} href="/knowledge" />
          <Stat label="Questions asked" value={data.questions_asked} href="/workspace" />
          <Stat label="Prospects researched" value={data.prospects_researched} href="/prospects" />
          <Stat label="Proposals generated" value={data.proposals_generated} href="/proposals" />
          <Stat label="Pending approvals" value={data.pending_approvals} href="/approvals" />
          <Stat label="Workflows succeeded" value={data.workflow_succeeded} href="/analytics" />
          <Stat label="Workflows failed" value={data.workflow_failed} href="/analytics" />
          <Stat label="Tokens used" value={(data.tokens_in + data.tokens_out).toLocaleString()}
            href="/analytics" />
        </div>
      )}
      {data && data.documents_total === 0 && (
        <Card className="mt-6">
          <CardHeader><CardTitle>Get started</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>1. <Link className="text-primary hover:underline" href="/knowledge">Upload your product docs, pricing and case studies</Link></p>
            <p>2. <Link className="text-primary hover:underline" href="/workspace">Ask a question in the AI Workspace</Link></p>
            <p>3. <Link className="text-primary hover:underline" href="/prospects">Add a prospect and research it</Link></p>
            <p>4. <Link className="text-primary hover:underline" href="/proposals">Generate a proposal</Link></p>
          </CardContent>
        </Card>
      )}
      <h2 className="mt-8 mb-3 text-sm font-medium">Recent activity</h2>
      {!activity ? <Loading /> : activity.length === 0 ? (
        <EmptyState icon={Activity} title="No activity yet">Actions taken by your team will appear here.</EmptyState>
      ) : (
        <ul className="divide-y rounded-lg border">
          {activity.map((a) => (
            <li key={a.id} className="flex flex-wrap justify-between gap-2 px-4 py-2.5 text-sm">
              <span><span className="font-medium">{a.user ?? "System"}</span> · {a.action.replaceAll(".", " ").replaceAll("_", " ")}</span>
              <span className="text-muted-foreground">{fmtDate(a.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
