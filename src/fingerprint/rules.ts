// Rule checks: plain code, exact, fast, no model needed. Each returns Findings; none decide.
import type { Finding, IncomingMessage, VendorProfile, Bank } from "./types.js";
import { compareDomains, domainOf } from "./domain.js";
import { BANK_CHANGE_RE, parseInvoiceText } from "./text.js";
import type { PdfScan } from "./pdf.js";

const f = (check: string, severity: Finding["severity"], expected: string, actual: string, explanation: string): Finding =>
  ({ check, severity, expected, actual, explanation, source: "rule" });

const bankStr = (b?: Bank) => (b ? [b.bank_name, b.routing && `routing ${b.routing}`, b.account && `account ${b.account}`].filter(Boolean).join(", ") : "none");
const sameBank = (a?: Bank, b?: Bank) => !!a && !!b && a.routing === b.routing && a.account === b.account;

export function ruleChecks(profile: VendorProfile, msg: IncomingMessage, pdfScans: PdfScan[] = []): Finding[] {
  const out: Finding[] = [];
  const sender = msg.from.toLowerCase();
  const senderDomain = domainOf(sender);

  // --- identity
  if (senderDomain !== profile.domain) {
    const cmp = compareDomains(senderDomain, profile.domain);
    if (cmp.lookalike) {
      out.push(f("lookalike_domain", "high", profile.domain, senderDomain,
        `Sent from ${senderDomain}, which imitates ${profile.name}'s real domain ${profile.domain} (${cmp.technique}).`));
    }
  }
  if (!profile.contacts.some((c) => c.email === sender)) {
    out.push(f("unknown_sender", "medium", profile.contacts.map((c) => c.email).join(", "), sender,
      `${sender} is not a known contact for ${profile.name}.`));
  }
  if (msg.replyTo && domainOf(msg.replyTo) !== senderDomain) {
    out.push(f("reply_to_mismatch", "medium", senderDomain, domainOf(msg.replyTo),
      `Replies would go to ${msg.replyTo}, not the sender's domain.`));
  }

  // --- payment details
  const asksBankChange = !!msg.requestedBank || BANK_CHANGE_RE.test(msg.body) || BANK_CHANGE_RE.test(msg.subject);
  if (asksBankChange) {
    out.push(f("bank_change_request", "medium", "no change to payment details", msg.requestedBank ? bankStr(msg.requestedBank) : "asks to change payment details",
      `The message asks to change where ${profile.name} gets paid. Verify by calling ${profile.phoneOnFile} (number on file).`));
    if (!profile.everRequestedBankChange) {
      out.push(f("first_bank_change", "high", `${profile.name} has never asked for a bank change (${profile.sampleEmails.length} past emails)`, "bank change requested",
        `First bank-change request ever from ${profile.name}. This is the most common fraud pattern.`));
    }
  }

  // invoice: from the message, else read it off the attached PDF
  const parsed = pdfScans.length ? parseInvoiceText(pdfScans[0].text) : undefined;
  const pdfInvoice = parsed?.invoice_number && parsed.amount !== undefined
    ? { invoice_number: parsed.invoice_number, invoice_date: parsed.invoice_date ?? "", po_number: parsed.po_number, amount: parsed.amount, bank: parsed.bank }
    : undefined;
  const invoice = msg.invoice ?? pdfInvoice;
  if (invoice) {
    const bank = invoice.bank ?? pdfInvoice?.bank;
    if (bank && (bank.routing || bank.account) && !sameBank(bank, profile.bank)) {
      out.push(f("bank_mismatch", "high", bankStr(profile.bank), bankStr(bank),
        `Invoice ${invoice.invoice_number} pays a different bank account than the one on file.`));
    }
    if (bank?.remit_address && profile.bank.remit_address && bank.remit_address !== profile.bank.remit_address) {
      out.push(f("remit_change", "medium", profile.bank.remit_address, bank.remit_address, "Remit-to address differs from the one on file."));
    }

    // --- billing pattern
    if (profile.invoiceNumbers.includes(invoice.invoice_number)) {
      out.push(f("duplicate_invoice", "high", "a new invoice number", invoice.invoice_number,
        `Invoice ${invoice.invoice_number} was already received${bank && !sameBank(bank, profile.bank) ? " with different bank details" : ""}.`));
    } else {
      const seq = sequenceCheck(profile.invoiceNumbers, invoice.invoice_number);
      if (seq) out.push(seq);
    }
    if (profile.po && invoice.po_number && invoice.po_number !== profile.po.number) {
      out.push(f("po_mismatch", "medium", profile.po.number, invoice.po_number, "Invoice cites a PO this vendor isn't on."));
    }
    const max = Math.max(profile.amount.max, profile.po?.monthlyMax ?? 0);
    const min = Math.min(profile.amount.min || Infinity, profile.po?.monthlyMin ?? Infinity);
    if (invoice.amount > max * 1.1 || (Number.isFinite(min) && invoice.amount < min * 0.5)) {
      out.push(f("amount_out_of_range", "medium", `$${min.toFixed(2)}–$${max.toFixed(2)}`, `$${invoice.amount.toFixed(2)}`,
        "Amount is outside this vendor's usual range."));
    }
    if (profile.billingDay && invoice.invoice_date) {
      const day = Number(invoice.invoice_date.slice(8, 10));
      const diff = Math.min(Math.abs(day - profile.billingDay), 31 - Math.abs(day - profile.billingDay));
      if (day && diff > 2) {
        out.push(f("off_cycle_date", "low", `around day ${profile.billingDay} of the month`, invoice.invoice_date,
          `${profile.name} normally bills on day ${profile.billingDay}; this invoice is dated ${invoice.invoice_date}.`));
      }
    }
  }

  // --- documents: text a person can't see
  for (const scan of pdfScans) {
    for (const h of scan.hidden) {
      out.push(f("hidden_pdf_text", "high", "no hidden text", `"${h.text.slice(0, 120)}" (${h.reasons.join(", ")})`,
        "The invoice contains text a person can't see. Hidden instructions are ignored: the agent has no approve tool."));
    }
  }
  return out;
}

function sequenceCheck(known: string[], num: string): Finding | undefined {
  const parse = (s: string) => s.match(/^(.*?)(\d+)$/);
  const m = parse(num);
  const nums = known.map(parse).filter((x): x is RegExpMatchArray => !!x && !!m && x[1] === m[1]).map((x) => Number(x[2]));
  if (!m || !nums.length) return undefined;
  const last = Math.max(...nums), n = Number(m[2]);
  if (n < last) return f("invoice_out_of_sequence", "medium", `after ${m[1]}${last}`, num, "Invoice number is lower than the last one received.");
  if (n > last + 3) return f("invoice_out_of_sequence", "low", `${m[1]}${last + 1}`, num, "Invoice number jumps ahead of the usual sequence.");
  return undefined;
}
