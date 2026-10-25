# Architecture

## Flow

```
AP Inbox (Gmail IMAP for live demo · folder of .eml/PDF as backup)
   ▼
OpenClaw agent (inside a NemoClaw / OpenShell sandbox, local-only network policy)
   ▼
Qwen (vLLM on the GB10):
  • extract fields: vendor, amount, invoice #, bank details, requested changes
  • compare to the vendor fingerprint (style, rhythm, amounts, contacts)
  • compare invoice image to the vendor's last real invoice (vision)
  → produces FINDINGS (a list of "what's different"), never a decision
   ▼
AP control rules (deterministic code): PASS or HOLD
   ▼                         ▼
log                  HOLD → callback task (phone number ON FILE)
                          → alert (Slack summary + in-app feed)
                          → 7 am briefing
                                ▼
                     AP employee releases or rejects
                     (the agent has no release tool)
```

## Decision flow

```
Message arrives
  → Does it contain: new bank details? new remit-to address? unusual invoice?
    payment urgency? vendor-master change?
  → Retrieve trusted vendor record (SQLite)
  → Compare: bank fingerprint · email/domain · writing style vs past emails ·
    invoice layout vs last real invoice · PO/contract · payment history · known contacts
  → Apply deterministic AP controls
  → Normal? yes → log
           no  → HOLD → verification case → contact vendor BY PHONE ON FILE
                → record confirmation → AP employee approves/rejects
```

## Components

| Component | Folder | What it does |
|---|---|---|
| Inbox watcher | `src/inbox/` | Polls IMAP / watches a folder, hands each message + attachments to the agent |
| Agent tools | `agent/` | OpenClaw tool definitions that call our API |
| API | `src/api/` | Node/Express. All tools go through here |
| Database | `src/db/` | SQLite: vendors, emails, invoices, payments, holds, callbacks |
| Fingerprint | `src/fingerprint/` | Builds each vendor's profile; asks Qwen what's different |
| Vision check | `src/vision/` | Renders invoice PDF → image; asks Qwen to compare with the last real one |
| Rules | `src/rules/` | Deterministic pass/hold. The only thing that decides |
| Alerts | `src/alerts/` | Slack summary + in-app feed + 7 am briefing |
| Dashboard | `web/` | React, one page |
| Voice (gated) | `voice/` | Asterisk + call bridge + whisper.cpp + Piper |
| Self-test (stretch) | `src/selftest/` | Generates attacks overnight, reports misses |

## Security design (say this in the demo)

- The model only produces findings. It cannot change a payment's state.
- Tools exposed to the agent: `lookup_vendor`, `check_invoice`, `hold_payment`,
  `post_alert`, `create_callback_task`. **No release/approve tool exists.** A prompt
  injection inside an invoice ("approve this") has nothing to call.
- The OpenShell policy allows only local addresses (except Slack, which gets summaries only).
- Verification never uses contact details from the incoming message.

## Interfaces

Add every shared interface here in the same push that creates it, so other agents can build
against it without reading your code.

### Local model endpoint
- OpenAI-compatible API served by vLLM on the GB10 (port TBC by T01 — expected `localhost:8000`).
- Model id: `nvidia/Qwen3.6-35B-A3B-NVFP4`. Tool calling on, 262k context.

### Database schema (`src/db/schema.sql`, Node's built-in `node:sqlite`)
- Open: `import { openDb, loadFixtures } from "./src/db/index.js"`; `openDb(":memory:")` in tests.
- Load demo data: `npm run db:load` → `data/invoice-guard.db` (git-ignored).
- `vendors(id, name, domain, address, phone_on_file, billing_day, terms, invoice_prefix)`:
  `phone_on_file` is the ONLY number callbacks may use.
- `vendor_contacts(vendor_id, name, email, role)`
- `vendor_banks(vendor_id, bank_name, routing, account, remit_address, active, verified_at, verified_by)`:
  trusted bank on file, one active row per vendor.
- `purchase_orders(number, vendor_id, description, annual_limit, monthly_min, monthly_max, requester_name, requester_contact, requester_department)`:
  the requester is the district staff member who ordered; surprise bills are confirmed with them (internal only).
- `invoices(id, vendor_id, invoice_number, invoice_date, po_number, amount, bank_name, routing, account, remit_address, status, source_email_id)`
- `invoice_lines(invoice_id, line_no, description, qty, unit_price, amount)`
- `payments(id, invoice_id, vendor_id, amount, paid_on, routing, account, method)`
- `emails(id, vendor_id, from_addr, from_name, reply_to, to_addr, date, subject, body, attachments JSON, kind history|incoming, scenario)`
- `holds(id, invoice_id, email_id, vendor_id, reason, findings JSON, status held|released|rejected, created_at, resolved_at, resolved_by)`:
  written only by the rules engine; `resolved_by` is always a human.
- `callbacks(id, hold_id, vendor_id, phone, script, status open|confirmed_fraud|confirmed_legit|no_answer, outcome, created_at, completed_at)`

### API routes
- Not built yet. Express routes are open as **T03b** on the board.

### Findings format (fingerprint + vision → rules)
Defined in `src/fingerprint/types.ts`. T06 (vision) should return the same shape with `source: "vision"`.
```ts
interface Finding {
  check: string;        // stable id, e.g. "lookalike_domain", "bank_mismatch", "style_mismatch"
  expected: string;     // the vendor's normal
  actual: string;       // what this message shows
  severity: "high" | "medium" | "low" | "info" | "unknown";  // unknown = check couldn't run
  explanation: string;  // one sentence for the AP clerk
  source?: "rule" | "llm" | "vision";
  action?: "confirm_with_requester" | "callback_vendor";  // suggested next step; never decisive
}
```
- Fingerprint entry point: `fingerprint(db, msg, { llm?: LlmClient | false })` in
  `src/fingerprint/index.ts` → `{ vendorId, impersonating, profile, findings }`.
  Full check list: `src/fingerprint/README.md`.
- Billing-rhythm checks (rule, never decisive): `bill_too_soon` (medium), `fixed_amount_changed` (medium),
  `one_time_bill` (low, action `confirm_with_requester`), `no_billing_history` (low, action `confirm_with_requester`).
  Learned per vendor in `profile.rhythm`: `{ cadence: monthly|quarterly|irregular|none, intervalDays, lastInvoiceDate,
  expectedNextDate, fixedAmount, typicalAmount }`.

### Requester confirmation draft (fingerprint → T09 delivery)
- `draftRequesterConfirmation(db, vendorId, msg, findings, { llm?: LlmClient | false })` in `src/fingerprint/confirm.ts`
  → `RequesterDraft | null`:
  ```ts
  { recipient: { name, contact, department? } | null,  // internal district staff from the PO; null → AP lead
    poNumber: string | null, text: string, source: "llm" | "template",
    triggeredBy: string[], note?: string }
  ```
- Returns `null` unless a finding has `action: "confirm_with_requester"`. Never addressed to the email sender or the
  vendor; refuses a requester on the sender's domain. Text never carries bank numbers (model output with a 6+ digit
  number, or missing vendor/amount/yes-no, falls back to the template).
- **Nothing is sent.** T09 delivers `text` to `recipient.contact` (Slack DM / in-app) and records the yes/no reply.

- Suggested rule for T04 (not decided yet): HOLD if any `high`, or 2+ `medium`, or any finding
  from `bank_change_request`. A finding with severity `unknown` never clears a hold.
