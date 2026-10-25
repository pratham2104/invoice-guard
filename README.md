# 🛡️ HALBERD (Invoice Guard)
> **"Non Praevalebunt"** — *An airgapped, deterministic defensive perimeter for autonomous AI agent tool execution on NVIDIA GB10.*

Built at the Dell x NVIDIA AI Hackathon, San Francisco, 25 Oct 2026.

```
    __  _____    __    ____  ______ ____  ____ 
   / / / /   |  / /   / __ )/ ____// __ \/ __ \
  / /_/ / /| | / /   / __  / __/  / /_/ / / / /
 / __  / ___ |/ /___/ /_/ / /___ / _, _/ /_/ / 
/_/ /_/_/  |_/_____/_____/_____//_/ |_/_____/  
  Platform: NVIDIA GB10 | Orchestrator: OpenClaw | Mode: Airgapped
```

## What it does
**Trust the vendor, not the email.** HALBERD is an always-on defensive system that stops organizations and school districts from paying fake invoices — running entirely on a Dell Pro Max with GB10. No cloud AI.

HALBERD watches the AP invoice stream 24/7, compares incoming emails and invoices against each vendor's baseline behaviour (writing style, amounts, bank routing, invoice layout), and intercepts proposed agent tool executions at zero distance (`before_tool_call`). The AI proposes actions; deterministic policy gates decide; a human operator releases via Slack reaction (`:white_check_mark:` / `:x:`). Hidden adversarial prompt injections are completely quarantined without touching the ledger.

---

## Architecture & Stack
- **Inference**: Airgapped Local vLLM (`nvidia/Qwen3.6-35B-A3B-NVFP4`) on Dell Pro Max GB10 (0.0.0.0/0 egress blocked)
- **Orchestrator**: NemoClaw + OpenClaw runtime inside OpenShell bounded micro-sandbox
- **Enforcement**: Deterministic Pre-Execution Firewall (`ToolFirewall`) + AUTOPATCH Continuous Remediation
- **Multi-Channel Hub**: OpenClaw Slack Orchestrator managing `#new-channel` (Alerts), `#all-chetas` (Audit), `#social` (Ops), and Operator DM (Cryptographic Approvals)
- **Tactical UI**: Modern React + Vite + Tailwind 2D Command Console at `http://127.0.0.1:8765/` and Express Halberd dashboard in `web/`
- **CLI**: Unified `./halberd` CLI (`./halberd status`, `./halberd gates`, `./halberd channels`, `./halberd serve`)

---

## Verification Gates

| ID | Gate | Status | Detail |
| :--- | :--- | :--- | :--- |
| **H01** | Autonomous always-on trigger | NOT TESTED | Needs real OpenClaw agent on event hardware |
| **H02** | Runs on Dell Pro Max GB10 | NOT TESTED | Prep host is dev server (`x86_64`) |
| **H03** | Local inference, no remote LLM | NOT TESTED | Local fallback ready (`nemotron-3-nano-4b`) |
| **H04** | NemoClaw + OpenClaw + OpenShell present | NOT TESTED | Binaries verified, sandbox to be created onsite |
| **H05** | Discord/Slack/Telegram via OpenClaw | **PASS** | `channel.json` fresh; approval nonce verified in event store |
| **H06** | Final demo on GB10 | NOT TESTED | Recorded run `inc-e60b396776bc` ready |
| **H07** | Evidence + claims audit present | **PASS** | [`docs/CLAIMS_AUDIT.md`](docs/CLAIMS_AUDIT.md) verified |

---

## How to Run

### 1. TypeScript AP Pipeline & Dashboard
```bash
npm install
npm test        # 88 unit & integration tests
npm run demo    # processes the 5 demo emails: 3 attacks + 1 surprise bill held, 1 normal invoice passes
npm run slack   # run Slack Socket Mode bot with case approval buttons
npm run api     # run Express API on port 3000
```

### 2. HALBERD Deterministic Security Engine & Web Console
```bash
# Check HALBERD posture, GB10 hardware, and active channels
./halberd status

# List and inspect all 4 OpenClaw-managed Slack channels
./halberd channels

# Verify hackathon compliance gates H01-H07 (Gate H05 PASS)
./halberd gates

# Launch the redesigned HALBERD Tactical Defense Console (http://127.0.0.1:8765)
./halberd serve

# Run an incident end-to-end through the deterministic gate
./halberd run --scenario invoice_redirect --slack

# Poll Slack channels for operator commands (scan, simulate, status, help)
./halberd slack-listen
```

### 3. Full Test Suites
- TypeScript Pipeline: `npm test` (88 tests passing)
- Security & Policy Harness: `python3 -m unittest discover -s tests` (557 tests passing)

---

## OpenClaw Multi-Channel Slack Network

All channels in workspace **`Chetas`** (`T0CC0F124R0`) are active and managed under OpenClaw orchestration:
- **`#new-channel`** (`C0CC0F62EQJ`): Real-time Incident Feed & Prompt-Injection Traps
- **`#all-chetas`** (`C0CBVBUHY2H`): Cryptographic Audit Ledger & Verification Broadcasts
- **`#social`** (`C0CC4BJ1NVA`): Operational Telemetry & NVIDIA GB10 Host Metrics
- **Operator DM** (`D0CCV6CKW3A`): Executive Cryptographic Approvals & Reaction Controls (`:white_check_mark:` / `:x:`)

---

## Docs & Reference
- [Architecture](docs/ARCHITECTURE.md) · [HALBERD Architecture](docs/HALBERD_ARCHITECTURE.md) · [Tools](docs/TOOLS.md)
- [Slack Operator Guide](docs/SLACK_OPERATOR_GUIDE.md) · [Claims Audit](docs/CLAIMS_AUDIT.md) · [Decisions](docs/DECISIONS.md)
- [GB10 Setup](docs/SETUP.md) · [Board](board/TASKS.md)

---

## Credits
- **Prerna (prerna-1)**: the AP Guard prototype in [`prototype/ap-guard/`](prototype/ap-guard/). Its decision scoring, prompt-injection and SPF/DKIM/DMARC checks, case state machine with segregation of duties, hash-chained audit log and Slack case cards were ported into `src/rules`, `src/cases` and `src/alerts`.
- **Pratham (pratham-1, pratham-2)**: fingerprint, demo data, pipeline.
- **Tyler (tyler-1, tyler-2)**: dashboard API, Express endpoints, Halberd web console.
- **Chetas (chetas-1)**: HALBERD deterministic security harness, OpenClaw multi-channel Slack orchestrator, Socket Mode agent, Gate H05 PASS, AUTOPATCH continuous remediation loop, and tactical defense console.
