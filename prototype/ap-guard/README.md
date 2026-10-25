# AP Guard (Tier 1)

Local-first agent that watches an accounts-payable inbox for vendor-payment fraud
(fake bank-detail changes, lookalike domains, duplicate/over-PO invoices, prompt injection),
holds suspicious items, and runs a human-approved verification case.

**Principle: the LLM reads, deterministic code decides, a human approves.**

```
.eml -> parser -> extractor (regex + optional local LLM, fixed JSON, no tools)
     -> rules.py (deterministic controls, fails closed)
     -> PASS (logged)  |  HOLD -> case -> verify via TRUSTED contact -> manager approves
                                   SQLite + hash-chained audit log + Slack cards
```

## Run (no dependencies, Python 3.11+)

```bash
python -m apguard seed        # vendors, history, POs + 6 demo emails in fixtures/inbox
python -m apguard process     # triage the inbox
python -m apguard cases
python -m apguard show CASE-0002
python -m apguard draft CASE-0002                 # phone callback script (vendor-master number only)
python -m apguard verify CASE-0002 --user alice   # start verification
python -m apguard confirm CASE-0002 --user alice --note "called Dana on file number"
python -m apguard approve CASE-0002 --user bob    # must be a manager and != the verifier
python -m apguard audit CASE-0002 ; python -m apguard verify-audit
python -m unittest discover -s tests -v
```

## Demo emails

| File | Expected |
|---|---|
| 01_normal_invoice | PASS, zero findings |
| 02_lookalike_bank_change | HOLD critical (`acmeindustrlal.example`, SPF/DKIM/DMARC fail, bank change, urgency) |
| 03_real_domain_new_contact | HOLD critical (genuine domain, unknown sender, bank + remit change) |
| 04_duplicate_invoice | HOLD (INV-7714 already paid) |
| 05_over_po_amount | HOLD ($18,450 vs PO $12,000) |
| 06_prompt_injection | HOLD (hostile instructions inside an otherwise clean invoice) |

## Test locally on a Mac before OpenClaw

1. **Deterministic path (no model):** `python -m apguard seed && python -m apguard process`, then the unit tests.
2. **Local LLM stand-in via Ollama.** The production model (Qwen3.6-35B-A3B-NVFP4) cannot run on a Mac:
   NVFP4 needs Blackwell tensor cores. Use a small Qwen3 with the same chat template and API shape:
   ```bash
   brew install ollama && ollama serve &          # OpenAI-compatible API on :11434
   ollama pull qwen3:4b                            # ~2.5 GB, fits an 8 GB Mac
   export APG_LLM_BASE_URL=http://localhost:11434/v1 APG_LLM_MODEL=qwen3:4b
   python -m apguard seed && python -m apguard llm-check
   ```
   `llm-check` runs every inbox email with and without the model and fails if any verdict or rule differs.
   The model only fills extraction gaps, so it must never change a verdict.
3. **Agent surface (what OpenClaw will call):**
   ```bash
   export APG_AGENT_MODE=1
   python -m apguard process --json; python -m apguard cases --json; python -m apguard draft CASE-0002 --json
   python -m apguard approve CASE-0002 --user bob   # -> BLOCKED (exit 2): approval is human-only
   ```
4. **Slack from your laptop.** Socket Mode needs no public URL, so this works locally. Map real Slack IDs to roles
   with `APG_USERS='{"U012ABC":"ap_clerk","U045DEF":"ap_manager"}'`.

### Moving to OpenClaw / NemoClaw
- Copy `openclaw/skills/ap-guard/` into your OpenClaw workspace `skills/` folder. Run the agent with
  `APG_AGENT_MODE=1` and the project directory as its working dir.
- Point the agent's model at the GB10's local endpoint (same `APG_LLM_*` vars for the extractor).
- Keep `python -m apguard slack` as a separate process. Humans press the buttons, and the agent can't.
- OpenShell policy: allow outbound only to Slack API domains plus the local inference port.

## Production stack (Dell Pro Max with GB10, all inference local)

```
Slack  <->  OpenClaw agent (ap-guard skill)  ->  apguard CLI (APG_AGENT_MODE=1)  ->  SQLite
               |                                    |  extractor
               +------------- vLLM :8000 -----------+  Qwen3.6-35B-A3B-NVFP4 (thinking on for agent, off for extraction)
OpenShell sandbox: egress only to Slack API + localhost:8000. NemoClaw packages the agent + sandbox.
```

One model serves both jobs. It is a MoE with ~3B active parameters, so it is fast, and at FP4 the weights
are roughly 20 GB, leaving most of the 128 GB unified memory for KV cache.

```bash
# On the GB10 (DGX OS). Check the exact checkpoint name and parser names for your vLLM version.
vllm serve <NVFP4 checkpoint path or HF id> \
  --served-model-name qwen3.6-35b-a3b --port 8000 \
  --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder

export APG_LLM_BASE_URL=http://localhost:8000/v1 APG_LLM_MODEL=qwen3.6-35b-a3b
python -m apguard llm-check        # must report "all verdicts match" before you demo
python -m apguard process --llm
```
Extraction requests send `chat_template_kwargs.enable_thinking=false` (set `APG_LLM_THINKING=1` to turn it back on).
The LLM only fills gaps in extraction. Bank-change, urgency and injection flags are always
computed by regex too and OR-ed in; if the model is down or returns junk, it degrades to regex.

## Slack (untested here; test on the box)

```bash
pip install slack-bolt
export SLACK_BOT_TOKEN=xoxb-... SLACK_APP_TOKEN=xapp-... APG_SLACK_CHANNEL=C0123...
# map Slack user IDs to roles in apguard/config.py USERS
python -m apguard slack
```
Socket Mode: no public URL. Buttons call the same `cases.py` functions, so controls cannot be bypassed.

## Controls implemented
Lookalike/homoglyph domains - Reply-To mismatch - SPF/DKIM/DMARC - unknown contact - bank
fingerprint (HMAC, raw account never stored/logged) - remit-address change - urgency - duplicate
invoice - PO missing/closed/other vendor/over amount - history outlier - prompt injection -
unknown vendor (fail closed) - callback only to vendor-master contacts - approval needs
manager role + segregation of duties - tamper-evident audit chain.

## Known gaps / next steps
- Approval does not yet update the vendor master (bank fingerprint) or release a payment.
- No PDF/attachment parsing (invoice details are read from the email body).
- No real IMAP; the inbox is a folder of .eml files.
- Fingerprint covers the account number only (not routing).
- Set `APG_FINGERPRINT_KEY` to a real secret on the box. USERS in config.py is a demo map.
- Sandbox: allow outbound only to Slack API domains + local vLLM.
