# 3-minute PAYGUARD demo script

Prerequisites: `python3 -m phantomshift serve` on GB10 or dev; open `http://127.0.0.1:8765/payguard/`.

| Time | Action | What judges should see |
|------|--------|------------------------|
| 0:00 | Header badge | **SYNTHETIC DEMO** (unless live gates PASS) |
| 0:20 | Select *Invoice payment redirect* | Exposure $24,800 labeled **synthetic** |
| 0:40 | Inspector source excerpt | Hidden invoice instruction vs trusted task |
| 1:00 | **Trace attack** + click policy gate | Red denial; no completed payment node animation |
| 1:25 | **Fork 3 policies** | Baseline / lockdown / context-bound denominators |
| 2:00 | **Request approval (status only)** | Discord gate NOT_TESTED or honest channel state |
| 2:25 | Footer receipts | `policy_only_replay`, evidence fixture |
| 2:50 | **Reset demo** | Clears UI selection only |

Optional: **Demo sequence** button steps through the same states automatically.

Classic console at `/` remains for receipt JSON download and eval tables.
