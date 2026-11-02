"use client";

import { useApi } from "@/lib/api";
import { ErrorBox, Loading, PageHeader, StatusBadge } from "@/components/app/ui";

export default function Integrations() {
  const { data, error } = useApi<any[]>("/integrations");
  return (
    <>
      <PageHeader title="Integrations" description="Connections are shown as connected only when they actually work." />
      <ErrorBox error={error} />
      {!data ? <Loading /> : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {data.map((i) => (
            <li key={i.key} className="flex items-start justify-between gap-3 rounded-lg border p-4">
              <div><p className="font-medium">{i.name}</p><p className="mt-0.5 text-sm text-muted-foreground">{i.description}</p></div>
              <StatusBadge status={i.status} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
