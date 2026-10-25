# Hackathon compliance matrix (rewritten 2026-10-25 from measured evidence)

Source: Luma listing https://luma.com/builde-ixyz as quoted in the project brief (not re-fetched in this session).
Evidence host: the PREPARATION server (x86_64, 2x RTX 3090), never the GB10. Machine-readable: `artifacts/readiness.json`, `artifacts/runtime-verification/verify.json`.
Statuses: PASS | FAIL | NOT_TESTED | BLOCKED. Nothing here is PASS unless a probe observed it.

| ID | Requirement | Status | Evidence / what is missing |
|---|---|---|---|
| H01 | Autonomous always-on agent, useful work | NOT_TESTED | `phantomshift watch` is an autonomous inbox poller over fixtures, not an OpenClaw agent; gate needs an event-store incident started by a real OpenClaw agent |
| H02 | Runs on the event Dell Pro Max GB10 | NOT_TESTED | prep host is x86_64 / RTX 3090 by design |
| H03 | All inference local, no remote LLM | NOT_TESTED | only a Nano-4B Q4 GGUF ever ran (CPU, llama.cpp). Lightning NVFP4 and Nano FP8 are staged and verified-on-disk but never ran |
| H04 | NemoClaw + OpenClaw + OpenShell, real | NOT_TESTED | nemoclaw v0.0.137 + openshell 0.0.116 installed, preflight passes; onboarding failed on this host (rootless Docker, gateway bind); no sandbox ever created |
| H05 | Discord/Slack/Telegram through OpenClaw | NOT_TESTED | bot works through our REST rehearsal channel (not OpenClaw-managed); live approval round trip not yet observed (two timeouts, no operator reaction) |
| H06 | Final demo on the GB10 | NOT_TESTED | event-time |
| H07 | Judged on execution, value, local-first, demo | n/a (judging) | demo script `docs/DEMO_SCRIPT.md`; evidence matrix is this file + `docs/CLAIMS_AUDIT.md` |
| H08 | Team 2-5, each registered, in person 18+ | NOT_TESTED | administrative, outside the code |
| H09 | Schedule: build 10:00-18:00 PT Sun Oct 25, demos 18:30 | planned | `PROGRESS.md` |
| H10 | Bring offline SSD with models/datasets/packages | PARTIAL | stage built and verified on the prep server (199 files, 48 GB); not yet copied to the SSD; NemoClaw lists offline installs as unsupported so the GB10 still needs network at install |

Offline staging gate (what the operator's "H07 PASS" meant): `sha256sum -c manifest.sha256` exit 0 on 2026-10-25. Our `verify_hackathon.py` H07 means "claims audit present".

## Organizer questions
- **Prebuilt/scaffold code allowed?** Operator stated (2026-10-25) they are the event organizer, so this is theirs to decide. The rule itself is NOT yet recorded here: operator to state it. We disclose the scaffold regardless (`docs/DEMO_SCRIPT.md` line 1).
- Submission format, public-repo requirement, judging weights, post-event machine access: not on the public page; unrecorded.

## What can honestly be said today
Fixture-level counterfactual policy replay with a deterministic gate, strict payment adapter, hash-chained event store, 506 passing tests, a frozen 39-case suite with intervals, staged and checksummed GB10 assets. Not claimable: any live OpenClaw agent, NemoClaw sandbox, GB10 inference, OpenClaw-managed Discord, or measured savings.
