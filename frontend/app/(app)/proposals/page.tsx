"use client";

import Link from "next/link";
import { FileText, Plus } from "lucide-react";
import { fmtDate, useApi } from "@/lib/api";
import { EmptyState, ErrorBox, Loading, PageHeader, StatusBadge } from "@/components/app/ui";
import { buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function Proposals() {
  const { data, error, mutate } = useApi<any[]>("/proposals", {
    refreshInterval: (d) => (d?.some((p: any) => p.status === "generating") ? 3000 : 0),
  });
  return (
    <>
      <PageHeader title="Proposal Studio" description="Proposals grounded in your Knowledge Base and approved price list."
        actions={<Link href="/proposals/new" className={buttonVariants()}><Plus /> New proposal</Link>} />
      <ErrorBox error={error} retry={() => mutate()} />
      {!data ? <Loading /> : data.length === 0 ? (
        <EmptyState icon={FileText} title="No proposals yet">Pick a prospect, describe the requirements and select approved price items.</EmptyState>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader><TableRow><TableHead>Proposal</TableHead><TableHead>Status</TableHead>
              <TableHead className="hidden md:table-cell">Version</TableHead><TableHead className="hidden md:table-cell">Updated</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell><Link href={`/proposals/${p.id}`} className="font-medium hover:underline">{p.title}</Link>
                    <span className="block text-xs text-muted-foreground">{p.prospect_name}</span></TableCell>
                  <TableCell><StatusBadge status={p.status} /></TableCell>
                  <TableCell className="hidden md:table-cell">v{p.current_version}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{fmtDate(p.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
