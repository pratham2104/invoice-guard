"""CLI:  python -m apguard <command>"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import cases, config, db, pipeline, rules, seed
from .extractor import extract
from .parser import parse_eml

SEV_ICON = {"critical": "[CRIT]", "high": "[HIGH]", "medium": "[MED ]", "info": "[INFO]"}


def print_result(r):
    if r.skipped:
        print(f"  {r.filename}: already processed")
        return
    v = r.verdict
    tag = "HOLD" if v.verdict == "HOLD" else "PASS"
    print(f"\n{tag:4} score={v.score:3}  {r.filename}  vendor={v.vendor_name} ({v.vendor_match})"
          + (f"  -> {r.case_id}" if r.case_id else ""))
    for f in sorted(v.findings, key=lambda f: -f.points):
        print(f"      {SEV_ICON[f.severity]} {f.rule}: {f.message}")


def result_dict(r):
    if r.skipped:
        return {"filename": r.filename, "skipped": True, "case_id": r.case_id}
    v = r.verdict
    return {"filename": r.filename, "verdict": v.verdict, "score": v.score, "severity": v.severity,
            "vendor": v.vendor_name, "vendor_match": v.vendor_match, "case_id": r.case_id,
            "findings": [{"rule": f.rule, "severity": f.severity, "message": f.message}
                         for f in sorted(v.findings, key=lambda f: -f.points)]}


def emit(obj):
    print(json.dumps(obj, indent=2, default=str))


def llm_check(conn, inbox: Path) -> int:
    """Read-only: the LLM must never change a verdict, only fill extraction gaps."""
    print(f"model={config.LLM_MODEL} at {config.LLM_BASE_URL or '(APG_LLM_BASE_URL unset)'}")
    bad = 0
    for p in sorted(inbox.glob("*.eml")):
        email = parse_eml(p)
        base = rules.evaluate(conn, email, extract(email, use_llm=False))
        t0 = time.time()
        ex = extract(email, use_llm=True)
        secs = time.time() - t0
        llm = rules.evaluate(conn, email, ex)
        same = base.verdict == llm.verdict and {f.rule for f in base.findings} == {f.rule for f in llm.findings}
        bad += not same
        status = "OK  " if same else "DIFF"
        if ex.llm_error:
            status = "ERR "
            bad += same  # an unreachable model is a failed check, even though the verdict held
        print(f"{status} {p.name:34} {base.verdict}->{llm.verdict}  {secs:5.1f}s"
              + (f"  {ex.llm_error}" if ex.llm_error else ""))
        if not same:
            print(f"     added={sorted({f.rule for f in llm.findings} - {f.rule for f in base.findings})}"
                  f" removed={sorted({f.rule for f in base.findings} - {f.rule for f in llm.findings})}")
    print("all verdicts match" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="apguard")
    js = argparse.ArgumentParser(add_help=False)
    js.add_argument("--json", action="store_true", help="machine-readable output (for the OpenClaw agent)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="reset DB, seed vendors/history, regenerate demo emails")
    p = sub.add_parser("process", parents=[js], help="process an .eml file or a folder")
    p.add_argument("path", nargs="?", default=str(config.INBOX_DIR))
    p.add_argument("--llm", action="store_true", help="use the local LLM extractor (APG_LLM_BASE_URL)")
    w = sub.add_parser("watch", help="poll the inbox folder forever")
    w.add_argument("--interval", type=float, default=5)
    w.add_argument("--llm", action="store_true")
    sub.add_parser("cases", parents=[js], help="list cases")
    for name in ("show", "audit", "draft", "verify"):
        s = sub.add_parser(name, parents=[js] if name != "verify" else [])
        s.add_argument("case")
        if name == "verify":
            s.add_argument("--user", required=True)
    c = sub.add_parser("confirm", help="record the callback result")
    c.add_argument("case"); c.add_argument("--user", required=True)
    c.add_argument("--deny", action="store_true"); c.add_argument("--note", default="")
    a = sub.add_parser("approve"); a.add_argument("case"); a.add_argument("--user", required=True)
    r = sub.add_parser("reject"); r.add_argument("case"); r.add_argument("--user", required=True)
    r.add_argument("--reason", default="")
    sub.add_parser("verify-audit", help="check the audit hash chain")
    lc = sub.add_parser("llm-check", help="compare regex-only vs LLM verdicts on every inbox email")
    lc.add_argument("path", nargs="?", default=str(config.INBOX_DIR))
    sub.add_parser("slack", help="run the Slack app (needs SLACK_BOT_TOKEN / SLACK_APP_TOKEN)")

    args = ap.parse_args(argv)
    if config.AGENT_MODE and args.cmd not in config.AGENT_ALLOWED:
        print(f"BLOCKED: '{args.cmd}' is a human-only action (APG_AGENT_MODE is set).", file=sys.stderr)
        return 2
    conn = db.connect()
    try:
        if args.cmd == "seed":
            names = seed.seed(conn, config.INBOX_DIR)
            print(f"Seeded {len(names)} vendors; wrote demo emails to {config.INBOX_DIR}")
        elif args.cmd == "process":
            p = Path(args.path)
            results = pipeline.process_dir(conn, p, args.llm or None) if p.is_dir() \
                else [pipeline.process_eml(conn, p, args.llm or None)]
            if args.json:
                emit([result_dict(r) for r in results])
                return 0
            for r in results:
                print_result(r)
            held = sum(1 for r in results if r.case_id and not r.skipped)
            print(f"\n{len(results)} processed, {held} held")
        elif args.cmd == "watch":
            print(f"Watching {config.INBOX_DIR} every {args.interval}s (Ctrl-C to stop)")
            while True:
                for r in pipeline.process_dir(conn, config.INBOX_DIR, args.llm or None):
                    if not r.skipped:
                        print_result(r)
                time.sleep(args.interval)
        elif args.cmd == "cases":
            rows = conn.execute("SELECT c.*, v.name vendor FROM cases c LEFT JOIN vendors v ON v.id=c.vendor_id").fetchall()
            if args.json:
                emit([dict(r) for r in rows])
                return 0
            for r in conn.execute("SELECT c.*, v.name vendor FROM cases c LEFT JOIN vendors v ON v.id=c.vendor_id"):
                print(f"{r['id']}  {r['state']:18} {r['severity']:8} score={r['risk_score']:3}  {r['vendor']}")
        elif args.cmd == "show":
            c = cases.get_case(conn, args.case)
            m = conn.execute("SELECT * FROM messages WHERE id=?", (c["message_pk"],)).fetchone()
            if args.json:
                emit({**dict(c), "sender": m["sender"], "subject": m["subject"],
                      "findings": json.loads(m["findings_json"])})
                return 0
            print(f"{c['id']}  state={c['state']}  severity={c['severity']}  score={c['risk_score']}")
            print(f"From: {m['sender']}\nSubject: {m['subject']}\n")
            for f in json.loads(m["findings_json"]):
                print(f"  {SEV_ICON[f['severity']]} {f['rule']}: {f['message']}")
        elif args.cmd == "audit":
            if args.json:
                emit([dict(e) for e in conn.execute("SELECT * FROM case_events WHERE case_id=? ORDER BY id",
                                                    (args.case,))])
                return 0
            for e in conn.execute("SELECT * FROM case_events WHERE case_id=? ORDER BY id", (args.case,)):
                print(f"{e['ts']}  {e['actor']:8} {e['action']:22} {e['detail_json']}")
        elif args.cmd == "draft":
            d = cases.draft_callback(conn, args.case)
            if args.json:
                emit(d)
                return 0
            print(f"CALL: {d['contact']} at {d['phone']} (vendor master)\n\nCALL SCRIPT:")
            for s in d["call_script"]:
                print(f"  - {s}")
        elif args.cmd == "verify":
            ct = cases.start_verification(conn, args.case, args.user); conn.commit()
            print(f"Verification started. Call {ct['name']} at {ct['phone']} (vendor master).")
        elif args.cmd == "confirm":
            cases.record_confirmation(conn, args.case, args.user, not args.deny, args.note); conn.commit()
            print("Recorded.")
        elif args.cmd == "approve":
            cases.approve(conn, args.case, args.user); conn.commit(); print("Approved.")
        elif args.cmd == "reject":
            cases.reject(conn, args.case, args.user, args.reason); conn.commit(); print("Rejected.")
        elif args.cmd == "verify-audit":
            ok, bad = cases.verify_audit_chain(conn)
            print("Audit chain OK" if ok else f"AUDIT CHAIN BROKEN at event {bad}")
            return 0 if ok else 1
        elif args.cmd == "llm-check":
            return llm_check(conn, Path(args.path))
        elif args.cmd == "slack":
            from .slack_app import run
            run(conn)
    except cases.ControlError as e:
        conn.rollback()
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
