"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, FileText, MessageSquare, Plus, Send, Square, Trash2 } from "lucide-react";
import { api, ApiError, useApi } from "@/lib/api";
import { ErrorBox, Md } from "@/components/app/ui";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type Source = { chunk_id: string; document_id: string; title: string; page: number | null; section: string | null; excerpt: string };
type Msg = { id: string; role: "user" | "assistant"; content: string; sources: Source[]; meta: { uncertain?: boolean; follow_ups?: string[] } };

const EXAMPLES = [
  "What are the approved prices for our enterprise plan?",
  "Summarize our implementation process.",
  "Find case studies relevant to healthcare clients.",
  "Which of our services fits a company migrating from legacy infrastructure?",
];

function Sources({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">Sources</p>
      {sources.map((s, i) => (
        <details key={s.chunk_id} className="rounded-md border bg-background text-xs">
          <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5">
            <FileText className="size-3.5 shrink-0" aria-hidden />
            <span className="font-medium">[{i + 1}] {s.title}</span>
            <span className="text-muted-foreground">{[s.page && `p. ${s.page}`, s.section].filter(Boolean).join(" · ")}</span>
          </summary>
          <p className="whitespace-pre-wrap border-t px-2.5 py-2 text-muted-foreground">{s.excerpt}</p>
          <a href={`/knowledge/${s.document_id}`} className="block border-t px-2.5 py-1.5 text-primary hover:underline">Open document</a>
        </details>
      ))}
    </div>
  );
}

export default function Workspace() {
  const { data: convs, mutate: refreshConvs } = useApi<any[]>("/conversations");
  const [convId, setConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [messages, pending]);

  async function open(id: string) {
    setConvId(id);
    setError(null);
    setMessages(await api(`/conversations/${id}/messages`));
  }

  async function send(text: string) {
    const q = text.trim();
    if (!q || pending) return;
    setPending(q);
    setInput("");
    setError(null);
    abort.current = new AbortController();
    try {
      const r = await api("/chat", { json: { message: q, conversation_id: convId }, signal: abort.current.signal });
      setConvId(r.conversation_id);
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: q, sources: [], meta: {} }, r.message]);
      refreshConvs();
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError(e);
        setInput(q);
      }
    } finally {
      setPending(null);
    }
  }

  async function remove(id: string) {
    await api(`/conversations/${id}`, { method: "DELETE" });
    if (id === convId) { setConvId(null); setMessages([]); }
    refreshConvs();
  }

  const notConfigured = error instanceof ApiError && error.code === "llm_not_configured";

  return (
    <div className="-my-6 flex h-[calc(100vh-3.5rem)] gap-4 py-4">
      <aside className="hidden w-56 shrink-0 flex-col md:flex" aria-label="Conversation history">
        <Button variant="outline" className="mb-2 justify-start" onClick={() => { setConvId(null); setMessages([]); setError(null); }}>
          <Plus /> New conversation
        </Button>
        <ul className="flex-1 space-y-0.5 overflow-y-auto">
          {convs?.map((c) => (
            <li key={c.id} className="group flex items-center">
              <button onClick={() => open(c.id)}
                className={cn("flex-1 truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted", c.id === convId && "bg-muted font-medium")}>
                {c.title}
              </button>
              <button aria-label={`Delete ${c.title}`} onClick={() => remove(c.id)}
                className="p-1 text-muted-foreground opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-destructive">
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col rounded-xl border">
        <div className="flex-1 space-y-5 overflow-y-auto p-4 md:p-6" aria-live="polite">
          {messages.length === 0 && !pending && (
            <div className="mx-auto max-w-lg pt-10 text-center">
              <MessageSquare className="mx-auto size-8 text-muted-foreground" aria-hidden />
              <h1 className="mt-3 font-semibold">Ask about your company knowledge</h1>
              <p className="mt-1 text-sm text-muted-foreground">Answers come only from your Knowledge Base, with sources. If something can&apos;t be verified, SalesPilot says so.</p>
              <div className="mt-5 grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((e) => (
                  <button key={e} onClick={() => send(e)} className="rounded-lg border px-3 py-2 text-left text-sm hover:bg-muted">{e}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={cn("max-w-3xl", m.role === "user" && "ml-auto w-fit rounded-xl bg-primary px-3.5 py-2 text-sm text-primary-foreground")}>
              {m.role === "user" ? m.content : (
                <div className="rounded-xl bg-muted/50 p-4">
                  {m.meta.uncertain && (
                    <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                      <AlertTriangle className="size-3.5" aria-hidden /> Not fully verified by your documents
                    </p>
                  )}
                  <Md>{m.content}</Md>
                  <Sources sources={m.sources} />
                  {!!m.meta.follow_ups?.length && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {m.meta.follow_ups.map((f) => (
                        <button key={f} onClick={() => send(f)} className="rounded-full border bg-background px-2.5 py-1 text-xs hover:bg-muted">{f}</button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          {pending && (
            <>
              <div className="ml-auto w-fit max-w-3xl rounded-xl bg-primary px-3.5 py-2 text-sm text-primary-foreground">{pending}</div>
              <p className="animate-pulse text-sm text-muted-foreground">Searching your knowledge base and drafting an answer…</p>
            </>
          )}
          {error ? (
            <div className="space-y-2">
              <ErrorBox error={error} retry={notConfigured ? undefined : () => send(input)} />
              {notConfigured && <p className="text-xs text-muted-foreground">An administrator needs to set CHAT_MODEL and EMBEDDING_MODEL on the API server.</p>}
            </div>
          ) : null}
          <div ref={bottom} />
        </div>
        <form className="flex items-end gap-2 border-t p-3" onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <label htmlFor="chat-input" className="sr-only">Message</label>
          <Textarea id="chat-input" value={input} onChange={(e) => setInput(e.target.value)} rows={1} maxLength={4000}
            placeholder="Ask a question about your products, pricing, case studies…" className="max-h-40 min-h-10 flex-1 resize-none"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} />
          {pending ? (
            <Button type="button" variant="outline" size="icon" aria-label="Stop waiting" onClick={() => abort.current?.abort()}><Square /></Button>
          ) : (
            <Button type="submit" size="icon" aria-label="Send" disabled={!input.trim()}><Send /></Button>
          )}
        </form>
      </section>
    </div>
  );
}
