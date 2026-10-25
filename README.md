# 🛡️ Invoice Guard

**Trust the vendor, not the email.** An always-on AI agent that stops school districts from
paying fake invoices — running entirely on a Dell Pro Max with GB10. No cloud AI.

Built at the Dell x NVIDIA AI Hackathon, San Francisco, 25 Oct 2026.

## What it does
Watches the AP inbox 24/7, compares every email and invoice to that vendor's own normal
behaviour (writing style, amounts, bank, invoice layout), holds anything suspicious before
the pay run, and creates a callback task using the phone number already on file.
The AI finds what's different; fixed rules decide; a human releases. The agent has no
"approve" tool, so instructions hidden inside an invoice have nothing to call.

## Stack
OpenClaw in NVIDIA NemoClaw + OpenShell · Qwen3.6-35B-A3B-NVFP4 on vLLM · Node/Express ·
React · SQLite · Slack (summaries only). Details: [docs/TOOLS.md](docs/TOOLS.md).

## Run it
```
npm install
npm test        # 88 tests
npm run demo    # processes the 5 demo emails: 3 attacks + 1 surprise bill held, 1 normal invoice passes
```

## Docs
- [Product](docs/PRODUCT.md) · [Architecture](docs/ARCHITECTURE.md) · [Tools](docs/TOOLS.md)
- [GB10 setup](docs/SETUP.md) · [Decisions](docs/DECISIONS.md)

## Working in this repo
Multiple coding agents build this at once. Rules: [CLAUDE.md](CLAUDE.md).
Who's doing what: [board/TASKS.md](board/TASKS.md).

## Credits
- **Prerna (prerna-1)**: the AP Guard prototype in [`prototype/ap-guard/`](prototype/ap-guard/). Its decision scoring,
  prompt-injection and SPF/DKIM/DMARC checks, case state machine with segregation of duties, hash-chained audit log
  and Slack case cards were ported into `src/rules`, `src/cases` and `src/alerts`.
- Pratham (pratham-1, pratham-2): fingerprint, demo data, pipeline.

