# Decisions

One line each: what, why. Newest at the bottom. Don't relitigate without new facts.

- Idea: Invoice Guard over alternatives (FERPA records agent, factory camera, AI data-leak filter) — scores highest on all 4 judging criteria; real villain + dollar value + personal story.
- Model: Qwen3.6-35B-A3B-NVFP4 from USB — already downloaded and verified; fast; reads images. Nemotron Super 120B rejected for today (download size, thermal report).
- The model never decides: it produces findings; deterministic rules decide; humans release. No release tool.
- Bank changes verified by phone number on file, never by email (a hacked mailbox would confirm itself).
- Build: vendor fingerprint (core) + invoice vision check. Overnight self-test = slide unless both done by 2:30.
- Voice callback gated: start only if fingerprint + vision work end to end by 1:30.
- Vision fallback: if Qwen image compare is slow (>~20 s) or wrong at the 12:30 test, compare extracted text fields instead.
- Scope cuts: no real AP-system integration (SQLite fake data); dashboard is one page.
- Repo: one public repo; push to main; claiming a task locks its folders; one status file per agent.
- Slack gets summaries only, no invoice data.
- Data: Maria's 22 baseline emails are written for the demo, with cadence modelled on one real Enron sender (phillip.allen@enron.com). No Enron text is committed. Provenance in data/README.md.
- DB: Node's built-in node:sqlite (Node >= 22.13), not better-sqlite3, so nothing compiles natively on the GB10's ARM CPU.
- Fingerprint: rule checks are plain code; only urgency/style_mismatch/unusual_request come from Qwen. Unknown check ids from the model are dropped (stops injected findings).
- LLM client refuses non-local hosts in code (loopback, private ranges, *.local, *.internal, single-label names only).
- Hidden-text check flags tiny (<4pt), white-on-white, invisible-mode and off-page text; white text on a dark filled box (logos) is allowed.
- "today" counts as urgency only next to pay/payment/process/wire/transfer (Maria's "shipped today" isn't pressure).
- Red-team fixes (T05): a non-contact asking to change payment details is always high (`payment_change_from_unknown_sender`), even with no vendor match. Freemail senders claiming a vendor are high (`freemail_sender`).
- Vendor resolution needs a FULL vendor name or FULL contact name (display name or address local part); single generic words never match. A subdomain of the vendor's real domain counts as the vendor.
- Lookalikes now include plurals/suffixes (s, es, inc, llc, billing, payments, invoices, ar, ...) and combosquats (vendor domain inside a longer name, or all vendor-name tokens with one distinctive token).
- Bank-change wording widened ("different now", "going forward", "from now on", "remittance info", "payment instructions", "details in the attached letter", "remit to:"). Checked against all 22 of Maria's history emails: none trigger it.
- Billing rhythm (T05): cadence/interval/fixed-amount learned per vendor from past invoices. `bill_too_soon` (<50% of usual gap) and `fixed_amount_changed` (>15% off a fixed amount) are medium; `one_time_bill` (irregular vendor or no PO) and `no_billing_history` are low with action `confirm_with_requester`. None decide on their own.
- Surprise bills are confirmed with the internal PO requester (new `purchase_orders.requester_*` columns), never with the email sender or vendor. No-PO invoices go to the vendor's usual PO requester.
- Requester draft lives in `src/fingerprint/confirm.ts` (not a new src/confirm/ folder). Local Qwen writes it; model text is rejected (template used) if it has a 6+ digit number, or misses the vendor, amount or yes/no. Nothing is sent; T09 delivers.
- Prerna's (prerna-1) Python prototype merged as reference in prototype/ap-guard/ (unchanged). The TypeScript pipeline ports her decision, case and Slack logic; our fingerprint replaces her identity/bank checks so vendor resolution isn't duplicated.
- T04 decision: three outcomes PASS / HOLD_FRAUD_RISK (phone callback) / HOLD_CONFIRM (requester confirmation). Points per finding (high 45, medium 20, low 5) and HOLD at 40 come from her `_finish`. Two of her checks were ported as message checks: prompt-injection wording in the email body, and failed SPF/DKIM/DMARC (missing headers are not flagged: our demo emails have none).
- Divergences from her prototype: over-PO amounts become HOLD_CONFIRM (the requester can settle it) instead of a fraud hold; an unknown sender only fails closed when it sends an invoice or asks for a payment change (a newsletter passes).
- T09 alerts are webhook-only (SLACK_WEBHOOK_URL). Prerna's interactive Slack buttons (Socket Mode) were not ported: buttons need a public URL or a bot token on the box. Humans act on cases in the app/CLI. Alerts use fixed phrases, never message data.
- T15: one TypeScript pipeline (.eml → fingerprint → rules → case + audit + alert). Ported from prerna-1's prototype: case state machine, manager-only approval with segregation of duties, human-only actions (the agent only opens cases and drafts), and her hash-chained audit log (now `audit_events`, one global chain). Cases live in `holds` (new columns) with `callbacks` (phone always `vendors.phone_on_file`) and new `requester_checks`.
- Account-length numbers (6+ digits) are masked to the last 4 in stored findings and audit details, as her prototype did for bank accounts.
- The surprise demo email now carries its invoice as a PDF (data/invoices/ACME-1052-lab.pdf), so the pipeline reads amount and PO from the attachment like a real invoice.
- Build order was T04 → T09 → T15 (not T04 → T15 → T09) because the pipeline calls the alerts module.
- Vision (T06): the text compare always runs and draws the boxes (PDF text positions are exact); Qwen vision only adds findings, and a model-only claim the PDF text contradicts stays `low`. Rendering uses `@napi-rs/canvas` (already in the lockfile via pdfjs-dist; prebuilt for linux-arm64).
- T17 verify-local is evidence, not a gate: checks that can't run on a machine (GPU on a Mac) skip instead of failing. It never prints or stores env values, only names. Idea from Chetas's verify_qwen_route.py; written fresh in TypeScript.
- First real-model run (14:55, via SSH tunnel): attack 2's urgency/style_mismatch/unusual_request come back exactly as designed and the requester draft passes its guard. It also exposed a false positive: vendors with no email history (Bright Bus) get style_mismatch. Fixed in T19 (see below).
- T19: Qwen style checks need at least 5 past emails from the vendor (MIN_STYLE_BASELINE). Below that the model is asked only about urgency and unusual requests, and any style_mismatch it returns is dropped. Verified on the real model: Bright Bus control is PASS again; attack 2 still gets urgency/style_mismatch/unusual_request.
- T18 supersedes the "webhook only" note for T09: with SLACK_BOT_TOKEN + SLACK_APP_TOKEN the bot posts case cards and a Socket Mode listener (no public URL) handles buttons through src/cases. Webhook path kept as the fallback. Uses @slack/bolt (public open source); idea from Chetas's branch, written fresh. Bot tokens only: xoxp- user tokens are refused in code.
