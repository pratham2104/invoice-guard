# Gap report (read-only audit, 2026-10-25 00:31Z = Sat 17:31 PDT; event starts Sun 10:00 PDT)

Everything below was measured in this session on the PREPARATION server (x86_64, 2x RTX 3090, shared). Machine-readable twin: `artifacts/readiness.json`.
Operator-reported figures in the V2 brief (323 tests, 48 GB / 199 files, 529 GB free, watcher green, no owned processes, six Discord channels) were re-checked: all matched except free disk, now 520 GB.

| Area | Status | Evidence (this session) | Gap / next |
|---|---|---|---|
| Tests | GREEN | 323 OK, 39.9 s | fixtures and stubs only |
| Offline stage | GREEN | `sha256sum -c manifest.sha256` exit 0, 199 files, 48 GB | re-verify after copy to SSD and on the GB10 |
| Discord token | **RED** | read-only API call: token still valid | operator must rotate (it was pasted into chat twice); I will not rotate or print it |
| Discord bot/server | GREEN (rehearsal only) | in server, operator is a member, 6 text channels | intents OFF; REST channel is NOT OpenClaw-managed (gate H05 still NOT_TESTED) |
| NemoClaw/OpenShell | YELLOW | v0.0.137 / 0.0.116 installed; onboarding preflight passed | onboarding FAILED at gateway bind on this rootless-Docker host; no sandbox ever created |
| Local model | YELLOW | Nano-4B Q4 GGUF ran on CPU earlier (6.4-6.8 tok/s, native tool calls) | Lightning NVFP4 and Nano FP8 are staged, never run; need the GB10 |
| Agent-facing adapter | YELLOW | `adapter-serve` + 8 tests with stub clients | never called from a real sandbox; plugin/preset are unverified skeletons |
| Git work branch | BLOCKED | not a git repository | `git init` if wanted |
| Gates H01-H06 | NOT_TESTED | see readiness.json | only observable on the GB10 |

## Risks to the event plan, in order
1. GB10 Docker may be rootless like this host: NemoClaw onboarding would fail the same way. `scripts/gb10_preflight.sh` (in progress) checks for it.
2. NemoClaw lists offline installs as unsupported: network is needed on site for the installer/OpenShell/OpenClaw packages.
3. Lightning on a Dell GB10 is unvalidated (NVIDIA's profile is DGX Spark, experimental, one concurrent sequence). Keep the Nano-4B fallback and the llama.cpp Nano-30B profile in mind; do not override a failed host check.
4. Prebuilt-code rules are unknown: ask the organizers, disclose the scaffold.
5. Token not rotated.

## Not claimable today
No live OpenClaw agent, no OpenClaw-managed Discord, no GB10 inference, no NemoClaw sandbox, no measured business savings.
