"""CLI: serve the UI, print an eval table, or probe a local model."""

from __future__ import annotations

import argparse
import json
import os
import sys

import time
from pathlib import Path

from . import engine, evalset, incident
from .policies import CANDIDATES, evaluate
from .scenarios import SCENARIOS


def cmd_eval(_: argparse.Namespace) -> int:
    s = engine.summary()
    print(f"{'policy':<14}{'attacks blocked':>18}{'legit allowed':>16}")
    for name in ["baseline", *[p["name"] for p in CANDIDATES]]:
        r = s[name]
        print(f"{name:<14}{r['attacks_blocked']:>10}/{r['attacks_total']:<7}{r['legit_allowed']:>9}/{r['legit_total']:<6}")
    print("\n" + s["disclaimer"])
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "environment": "fixture, policy-only replay, no model",
           "heldout": evalset.evaluate("heldout"), "dev": evalset.evaluate("dev")}
    path = Path("artifacts/benchmarks/results.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    h = out["heldout"]["results"]
    print(f"\nheld-out (seed {out['heldout']['seed']}), policy_only, attacks succeeded / legit completed")
    for kind in ("parametric", "hard"):
        for name, t in h[kind].items():
            a = t["policy_only"]
            print(f"  {kind:<11}{name:<14}{a['attacks_succeeded']:>3}/{a['attacks']:<4}{a['legit_completed']:>4}/{a['legit']:<4} p95 {a['p95_ms']} ms")
    print(f"wrote {path}")
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    channel = None
    if getattr(a, "slack", False) or (os.environ.get("SLACK_BOT_TOKEN") and not a.discord):
        from .slack_channel import SlackChannel
        channel = SlackChannel.from_env()
    elif a.discord:
        from .discord_channel import DiscordChannel
        channel = DiscordChannel.from_env()
    rec = incident.run_incident(a.scenario, channel=channel, wait_s=a.wait)
    path = Path("artifacts/runs") / f"{rec['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2))
    print(f"run {rec['run_id']} selected={rec['selected']} approval={rec['approval']['state']} "
          f"verified={rec['verification'] and rec['verification']['verified']} chain_ok={rec['trace_chain_ok']}")
    print(f"evidence={rec['evidence']} replay={rec['replay_mode']} real_channel={rec['approval'].get('real_channel')}")
    print(f"wrote {path}")
    return 0


def cmd_model(a: argparse.Namespace) -> int:
    from . import modelreplay
    rec = modelreplay.run(a.scenario, a.base_url, a.model, a.trials, temperature=a.temperature, seed=a.seed)
    path = Path("artifacts/runs") / f"model-{a.scenario}-{int(time.time())}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2))
    u = rec["unguarded_hijack_rate"]
    print(f"model={rec['model']} trials={rec['trials']} parse_failures={rec['parse_failures']} "
          f"unguarded hijack {u['hijacked']}/{u['attacked_trials']}")
    for n, r in rec["policies"].items():
        print(f"  {n:<14}attacks succeeded {r['attacks_succeeded']}/{r['attacked_trials']}  legit completed {r['legit_completed']}/{r['control_trials']}")
    print(f"mode={rec['replay_mode']} wrote {path}")
    return 0


def cmd_slack_setup(_: argparse.Namespace) -> int:
    import subprocess
    from .slack_channel import SlackChannel
    from . import slack_views
    ch = SlackChannel.from_env()
    root = Path(__file__).resolve().parent.parent
    subprocess.run([sys.executable, str(root / "scripts/verify_hackathon.py")], capture_output=True, cwd=root)
    gates = json.loads((root / "artifacts/runtime-verification/verify.json").read_text())
    t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], capture_output=True, text=True, cwd=root)
    tests = next((l for l in t.stderr.splitlines() if l.startswith(("OK", "FAILED"))), "tests: unknown")
    ran = next((l for l in t.stderr.splitlines() if l.startswith("Ran ")), "")
    blocks = slack_views.slack_status_blocks(gates, f"{ran} · {tests}")
    ts = ch.post("phantomshift-control", blocks=blocks)
    print(f"posted status to Slack (#phantomshift-control / operator DM, ts={ts})")
    return 0


