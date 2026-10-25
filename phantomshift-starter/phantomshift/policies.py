"""Declarative policy configs and the evaluator that judges one proposed action.

A policy is plain data, so a "repair" is a reviewable diff against BASELINE
rather than opaque code.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

TRUSTED_PROV = {"user", "registry"}
EGRESS_TOOLS = {"send_email", "http_post"}
DEST_PARAM = {"send_email": "to", "http_post": "url"}

BASELINE: dict[str, Any] = {
    "name": "baseline",
    "label": "Current policy (tool allow-list only)",
    "deny_tools": [],
    "domain_allowlist": None,
    "bind_params": {},
    "egress_label_rules": {},
}

CANDIDATES: list[dict[str, Any]] = [
    {
        "name": "lockdown",
        "label": "A. Lockdown: deny every money / mail / network tool",
        "deny_tools": ["pay_invoice", "send_email", "http_post"],
        "domain_allowlist": None,
        "bind_params": {},
        "egress_label_rules": {},
    },
    {
        "name": "allowlist",
        "label": "B. Destination allow-list: known domains only",
        "deny_tools": [],
        "domain_allowlist": ["acme.example", "customer.example", "partner.example"],
        "bind_params": {},
        "egress_label_rules": {},
    },
    {
        "name": "context_bound",
        "label": "C. Context-bound: sensitive args must trace to trusted sources",
        "deny_tools": [],
        "domain_allowlist": None,
        "bind_params": {
            "pay_invoice": ["account", "amount", "invoice_id", "currency"],
            "send_email": ["to"],
            "http_post": ["url"],
        },
        "egress_label_rules": {"secret": "deny", "pii": "trusted_destination"},
    },
]


def decision(allow: bool, rule: str = "", reason: str = "") -> dict:
    return {"allow": allow, "rule": rule, "reason": reason}


_BAD_DEST_CHARS = re.compile(r"[\s\\\x00-\x1f\x7f<>()\"'`]")


def _dest_host(act: dict) -> str | None:
    """Destination host of an egress action, or None when it cannot be determined unambiguously.

    None is treated as "not allowed" by the allow-list. Anything a mail client or an HTTP library might
    parse differently from us is rejected rather than interpreted: several recipients (, ; whitespace or
    more than one '@'), backslashes, control characters, userinfo, non-http(s) schemes, bad ports.
    """
    param = DEST_PARAM.get(act["tool"])
    if not param or param not in act["args"]:
        return None
    raw = act["args"][param]
    if not isinstance(raw, str):
        return None
    value = raw
    if not value or value != value.strip() or _BAD_DEST_CHARS.search(value):
        return None
    if act["tool"] == "send_email":
        if "," in value or ";" in value or value.count("@") != 1:
            return None
        local, host = value.split("@")
        if not local or not host or host.endswith("."):
            return None
        return host.lower()
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018  raises ValueError on a bad port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return None
    return (parts.hostname or "").lower() or None


def _host_allowed(host: str, allowed: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in allowed)


def evaluate(policy: dict[str, Any], act: dict) -> dict:
    tool = act["tool"]

    if tool in policy["deny_tools"]:
        return decision(False, "tool_denied", f"{tool} is denied outright")

    allowed = policy["domain_allowlist"]
    if allowed is not None and tool in EGRESS_TOOLS:
        host = _dest_host(act)
        if host is None or not _host_allowed(host, allowed):
            return decision(False, "destination_not_allowed", f"destination host {host!r} not in allow-list")

    for param in policy["bind_params"].get(tool, []):
        if param not in act["args"]:
            continue  # an argument the tool is not given cannot carry untrusted content
        prov = act["prov"].get(param, "untrusted")
        if prov not in TRUSTED_PROV:
            return decision(False, "untrusted_binding",
                            f"{tool}.{param} came from '{prov}' content, trusted sources are {sorted(TRUSTED_PROV)}")

    if tool in EGRESS_TOOLS:
        dest_prov = act["prov"].get(DEST_PARAM[tool], "untrusted")
        for label in act["labels"]:
            mode = policy["egress_label_rules"].get(label)
            if mode == "deny":
                return decision(False, "label_egress_denied", f"'{label}' data may not leave via {tool}")
            if mode == "trusted_destination" and dest_prov not in TRUSTED_PROV:
                return decision(False, "label_needs_trusted_destination",
                                f"'{label}' data requires a destination from a trusted source")

    return decision(True)


def diff_from_baseline(policy: dict[str, Any]) -> dict[str, Any]:
    """Minimal config diff a human can review and approve."""
    out = {}
    for key, base in BASELINE.items():
        if key in ("name", "label"):
            continue
        if policy[key] != base:
            out[key] = {"from": base, "to": policy[key]}
    return out


_CONFIG_KEYS = {"name", "label", "deny_tools", "domain_allowlist", "bind_params", "egress_label_rules"}
_TOOLS = {"pay_invoice", "lookup_vendor", "send_email", "http_post", "read_file"}
# Parameter names a bind_params entry may reference (every argument a built-in tool takes).
_BIND_PARAMS = {"account", "amount", "vendor_id", "invoice_id", "currency", "to", "url", "path"}
_RULE_MODES = {"deny", "trusted_destination"}
_RULE_STRENGTH = {"trusted_destination": 1, "deny": 2}  # deny > trusted_destination > no rule
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
# Public-suffix shapes ("co.uk", "com.au"): allow-listing one would trust every registrant under it.
_SLD_LABELS = {"co", "com", "org", "net", "gov", "edu", "ac", "mil", "or", "ne", "go", "gob"}


def _domain_problem(d: Any) -> str | None:
    if not isinstance(d, str):
        return f"domain entry {d!r} is not a string"
    if d != d.strip() or d != d.lower():
        return f"domain {d!r} must be lowercase with no surrounding whitespace"
    if d.endswith("."):
        return f"domain {d!r} has a trailing dot"
    if not _DOMAIN_RE.match(d):
        return f"domain {d!r} is not a registrable domain name (bare TLDs and malformed names are refused)"
    labels = d.split(".")
    if len(labels) == 2 and len(labels[1]) == 2 and labels[0] in _SLD_LABELS:
        return f"domain {d!r} looks like a public suffix; list a registrable domain under it"
    return None


def _weaker_than(base: dict, cfg: dict) -> list[str]:
    """Axes on which cfg grants MORE than base (deny_tools / allow-list / bindings / label rules)."""
    out: list[str] = []
    missing_deny = sorted(set(base["deny_tools"]) - set(cfg["deny_tools"]))
    if missing_deny:
        out.append(f"weaker than {base['name']!r}: tools no longer denied: {missing_deny}")
    b_da, c_da = base["domain_allowlist"], cfg["domain_allowlist"]
    if b_da is not None and (c_da is None or any(not _host_allowed(d, b_da) for d in c_da)):
        out.append(f"weaker than {base['name']!r}: domain allow-list is dropped or widened")
    for tool, params in base["bind_params"].items():
        lost = sorted(set(params) - set(cfg["bind_params"].get(tool, [])))
        if lost:
            out.append(f"weaker than {base['name']!r}: {tool} no longer binds {lost}")
    for label, mode in base["egress_label_rules"].items():
        if _RULE_STRENGTH.get(cfg["egress_label_rules"].get(label), 0) < _RULE_STRENGTH.get(mode, 0):
            out.append(f"weaker than {base['name']!r}: egress rule for {label!r} is dropped or relaxed")
    return out


def validate_config(cfg: Any, against: dict[str, Any] | None = None) -> list[str]:
    """Return problems with a proposed policy config; empty list means acceptable. Never raises.

    Repair proposals (possibly model-written) are data and must pass this before activation.
    Every element is type-checked before it is used as a set member or dict key.

    Rule: a candidate must not be WEAKER than the reference policy on any axis. The reference is BASELINE
    unless `against` (e.g. the currently active policy) is given; it must be a valid config itself. BASELINE
    denies/binds nothing, so against BASELINE the check is vacuous and what remains is the structural rule
    that no-op entries are refused: an empty bind_params list for a tool binds nothing yet looks like a
    binding in a diff, so it is rejected instead of being allowed to masquerade as hardening.
    """
    try:
        return _validate(cfg, BASELINE if against is None else against)
    except Exception as exc:  # noqa: BLE001  a validator that raises is a bypass; fail closed
        return [f"config could not be validated: {type(exc).__name__}"]


def _validate(cfg: Any, ref: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(cfg, dict):
        return ["config must be an object"]
    if not all(isinstance(k, str) for k in cfg):
        return ["config keys must be strings"]
    extra = set(cfg) - _CONFIG_KEYS
    missing = _CONFIG_KEYS - set(cfg)
    if extra:
        errs.append(f"unknown keys: {sorted(extra)}")
    if missing:
        errs.append(f"missing keys: {sorted(missing)}")
    if errs:
        return errs
    for key in ("name", "label"):
        if not (isinstance(cfg[key], str) and cfg[key].strip()):
            errs.append(f"{key} must be a non-empty string")
    dt = cfg["deny_tools"]
    if not (isinstance(dt, list) and all(isinstance(t, str) and t in _TOOLS for t in dt)):
        errs.append("deny_tools must be a list of known tools")
    da = cfg["domain_allowlist"]
    if da is not None:
        if not isinstance(da, list):
            errs.append("domain_allowlist must be null or a list of domains")
        else:
            errs.extend(p for p in map(_domain_problem, da) if p)
    bp = cfg["bind_params"]
    if not isinstance(bp, dict):
        errs.append("bind_params must map known tools to param lists")
    else:
        for tool, params in bp.items():
            if not (isinstance(tool, str) and tool in _TOOLS):
                errs.append(f"bind_params key {tool!r} is not a known tool")
            elif not (isinstance(params, list) and params):
                errs.append(f"bind_params[{tool!r}] must be a non-empty list (an empty list binds nothing)")
            elif not all(isinstance(p, str) and p in _BIND_PARAMS for p in params):
                errs.append(f"bind_params[{tool!r}] may only name {sorted(_BIND_PARAMS)}")
    el = cfg["egress_label_rules"]
    if not isinstance(el, dict):
        errs.append("egress_label_rules values must be 'deny' or 'trusted_destination'")
    else:
        if not all(isinstance(k, str) and k for k in el):
            errs.append("egress_label_rules labels must be non-empty strings")
        if not all(isinstance(v, str) and v in _RULE_MODES for v in el.values()):
            errs.append("egress_label_rules values must be 'deny' or 'trusted_destination'")
    if not errs and isinstance(ref, dict):
        if validate_config_shape_ok(ref):
            errs.extend(_weaker_than(ref, cfg))
        else:
            errs.append("reference policy is malformed; cannot compare")
    return errs


def validate_config_shape_ok(ref: dict) -> bool:
    """Cheap structural check of a reference policy (no recursion into _weaker_than)."""
    return (isinstance(ref.get("name"), str) and isinstance(ref.get("deny_tools"), list)
            and isinstance(ref.get("bind_params"), dict) and isinstance(ref.get("egress_label_rules"), dict)
            and (ref.get("domain_allowlist") is None or isinstance(ref.get("domain_allowlist"), list)))
