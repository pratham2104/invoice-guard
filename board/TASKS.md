# Task board

The one shared file. Change only your own row, one line at a time, and push right away.
Status: `open` → `claimed` → `in-progress` → `done` (or `blocked`).
"Folders" are locked to the owner until the task is `done`.

| ID | Task | Status | Owner | Folders | Notes |
|----|------|--------|-------|---------|-------|
| T01 | GB10: NemoClaw + Qwen running, model answers locally | in-progress | pratham-1 | `docs/SETUP.md` | Model copied from USB; installer next |
| T02 | Fake data: 1 real vendor with 20 normal emails + 3 real invoices, 3 attack emails/invoices, SQLite seed | done | pratham-2 | | See PRODUCT.md "Demo scenarios". Do this first, everything tests against it |
| T03 | App skeleton: Node/Express API + SQLite schema (vendors, invoices, payments, holds, callbacks) | done | pratham-2 | | Schema + loader + package.json done. Express routes split out as T03b |
| T03b | Express API routes over the DB (vendors, invoices, holds, callbacks); add deps to package.json | done | tyler-1 | `src/api/` | Express API (src/api/): status, cases, case detail, alerts, vendors, callback/approve/reject (manager-only), demo reset/ingest/files, SSE events, invoice PDFs; inbox folder watch; 11 route tests. Run: npm run api (port 4400) |
| T04 | AP control rules (deterministic pass/hold) | done | pratham-2 | | decide() + messageChecks() ported from prerna-1's prototype; 18 tests |
| T05 | Vendor fingerprint: profile per vendor + Qwen "what's different" compare | done | pratham-2 | | Rules, red-team, rhythm + requester-confirmation drafts done (47 tests). Qwen paths NOT yet tried on the real GB10 model |
| T06 | Invoice vision check: Qwen compares new invoice image vs last real one | done | prerna-1 | | Merged. Standalone `npm run vision`; NOT yet wired into src/pipeline + src/rules (see T16) |
| T16 | Wire T06 vision findings into the pipeline + rules (demo table + dashboard image) | open | | `src/pipeline/`, `src/rules/` | Qwen vision works on our vLLM (multimodal loaded) |
| T07 | OpenClaw tools: lookup_vendor, check_invoice, hold_payment, post_alert, create_callback_task | open | | `agent/` | No release tool, by design |
| T08 | Inbox watcher: folder of .eml/PDF (backup) + Gmail IMAP (live demo) | open | | `src/inbox/` | |
| T09 | Alerts: Slack summary (no invoice data) + in-app alert feed | done | pratham-2 | | Slack webhook summary + in-app alerts feed (port of prerna-1's case_blocks); 5 tests |
| T10 | React dashboard, ONE page: held payments, vendor card with red "what's different", invoice side-by-side | claimed | tyler-2 | `web/` | |
| T11 | Voice callback: Asterisk + call bridge + whisper.cpp + Piper | open | | `voice/` | GATED: only start if T05 + T06 work end to end by 1:30 |
| T12 | Prompt-injection invoice demo (hidden "approve this" text gets ignored) | open | | `data/attacks/`, `tests/` | Coordinate with T02 owner |
| T13 | Overnight self-test (agent attacks itself) | open | | `src/selftest/` | STRETCH: only if T05 + T06 done by 2:30, else a slide |
| T14 | Submission: demo video < 2 min, write-up, deck, NVIDIA form answers | open | | `submission/` | Record on the box before 5:15 |
| T15 | Pipeline + case workflow: .eml → fingerprint → rules → case + audit + alert; case state machine, roles, hash-chained audit (port of prerna-1's cases.py); `npm run demo` | done | pratham-2 | | Pipeline, cases, audit chain, `npm run demo` done (ported from prerna-1); 18 tests |
| T17 | `npm run verify-local`: local-inference proof (GPU, loopback port, weights, /v1/models, chat, tool call, injection hold, egress audit, NemoClaw route) + demo banner | done | pratham-2 | | `npm run verify-local`; 6/9 pass from the Mac via tunnel (GPU/weights/NemoClaw skip off-box). Needs a full run on the GB10 |
| T18 | Slack bot + buttons: chat.postMessage case cards + Socket Mode listener (`npm run slack`) wired to src/cases with role checks | in-progress | pratham-2 | `src/alerts/`, `.env.example` | Idea from Chetas's branch (Socket Mode, Block Kit), written fresh. Tokens only in ~/.invoice-guard-slack.env on the GB10 |
| T19 | Fix: skip Qwen style checks for vendors without enough email history (false style_mismatch on Bright Bus control) | done | pratham-2 | | Verified on the real model via tunnel: control PASS, attacks unchanged |