def cmd_slack_listen(a: argparse.Namespace) -> int:
    from . import commands
    from .slack_channel import SlackChannel
    ch = SlackChannel.from_env()
    print(f"listening in Slack #{a.channel} for {a.seconds:.0f}s; send commands: scan | simulate | report | help")
    n = ch.listen(a.channel, commands.dispatch, a.seconds)
    print(f"replied to {n} command(s)")
    return 0


def cmd_discord_setup(_: argparse.Namespace) -> int:
    import subprocess
    from .discord_channel import CHANNELS, DiscordChannel, _load_env
    from . import discord_views
    ch = DiscordChannel.from_env()
    ids = ch.ensure_channels(_load_env()["DISCORD_SERVER_ID"])
    print("channels:", ", ".join(f"#{n}" for n in ids))
    root = Path(__file__).resolve().parent.parent
    subprocess.run([sys.executable, str(root / "scripts/verify_hackathon.py")], capture_output=True, cwd=root)
    gates = json.loads((root / "artifacts/runtime-verification/verify.json").read_text())
    t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], capture_output=True, text=True, cwd=root)
    tests = next((l for l in t.stderr.splitlines() if l.startswith(("OK", "FAILED"))), "tests: unknown")
    ran = next((l for l in t.stderr.splitlines() if l.startswith("Ran ")), "")
    ch.post("phantomshift-control", embed=discord_views.status_embed(gates, f"{ran} · {tests}"))
    print("posted status to #phantomshift-control")
    return 0


def cmd_discord_listen(a: argparse.Namespace) -> int:
    from . import commands
    from .discord_channel import DiscordChannel
    ch = DiscordChannel.from_env()
    print(f"listening in #{a.channel} for {a.seconds:.0f}s; mention the bot with: scan | simulate | report | help")
    n = ch.listen(a.channel, commands.dispatch, a.seconds)
    print(f"replied to {n} command(s)")
    return 0


def cmd_watch(a: argparse.Namespace) -> int:
    import threading
    from .eventstore import EventStore
    from .inference_gate import check_inference_config
    from .trigger import InboxTrigger
    cfg = {"provider": "vllm", "base_url": os.environ.get("LOCAL_MODEL_URL", "http://127.0.0.1:8000/v1")}
    gate = check_inference_config(cfg, a.mode, dict(os.environ))
    for w in gate.get("warnings", []):
        print("inference warning:", w)
    if not gate["ok"]:
        for v in gate["violations"]:
            print(f"inference violation [{v['code']}] {v['path']}: {v['detail']}")
        if a.mode == "competition":
            print("competition mode: refusing to start with a non-local or unsafe inference config")
            return 1
    channel = None
    if getattr(a, "slack", False) or (os.environ.get("SLACK_BOT_TOKEN") and not getattr(a, "discord", False)):
        try:
            from .slack_channel import SlackChannel
            channel = SlackChannel.from_env()
        except Exception:
            pass
    elif getattr(a, "discord", False):
        from .discord_channel import DiscordChannel
        channel = DiscordChannel.from_env()
    store = EventStore(a.db)
    meta = {"policy_version": "baseline", "model_id": os.environ.get("LOCAL_MODEL_NAME") or "none (no model in loop)",
            "inference_server": "127.0.0.1"}
    def handler(job):
        scn = job.data.get("scenario")
        if scn not in SCENARIOS:
            raise ValueError(f"unknown scenario {scn!r}")
        rec = incident.run_incident(scn, channel=channel, wait_s=a.wait, store=job.store,
                                    incident_id=job.incident_id, run_id=job.run_id, meta={k: v for k, v in meta.items() if v})
        path = Path("artifacts/runs") / f"{rec['run_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, indent=2))
        print(f"processed {job.path.name}: {scn} -> {rec['selected']} / {rec['event_store']['final_state']} ({path})")
    trig = InboxTrigger(a.inbox, store, notify=lambda e: print("OPERATOR ALERT:", e.get("payload", {}).get("alert", e["state"])), meta=meta)
    stop = threading.Event()
    if a.seconds:
        threading.Timer(a.seconds, stop.set).start()
    print(f"watching {a.inbox} every {a.interval}s ({'forever' if not a.seconds else f'{a.seconds:.0f}s'}); db={a.db}")
    try:
        if a.once:
            print(trig.run_once(handler))
        else:
            trig.run_forever(handler, a.interval, stop)
    except KeyboardInterrupt:
        pass
    v = store.verify()
    print(f"event store verify ok={v['ok']} events={v['events']} head={v['head'][:16]}")
    return 0 if v["ok"] else 1


