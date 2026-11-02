"use client";

import { ExternalLink } from "lucide-react";
import { fmtDate } from "@/lib/api";
import { StatusBadge } from "@/components/app/ui";

const RATING: Record<string, string> = { strong: "Strong", partial: "Partial", none: "No fit", unknown: "Unknown" };
const FACT_LABEL: Record<string, string> = {
  verified: "verified", sourced_unverified: "sourced_unverified", user_provided: "user_provided",
};

function SourceLink({ url }: { url: string }) {
  if (!url) return null;
  if (url === "user-notes") return <span className="text-xs text-muted-foreground">from your notes</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
      {new URL(url).pathname || "/"} <ExternalLink className="size-3" aria-hidden />
    </a>
  );
}

export function ResearchView({ r }: { r: any }) {
  const q = r.qualification ?? {};
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border p-4">
          <p className="text-xs text-muted-foreground">Qualification score</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums">{r.score ?? "—"}<span className="text-base text-muted-foreground">/100</span></p>
          <p className="mt-1 text-xs text-muted-foreground">Rubric v{r.rubric_version} · evidence coverage {q.evidence_coverage ?? 0}%</p>
        </div>
        <div className="rounded-lg border p-4 sm:col-span-2">
          <p className="text-xs text-muted-foreground">Recommended next step</p>
          <p className="mt-1 text-sm">{q.next_step}</p>
          {r.recommended_offering && <p className="mt-2 text-sm"><span className="text-muted-foreground">Best-fit offering (AI suggestion):</span> {r.recommended_offering}</p>}
          {r.value_proposition && <p className="mt-1 text-sm"><span className="text-muted-foreground">Value proposition (AI suggestion):</span> {r.value_proposition}</p>}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">A score reflects fit on available evidence only; it does not predict willingness to buy.</p>

      {!!r.warnings?.length && (
        <ul className="space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          {r.warnings.map((w: string) => <li key={w}>⚠ {w}</li>)}
        </ul>
      )}

      <section>
        <h3 className="mb-2 text-sm font-medium">Qualification criteria</h3>
        <div className="divide-y rounded-lg border">
          {q.criteria?.map((c: any) => (
            <div key={c.key} className="grid gap-1 p-3 text-sm sm:grid-cols-[180px_90px_1fr]">
              <span className="font-medium">{c.label} <span className="font-normal text-muted-foreground">({c.weight})</span></span>
              <span className={c.rating === "unknown" ? "text-muted-foreground" : ""}>{RATING[c.rating]}</span>
              <span>
                {c.explanation}
                {c.evidence_quote && <q className="mt-1 block text-xs italic text-muted-foreground">{c.evidence_quote}</q>}
                <SourceLink url={c.source_url} />
              </span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-sm font-medium">Facts found</h3>
        {r.facts.length === 0 ? <p className="text-sm text-muted-foreground">No facts could be extracted.</p> : (
          <ul className="space-y-2">
            {r.facts.map((f: any, i: number) => (
              <li key={i} className="rounded-lg border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2"><StatusBadge status={FACT_LABEL[f.kind] ?? f.kind} /> {f.claim}</div>
                <q className="mt-1 block text-xs italic text-muted-foreground">{f.quote}</q>
                <SourceLink url={f.source_url} />
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          <b>Verified</b>: the quote was found word-for-word in the cited page. <b>Sourced unverified</b>: attributed to a page but the quote could not be matched. Treat it as unconfirmed.
        </p>
      </section>

      {!!r.needs.length && (
        <section>
          <h3 className="mb-2 text-sm font-medium">Potential needs <span className="font-normal text-muted-foreground">(hypotheses, not facts)</span></h3>
          <ul className="space-y-2">
            {r.needs.map((n: any, i: number) => (
              <li key={i} className="rounded-lg border p-3 text-sm"><StatusBadge status="hypothesis" /> <span className="font-medium">{n.need}</span>
                <p className="mt-1 text-muted-foreground">{n.reasoning}</p></li>
            ))}
          </ul>
        </section>
      )}

      {!!r.unknowns.length && (
        <section>
          <h3 className="mb-2 text-sm font-medium">Unknowns</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted-foreground">{r.unknowns.map((u: string) => <li key={u}>{u}</li>)}</ul>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-sm font-medium">Sources</h3>
        <ul className="space-y-1 text-sm">
          {r.sources.map((s: any) => (
            <li key={s.url} className="flex flex-wrap justify-between gap-2">
              {s.url === "user-notes" ? <span>Notes supplied by you</span> :
                <a href={s.url} target="_blank" rel="noreferrer noopener" className="text-primary hover:underline">{s.title || s.url}</a>}
              <span className="text-xs text-muted-foreground">retrieved {fmtDate(s.retrieved_at)}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
