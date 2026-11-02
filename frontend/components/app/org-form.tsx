"use client";

import { Field } from "@/components/app/ui";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export type Org = Record<string, any>;

export const ORG_FIELDS = ["name", "website", "industry", "description", "offerings", "target_customer",
  "target_markets", "team_size", "currency", "timezone"] as const;

export function orgPayload(f: FormData) {
  const out: Record<string, unknown> = {};
  for (const k of ORG_FIELDS) {
    const v = String(f.get(k) ?? "").trim();
    if (k === "team_size") out[k] = v ? Number(v) : null;
    else if (k === "currency") out[k] = v ? v.toUpperCase() : null;
    else out[k] = v || (k === "name" ? null : "");
  }
  return out;
}

export function OrgFields({ org = {}, disabled }: { org?: Org; disabled?: boolean }) {
  return (
    <fieldset disabled={disabled} className="grid gap-4 sm:grid-cols-2">
      <Field label="Organization name" htmlFor="name"><Input id="name" name="name" required defaultValue={org.name} /></Field>
      <Field label="Website" htmlFor="website"><Input id="website" name="website" placeholder="https://" defaultValue={org.website} /></Field>
      <Field label="Industry" htmlFor="industry"><Input id="industry" name="industry" defaultValue={org.industry} /></Field>
      <Field label="Sales team size" htmlFor="team_size"><Input id="team_size" name="team_size" type="number" min={1} defaultValue={org.team_size ?? ""} /></Field>
      <div className="sm:col-span-2"><Field label="Company description" htmlFor="description">
        <Textarea id="description" name="description" defaultValue={org.description} /></Field></div>
      <div className="sm:col-span-2"><Field label="Products and services" htmlFor="offerings" hint="Used by research and proposals to match prospects to what you sell.">
        <Textarea id="offerings" name="offerings" defaultValue={org.offerings} /></Field></div>
      <div className="sm:col-span-2"><Field label="Ideal customer profile" htmlFor="target_customer">
        <Textarea id="target_customer" name="target_customer" defaultValue={org.target_customer} /></Field></div>
      <div className="sm:col-span-2"><Field label="Target markets" htmlFor="target_markets">
        <Input id="target_markets" name="target_markets" placeholder="e.g. UK, DACH, North America" defaultValue={org.target_markets} /></Field></div>
      <Field label="Default currency" htmlFor="currency"><Input id="currency" name="currency" maxLength={3} defaultValue={org.currency ?? "USD"} /></Field>
      <Field label="Timezone" htmlFor="timezone"><Input id="timezone" name="timezone" defaultValue={org.timezone ?? "UTC"} /></Field>
    </fieldset>
  );
}
