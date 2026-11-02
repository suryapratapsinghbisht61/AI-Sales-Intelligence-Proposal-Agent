"use client";

import useSWR, { type SWRConfiguration } from "swr";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

type Opts = { method?: string; json?: unknown; form?: FormData; signal?: AbortSignal };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method: opts.method ?? (opts.json || opts.form ? "POST" : "GET"),
    credentials: "same-origin",
    signal: opts.signal,
    headers: opts.json !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.form ?? (opts.json !== undefined ? JSON.stringify(opts.json) : undefined),
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body.detail;
    const msg = Array.isArray(d) ? d.map((e: any) => `${e.loc?.at(-1)}: ${e.msg}`).join("; ") : d;
    throw new ApiError(res.status, msg || `Request failed (${res.status})`, body.code);
  }
  return body as T;
}

export async function download(path: string, method = "GET") {
  const res = await fetch(`/api/v1${path}`, { method, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? "Download failed");
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "download";
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export function useApi<T = any>(path: string | null, config?: SWRConfiguration) {
  return useSWR<T>(path, (p: string) => api<T>(p), config);
}

export type Me = {
  user: { id: string; email: string; name: string };
  organizations: { id: string; name: string; role: string; onboarding_completed: boolean }[];
  active_organization: { id: string; name: string; role: string; onboarding_completed: boolean } | null;
  permissions: string[];
};

export const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
