"use client";

import Link from "next/link";
import Markdown from "react-markdown";
import { AlertTriangle, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed px-6 py-12 text-center">
      <Icon className="mb-3 size-8 text-muted-foreground" aria-hidden />
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
      <span className="flex items-center gap-2 text-destructive">
        <AlertTriangle className="size-4 shrink-0" aria-hidden />
        {error instanceof Error ? error.message : String(error)}
      </span>
      {retry && <Button size="sm" variant="outline" onClick={retry}>Retry</Button>}
    </div>
  );
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-10 w-full" />)}
    </div>
  );
}

const TONE: Record<string, string> = {
  ready: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  done: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  approved: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  verified: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  connected: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  failed: "bg-red-500/10 text-red-700 dark:text-red-400",
  rejected: "bg-red-500/10 text-red-700 dark:text-red-400",
  pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  pending_approval: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  changes_requested: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  sourced_unverified: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  hypothesis: "bg-violet-500/10 text-violet-700 dark:text-violet-400",
  not_configured: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="secondary" className={cn("font-normal capitalize", TONE[status])}>
      {status.replaceAll("_", " ")}
    </Badge>
  );
}

export function Md({ children }: { children: string }) {
  return (
    <div className="prose-sm max-w-none space-y-2 text-sm leading-relaxed [&_a]:text-primary [&_a]:underline [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-semibold [&_table]:w-full [&_table]:text-left [&_td]:border-b [&_td]:py-1 [&_td]:pr-3 [&_th]:border-b [&_th]:py-1 [&_th]:pr-3 [&_ul]:list-disc [&_ul]:pl-5">
      <Markdown>{children}</Markdown>
    </div>
  );
}

export function NativeSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30",
        props.className,
      )}
    />
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: string; children: React.ReactNode; htmlFor: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export const textareaCls = "min-h-24 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

export function Stat({ label, value, href }: { label: string; value: React.ReactNode; href?: string }) {
  const body = (
    <div className="rounded-lg border bg-card p-4 transition-colors hover:bg-muted/40">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export function DaysFilter({ days, setDays }: { days: number; setDays: (d: number) => void }) {
  return (
    <NativeSelect aria-label="Date range" className="w-36" value={days} onChange={(e) => setDays(Number(e.target.value))}>
      <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
    </NativeSelect>
  );
}

