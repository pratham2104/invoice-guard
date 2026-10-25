# PHANTOMSHIFT in one page

**What it is:** a local security harness for autonomous business agents. It holds a hijacked agent action before any effect, replays candidate policies in disposable worlds, picks the least disruptive one that also keeps legitimate work running, and needs a human to approve the change.

| Piece | File(s) | State |
|---|---|---|
| Authority record + live/sandbox gateway | `phantomshift/guardian.py` | tested |
| Strict payment adapter (idempotent, registry-bound) | `phantomshift/adapter.py`, `adapter_server.py` | tested with stubs |
| Policies as data + validation | `phantomshift/policies.py` | tested |
| Incident flow, forks, approval, event store | `incident.py`, `approval.py`, `eventstore.py` | fixtures only |
| Autonomous inbox trigger | `trigger.py`, `python3 -m phantomshift watch` | fixture pipeline, not OpenClaw |
| Multi-model decision router | `decision_router.py` | fake clients only |
| Reusable skills | `skills/*` | format hand-checked, not installed anywhere |
| Frozen eval + baselines | `evalsuite.py`, `scripts/evaluate.py` | simulated |
| Local-model replay | `modelreplay.py`, `llm.py` | one 4B model, CPU, weak evidence |
| UI | `phantomshift/static/*`, `python3 -m phantomshift` | never viewed in a real browser |
| GB10 kit | `../offline-stage`, `scripts/*gb10*`, `openclaw-integration/` | staged, never run on a GB10 |

Run: `python3 -m unittest discover -s tests` (506) · `python3 -m phantomshift` (UI) · `python3 -m phantomshift watch --once` · `python3 scripts/verify_hackathon.py --mode prep` · `scripts/gb10_preflight.sh --require-gb10` (on the GB10).
Read first: `PROGRESS.md`, `docs/GAP_REPORT.md`, `docs/CLAIMS_AUDIT.md`, `docs/GB10_RUNBOOK.md`.
