# 3-minute demo script

Read 2026-10-24 about 10:00Z. Builds on `artifacts/demo/demo_script.md` (draft). Judged on technical execution, business value, local-first design and demo quality (`docs/HACKATHON_COMPLIANCE.md`, R07). Submission format, prebuilt-code rules and weights are unknown; do not invent them in the pitch.

Rule for this whole script: **a segment may only be spoken as "live" if its live-evidence check in section 2 is green at demo time.** Otherwise the fixture line is spoken, word for word. Nothing here lets a recording, a fixture or a rehearsal channel be passed off as a live OpenClaw agent.

## 1. Status key

| Tag | Meaning |
|---|---|
| TODAY | Works on the preparation host now (x86_64, 2x RTX 3090) on fixtures. Always labelled fixture. |
| GB10-LIVE | Must run on the Dell GB10 through NemoClaw/OpenClaw/OpenShell with a local model. **Not built, not run anywhere.** |
| UNKNOWN | Depends on something the docs or organizers have not told us. |

## 2. Live-evidence checks (all must be green before the word "live" is spoken)

| Claim you want to make | Check (run on the GB10, from real command output) | Today |
|---|---|---|
| "This is the Dell GB10" | `python3 scripts/verify_hackathon.py --competition` shows H02 PASS | H02 not PASS (x86_64) |
| "Inference is local" | H03 PASS and `artifacts/runtime-verification/local-inference.json` from real output | not produced, no model server |
| "NemoClaw, OpenClaw, OpenShell are running" | H04 PASS plus `nemoclaw <sandbox> status` output saved | `openclaw` not found; nothing running |
| "The approval came through the agent's channel" | H05 PASS: `channel.json` with `is_live`, `openclaw_managed`, `type`, `round_trip` | no proof file; Discord path is the REST rehearsal channel |
| "The agent works on its own" | H01 PASS: a live OpenClaw agent trace in `artifacts/runs/` | `trigger.py` polls a local fixture directory and says it is not H01 |

Statuses are in `artifacts/runtime-verification/verify.json`. Note that running the unit tests rewrites that file in competition mode; re-run `python3 scripts/verify_hackathon.py` for prep-mode statuses.

## 3. Pre-demo setup

| Step | Command | Status |
|---|---|---|
| Start the console | `python3 -m phantomshift --port 8765` then open `http://127.0.0.1:8765` (binds loopback only) | TODAY (UI is being reworked by another contributor, see `PROGRESS.md`) |
| Pre-generate a fixture run to show if the UI is down | `python3 -m phantomshift run --scenario invoice_redirect` writes `artifacts/runs/<id>.json` | TODAY |
| Print the numbers | `python3 -m phantomshift eval` (rewrites `artifacts/benchmarks/results.json`) | TODAY |
| Operator channel rehearsal | `python3 -m phantomshift run --scenario invoice_redirect --discord --wait 90` | TODAY, REST rehearsal channel, **not** OpenClaw-managed |
| Real model sampling | `python3 -m phantomshift model-replay --scenario invoice_redirect --model <name> --base-url http://127.0.0.1:8000/v1` | harness exists; **no real model has ever been run**; do not mention results until `artifacts/runs/model-*.json` exists |

## 4. Minute by minute

Timings follow the draft in `artifacts/demo/demo_script.md`. Speaker lines in quotes. Disclosure lines are mandatory when the tag is TODAY.

### 0:00 to 0:20. The problem

| | |
|---|---|
| Screen | Console header, or one slide |
| Say | "An autonomous agent reads vendor invoices and pays them. One buried sentence in an invoice can change the payment tool call. We built the layer that catches that call, tests defences against it, and asks a human before changing policy." |
| Status | TODAY (message only) |
| Disclosure | none needed |

### 0:20 to 0:55. The hostile invoice

