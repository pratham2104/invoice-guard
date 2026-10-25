# 3-minute demo (DRAFT: fixture parts are labelled; replace with live parts on the GB10)

- 0:00 Problem: a buried sentence in a vendor invoice can change an agent's payment tool call.
- 0:20 Show invoice, highlight the injected sentence. *Today: fixture text. On GB10: real OpenClaw agent output.*
- 0:55 The proposed pay_invoice is HELD by the gateway before the mock backend sees it. Show the trace row and the violated authority value.
- 1:20 Three forks, each tested on the attack and a legit task. Say "policy-only replay of the captured proposal". Lockdown fails legit work; allow-list misses; context-bound passes.
- 2:00 Approval request to the operator. *Today: simulated channel, say so. On GB10: real Telegram/Slack/Discord via OpenClaw.* Approve, re-verify.
- 2:30 Numbers with denominators: held-out 60+60, 6 hard cases, p95 latency on the GB10. Show the hard cases where context-bound alone fails. Exposure is "synthetic $24,800", never "saved".

Backup if the channel is down: say it is down, show the nonce flow in the simulated channel, do not claim a channel event.
