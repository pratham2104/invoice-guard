# Architecture

## Flow (as built: `src/pipeline/processEml`, run it with `npm run demo`)

```
.eml (AP inbox folder; Gmail IMAP later)
   ▼  parseEml: sender, reply-to, Authentication-Results, body, PDF attachments → temp files
fingerprint(db, msg)              src/fingerprint   resolve vendor · rule checks · PDF hidden text · rhythm
   │                                                · local Qwen language checks (optional, fails soft)
   ▼  + messageChecks(msg, auth)  src/rules         prompt-injection wording · SPF/DKIM/DMARC failures
decide(findings)                  src/rules         deterministic: PASS | HOLD_FRAUD_RISK | HOLD_CONFIRM
   ▼                     ▼                                  ▼
 PASS → log      HOLD_FRAUD_RISK                    HOLD_CONFIRM
                 openCase → callback script to       openCase → draftRequesterConfirmation()
                 vendors.phone_on_file               to the internal PO requester
                          └──────────────┬──────────────────┘
                                         ▼
                 audit_events (hash chain) · raiseAlert → Slack summary (if SLACK_WEBHOOK_URL) + in-app feed
                                         ▼
                 humans only: start_verification → record_confirmation → approve (manager, not the verifier)
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
- `holds(id HOLD-0001, invoice_id, email_id, vendor_id, reason, findings JSON (6+ digit numbers masked), status held|released|rejected,
  outcome, next_step, state, severity, score, source_file, verification_started_by, created_at, updated_at, resolved_at, resolved_by)`:
  one row per case; `resolved_by` is always a human.
- `callbacks(id, hold_id, vendor_id, phone, script, status open|confirmed_fraud|confirmed_legit|no_answer, outcome, created_at, completed_at)`
- `requester_checks(id, hold_id, recipient_name, recipient_contact, recipient_department, text, source llm|template, status open|confirmed|denied, reply, created_at, completed_at)`
- `audit_events(id, case_id, ts, actor, action, detail_json, prev_hash, hash)`: hash chain, see "Case workflow".
- `processed_messages(message_id, file, processed_at, outcome, case_id)`: each email processed once.
- `alerts(...)`: in-app feed, see "Alert format".

### API routes (T03b, `src/api/`)
- Run: `npm run api` → `http://127.0.0.1:${PORT_API:-4400}`. Loads `.env` like `npm run demo`; DB `DEMO_DB_PATH` (default
  `data/demo.db`, kept across restarts). Env: `HOST_API` (default 127.0.0.1), `CORS_ORIGINS` (default
  `http://localhost:5180,http://127.0.0.1:5180`), `INBOX_WATCH=0` turns the inbox folder watcher off, `LLM_BASE_URL`.
- `createApi({ dbPath, inboxDir?, invoicesDir?, llmBaseUrl?, slackWebhookUrl?, fetchImpl? })` in `src/api/app.ts` returns
  `{ app, ingest, reset, startWatching, ... }` (tests use `dbPath: ":memory:"`).
- JSON, camelCase. Errors are `{ error }`: 400 bad body, 403 control violation, 404 unknown case/file, 409 wrong state.
- Writes go only through `processEml` (ingest) and `src/cases` (human actions); one write at a time. No route lets the
  model approve. Every response is masked (6+ digit runs → `••••1234`); bank fields are `routingLast4` / `accountLast4`.

