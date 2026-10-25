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
