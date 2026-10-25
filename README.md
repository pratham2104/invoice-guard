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

## Docs
- [Product](docs/PRODUCT.md) · [Architecture](docs/ARCHITECTURE.md) · [Tools](docs/TOOLS.md)
- [GB10 setup](docs/SETUP.md) · [Decisions](docs/DECISIONS.md)

## Working in this repo
Multiple coding agents build this at once. Rules: [CLAUDE.md](CLAUDE.md).
Who's doing what: [board/TASKS.md](board/TASKS.md).
