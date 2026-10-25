# Invoice Guard — rules for every agent

You are one of several Claude Code agents building this repo at the same time,
for 2–3 people, at the Dell x NVIDIA AI Hackathon (SF, 25 Oct 2026).
These rules exist so no two agents ever edit the same files.

## Read first, every session

1. `git pull`
2. `docs/PRODUCT.md` — what we're building and the 3 demo scenarios
3. `docs/ARCHITECTURE.md` — how the pieces fit
4. `board/TASKS.md` — what's open, what's claimed, who owns which folders
5. Every file in `board/` — what the other agents are doing right now

Then pick your agent name: `<person>-<n>` (e.g. `pratham-1`, `alex-2`).
Your status file is `board/<agent-name>.md`. Copy `board/_template.md` if it doesn't exist.

## Claiming work (git is the lock)

1. In `board/TASKS.md`, set one `open` task to `claimed` and put your agent name in "Owner".
2. Commit and push **immediately**, before writing any code:
   `git add board/TASKS.md && git commit -m "claim T05" && git push`
3. If the push is rejected, someone pushed first. `git pull --rebase`, re-read the row.
   If they took the same task, undo your claim and pick another.
4. One task at a time per agent.

## While working

- **Only edit the folders listed for your task in TASKS.md.** Plus your own status file.
- Need a change in someone else's folder? Write it under "Requests for others" in your
  status file and mention it in their area. Do not edit their files.
- New shared interface (a function, an API route, a DB table another task will use)?
  Write it in `docs/ARCHITECTURE.md` under "Interfaces" in the same push.
- Update your status file when you start, finish, or get blocked.
- Commit small and often. `git pull --rebase` before every push.
- Made a decision others should know (library choice, data format, cut a feature)?
  Add one line to `docs/DECISIONS.md`.

## Finishing

1. Make sure the auto-checks pass (green tick on GitHub; see "Checks" below).
2. Set the task to `done` in TASKS.md, clear its folders, update your status file, push.

## Hard rules

- **This repo is public.** Never commit passwords, tokens, Slack webhook URLs, or `.env`.
  Put secrets in `.env` (git-ignored) and document the variable name in `.env.example`.
  The secret scanner fails the push if it finds one; if that happens, rotate the secret.
- **All AI inference runs on the GB10.** No OpenAI/Anthropic/Gemini or any cloud LLM call
  anywhere in the product's runtime path. (Dev tools like Claude Code are fine.)
- **The model never approves a payment.** Qwen reads, compares and flags. Deterministic
  rules decide hold/pass. Only a human releases a held payment. There is no `release_payment` tool.
- **Bank changes are never confirmed by email.** Verification uses the phone number already
  on file in the AP system.
- **Slack messages carry a short summary only** — no invoice data, no bank numbers.
- Don't push broken main. If you break the checks, fixing them is your next task.

## Checks (`.github/workflows/checks.yml`)

On every push: secret scan; and once `package.json` exists, install + typecheck + tests.

## Deadlines (PT)

- **5:30 PM** code locks, GB10 returned, Round 1 due (video under 2 min + repo)
- 6:00 PM final submission · 7:00 PM pitch deck link due, top 8 live demos
