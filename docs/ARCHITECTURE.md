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

### Database schema
- *(T03 owner: publish tables here.)*

### API routes
- *(T03 owner: publish routes here.)*

### Findings format (fingerprint + vision → rules)
- *(T05/T06 owners: agree a JSON shape here before building, e.g.
  `{ source, field, expected, actual, severity, explanation }`.)*
