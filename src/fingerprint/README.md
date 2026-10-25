# Vendor fingerprint (T05)

Compares one incoming message to the claimed vendor's own normal and returns **Findings**.
It never decides: the rules engine (T04) turns Findings into PASS/HOLD.

```ts
import { openDb } from "../db/index.js";
import { fingerprint, messageFromFixture } from "./index.js";

const r = await fingerprint(db, msg);                 // rule checks + local Qwen language checks
const r = await fingerprint(db, msg, { llm: false }); // rule checks only (no model needed)
// r = { vendorId, impersonating, profile, findings: Finding[] }
```

| File | What |
|---|---|
| `types.ts` | `Finding`, `IncomingMessage`, `VendorProfile` |
| `profile.ts` | Builds a vendor's normal from the DB (contacts, bank, amounts, billing day, invoice #s, style) |
| `domain.ts` | Lookalike domains: homoglyphs/confusables, hyphenation, TLD swap, subdomain, typo |
| `rules.ts` | Rule checks (no model) |
| `pdf.ts` | PDF text + hidden text (tiny, white-on-white, invisible, off-page) via pdfjs-dist |
| `text.ts` | Shared patterns: bank-change wording, urgency, bank details, invoice fields from PDF text |
| `llm.ts` | Language checks by the local Qwen (urgency, style_mismatch, unusual_request). Fails soft. Refuses non-local hosts |

## Checks

Rule (`source: "rule"`): `lookalike_domain`, `unknown_sender`, `reply_to_mismatch`,
`bank_change_request`, `first_bank_change`, `bank_mismatch`, `remit_change`,
`duplicate_invoice`, `invoice_out_of_sequence`, `po_mismatch`, `amount_out_of_range`,
`off_cycle_date`, `hidden_pdf_text`, `unknown_vendor`.

Model (`source: "llm"`): `urgency`, `style_mismatch`, `unusual_request`. Anything else the model
returns is dropped, so an injected "approve_payment" finding can't get through.
If the model is unreachable you get one `language_checks` finding with severity `unknown`.

## Model endpoint

`LLM_BASE_URL` (default `http://localhost:8000/v1`), `LLM_MODEL` (default
`nvidia/Qwen3.6-35B-A3B-NVFP4`). Only loopback, private-range, single-label, `*.local` and
`*.internal` hosts are accepted. The request sets `chat_template_kwargs.enable_thinking=false`
and `response_format: json_object`. Neither has been tried against the real vLLM server yet.