| Route | Returns |
|---|---|
| `GET /api/status` | `{ product:"Halberd", org, model:{endpoint,id,up}, mode:"model"\|"rules-only", cloudCalls:0, inbox:{watching,dir}, sandbox:{name:"OpenShell",egress:"local only"}, counts:{heldAmount,held,checkedToday,cleared,awaitingVendor,awaitingRequester} }`. `model.up` = `GET ${LLM_BASE_URL}/models` answers within 1.5 s (cached 10 s; non-local endpoints are never probed and count as down). `held` = non-terminal cases; `heldAmount` = sum of their known invoice amounts; `cleared` = PASS emails + APPROVED cases; `awaitingVendor`/`awaitingRequester` = held cases by `nextStep` (phone_callback / requester_confirmation). |
| `GET /api/cases` | newest first: `{ id, vendorId, vendorName, invoiceNumber, amount, outcome, nextStep, state, status, severity, score, reason, createdAt, topChecks }`. `amount` is `null` when the email carried no invoice (attack 1). `topChecks` = check ids from `decide().top` (map to words with `PHRASES` in src/alerts). |
| `GET /api/cases/:id` | `{ case (+resolvedAt, resolvedBy), vendor, bankOnFile, invoice:{current,lastReal}, email, findings, decision:{outcome,nextStep,score,severity,reasons}, callbacks, requesterChecks, audit:{events,chainOk,count} }`. `invoice.current` is parsed from the email's PDF the way the pipeline reads it (fixture invoice fields as a fallback); `lastReal` = the vendor's latest `paid`/`approved` invoice. `pdfUrl` → `/files/invoices/<name>.pdf` when the file exists. `audit.chainOk` verifies the whole global chain. |
| `GET /api/alerts` | `[{ id, ts, caseId, text, channel:"slack"\|"in-app", sent, vendorName, outcome, state, headline, reason }]` |
| `GET /api/vendors` | `[{ id, name, domain, phoneOnFile, invoices, lastPaid }]` |
| `GET /api/users` | `[{ id, role:"manager"\|"clerk" }]` from `IG_USERS` (default janet.kim clerk; omar.reyes, pat.lee managers) |
| `POST /api/cases/:id/callback` `{ result:"confirmed_fraud"\|"confirmed_legit"\|"no_answer", actor, note? }` | case detail. Starts verification first if the case is OPEN (that actor becomes the verifier). legit → READY_FOR_APPROVAL, fraud → REJECTED, no_answer → stays held (audit event). Also records the requester's yes/no on HOLD_CONFIRM cases. |
| `POST /api/cases/:id/approve` `{ actor, role }` | case detail. `cases.approve`: manager per the server's user list, state READY_FOR_APPROVAL, not the verifier. `role:"clerk"` → 403. |
| `POST /api/cases/:id/reject` `{ actor, role, reason? }` | case detail. Manager only (checked against the user list), any non-terminal state. |
| `POST /api/demo/reset` | fresh DB file + fixtures, no cases: `{ ok, loaded }` |
| `POST /api/demo/ingest` `{ file? }` | next unprocessed `.eml` in `data/emails/incoming` (or `file`) through `processEml`: `{ processed, caseId, outcome, skipped, mode }`. 409 when nothing is left. Uses the model only when `model.up`. |
| `GET /api/demo/files` | `[{ file, processed, outcome, caseId }]` |
| `GET /api/events` | SSE. `event: case` / `alert` with `data: {"id":...}`, `event: status` and `event: reset` with `data: {}`; sent after ingest, callback, approve, reject, reset. |
| `GET /files/invoices/:name` | PDFs from `data/invoices` only |

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
- Vision entry point (T06): `visionCheck(db, vendorId, pdfPath, { qwen?: VisionClient | false })` in
  `src/vision/index.ts` → `{ method, referencePdf, findings, regions, annotatedPng }`. Checks:
  `invoice_bank_changed` (high), `invoice_remit_changed` (high), `invoice_contact_changed` (medium),
  `invoice_visual_change` (low, model-only), `invoice_compare` (unknown). `annotatedPng` is page 1 of
  the new invoice with each change boxed (for T10). Not wired into `src/pipeline/` yet. Details: `src/vision/README.md`.

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

