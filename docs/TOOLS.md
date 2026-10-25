# Tools and stack

| Layer | What | Runs where | Why |
|---|---|---|---|
| Hardware | Dell Pro Max with GB10 (Ubuntu 24.04, arm64, NVIDIA GB10, 128 GB unified memory) | On the table | Required; enough memory for model + speech at once |
| Agent | **OpenClaw** agent inside a **NemoClaw** sandbox, with an **OpenShell** policy allowing only local addresses | GB10 | Required stack; sandbox makes the prompt-injection story real |
| Language model | **vLLM** serving **Qwen3.6-35B-A3B-NVFP4** (35B total, ~3B active per token; reads images; 262k context) | GB10 (`localhost:8000`, TBC) | Fast MoE, NVFP4 is native to the GB10 chip, vision for the invoice check. Loaded from our USB drive |
| App | Invoice Guard: **Node/Express** API, **React** dashboard, **SQLite** | GB10 | Simple, one process, no external DB |
| Alerts | **Slack** incoming webhook — short summary only, no invoice data | Internet | Judges like seeing alerts land. In-app feed is the fully local option |
| Phone system (gated) | **Asterisk**, controlled through its built-in remote-control interface | GB10 | Open-source; in production it becomes one extension on the district's phone system |
| Call bridge (gated) | Our small service: places the call, plays each question, records each answer | GB10 | |
| Speech-to-text (gated) | **whisper.cpp** on the GPU, `small.en` model | GB10 | Local, fast |
| Text-to-speech (gated) | **Piper**, English voice (`en_US-lessac-medium`) | GB10 | Local, fast |
| "Vendor's phone" (demo) | Teammate's phone running **Linphone**, logged in to Asterisk | Same local network | Phone rings in the room; call never touches the internet |
| Network | A **phone hotspot** with the GB10 and laptops on it | In the room | Venue Wi-Fi blocks device-to-device traffic |

**Slack is the one exception to "all local":** it's an internet service. Keep alerts to a
short summary with no invoice data, and say so: *"Alerts are a heads-up; the data stays on
the box."*

## Rejected / not used

- Nemotron 3 Super 120B: smarter, but ~3x bigger download and a forum report of thermal
  shutdowns on long inputs. Possible later swap; not today.
- Cloud LLM APIs: forbidden by the rules and by our design.

## Open-source inspiration (allowed: public open source)

| Piece | Project | What we take |
|---|---|---|
| Lookalike domains | dnstwist | Its fuzzing tricks: swaps, homoglyphs (1/l), hyphens, TLD swaps |
| Unicode tricks | Unicode TR39 confusables | Cyrillic/Latin lookalike letters |
| Email parsing | mailparser, imapflow (Node) | .eml + Gmail IMAP |
| Hidden PDF text | pdfjs-dist | Text items with size/position → tiny/off-page/white text |
| Invoice fields | invoice2data | Field-extraction patterns |

## Datasets (samples only)
- Writing-style baseline: Enron email corpus (one sender as the "vendor").
- Invoice images: Voxel51/high-quality-invoice-images-for-ocr (Hugging Face).
- Scam phrasing: zefang-liu/phishing-email-dataset (Hugging Face).