def cmd_autopatch(a: argparse.Namespace) -> int:
    from pathlib import Path
    from .autopatch.events import AutopatchStore
    from .autopatch.research import run_research_cycle
    from .autopatch.deploy import PolicyDeployService
    from .policies import CANDIDATES
    from .approval import config_digest

    store = AutopatchStore(a.db)
    if a.research_once:
        out = run_research_cycle(store, scenario_id=a.scenario)
        print(json.dumps(out, indent=2))
        return 0
    if a.status:
        print(json.dumps({"events": store.list_events(20)}, indent=2))
        return 0
    if a.deploy_context_bound:
        cfg = next(p for p in CANDIDATES if p["name"] == "context_bound")
        svc = PolicyDeployService()
        out = svc.deploy(cfg, expected_version="baseline", candidate_hash=config_digest(cfg), finding_id="manual")
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1
    if a.drain_outbox:
        from .autopatch.discord_publish import drain_outbox
        ch = None
        if os.environ.get("SLACK_BOT_TOKEN") or getattr(a, "slack", False):
            try:
                from .slack_channel import SlackChannel
                ch = SlackChannel.from_env()
            except Exception:
                pass
        if ch is None:
            try:
                from .discord_channel import DiscordChannel
                ch = DiscordChannel.from_env()
            except Exception as e:
                print(f"error: failed to initialize Slack or Discord channel: {e}", file=sys.stderr)
                return 1
        out = drain_outbox(store, ch.post)
        print(json.dumps(out, indent=2))
        return 0 if out.get("failed", 0) == 0 else 1
    print("use --research-once, --status, --deploy-context-bound, or --drain-outbox")
    return 1


