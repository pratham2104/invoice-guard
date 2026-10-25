"""Transport-agnostic PHANTOMSHIFT commands: scan, simulate, report.

Each handler takes parsed args and returns (embed, plain_text). They run on fixtures only and
never execute anything outside the in-memory mock backend. The same handlers are meant to be
exposed as OpenClaw tools on the GB10; the Discord polling listener is rehearsal glue.
"""

from __future__ import annotations

from . import discord_views, evalset
from .guardian import Authority, Gateway
from .incident import REPLAY_MODE, fork
from .mockapi import MockBusiness
from .policies import BASELINE, CANDIDATES
from .scenarios import SCENARIOS

DEFAULT = "invoice_redirect"


def _scenario(args: list[str]) -> str | None:
    sid = args[0] if args else DEFAULT
    return sid if sid in SCENARIOS else None


def scan(args: list[str]):
    sid = _scenario(args)
    if not sid:
        return None, f"unknown scenario; choose from {', '.join(SCENARIOS)}"
    scn, auth = SCENARIOS[sid], Authority.for_scenario(sid)
    rows = []
    for kind, acts in (("attack", scn["attacks"]), ("legit", scn["legit"])):
        for a in acts:
            res = Gateway(auth, BASELINE, MockBusiness(), mode="live").submit(a)
            rows.append({"kind": kind, "note": a["note"], "held": res["held"], "violations": res["violations"]})
    return discord_views.scan_embed(scn, rows), f"scan {sid}"


def simulate(args: list[str]):
    sid = _scenario(args)
    if not sid:
        return None, f"unknown scenario; choose from {', '.join(SCENARIOS)}"
    scn, auth = SCENARIOS[sid], Authority.for_scenario(sid)
    forks = [fork(auth, p, scn) for p in [BASELINE, *CANDIDATES]]
    sel = next((f["name"] for f in forks if f["name"] != "baseline" and f["verified"]), None)
    return discord_views.forks_embed({"title": scn["title"], "forks": forks, "replay_mode": REPLAY_MODE,
                                      "selected": sel}), f"simulate {sid}"


def report(args: list[str]):
    return discord_views.report_embed(evalset.evaluate("heldout")), "report"


def help_(args: list[str]):
    return discord_views.help_embed(), "help"


HANDLERS = {"scan": scan, "simulate": simulate, "report": report, "help": help_}


def dispatch(text: str):
    """text is the message with the bot mention removed, e.g. 'scan ticket_exfil'."""
    words = text.replace("/phantom", " ").split()
    if not words:
        return help_([])
    fn = HANDLERS.get(words[0].lower())
    if not fn:
        return None, f"unknown command '{words[0]}'. Try: {', '.join(HANDLERS)}"
    return fn(words[1:])
