"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtDate, useApi } from "@/lib/api";
import { DaysFilter, ErrorBox, Loading, PageHeader, Stat } from "@/components/app/ui";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const SERIES = [
  { key: "qa", name: "Questions", color: "var(--chart-1)" },
  { key: "research", name: "Research", color: "var(--chart-2)" },
  { key: "proposal", name: "Proposals", color: "var(--chart-3)" },
];

export default function Analytics() {
  const [days, setDays] = useState(30);
  const { data, error } = useApi(`/analytics/overview?days=${days}`);
  const { data: usage } = useApi(`/usage?days=${days}`);
  return (
    <>
      <PageHeader title="Analytics" description="Workflow activity, model usage and failures." actions={<DaysFilter days={days} setDays={setDays} />} />
      <ErrorBox error={error} />
      {!data ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Workflows succeeded" value={data.workflow_succeeded} />
            <Stat label="Workflows failed" value={data.workflow_failed} />
            <Stat label="Tokens (in / out)" value={`${data.tokens_in.toLocaleString()} / ${data.tokens_out.toLocaleString()}`} />
            <Stat label="Estimated model cost" value={data.est_cost_usd == null ? "Not configured" : `$${data.est_cost_usd.toFixed(2)}`} />
          </div>
          <section className="mt-6 rounded-lg border p-4">
            <h2 className="mb-3 text-sm font-medium">Workflow runs per day</h2>
            {data.daily.length === 0 ? <p className="py-10 text-center text-sm text-muted-foreground">No workflow runs in this period.</p> : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.daily}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="date" fontSize={12} stroke="var(--muted-foreground)" />
                    <YAxis allowDecimals={false} fontSize={12} stroke="var(--muted-foreground)" />
                    <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8 }} />
                    <Legend />
                    {SERIES.map((s) => <Bar key={s.key} dataKey={s.key} name={s.name} stackId="a" fill={s.color} />)}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>
        </>
      )}
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-medium">Model usage</h2>
        {!usage ? <Loading rows={2} /> : usage.by_model.length === 0 ? <p className="text-sm text-muted-foreground">No model calls recorded in this period.</p> : (
          <div className="rounded-lg border"><Table>
            <TableHeader><TableRow><TableHead>Model</TableHead><TableHead>Purpose</TableHead><TableHead className="text-right">Calls</TableHead>
              <TableHead className="text-right">Tokens in</TableHead><TableHead className="text-right">Tokens out</TableHead><TableHead className="text-right">Est. cost</TableHead></TableRow></TableHeader>
            <TableBody>{usage.by_model.map((u: any, i: number) => (
              <TableRow key={i}><TableCell>{u.model}</TableCell><TableCell>{u.purpose}</TableCell><TableCell className="text-right tabular-nums">{u.calls}</TableCell>
                <TableCell className="text-right tabular-nums">{u.input_tokens.toLocaleString()}</TableCell><TableCell className="text-right tabular-nums">{u.output_tokens.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{u.est_cost_usd == null ? "—" : `$${u.est_cost_usd.toFixed(4)}`}</TableCell></TableRow>
            ))}</TableBody>
          </Table></div>
        )}
      </section>
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-medium">Recent failures</h2>
        {!usage ? null : usage.recent_failures.length === 0 ? <p className="text-sm text-muted-foreground">No failures.</p> : (
          <ul className="divide-y rounded-lg border text-sm">
            {usage.recent_failures.map((f: any) => <li key={f.id} className="flex flex-wrap justify-between gap-2 px-4 py-2"><span><b className="capitalize">{f.kind}</b>: {f.error}</span><span className="text-muted-foreground">{fmtDate(f.at)}</span></li>)}
          </ul>
        )}
      </section>
    </>
  );
}
