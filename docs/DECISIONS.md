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
