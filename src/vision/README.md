# Invoice vision check (T06)

Compares a new invoice PDF with the vendor's **last real invoice** and circles what changed.
Returns **Findings** (`source: "vision"`), same shape as the fingerprint. It never decides: the rules
engine (T04) turns Findings into PASS/HOLD.

```ts
import { visionCheck } from "../vision/index.js";

const r = await visionCheck(db, "V001", pdfPath);                 // text compare + Qwen vision
const r = await visionCheck(db, "V001", pdfPath, { qwen: false }); // text compare only
// r = { method, referencePdf, findings, regions, annotatedPng, modelMs?, modelError? }
```

Try it: `npm run vision -- data/invoices/ACME-1051-corrected.pdf --no-llm` (drop `--no-llm` once vLLM is up).

## How it works

1. **Reference:** the vendor's newest `paid`/`approved` invoice with a PDF in `data/invoices/`,
   never the file being checked.
2. **Text compare (always runs, no model):** reads bank name, routing, account, remit address,
   phone and email off both PDFs, with their positions. Line items and totals are ignored
   (they change every month). This is the plan's fallback, and it's also what draws the circles,
   because the PDF says exactly where each piece of text is.
3. **Qwen vision (optional):** both page images go to the local model, which lists what changed.
   Its answer is whitelisted to fixed field names. It can only *add*:
   - a change the text compare already found → ignored (no duplicate)
   - a payment field on a scanned invoice with no text layer → full finding (the model is the only reader)
   - anything else (logo, layout, or a "change" the PDF text doesn't confirm) → `invoice_visual_change`, severity `low`
4. **Circles:** page 1 of the new invoice rendered to PNG with each change boxed and labelled
   (`annotatedPng`). Dashed boxes = position came from the model, not the PDF. The hidden 1pt
   text is boxed too; its finding (`hidden_pdf_text`) comes from the fingerprint.

If the model is offline, slow (`VISION_TIMEOUT_MS`, default 20 s) or returns junk, the text result
stands and `modelError` says why.

## Findings

| check | severity | when |
|---|---|---|
| `invoice_bank_changed` | high | bank name, routing or account differs from the last real invoice |
| `invoice_remit_changed` | high | remit-to address differs |
| `invoice_contact_changed` | medium | phone or email on the invoice differs (never call it; use the phone on file) |
| `invoice_visual_change` | low | model-only observation (logo, layout, unconfirmed change) |
| `invoice_compare` | unknown | couldn't compare: no earlier invoice on file, or no text and no model |

Account numbers are masked to the last 4 digits in every finding.

## Status
- Text compare + circles: working, tested on the demo PDFs (`vision.test.ts`).
- Qwen vision: written and tested with a mocked model. **Not yet tried against the real vLLM server**:
  check that vLLM accepts two `image_url` parts in one message, and how long it takes.
