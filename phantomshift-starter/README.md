# PHANTOMSHIFT

Local security harness for autonomous business agents. It **holds a hijacked agent action before any effect**, replays candidate policies in disposable worlds, picks the least disruptive one that also keeps legitimate work running, and needs a human to approve the change.

**Status in one line:** fixture-level and heavily tested on a preparation server (x86_64, RTX 3090). No live OpenClaw agent, no NemoClaw sandbox, no GB10 inference, no OpenClaw-managed Discord has ever run. Read `docs/GAP_REPORT.md` and `docs/CLAIMS_AUDIT.md` before quoting any number.

Python 3.10+, standard library only (the model server for rehearsals is a separate llama.cpp build).

## Run
```
python3 -m unittest discover -s tests            # 506 tests
python3 -m phantomshift                          # UI at http://127.0.0.1:8765 (loopback only)
python3 -m phantomshift run --scenario invoice_redirect
python3 -m phantomshift watch --once             # autonomous inbox poller over fixtures/inbox
python3 -m phantomshift eval                     # fixture tables + benchmark artifacts
python3 -m phantomshift.evalsuite                # frozen 39-case suite with Wilson intervals
python3 scripts/evaluate.py                      # baselines (a)-(c); (d)-(f) need local model endpoints
python3 -m phantomshift model-replay --scenario invoice_redirect --model <id> --temperature 0.7 --seed 1
python3 -m phantomshift adapter-serve            # submit-only listener for the future OpenClaw tool
python3 scripts/verify_hackathon.py --mode prep  # honest gate table (competition mode exits 1 off the GB10)
scripts/gb10_preflight.sh --require-gb10         # run ON the event machine first
```
Discord (rehearsal channel, not OpenClaw-managed): put `DISCORD_BOT_TOKEN`, `DISCORD_SERVER_ID`, `DISCORD_USER_ID` in `.env` (gitignored, mode 600), then `python3 scripts/discord_check.py`, `python3 -m phantomshift discord-setup`, `run --discord`.

## Where to read
| Need | File |
|---|---|
| Current state, newest first-ish | `PROGRESS.md`, `docs/GAP_REPORT.md`, `artifacts/readiness.json` |
| What is real vs fixture | `docs/OVERVIEW.md`, `docs/CLAIMS_AUDIT.md` |
| Event-day steps | `docs/GB10_RUNBOOK.md`, `openclaw-integration/ONSITE_CHECKLIST.md`, `docs/DEMO_SCRIPT.md` |
| Design and threats | `docs/ARCHITECTURE.md`, `docs/THREAT_MODEL.md`, `DECISIONS.md` |
| Models and routing | `docs/MODEL_MATRIX.md`, `phantomshift/decision_router.py` |
| Evaluation method | `docs/EVALSUITE.md`, `docs/BUSINESS_MODEL.md` (illustrative arithmetic only) |

All scenarios, accounts and amounts are synthetic. Hashes here are local checksums, not signatures.
