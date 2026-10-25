"""Embed builders. Every embed states what it is: fixture, replay mode, channel type."""

from __future__ import annotations

RED, BLUE, AMBER, GREEN, GREY = 0xE5484D, 0x3B82F6, 0xF5A524, 0x30A46C, 0x6B7280
FOOT = "SYNTHETIC FIXTURE · policy-only replay · dev rehearsal channel (not OpenClaw-managed)"
AUTOPATCH_FOOT = (
    "AUTOPATCH · fixture reproduction · RWCR triage score (heuristic, not calibrated loss) · "
    "dev REST channel (not OpenClaw interactive approval)"
)


def _e(title, desc, color, fields=None):
    return {"title": title[:250], "description": desc[:3500], "color": color,
            "fields": [{"name": n[:250], "value": (v or "-")[:1000], "inline": i} for n, v, i in (fields or [])],
            "footer": {"text": FOOT}}


def attack_embed(scn: dict, scenario_id: str, held: dict) -> dict:
    act = scn["attacks"][0]
    args = ", ".join(f"{k}={v}" for k, v in act["args"].items())
    usd = f"${scn['exposure_usd']:,} (synthetic)" if scn["exposure_usd"] else "n/a (data exposure)"
    return _e(f"HELD before execution: {scn['title']}", scn["task"], RED, [
        ("Untrusted source", scn["untrusted_source"], True),
        ("Proposed action", f"`{act['tool']}({args})`"[:1000], False),
        ("Broken trust boundary", scn["boundary"], False),
        ("Authority violations", "\n".join(f"• {v}" for v in held["violations"]) or "-", False),
        ("Exposure", usd, True), ("Backend reached", "no (held by gateway)", True)])


def forks_embed(rec: dict) -> dict:
    lines = []
    for f in rec["forks"]:
        mark = "VERIFIED" if f["verified"] else "rejected"
        lines.append(f"**{f['name']}** · attacks executed {f['harmful_executed']}/{f['attacks_total']} · "
                     f"legit completed {f['legit_completed']}/{f['legit_total']} · {mark}")
    return _e(f"Parallel worlds: {rec['title']}", "\n".join(lines), BLUE, [
        ("Selected", rec["selected"] or "none verified", True), ("Replay mode", rec["replay_mode"], True)])


def audit_embed(rec: dict) -> dict:
    v = rec.get("verification")
    ap = rec["approval"]
    trace_tail = rec["trace"][-1]["hash"][:16] if rec.get("trace") else "-"
    return _e(f"Audit: {rec['title']}", f"Run `{rec['run_id']}`", GREEN if v and v["verified"] else GREY, [
        ("Approval", f"{ap['state']} via {ap.get('channel', 'n/a')}", False),
        ("Post-activation verification", (f"attacks executed {v['harmful_executed']}/{v['attacks_total']}, "
                                          f"legit {v['legit_completed']}/{v['legit_total']}") if v else "not run", False),
        ("Trace chain", f"intact={rec['trace_chain_ok']} head `{trace_tail}` (local checksum chain, not a signature)", False),
        ("Evidence", f"{rec['evidence']} / {rec['replay_mode']}", True),
        ("OpenClaw-managed channel", "no", True)])


def status_embed(gates: list[dict], tests: str) -> dict:
    icon = {"PASS": "PASS", "FAIL": "FAIL", "NOT TESTED": "n/t"}
    rows = "\n".join(f"`{g['id']:<5}` {icon.get(g['status'], g['status']):<5} {g['gate']}" for g in gates)
    return _e("PHANTOMSHIFT status", f"{tests}\n\nHackathon gates on this dev host:\n{rows}", GREY, [
        ("Reality check", "Runs on the dev server, not the Dell GB10. No NemoClaw/OpenClaw/OpenShell yet. "
                          "Numbers are fixture results, see docs/CLAIMS_AUDIT.md.", False)])


def scan_embed(scn: dict, rows: list[dict]) -> dict:
    lines = []
    for r in rows:
        tag = "HELD" if r["held"] else "ok"
        extra = f" · {r['violations'][0]}" if r["violations"] else ""
        lines.append(f"`{tag:<4}` **{r['kind']}** {r['note']}{extra}")
    held_atk = sum(r["held"] for r in rows if r["kind"] == "attack")
    n_atk = sum(r["kind"] == "attack" for r in rows)
    leg_ok = sum(not r["held"] for r in rows if r["kind"] == "legit")
    n_leg = sum(r["kind"] == "legit" for r in rows)
    return _e(f"Scan: {scn['title']}", "\n".join(lines), RED if held_atk else GREEN, [
        ("Attacks held", f"{held_atk}/{n_atk}", True), ("Legit passed authority check", f"{leg_ok}/{n_leg}", True),
        ("Note", "Judged against the authority record only; the policy forks are in `simulate`.", False)])


def autopatch_finding_embed(payload: dict) -> dict:
    fid = payload.get("finding_id", "unknown")
    digest = (payload.get("digest") or "-")[:16]
    sev = payload.get("severity", "medium")
    desc = (
        "Proof-carrying approval request (fixture). "
        "Binds exact policy digest; operator allow-list required server-side. "
        "0/N guarded attack success is not zero residual risk (Wilson upper bound applies)."
    )
    return {
        "title": f"AUTOPATCH finding · {fid}"[:250],
        "description": desc[:3500],
        "color": AMBER,
        "fields": [
            {"name": "Severity", "value": str(sev)[:250], "inline": True},
            {"name": "Candidate digest", "value": f"`{digest}…`", "inline": True},
            {"name": "Exposure", "value": "simulated transaction exposure (not money saved)", "inline": False},
            {"name": "Evidence", "value": "Local UI /api/autopatch/events · not raw invoice data", "inline": False},
        ],
        "footer": {"text": AUTOPATCH_FOOT},
    }


def report_embed(ev: dict) -> dict:
    def line(kind, name):
        a = ev["results"][kind][name]["policy_only"]
        return (f"**{name}** attacks succeed {a['attacks_succeeded']}/{a['attacks']} · "
                f"legit complete {a['legit_completed']}/{a['legit']} · p95 {a['p95_ms']} ms")
    names = ["baseline", "lockdown", "allowlist", "context_bound"]
    return _e(f"Report: held-out set (seed {ev['seed']})", "policy_only column; fixtures, not a real agent", BLUE, [
        ("Parametric variants (same structure as fixtures)", "\n".join(line("parametric", n) for n in names), False),
        ("Hard cases (N=6, the informative ones)", "\n".join(line("hard", n) for n in names), False),
        ("Caveats", "context_bound alone misses provenance-laundered, PII-to-trusted-recipient and over-limit cases and "
                    "false-denies one legit action. No model run yet. See docs/CLAIMS_AUDIT.md.", False)])


def help_embed() -> dict:
    return _e("PHANTOMSHIFT commands", "Mention me with a command (operator only):", GREY, [
        ("scan [scenario]", "Hold-check the scripted attacks and legit actions against the authority record", False),
        ("simulate [scenario]", "Replay the attack under every candidate policy (policy-only replay)", False),
        ("report", "Held-out numbers, hard cases and caveats", False),
        ("Scenarios", "invoice_redirect, ticket_exfil, log_secret_post (default invoice_redirect)", False)])
