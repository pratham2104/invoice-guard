# Demo script (3 minutes). Say the bracketed disclosure lines aloud.

0. [Open: "This repository started as pre-event scaffolding built the day before; today's work is the GB10 integration."]
1. 0:00-0:25 The risk: an agent reads a vendor invoice; one hidden sentence tells it to change the payout account. Synthetic invoice, $24,800 synthetic exposure.
2. 0:25-0:55 Show the invoice and the injected sentence. On the GB10 this is the real OpenClaw agent's tool call and `nemoclaw inference get` proving a local route. [If not yet live: "this part is a scripted fixture, no live agent yet."]
3. 0:55-1:20 The proposed payment is HELD by the deterministic gate before any effect: show the rule and the trust boundary (account came from untrusted text, not the registry).
4. 1:20-2:00 Counterfactual Lab: four worlds, each tested on the attack AND a legitimate task. Baseline pays the attacker, lockdown breaks legitimate work, allow-list misses, context-bound passes both. Say: "these are policy-only replays of the captured proposal."
5. 2:00-2:30 Discord: incident posted, operator reacts to approve, post-approval verification reruns. [If the channel is not OpenClaw-managed, say so.]
6. 2:30-3:00 Numbers with denominators: frozen 39-case suite, heldout policy-only context_bound 1/8 substantive attacks succeed (failure E033 shown), live stack 0/9 (circular, say so), baselines table, local model result with its caveat. Business: illustrative $9,350/month productivity scenario, labelled illustrative; no savings claimed.

Fallback if Discord/Wi-Fi fails: say it failed, show the stored event record and receipt; never present a recording as live.
Full detail: `docs/DEMO_3_MINUTES.md`.
