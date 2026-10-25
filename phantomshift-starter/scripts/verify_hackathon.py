#!/usr/bin/env python3
"""Probe this machine against the Dell x NVIDIA hackathon technical gates (H01-H07).

PASS only on positive evidence from a probe. Anything not probed is NOT TESTED, never PASS.
--mode prep:        GB10-only gates report NOT TESTED (this is a preparation host); exit 0.
--mode competition: exit 1 unless every mandatory gate (H01-H06) is PASS.
Also writes artifacts/preflight/host.json (read-only probes, no secrets).

Evidence files (artifacts/runtime-verification/) must be fresh and bound to this machine; a bare file that
anyone could type is never enough for PASS:
  demo.json     (H06) {is_live: true, host: <this hostname>, timestamp: <within 24h>, run_id: <in event store>}
  channel.json  (H05) {is_live, openclaw_managed, type, round_trip, host: <this hostname>, timestamp: <within 24h>,
                       nonce: <appears in the event store or in `nemoclaw <sandbox> channels list` output>}
                A channel.json whose nonce cannot be corroborated is self-reported and stays NOT TESTED.
verify.json stays a plain list of gate rows (the UI and `discord-setup` read it that way); each row carries
generated_at and host, and verify.meta.json holds {generated_at, host, gates_sha256, gate_count} where
gates_sha256 is the sha256 of the canonical JSON of the verify.json gate list.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# PHANTOMSHIFT_ARTIFACTS lets tests write elsewhere so they never overwrite real evidence.
ART_ROOT = Path(os.environ.get("PHANTOMSHIFT_ARTIFACTS", ROOT / "artifacts"))
ART = ART_ROOT / "runtime-verification"
PRE = ART_ROOT / "preflight"
EVENTS_DB = Path(os.environ.get("PHANTOMSHIFT_EVENTS", ART_ROOT / "events.sqlite"))
REMOTE_KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY", "REMOTE_LLM_API_KEY"]


MAX_EVIDENCE_AGE_S = 24 * 3600
CLOCK_SKEW_S = 300


def hostname():
    return socket.gethostname()


def _ts_age(value):
    """Seconds since an ISO-8601 string or epoch number; None if unparseable (bool is not a timestamp)."""
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            t = float(value)
        elif isinstance(value, str):
            d = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            t = d.timestamp()
        else:
            return None
    except (ValueError, OverflowError, OSError):
        return None
    return time.time() - t


def evidence_problem(d):
    """Why an evidence dict is not acceptable (host/timestamp binding), or None if it is."""
    if not isinstance(d, dict):
        return "not a JSON object"
    host = d.get("host")
    if not isinstance(host, str) or host != hostname():
        return f"host {host!r} is not this machine ({hostname()!r})"
    age = _ts_age(d.get("timestamp"))
    if age is None:
        return "timestamp missing or unparseable"
    if age < -CLOCK_SKEW_S:
        return "timestamp is in the future"
    if age > MAX_EVIDENCE_AGE_S:
        return f"timestamp is {age / 3600:.0f}h old (limit 24h)"
    return None


def load_evidence(path):
    try:
        return json.loads(path.read_text()), None
    except FileNotFoundError:
        return None, "no file"
    except Exception as exc:  # noqa: BLE001
        return None, f"unreadable: {type(exc).__name__}"


def store_events():
    """(events, why_not). Only a store that passes its own hash-chain verify is believed."""
    if not EVENTS_DB.exists():
        return None, "no event store"
    try:
        from phantomshift.eventstore import EventStore
        st = EventStore(EVENTS_DB)
        try:
            v = st.verify()
            if not v["ok"]:
                return None, f"event store failed verify: {v['errors'][:1]}"
            return st.events(), None
        finally:
            st.close()
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return 127, str(exc)


def machine():
    rc, gpu = run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])
    mem_kb = 0
    try:
        mem_kb = int(next(l for l in open("/proc/meminfo") if l.startswith("MemTotal")).split()[1])
    except Exception:  # noqa: BLE001
        pass
    du = shutil.disk_usage(ROOT)
    return {"collected": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "arch": platform.machine(), "os": platform.platform(),
            "gpu": gpu.splitlines() if rc == 0 else [], "ram_gib": round(mem_kb / 1024 / 1024, 1),
            "disk_free_gib": round(du.free / 2**30, 1), "python": platform.python_version()}


def tool_versions():
    out = {}
    for t, args in (("docker", ["--version"]), ("nemoclaw", ["--version"]), ("openshell", ["--version"]),
                    ("openclaw", ["--version"]), ("ollama", ["--version"]), ("vllm", ["--version"]),
                    ("node", ["--version"]), ("git", ["--version"])):
        p = shutil.which(t) or (str(Path.home() / ".local/bin" / t) if (Path.home() / ".local/bin" / t).exists() else None)
        if not p:
            out[t] = None
            continue
        rc, txt = run([p, *args])
        out[t] = {"path": p, "version": txt.splitlines()[0] if rc == 0 and txt else f"exit {rc}"}
    return out


def local_model():
    for port in (8000, 11434):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as r:
                return {"endpoint": f"127.0.0.1:{port}", "models": [m["id"] for m in json.load(r).get("data", [])]}
        except Exception:  # noqa: BLE001
            continue
    return None


def nemoclaw_json(args):
    """Run a read-only nemoclaw command and parse its JSON (skipping node warning lines)."""
    exe = shutil.which("nemoclaw") or str(Path.home() / ".local/bin/nemoclaw")
    rc, txt = run([exe, *args], timeout=60)
    if rc != 0:
        return None, txt
    for opener in ("{", "["):
        i = txt.find(opener)
        if i >= 0:
            try:
                return json.loads(txt[i:]), txt
            except Exception:  # noqa: BLE001
                continue
    return None, txt


def live_sandboxes():
    data, _ = nemoclaw_json(["list", "--json"])
    items = data.get("sandboxes", data) if isinstance(data, dict) else data
    return [x for x in (items or []) if isinstance(x, dict)]


def openclaw_agent_incident():
    """True only if the event store holds an incident started by a real OpenClaw agent.
    Our fixture pipeline records 'not an OpenClaw agent' and can never satisfy this."""
    if not EVENTS_DB.exists():
        return False, "no event store"
    try:
        from phantomshift.eventstore import EventStore
        st = EventStore(EVENTS_DB)
        v = st.verify()
        if not v["ok"]:
            return False, f"event store failed verify: {v['errors'][:1]}"
        for e in st.events():
            agent = str((e.get("payload") or {}).get("agent", ""))
            if e["state"] == "AGENT_STARTED" and "openclaw" in agent.lower() and "not an openclaw" not in agent.lower():
                return True, f"incident {e['incident_id']} started by '{agent}'"
        return False, "no AGENT_STARTED event from a real OpenClaw agent (fixture runs do not count)"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def demo_evidence():
    """H06 evidence: artifacts/runtime-verification/demo.json bound to this host, fresh, and to a real run."""
    d, why = load_evidence(ART / "demo.json")
    if d is None:
        return False, why
    if not isinstance(d, dict) or d.get("is_live") is not True:
        return False, "is_live is not true"
    bad = evidence_problem(d)
    if bad:
        return False, bad
    run_id = d.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return False, "run_id missing"
    events, why = store_events()
    if events is None:
        return False, why
    if not any(e.get("incident_id") == run_id for e in events):
        return False, f"run_id {run_id!r} is not in the event store"
    return True, f"live demo run {run_id} recorded on {hostname()}"


def channel_gate(tools):
    """H05: PASS only for a fresh, host-bound channel.json whose nonce is corroborated independently of the file."""
    d, why = load_evidence(ART / "channel.json")
    if d is None:
        return "NOT TESTED", "no OpenClaw channel proof file" if why == "no file" else f"channel.json {why}"
    if not (isinstance(d, dict) and d.get("is_live") is True and d.get("openclaw_managed") is True
            and d.get("type") in ("telegram", "slack", "discord") and bool(d.get("round_trip"))):
        return "NOT TESTED", "channel.json lacks is_live/openclaw_managed/type/round_trip"
    bad = evidence_problem(d)
    if bad:
        return "NOT TESTED", f"channel.json {bad}"
    nonce = d.get("nonce")
    if not isinstance(nonce, str) or len(nonce) < 8:
        return "NOT TESTED", "channel.json has no nonce (>= 8 chars): self-reported, not corroborated"
    events, _ = store_events()
    if events is not None and any(nonce in json.dumps(e, default=str) for e in events):
        return "PASS", f"channel.json fresh on this host; nonce found in the event store ({d['type']})"
    if tools.get("nemoclaw"):
        for box in live_sandboxes():
            name = box.get("name") if isinstance(box, dict) else None
            if isinstance(name, str) and name:
                exe = shutil.which("nemoclaw") or str(Path.home() / ".local/bin/nemoclaw")
                rc, txt = run([exe, name, "channels", "list"], timeout=60)
                if rc == 0 and nonce in txt:
                    return "PASS", f"channel.json fresh on this host; nonce found in `nemoclaw {name} channels list`"
    return "NOT TESTED", "channel.json is self-reported: its nonce is in neither the event store nor `nemoclaw <sandbox> channels list`"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("prep", "competition"), default="prep")
    ap.add_argument("--competition", action="store_true", help="alias for --mode competition")
    args = ap.parse_args()
    mode = "competition" if args.competition else args.mode
    m, tools = machine(), tool_versions()
    ART.mkdir(parents=True, exist_ok=True)
    PRE.mkdir(parents=True, exist_ok=True)
    (ART / "machine.json").write_text(json.dumps(m, indent=2))
    (PRE / "host.json").write_text(json.dumps({**m, "tools": tools, "mode": mode,
                                               "note": "read-only probes; this is the preparation host unless gpu says GB10"}, indent=2))
    on_gb10 = any("GB10" in g.split(",")[0].upper() for g in m["gpu"]) and m["arch"] in ("aarch64", "arm64")
    model = local_model()
    remote = [k for k in REMOTE_KEYS if os.environ.get(k)]
    gates_ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    gb10_only_status = "NOT TESTED" if mode == "prep" else "FAIL"

    rows = []
    def add(i, name, status, detail, mandatory=True):
        rows.append((i, name, status, detail, mandatory))

    add("H02", "Runs on Dell Pro Max GB10", "PASS" if on_gb10 else gb10_only_status,
        f"arch={m['arch']} gpu={[g.split(',')[0] for g in m['gpu']] or 'none'}")
    if remote:
        add("H03", "Local inference, no remote LLM", "FAIL", f"remote provider keys set: {remote}")
    elif not model:
        add("H03", "Local inference, no remote LLM", "NOT TESTED", "no model server on 127.0.0.1:8000/11434")
    elif not on_gb10:
        add("H03", "Local inference, no remote LLM", gb10_only_status, f"model {model['models']} is local but not on the GB10")
    else:
        data, txt = nemoclaw_json(["inference", "get", "--json"]) if tools["nemoclaw"] else (None, "")
        route = (txt or "").lower()
        hosted = [w for w in ("build.nvidia", "openrouter", "openai.com", "anthropic", "generativelanguage") if w in route]
        local = any(w in route for w in ("vllm", "llama", "inference.local", "host.openshell.internal", "127.0.0.1", "localhost"))
        if hosted:
            add("H03", "Local inference, no remote LLM", "FAIL", f"nemoclaw route mentions hosted provider: {hosted}")
        elif tools["nemoclaw"] and local:
            add("H03", "Local inference, no remote LLM", "PASS", f"{model['models']} served locally; nemoclaw route is local")
        else:
            add("H03", "Local inference, no remote LLM", "NOT TESTED",
                f"{model['models']} served locally but nemoclaw route not confirmed (agent may not use it)")
    # openclaw lives inside the sandbox image; on the host only nemoclaw and openshell are required to be present
    missing = [t for t in ("nemoclaw", "openshell") if not tools[t]]
    if missing:
        add("H04", "NemoClaw + OpenClaw + OpenShell present", "FAIL" if mode == "competition" else "NOT TESTED",
            f"not found: {missing}")
    else:
        boxes = live_sandboxes()
        add("H04", "NemoClaw + OpenClaw + OpenShell present", "PASS" if boxes else "NOT TESTED",
            f"{len(boxes)} registered sandbox(es) via `nemoclaw list --json`" if boxes
            else "binaries found but no registered sandbox; a real tool call still needs proof")
    ch_status, ch_detail = channel_gate(tools)
    add("H05", "Discord/Slack/Telegram via OpenClaw", ch_status, ch_detail)
    ok01, why01 = openclaw_agent_incident()
    add("H01", "Autonomous always-on trigger", "PASS" if ok01 else "NOT TESTED", why01)
    demo_ok, demo_why = demo_evidence()
    if not demo_ok:
        add("H06", "Final demo on the GB10", "NOT TESTED", f"demo.json: {demo_why}")
    elif not on_gb10:
        add("H06", "Final demo on the GB10", gb10_only_status, f"demo evidence is valid but this host is not a GB10 ({demo_why})")
    else:
        add("H06", "Final demo on the GB10", "PASS", demo_why)
    add("H07", "Evidence + claims audit present", "PASS" if (ROOT / "docs/CLAIMS_AUDIT.md").exists() else "NOT TESTED",
        "docs/CLAIMS_AUDIT.md", mandatory=False)
    rows.sort(key=lambda r: r[0])

    print(f"mode={mode}\n{'ID':<6}{'Gate':<42}{'Status':<12}Detail")
    for i, n, s, d, _ in rows:
        print(f"{i:<6}{n:<42}{s:<12}{d}")
    host = hostname()
    gates = [{"id": i, "gate": n, "status": s, "detail": d, "generated_at": gates_ts, "host": host}
             for i, n, s, d, _ in rows]
    (ART / "verify.json").write_text(json.dumps(gates, indent=2))
    canon = json.dumps(gates, sort_keys=True, separators=(",", ":"))
    (ART / "verify.meta.json").write_text(json.dumps(
        {"generated_at": gates_ts, "host": host, "gate_count": len(gates),
         "gates_sha256": hashlib.sha256(canon.encode()).hexdigest(),
         "note": "sha256 of json.dumps(verify.json, sort_keys=True, separators=(',',':'))"}, indent=2))
    bad = [i for i, _, s, _, mand in rows if mand and s != "PASS"]
    if mode == "competition" and bad:
        print(f"\nCOMPETITION MODE: not ready. Gates not PASS: {bad}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
