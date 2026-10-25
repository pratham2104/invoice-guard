// Text fallback (and ground truth): compare the payment fields printed on the new invoice with the
// vendor's last real invoice. No model. Line items and totals change every month, so they're ignored;
// what must never change silently is where the money goes and who you'd call about it.
import type { Finding } from "../fingerprint/types.js";
import type { Layout, Region, TextBox } from "./layout.js";

export type Field = "bank_name" | "routing" | "account" | "remit_address" | "phone" | "email";
export type Group = "bank" | "remit" | "contact";

const PATTERNS: Record<Field, RegExp> = {
  bank_name: /\bBank\s*:\s*(.+?)\s*$/i,
  routing: /\bRouting(?:\s*(?:number|no\.?|#))?\s*:?\s*(\d{9})\b/i,
  account: /\bAccount(?:\s*(?:number|no\.?|#))?\s*:?\s*(\d[\d\- ]{3,}\d)\b/i,
  remit_address: /\bRemit(?:tance)?\s*(?:address|to)?\s*:\s*(.+?)\s*$/i,
  phone: /(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]\d{4})/,
  email: /([\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+)/,
};

export const GROUP_OF: Record<Field, Group> = {
  bank_name: "bank", routing: "bank", account: "bank", remit_address: "remit", phone: "contact", email: "contact",
};

const GROUP_INFO: Record<Group, { check: string; severity: "high" | "medium"; label: string; why: string }> = {
  bank: { check: "invoice_bank_changed", severity: "high", label: "Bank changed",
          why: "The bank details printed on this invoice differ from the vendor's last real invoice." },
  remit: { check: "invoice_remit_changed", severity: "high", label: "Remit address changed",
           why: "The remit-to address differs from the vendor's last real invoice." },
  contact: { check: "invoice_contact_changed", severity: "medium", label: "Contact changed",
             why: "The phone or email on this invoice differs from the vendor's last real invoice. Never call it; use the phone on file." },
};

export interface FieldHit { value: string; box: TextBox }
export type Fields = Partial<Record<Field, FieldHit>>;

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9@.]/g, "");
/** Never echo a full account number into a finding. */
export const maskAccount = (s: string) => { const d = s.replace(/\D/g, ""); return d.length > 4 ? `…${d.slice(-4)}` : d; };
const show = (f: Field, v: string) => (f === "account" ? maskAccount(v) : v);

export function extractFields(layout: Layout): Fields {
  const out: Fields = {};
  for (const box of layout.items) {
    for (const f of Object.keys(PATTERNS) as Field[]) {
      if (out[f]) continue;
      const m = box.text.match(PATTERNS[f]);
      if (m) out[f] = { value: m[1].trim(), box };
    }
  }
  return out;
}

export function hasText(layout: Layout) {
  return layout.items.map((i) => i.text).join("").replace(/\s/g, "").length > 20;
}

export function groupInfo(g: Group) { return GROUP_INFO[g]; }

/** Changed groups between the reference and the new invoice, as Findings plus where to circle them. */
export function compareFields(ref: Fields, cur: Fields): { findings: Finding[]; regions: Region[]; changed: Set<Group> } {
  const byGroup = new Map<Group, Field[]>();
  for (const f of Object.keys(PATTERNS) as Field[]) {
    const a = ref[f]?.value, b = cur[f]?.value;
    if (b === undefined) continue;                       // field absent from the new invoice: nothing to compare
    if (a !== undefined && norm(a) === norm(b)) continue;
    const g = GROUP_OF[f];
    byGroup.set(g, [...(byGroup.get(g) ?? []), f]);
  }
  const findings: Finding[] = [];
  const regions: Region[] = [];
  for (const [g, fields] of byGroup) {
    const info = GROUP_INFO[g];
    findings.push({
      check: info.check, severity: info.severity, source: "vision",
      expected: fields.map((f) => `${f}: ${ref[f] ? show(f, ref[f]!.value) : "(not on last real invoice)"}`).join("; "),
      actual: fields.map((f) => `${f}: ${show(f, cur[f]!.value)}`).join("; "),
      explanation: info.why,
    });
    const seen = new Set<TextBox>();
    for (const f of fields) {
      const box = cur[f]!.box;
      if (seen.has(box)) continue;
      seen.add(box);
      regions.push({ page: box.page, x: box.x, y: box.y, w: box.w, h: box.h, label: info.label, severity: info.severity });
    }
  }
  return { findings, regions, changed: new Set(byGroup.keys()) };
}
