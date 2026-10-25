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
