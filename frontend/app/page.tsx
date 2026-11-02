import Link from "next/link";
import { BookOpen, CheckSquare, FileText, Search } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";

const FEATURES = [
  { icon: BookOpen, title: "Verified company knowledge", body: "Upload product docs, pricing sheets and case studies. Every answer cites the exact document it came from, or says it can't verify." },
  { icon: Search, title: "Prospect research with evidence", body: "Reads a prospect's own public website, separates verified facts from hypotheses, and scores fit against your rubric." },
  { icon: FileText, title: "Grounded proposals", body: "Drafts proposals from your approved knowledge. Prices come only from your approved price list; unsupported claims are flagged." },
  { icon: CheckSquare, title: "Human approval built in", body: "Managers review the exact version submitted. Every decision is recorded in the audit log." },
];

export default function Landing() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <span className="flex items-center gap-2 font-semibold">
          <span className="grid size-7 place-items-center rounded-md bg-primary text-xs text-primary-foreground">SP</span>
          SalesPilot AI
        </span>
        <nav className="flex items-center gap-2">
          <Link href="/login" className={buttonVariants({ variant: "ghost" })}>Sign in</Link>
          <Link href="/signup" className={buttonVariants()}>Get started</Link>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4">
        <section className="max-w-3xl py-20">
          <p className="text-sm font-medium text-primary">For B2B sales teams</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">
            One place to find verified company knowledge, research prospects and prepare proposals.
          </h1>
          <p className="mt-5 text-lg text-muted-foreground">
            SalesPilot answers from your own documents with citations, keeps AI suggestions separate from verified facts,
            and puts a human approval step in front of anything a customer will see.
          </p>
          <div className="mt-8 flex gap-3">
            <Link href="/signup" className={buttonVariants({ size: "lg" })}>Create your workspace</Link>
            <Link href="/login" className={buttonVariants({ size: "lg", variant: "outline" })}>Sign in</Link>
          </div>
        </section>
        <section className="grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="bg-background p-6">
              <Icon className="size-5 text-primary" aria-hidden />
              <h2 className="mt-3 font-medium">{title}</h2>
              <p className="mt-1.5 text-sm text-muted-foreground">{body}</p>
            </div>
          ))}
        </section>
        <footer className="py-12 text-sm text-muted-foreground">SalesPilot AI</footer>
      </main>
    </div>
  );
}