| | |
|---|---|
| Screen | Console, scenario `invoice_redirect`, the invoice text with the injected "system note" highlighted |
| TODAY | Scripted invoice text from `phantomshift/scenarios.py`. Say: "This invoice is a fixture. The agent action you are about to see is scripted, not produced by a live agent." |
| GB10-LIVE | The real OpenClaw agent receives the invoice (via the real channel or its inbox) and its local model proposes the tool call. Say "live" only if the H01, H03, H04 checks are green and the proposal came from the model; show the model name from the saved status output. |
| Number allowed | `$24,800` only as "synthetic exposure". Never "saved", never "prevented". |

### 0:55 to 1:20. The call is held

| | |
|---|---|
| Screen | Control plane and trace: `action_held`, violated authority value (`pay_invoice.account='000123459921' is not an authorised value`), "Backend reached: no" |
| TODAY | The scripted `pay_invoice` is held by `guardian.Gateway` in live mode before `MockBusiness` is called. Say: "The backend here is an in-memory mock; a payment is a list entry. Held means the mock was never called." |
| GB10-LIVE | The same gateway guarding a registered OpenClaw tool. Registration of the tool is **UNKNOWN** (`docs/GB10_RUNBOOK.md`, "still unknown"). Do not claim it until done. |
| Must say | "The authority record that decides what is allowed lives outside the agent's context." |

### 1:20 to 2:00. Three futures

| | |
|---|---|
| Screen | Three forks plus baseline, each with attacks executed and legit completed; selected fork highlighted; replay mode label |
| Say | "Each candidate defence is replayed against the captured proposal and against a legitimate task. Lockdown stops the attack but breaks legitimate work. An allow-list misses attacks sent to trusted domains. Context-bound passes both." |
| Required disclosure | "This is a policy-only replay of the captured proposal. It is not the agent re-running in three parallel worlds." (`replay_mode: policy_only_replay`) |
| Status | TODAY. GB10-LIVE would only add that the proposal came from a real local model. |
| Numbers allowed (fixtures, simulated) | 3 scenarios, 6 attacks, 6 legit: baseline blocks 0/6; lockdown blocks 6/6 and allows 2/6 legit; allow-list blocks 2/6; context-bound blocks 6/6 and allows 6/6 (recomputed in-process 09:58Z; `python3 -m phantomshift eval` prints the same table) |

### 2:00 to 2:30. Human approval

| | |
|---|---|
| Screen | The approval request: candidate policy name, config diff, digest, expiry; then the operator's decision and the re-verification result |
| TODAY, console or `run` | `SimulatedChannel`. Say: "This approval channel is simulated. No message went to a real app." |
| TODAY, Discord REST | A real Discord message is posted and the operator reacts. Say: "This is a real Discord message but sent by a development script, not through the OpenClaw channel the hackathon requires." Note: both Discord runs on file ended `no operator response before timeout`; do not show a Discord approval you have not completed in rehearsal. |
| GB10-LIVE | Approval through the OpenClaw-managed channel. Whether OpenClaw can drive reaction approval is **UNKNOWN** (the pinned docs do not mention reactions); the text-message path `approve <nonce> <digest>` exists in `phantomshift/discord_auth.py` but is not wired in. Say "through OpenClaw" only if the H05 check is green. |
| Must say | "The agent can request a policy change but cannot approve it. Approval is single use, expires, and is bound to the exact config digest." |
| After approval | Re-verification runs the activated policy in live mode on the same fixtures. Say "verified on fixtures", not "verified in production". |

### 2:30 to 3:00. Numbers, hard cases, honesty

