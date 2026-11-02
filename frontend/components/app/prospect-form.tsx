"use client";

import { Field } from "@/components/app/ui";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export function prospectPayload(f: FormData) {
  const s = (k: string) => String(f.get(k) ?? "").trim();
  return {
    name: s("name"), domain: s("domain"), industry: s("industry"), location: s("location"),
    company_size: s("company_size"), contact_name: s("contact_name"), contact_email: s("contact_email"),
    source_url: s("source_url"), notes: s("notes"),
    tags: s("tags").split(",").map((t) => t.trim()).filter(Boolean),
  };
}

export function ProspectFields({ p = {} }: { p?: Record<string, any> }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Company name" htmlFor="name"><Input id="name" name="name" required defaultValue={p.name} /></Field>
      <Field label="Website / domain" htmlFor="domain"><Input id="domain" name="domain" placeholder="example.com" defaultValue={p.domain} /></Field>
      <Field label="Industry" htmlFor="industry"><Input id="industry" name="industry" defaultValue={p.industry} /></Field>
      <Field label="Location / market" htmlFor="location"><Input id="location" name="location" defaultValue={p.location} /></Field>
      <Field label="Company size" htmlFor="company_size"><Input id="company_size" name="company_size" defaultValue={p.company_size} /></Field>
      <Field label="Tags" htmlFor="tags" hint="Comma separated."><Input id="tags" name="tags" defaultValue={p.tags?.join(", ")} /></Field>
      <Field label="Contact name" htmlFor="contact_name" hint="Only if lawfully obtained."><Input id="contact_name" name="contact_name" defaultValue={p.contact_name} /></Field>
      <Field label="Contact email" htmlFor="contact_email"><Input id="contact_email" name="contact_email" type="email" defaultValue={p.contact_email} /></Field>
      <div className="sm:col-span-2"><Field label="Source URL" htmlFor="source_url"><Input id="source_url" name="source_url" defaultValue={p.source_url} /></Field></div>
      <div className="sm:col-span-2"><Field label="Notes" htmlFor="notes"><Textarea id="notes" name="notes" defaultValue={p.notes} /></Field></div>
    </div>
  );
}