def cmd_acceptance(a: argparse.Namespace) -> int:
    from . import enforcement_pipeline
    out = enforcement_pipeline.run_full_fixture_pipeline(a.scenario)
    print(json.dumps(out, indent=2))
    ok = out["firewall"]["passed"]
    print("ACCEPTANCE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_adapter_serve(a: argparse.Namespace) -> int:
    from . import adapter_server
    hosts = tuple(adapter_server.DEFAULT_HOSTS) + tuple(a.allow_host or ())
    adapter_server.serve(a.bind, a.adapter_port, hosts)
    return 0


def cmd_probe(a: argparse.Namespace) -> int:
    from . import llm
    act = llm.propose(a.scenario, a.base_url, a.model)
    print(json.dumps({k: act[k] for k in ("tool", "args", "prov")}, indent=2))
    for p in CANDIDATES:
        d = evaluate(p, act)
        print(f"{p['name']:<14}{'ALLOW' if d['allow'] else 'DENY ':<7}{d['reason']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="phantomshift")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("eval", help="print aggregate fixture results")
    rn = sub.add_parser("run", help="run one fixture incident end to end and write artifacts/runs/<id>.json")
    rn.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    rn.add_argument("--slack", action="store_true", help="post to Slack (.env) and wait for the operator reaction")
    rn.add_argument("--discord", action="store_true", help="post to Discord (.env) and wait for the operator reaction")
    rn.add_argument("--wait", type=float, default=90.0, help="seconds to wait for the operator reaction")
    sub.add_parser("slack-setup", help="verify/post status to Slack (#phantomshift-control / operator DM)")
    sl = sub.add_parser("slack-listen", help="poll Slack channel for operator commands for N seconds")
    sl.add_argument("--channel", default="phantomshift-control")
    sl.add_argument("--seconds", type=float, default=120.0)
    dl = sub.add_parser("discord-listen", help="rehearsal: poll a Discord channel for operator commands for N seconds")
    dl.add_argument("--channel", default="phantomshift-control")
    dl.add_argument("--seconds", type=float, default=120.0)
    sub.add_parser("discord-setup", help="create PHANTOMSHIFT channels in the Discord server and post status")
    atp = sub.add_parser("autopatch", help="AUTOPATCH research loop and policy deploy (fixture)")
    atp.add_argument("--db", default="artifacts/autopatch.sqlite")
    atp.add_argument("--scenario", choices=sorted(SCENARIOS), default="invoice_redirect")
    atp.add_argument("--research-once", action="store_true")
    atp.add_argument("--status", action="store_true")
    atp.add_argument("--deploy-context-bound", action="store_true")
    atp.add_argument("--drain-outbox", action="store_true", help="post pending AUTOPATCH outbox to Slack or Discord (.env)")
    atp.add_argument("--slack", action="store_true", help="drain outbox to Slack")
    ac = sub.add_parser("acceptance", help="firewall acceptance test + fixture incident pipeline")
    ac.add_argument("--scenario", choices=sorted(SCENARIOS), default="invoice_redirect")
    ad = sub.add_parser("adapter-serve", help="agent-facing firewall + submit listener (simulated ledger)")
    ad.add_argument("--bind", default="127.0.0.1", help="Docker bridge or private IP for a sandbox; never 0.0.0.0")
    ad.add_argument("--adapter-port", type=int, default=7890)
    ad.add_argument("--allow-host", action="append", help="extra Host header value to accept (repeatable)")
    wt = sub.add_parser("watch", help="autonomous trigger: poll an inbox dir, run the pipeline, record events")
    wt.add_argument("--inbox", default="fixtures/inbox")
    wt.add_argument("--interval", type=float, default=2.0)
    wt.add_argument("--seconds", type=float, default=0.0, help="stop after N seconds (0 = until Ctrl-C)")
    wt.add_argument("--once", action="store_true")
    wt.add_argument("--db", default="artifacts/events.sqlite")
    wt.add_argument("--mode", choices=("prep", "competition"), default="prep")
    wt.add_argument("--slack", action="store_true", help="post alerts to Slack")
    wt.add_argument("--discord", action="store_true")
    wt.add_argument("--wait", type=float, default=60.0)
    mr = sub.add_parser("model-replay", help="sample a local model on attacked + control inputs, judge with every policy")
    mr.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    mr.add_argument("--base-url", default=os.environ.get("LOCAL_MODEL_URL", "http://127.0.0.1:8000/v1"))
    mr.add_argument("--model", default=os.environ.get("LOCAL_MODEL_NAME"), required=not os.environ.get("LOCAL_MODEL_NAME"))
    mr.add_argument("--trials", type=int, default=10)
    mr.add_argument("--temperature", type=float, default=0.0, help="0 = near-identical trials; try 0.7 for variance")
    mr.add_argument("--seed", type=int, default=None)
    pr = sub.add_parser("probe", help="ask a localhost OpenAI-compatible model for one tool call")
    pr.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    pr.add_argument("--base-url", default=os.environ.get("LOCAL_MODEL_URL", "http://127.0.0.1:8000/v1"))
    pr.add_argument("--model", default=os.environ.get("LOCAL_MODEL_NAME"), required=not os.environ.get("LOCAL_MODEL_NAME"))
    a = ap.parse_args(argv)
    if a.cmd == "eval":
        return cmd_eval(a)
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "slack-listen":
        return cmd_slack_listen(a)
    if a.cmd == "slack-setup":
        return cmd_slack_setup(a)
    if a.cmd == "discord-listen":
        return cmd_discord_listen(a)
    if a.cmd == "discord-setup":
        return cmd_discord_setup(a)
    if a.cmd == "autopatch":
        return cmd_autopatch(a)
    if a.cmd == "acceptance":
        return cmd_acceptance(a)
    if a.cmd == "adapter-serve":
        return cmd_adapter_serve(a)
    if a.cmd == "watch":
        return cmd_watch(a)
    if a.cmd == "model-replay":
        return cmd_model(a)
    if a.cmd == "probe":
        return cmd_probe(a)
    from .server import serve
    serve(a.host, a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