| | |
|---|---|
| Screen | Measurement strip and hard cases |
| Say | "On held-out parametric variants, context-bound lets 0 of 60 attacks through and completes 60 of 60 legitimate actions. Those variants share structure with our fixtures, so near-perfect is expected and proves little. The informative result is the six hard cases." |
| Hard cases (observed, N tiny) | Context-bound alone lets 3 of 5 attacks through (provenance laundered as registry, correct account with 10x amount, PII to a trusted recipient) and false-denies the 1 legitimate email whose recipient provenance was untagged. Baseline and allow-list also let 3 of 5 through; lockdown blocks all 5 but completes 0 of 1 legit. |
| Say | "That is why policy alone is not enough: it needs the authority record or a registry-backed adapter underneath, and provenance from the agent runtime rather than from tags." |
| Latency | "p95 about 0.01 to 0.02 milliseconds, in-process Python on a development server. Not the GB10 and not end to end." On the GB10, re-run `python3 -m phantomshift eval` and quote that output instead; if not re-run, say the dev-server line. |
| Close, TODAY | "Everything you saw is fixture-level. The GB10 runtime pieces are what we are completing now." |
| Close, GB10-LIVE | List only the checks in section 2 that are green. |
| Never say | "tamper-proof", "signed", "saved $24,800", "customers would pay", "runs fully on NemoClaw" unless H04 and the integration are proven, "zero attacks succeed" without the circularity note |

Circularity disclosure if asked about the "0": "The authority record both blocks and defines harm, so a column that uses it scores 0 by construction. Our headline uses the policy-only column. An independent oracle such as a bank-side ledger is the fix and is not built."

## 5. Spoken disclosure lines (copy exactly)

| When | Line |
|---|---|
| Opening, if any part is fixture | "Parts of this demo are labelled fixture. I will say which." |
| Invoice and agent action | "The invoice and the agent's proposed action are scripted fixtures." |
| Held action | "The backend is an in-memory mock; no money, no mail, no network." |
| Forks | "These futures are policy-only replays of one captured proposal, not live parallel agents." |
| Approval, simulated | "This approval channel is simulated." |
| Approval, Discord REST | "Real Discord message from a development script, not the OpenClaw-managed channel." |
| Hashes | "The hashes are local checksums, not signatures." |
| Model | "No model run is shown here" (until a `model-*.json` artifact exists) |
| Machine | "This ran on a development server, not the Dell GB10" (whenever H02 is not PASS) |
| Synthetic money | "The $24,800 is synthetic exposure, not savings." |

## 6. Fallback: never pass a recording off as live

Order of preference when something live fails. In every case say the first line below out loud before showing anything.

| Failure | What to show | What to say first |
|---|---|---|
| GB10 runtime down (no OpenClaw agent, no local model) | The fixture console on whatever machine works, banner visible | "The live agent path is not running right now. This is the fixture build." |
| Channel down | The nonce flow in `SimulatedChannel` | "The channel is down. This is the simulated approval flow; no channel event is claimed." |
| Console down | A saved run record, `artifacts/runs/<id>.json`, opened on screen, with its `evidence: fixture` and `replay_mode` fields and file timestamp visible | "This is a saved record from <time> on <host>, not a live run." |
| Model fails | Skip the model segment; do not show stub-server output as a model result | "The model run is not shown." |
| Network or Discord API down | Console only | State it, do not mime a message arriving |

Recording rules, if a video is ever used:

1. Announce it before it plays: "This is a recording made at <time> on <host>."
2. Burn the label "RECORDING, not live" and the capture time into a corner of the video. Do not rely on narration alone.
3. Never narrate a recording in the present tense ("watch it block this now"). Use past tense.
4. Never switch from recording to live without saying so.
5. A recording of the Discord rehearsal channel is a recording of the rehearsal channel, not of OpenClaw. Label it that way.
6. If a judge asks "is this live?", the answer is the status of the section 2 checks, nothing else.

## 7. Rehearsal checklist

| Item | Done when |
|---|---|
| Fixture path timed | full script under 3:00 with the TODAY lines |
| GB10 path timed | only after each live check is green; otherwise skip |
| One completed Discord approval, if the Discord REST segment will be shown | a run record with `approval.state: activated` and `real_message: true`; none exists today (two timeouts) |
| Hard-case slide matches `artifacts/benchmarks/results.json` | numbers copied from the file, not from memory |
| Disclosure lines memorised | section 5 |
| Backup record opened in a tab | one `artifacts/runs/*.json` |