### Decision format (T04, `src/rules/index.ts`), ported from prerna-1's prototype `_finish`
```ts
decide(findings: Finding[], ctx?: { hasInvoice?: boolean }): Decision
messageChecks(msg, authResults?): Finding[]   // prompt_injection (email text), email_auth_failed (SPF/DKIM/DMARC)
interface Decision {
  outcome: "PASS" | "HOLD_FRAUD_RISK" | "HOLD_CONFIRM";
  nextStep: "none" | "phone_callback" | "requester_confirmation";
  score: number;        // high 45, medium 20, low 5, info/unknown 0; capped at 100
  severity: Severity;   // worst finding
  reasons: string[];    // plain sentences, no invoice/bank data
  top: Finding[];       // up to 3
  findings: Finding[];
}
```
Policy, in order: **HOLD_FRAUD_RISK** if any high, any bank/remit change (`bank_change_request`,
`first_bank_change`, `bank_mismatch`, `remit_change`, `payment_change_from_unknown_sender`), score ≥ 40, or an
unknown vendor sending an invoice → phone callback to `vendors.phone_on_file`. Else **HOLD_CONFIRM** if any finding has
`action: confirm_with_requester` or is a money/rhythm anomaly (`bill_too_soon`, `fixed_amount_changed`,
`one_time_bill`, `no_billing_history`, `amount_out_of_range`, `po_mismatch`, `invoice_out_of_sequence`) → requester
confirmation. Else **PASS**. `unknown` findings add no points and never clear a hold. The model never decides.

### Alert format (T09, `src/alerts/index.ts`), ported from prerna-1's `case_blocks`
- `raiseAlert(db, { caseId, vendorName, outcome, state, top })` → builds the alert, posts it to `SLACK_WEBHOOK_URL`
  if set (Slack hooks URLs only), and records it in the in-app `alerts` table
  (`id, case_id, created_at, vendor_name, outcome, state, headline, reason, slack_sent, slack_note`). `listAlerts(db)` reads the feed.
- Content: vendor, decision, top 1–3 reasons as fixed plain phrases (`PHRASES`), case id, state. Never invoice
  numbers, amounts, sender addresses or bank numbers; `scrub()` strips any digit run of 5+ and any address as a backstop.
- Webhook only: no interactive buttons (they need a public URL). Humans act on cases in the app/CLI.

### Case workflow (T15, `src/cases/index.ts`), ported from prerna-1's `cases.py`
```
OPEN ─startVerification─▶ AWAITING_VENDOR (fraud: phone)  │ AWAITING_REQUESTER (confirm: requester)
AWAITING_* ─recordConfirmation(yes)─▶ READY_FOR_APPROVAL ─approve─▶ APPROVED
AWAITING_* ─recordConfirmation(no)──▶ REJECTED ;  any non-terminal ─reject─▶ REJECTED
```
- `openCase(db, { decision, vendorId, messageId, invoiceNumber, msg })` is the only agent action: creates the hold,
  drafts the callback (phone from `vendors.phone_on_file`) or the requester question, writes audit events.
- `startVerification`, `recordConfirmation`, `approve`, `reject` are human-only (`ControlError` for the agent or an
  unknown user). `approve` needs role `ap_manager`, state `READY_FOR_APPROVAL`, and a different person from whoever
  started verification. Users/roles: `IG_USERS` JSON env, default `janet.kim` (clerk), `omar.reyes`, `pat.lee` (managers).
- Audit chain: `hash = sha256(prev_hash|case_id|ts|actor|action|detail_json)`, one global chain.
  `verifyAuditChain(db)` → `{ ok, firstBadId, events }`; any edited, deleted or reordered row breaks it.

### Pipeline (T15, `src/pipeline/index.ts`)
- `processEml(db, path, { llm?, slackWebhookUrl?, fetchImpl? })` → `{ file, messageId, skipped, decision, vendorId, vendorName, caseId, alert? }`.
  `processDir(db, dir, opts)` runs every `.eml` in filename order. Idempotent by Message-ID.
- `npm run demo`: fresh `data/demo.db`, all of `data/emails/incoming`, prints a table. Uses the model only if `LLM_BASE_URL` is set.

