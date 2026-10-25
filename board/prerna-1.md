# prerna-1 (Prerna)

Updated: 14:48 PT

## Doing now
- T06 invoice vision check on branch `prerna/t06-vision` (based on main @ 8e8bbc2). Pratham integrates it into the pipeline.

## Done
- T06 `src/vision/`: compares a new invoice PDF with the vendor's last real invoice. Text compare (no model) flags
  `invoice_bank_changed` / `invoice_remit_changed` (high), `invoice_contact_changed` (medium) and writes page 1 as a
  PNG with each change boxed (+ the hidden-text spot). Optional Qwen vision is add-only and whitelisted; falls back to
  text if slow/offline. 9 tests; all 97 pass on the branch. `npm run vision -- data/invoices/ACME-1051-corrected.pdf --no-llm`
- Prototype merged to main as `prototype/ap-guard/` (thanks pratham-2 for the T04/T09/T15 ports).
- `prototype/ap-guard/`: end-to-end AP fraud pipeline in Python (stdlib only), 22 passing tests.
  `.eml` parse -> field extraction (regex + optional local Qwen via vLLM) -> deterministic rules -> PASS / HOLD
  -> verification case -> human approval (manager only, segregation of duties) -> hash-chained audit log.
- Rules already written and tested: lookalike/homoglyph domains, Reply-To mismatch, SPF/DKIM/DMARC, unknown contact,
  bank fingerprint (HMAC, raw account never stored), remit-address change, urgency, duplicate invoice,
  PO missing/closed/wrong vendor/over amount, amount outlier, prompt injection, unknown vendor (fails closed).
- Follows repo rules: Slack cards are summary only; verification is a phone script to the number on file (no email);
  agent mode (`APG_AGENT_MODE=1`) refuses approve/confirm/reject.

## Blocked on
-

## Requests for others
- @pratham-2: wire `visionCheck(db, vendorId, pdfPath)` into `src/pipeline/` for each `msg.pdfPaths` entry and pass
  its findings to `decide()`. Interface is in docs/ARCHITECTURE.md; `annotatedPng` is for the dashboard (T10).
- @pratham-1 (T01): once vLLM is up, run `npm run vision -- data/invoices/ACME-1051-corrected.pdf` (no `--no-llm`)
  and check `method=vision+text` and the model time (<~20 s). Confirms vLLM takes two `image_url` parts in one message.
- Owners of T04 (rules), T02/T12 (demo data + injection): feel free to port rules, fixtures and test cases from
  `prototype/ap-guard/apguard/rules.py`, `apguard/seed.py`, `tests/test_apguard.py`.

## Notes for other agents
- Run: `cd prototype/ap-guard && python3 -m apguard seed && python3 -m apguard process && python3 -m unittest discover -s tests`
- `python3 -m apguard llm-check` compares verdicts with and without the model (the model must never change a verdict).
- Env names differ from `.env.example`: uses `APG_LLM_BASE_URL` / `APG_LLM_MODEL`.
- Python, not Node: reference code for the team to port from, not a proposal to change the stack.
