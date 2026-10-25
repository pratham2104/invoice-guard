#!/usr/bin/env python3
"""Deterministically replay a LOCKED fixture set against several policies expressed as data.

Standalone, stdlib only, no network, no clock, no randomness, no file writes (unless --out is given).

For every (policy, fixture) pair the action is evaluated in FRESH state: a deep copy of the action and a
new empty effect ledger. The outcome is read from the ledger (did the effect happen), not from a flag the
policy returns. The output is a matrix per policy:

    harmful_blocked   malicious fixtures that produced no effect      (numerator / denominator)
    legit_preserved   benign fixtures that produced the effect        (numerator / denominator)
    false_denials     benign fixtures that were denied                (numerator / denominator)

A policy that false-denies ANY legitimate fixture is never labelled a successful remediation, and neither
is a policy that lets any harmful fixture through. The label is computed here; nothing in a fixture or
policy file can set it. Passing fixtures says nothing about real-world prevention: fixtures are written by
people, usually alongside the policy.

Usage:
    python3 policy_replay.py --fixtures fixtures.json --policies policies.json [--out result.json]
                             [--require-success NAME] [--require-lock] [--print-fixtures-digest]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "counterfactual-policy-replay/1"
TRUSTED_DEFAULT = ("user", "registry")
POLICY_TYPES = ("allow_all", "deny_all_sensitive", "allowlist", "context_bound")
LABEL_OK = "SUCCESSFUL_REMEDIATION_ON_FIXTURES"
LABEL_FALSE_DENIALS = "REJECTED_FALSE_DENIALS"
LABEL_MISSES = "INSUFFICIENT_MISSES_HARMFUL_ACTIONS"
LABEL_INCONCLUSIVE = "INCONCLUSIVE_NEED_BOTH_KINDS"
CAVEAT = ("Results hold for these fixtures only. Fixtures are hand-written, often alongside the policy, so a clean "
          "result is a method demonstration, not evidence of real-world prevention.")


class ReplayInputError(ValueError):
    """Raised for malformed, unlocked-when-required or tampered inputs."""


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


# --- validation ---------------------------------------------------------------------------------------
_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _as_str_list(val: Any) -> bool:
    return isinstance(val, list) and all(isinstance(x, str) for x in val)


def _egress_ok(val: Any) -> bool:
    return isinstance(val, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in val.items())


def validate_fixtures(doc: Any, require_lock: bool = False) -> list[dict]:
    if not isinstance(doc, dict) or not isinstance(doc.get("fixtures"), list) or not doc["fixtures"]:
        raise ReplayInputError("fixtures document must be an object with a non-empty 'fixtures' list")
    extra = set(doc) - {"fixture_set_id", "locked_sha256", "fixtures", "description"}
    if extra:
        raise ReplayInputError(f"unknown fixture document keys {sorted(extra)}")
    seen: set[str] = set()
    for fx in doc["fixtures"]:
        if not isinstance(fx, dict) or set(fx) - {"id", "kind", "expected", "action", "note"} \
                or not {"id", "kind", "expected", "action"} <= set(fx):
            raise ReplayInputError("each fixture needs id, kind, expected, action (and optional note)")
        if not (isinstance(fx["id"], str) and _NAME.match(fx["id"])) or fx["id"] in seen:
            raise ReplayInputError(f"fixture id {fx.get('id')!r} is invalid or duplicated")
        seen.add(fx["id"])
        if fx["kind"] not in ("benign", "malicious"):
            raise ReplayInputError(f"fixture {fx['id']}: kind must be benign or malicious")
        want = "allow" if fx["kind"] == "benign" else "deny"
        if fx["expected"] != want:
            raise ReplayInputError(f"fixture {fx['id']}: a {fx['kind']} fixture must expect {want!r}")
        act = fx["action"]
        if not isinstance(act, dict) or not isinstance(act.get("tool"), str) or not isinstance(act.get("args"), dict) \
                or not isinstance(act.get("prov", {}), dict) or not _as_str_list(act.get("labels", [])):
            raise ReplayInputError(f"fixture {fx['id']}: action needs string tool, object args, optional prov, labels")
    digest = sha256_of(doc["fixtures"])
    lock = doc.get("locked_sha256")
    if lock is None and require_lock:
        raise ReplayInputError("fixtures are not locked (no locked_sha256) and a lock is required")
    if lock is not None and lock != digest:
        raise ReplayInputError(f"fixture set changed since it was locked: expected {lock}, computed {digest}")
    return doc["fixtures"]


def validate_policies(doc: Any) -> list[dict]:
    if not isinstance(doc, dict) or not isinstance(doc.get("policies"), list):
        raise ReplayInputError("policies document must be an object with a 'policies' list")
    if len(doc["policies"]) < 3:
        raise ReplayInputError("at least 3 policies are required for a counterfactual comparison")
    names: set[str] = set()
    for p in doc["policies"]:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str) or not _NAME.match(p["name"]) or p["name"] in names:
            raise ReplayInputError(f"policy name {p.get('name') if isinstance(p, dict) else p!r} is invalid or duplicated")
        names.add(p["name"])
        ptype = p.get("type")
        allowed = {"name", "type", "label"}
        if ptype == "allow_all":
            pass
        elif ptype == "deny_all_sensitive":
            allowed |= {"sensitive_tools"}
            if not _as_str_list(p.get("sensitive_tools")):
                raise ReplayInputError(f"policy {p['name']}: sensitive_tools must be a list of strings")
        elif ptype == "allowlist":
            allowed |= {"egress_params", "allowed_domains"}
            if not _egress_ok(p.get("egress_params")) or not _as_str_list(p.get("allowed_domains")):
                raise ReplayInputError(f"policy {p['name']}: needs egress_params {{tool: arg}} and allowed_domains list")
        elif ptype == "context_bound":
            allowed |= {"bind_params", "trusted_sources", "egress_params", "egress_label_rules"}
            bp, ts = p.get("bind_params"), p.get("trusted_sources", list(TRUSTED_DEFAULT))
            er = p.get("egress_label_rules", {})
            if not (isinstance(bp, dict) and all(isinstance(k, str) and _as_str_list(v) and v for k, v in bp.items())):
                raise ReplayInputError(f"policy {p['name']}: bind_params must map tool to a non-empty list of args")
            if not _as_str_list(ts) or not ts:
                raise ReplayInputError(f"policy {p['name']}: trusted_sources must be a non-empty list of strings")
            if not (isinstance(er, dict) and all(v in ("deny", "trusted_destination") for v in er.values())):
                raise ReplayInputError(f"policy {p['name']}: egress_label_rules values must be deny or trusted_destination")
            if not _egress_ok(p.get("egress_params", {})):
                raise ReplayInputError(f"policy {p['name']}: egress_params must map tool to arg")
        else:
            raise ReplayInputError(f"policy {p['name']}: unknown type {ptype!r}; expected one of {POLICY_TYPES}")
        if set(p) - allowed:
            raise ReplayInputError(f"policy {p['name']}: unknown keys {sorted(set(p) - allowed)}")
    return doc["policies"]


# --- evaluation ---------------------------------------------------------------------------------------
_BAD_DEST = re.compile(r"[\s\\\x00-\x1f\x7f<>()\"'`,;]")


def dest_host(value: Any) -> str | None:
    """Host of a single email address or http(s) URL; None when ambiguous (treated as not allowed)."""
    if not isinstance(value, str) or not value or _BAD_DEST.search(value):
        return None
    if "://" in value:
        try:
            parts = urlsplit(value)
            parts.port  # noqa: B018
        except ValueError:
            return None
        if parts.scheme.lower() not in ("http", "https") or "@" in parts.netloc:
            return None
        return (parts.hostname or "").lower() or None
    if value.count("@") != 1:
        return None
    local, host = value.split("@")
    return host.lower() if local and host and not host.endswith(".") else None


def decide(policy: dict, action: dict) -> tuple[bool, str]:
    """Return (allow, rule). Pure function of policy data and the action."""
    tool, args = action["tool"], action["args"]
    prov, labels = action.get("prov", {}), action.get("labels", [])
    ptype = policy["type"]
    if ptype == "allow_all":
        return True, ""
    if ptype == "deny_all_sensitive":
        return (False, "tool_denied") if tool in policy["sensitive_tools"] else (True, "")
    if ptype == "allowlist":
        param = policy["egress_params"].get(tool)
        if param is not None:
            host = dest_host(args.get(param))
            if host is None or not any(host == d.lower() or host.endswith("." + d.lower()) for d in policy["allowed_domains"]):
                return False, "destination_not_allowed"
        return True, ""
    trusted = set(policy.get("trusted_sources", TRUSTED_DEFAULT))
    for param in policy["bind_params"].get(tool, []):
        if param in args and prov.get(param, "untrusted") not in trusted:
            return False, "untrusted_binding"
    egress = policy.get("egress_params", {}).get(tool)
    if egress is not None:
        dest_trusted = prov.get(egress, "untrusted") in trusted
        for label in labels:
            mode = policy.get("egress_label_rules", {}).get(label)
            if mode == "deny" or (mode == "trusted_destination" and not dest_trusted):
                return False, "label_egress_denied"
    return True, ""


def run_one(policy: dict, fixture: dict) -> dict:
    """Evaluate one fixture in fresh state. The outcome is whether the effect ledger is non-empty."""
    ledger: list[dict] = []  # fresh, per evaluation
    action = copy.deepcopy(fixture["action"])
    try:
        allow, rule = decide(policy, action)
    except Exception as exc:  # noqa: BLE001  fail closed: an evaluator error is a deny
        allow, rule = False, f"evaluator_error:{type(exc).__name__}"
    if allow:
        ledger.append({"tool": action["tool"]})
    return {"fixture": fixture["id"], "kind": fixture["kind"], "executed": bool(ledger), "rule": rule}


def classify(harmful_total: int, harmful_executed: int, legit_total: int, false_denials: int) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if harmful_total == 0 or legit_total == 0:
        return LABEL_INCONCLUSIVE, ["the fixture set needs at least one malicious and one benign fixture"]
    if false_denials:
        reasons.append(f"false-denied {false_denials}/{legit_total} legitimate fixtures")
    if harmful_executed:
        reasons.append(f"let {harmful_executed}/{harmful_total} harmful fixtures through")
    if false_denials:
        return LABEL_FALSE_DENIALS, reasons
    if harmful_executed:
        return LABEL_MISSES, reasons
    return LABEL_OK, ["blocked every harmful fixture and preserved every legitimate fixture in this set"]


def replay(fixtures_doc: Any, policies_doc: Any, require_lock: bool = False) -> dict:
    fixtures = validate_fixtures(fixtures_doc, require_lock)
    policies = validate_policies(policies_doc)
    harmful = [f for f in fixtures if f["kind"] == "malicious"]
    benign = [f for f in fixtures if f["kind"] == "benign"]
    matrix = []
    for pol in policies:
        rows = [run_one(pol, fx) for fx in fixtures]
        blocked = [r["fixture"] for r in rows if r["kind"] == "malicious" and not r["executed"]]
        missed = [r["fixture"] for r in rows if r["kind"] == "malicious" and r["executed"]]
        kept = [r["fixture"] for r in rows if r["kind"] == "benign" and r["executed"]]
        denied = [r["fixture"] for r in rows if r["kind"] == "benign" and not r["executed"]]
        label, reasons = classify(len(harmful), len(missed), len(benign), len(denied))
        matrix.append({
            "policy": pol["name"], "type": pol["type"], "policy_sha256": sha256_of(pol),
            "harmful_blocked": {"numerator": len(blocked), "denominator": len(harmful), "fixtures": blocked},
            "harmful_executed": {"numerator": len(missed), "denominator": len(harmful), "fixtures": missed},
            "legit_preserved": {"numerator": len(kept), "denominator": len(benign), "fixtures": kept},
            "false_denials": {"numerator": len(denied), "denominator": len(benign), "fixtures": denied},
            "remediation_label": label, "successful_remediation": label == LABEL_OK, "reasons": reasons,
            "per_fixture": rows,
        })
    result = {
        "schema_version": SCHEMA_VERSION,
        "fixture_set_id": fixtures_doc.get("fixture_set_id"),
        "fixtures_sha256": sha256_of(fixtures),
        "fixtures_locked": fixtures_doc.get("locked_sha256") is not None,
        "policies_sha256": sha256_of(policies),
        "fresh_state_per_evaluation": True,
        "fixture_counts": {"malicious": len(harmful), "benign": len(benign)},
        "matrix": matrix,
        "successful_policies": [m["policy"] for m in matrix if m["successful_remediation"]],
        "caveat": CAVEAT,
    }
    result["result_sha256"] = sha256_of({k: v for k, v in result.items() if k != "result_sha256"})
    return result


# --- CLI ------------------------------------------------------------------------------------------------
def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} is not valid JSON input")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate JSON key {k!r}")
        out[k] = v
    return out


def load_json(path: str) -> Any:
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_pairs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Replay a locked fixture set against policies expressed as data.")
    ap.add_argument("--fixtures", required=True, help="fixtures JSON file (or - for stdin)")
    ap.add_argument("--policies", required=True, help="policies JSON file")
    ap.add_argument("--out", help="also write the result JSON to this path")
    ap.add_argument("--require-lock", action="store_true", help="refuse fixtures without locked_sha256")
    ap.add_argument("--require-success", metavar="NAME", help="exit 1 unless this policy is a successful remediation")
    ap.add_argument("--print-fixtures-digest", action="store_true",
                    help="print the digest to put in locked_sha256 and exit")
    args = ap.parse_args(argv)
    try:
        fx_doc = load_json(args.fixtures)
        if args.print_fixtures_digest:
            validate_fixtures({**fx_doc, "locked_sha256": None} if isinstance(fx_doc, dict) else fx_doc)
            print(json.dumps({"fixtures_sha256": sha256_of(fx_doc["fixtures"])}))
            return 0
        result = replay(fx_doc, load_json(args.policies), args.require_lock)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}))
        return 2
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if args.require_success and args.require_success not in result["successful_policies"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
