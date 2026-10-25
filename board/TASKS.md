# Task board

The one shared file. Change only your own row, one line at a time, and push right away.
Status: `open` → `claimed` → `in-progress` → `done` (or `blocked`).
"Folders" are locked to the owner until the task is `done`.

| ID | Task | Status | Owner | Folders | Notes |
|----|------|--------|-------|---------|-------|
| T01 | GB10: NemoClaw + Qwen running, model answers locally | in-progress | pratham-1 | `docs/SETUP.md` | Model copied from USB; installer next |
| T02 | Fake data: 1 real vendor with 20 normal emails + 3 real invoices, 3 attack emails/invoices, SQLite seed | done | pratham-2 | | See PRODUCT.md "Demo scenarios". Do this first, everything tests against it |
| T03 | App skeleton: Node/Express API + SQLite schema (vendors, invoices, payments, holds, callbacks) | done | pratham-2 | | Schema + loader + package.json done. Express routes split out as T03b |
| T03b | Express API routes over the DB (vendors, invoices, holds, callbacks); add deps to package.json | open | | `src/api/` | Schema in ARCHITECTURE.md Interfaces |
| T04 | AP control rules (deterministic pass/hold) | open | | `src/rules/` | Needs T03 schema |
| T05 | Vendor fingerprint: profile per vendor + Qwen "what's different" compare | done | pratham-2 | | Rules done + tested; Qwen language checks written, mocked in tests, NOT yet tried on the real GB10 model |
| T06 | Invoice vision check: Qwen compares new invoice image vs last real one | open | | `src/vision/` | Test speed/accuracy by 12:30; fallback = compare text fields |
| T07 | OpenClaw tools: lookup_vendor, check_invoice, hold_payment, post_alert, create_callback_task | open | | `agent/` | No release tool, by design |
| T08 | Inbox watcher: folder of .eml/PDF (backup) + Gmail IMAP (live demo) | open | | `src/inbox/` | |
| T09 | Alerts: Slack summary (no invoice data) + in-app alert feed | open | | `src/alerts/` | Webhook URL in .env only |
| T10 | React dashboard, ONE page: held payments, vendor card with red "what's different", invoice side-by-side | open | | `web/` | |
| T11 | Voice callback: Asterisk + call bridge + whisper.cpp + Piper | open | | `voice/` | GATED: only start if T05 + T06 work end to end by 1:30 |
| T12 | Prompt-injection invoice demo (hidden "approve this" text gets ignored) | open | | `data/attacks/`, `tests/` | Coordinate with T02 owner |
| T13 | Overnight self-test (agent attacks itself) | open | | `src/selftest/` | STRETCH: only if T05 + T06 done by 2:30, else a slide |
| T14 | Submission: demo video < 2 min, write-up, deck, NVIDIA form answers | open | | `submission/` | Record on the box before 5:15 |
