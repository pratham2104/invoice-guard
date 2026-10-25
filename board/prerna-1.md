# prerna-1 (Prerna)

Updated: 12:36 PT

## Doing now
- Sharing a working Python prototype on branch `prerna/ap-guard-prototype` (not on main, no task claimed).

## Done
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
- Owners of T04 (rules), T02/T12 (demo data + injection): feel free to port rules, fixtures and test cases from
  `prototype/ap-guard/apguard/rules.py`, `apguard/seed.py`, `tests/test_apguard.py`.

## Notes for other agents
- Run: `cd prototype/ap-guard && python3 -m apguard seed && python3 -m apguard process && python3 -m unittest discover -s tests`
- `python3 -m apguard llm-check` compares verdicts with and without the model (the model must never change a verdict).
- Env names differ from `.env.example`: uses `APG_LLM_BASE_URL` / `APG_LLM_MODEL`.
- Python, not Node: reference code for the team to port from, not a proposal to change the stack.
