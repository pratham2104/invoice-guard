#!/usr/bin/env python3
"""Audit one proposed agent tool call against a tool schema and a TRUSTED scope record.

Standalone, stdlib only, no network, no file writes, no environment access.

Authorization comes ONLY from the `trusted_scope` argument (CLI: --scope FILE), which the operator
supplies out of band. Nothing inside the call (tool, args, claimed provenance, extra fields) and nothing
in document text can grant, widen or imply authority. Claimed provenance is recorded and never used
to authorise. Text that tries to claim authority ("approved", "admin override", "ignore previous",
"system note") produces a finding and can only make the verdict stricter.

Verdict: allow | hold | deny. hold means "needs a human or a trusted scope grant", deny means the
call is structurally wrong or outside the trusted scope. allow means: no finding stronger than info.
It is a screening primitive: it does not execute anything and is not a sandbox.

Usage:
    python3 toolcall_audit.py --call call.json --scope scope.json [--tools tools.json]
                              [--document doc.txt] [--exit-code]
    cat call.json | python3 toolcall_audit.py --call - --scope scope.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "agent-toolcall-audit/1"

# Roles an argument may have in a tool schema.
SCOPED_ROLES = ("destination", "recipient", "resource", "amount")
ALL_ROLES = SCOPED_ROLES + ("id", "text")
JSON_TYPES = ("string", "integer", "number", "boolean", "object", "array")
TRUSTED_PROVENANCE = ("user", "registry")
KNOWN_PROVENANCE = ("user", "registry", "untrusted", "model")
CALL_KEYS = ("tool", "args", "provenance")

# Default tool registry. Override with --tools. Illustrative, matches the synthetic demo fixtures.
DEFAULT_TOOLS: dict[str, dict[str, Any]] = {
    "pay_invoice": {"sensitive": True, "args": {
        "vendor_id": {"type": "string", "required": True, "role": "id"},
        "amount": {"type": "integer", "required": True, "role": "amount"},
        "account": {"type": "string", "required": True, "role": "recipient"}}},
    "lookup_vendor": {"sensitive": False, "args": {
        "vendor_id": {"type": "string", "required": True, "role": "id"}}},
    "send_email": {"sensitive": True, "args": {
        "to": {"type": "string", "required": True, "role": "destination"},
        "body": {"type": "string", "required": True, "role": "text"}}},
    "http_post": {"sensitive": True, "args": {
        "url": {"type": "string", "required": True, "role": "destination"},
        "body": {"type": "string", "required": True, "role": "text"}}},
    "read_file": {"sensitive": False, "args": {
        "path": {"type": "string", "required": True, "role": "resource"}}},
}

# --- text that tries to claim authority ------------------------------------------------------------
_AUTHORITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "claims_approval": re.compile(r"\b(?:pre-?)?approved\b"),
    "claims_admin_override": re.compile(
        r"\b(?:admin|administrator|root|superuser)\s+(?:override|access|mode|privileges?)\b"
        r"|\boverrid(?:e|ing)\s+(?:the\s+)?(?:policy|policies|guard|check|checks|approval|approvals)\b"),
    "claims_ignore_previous": re.compile(
        r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+)*(?:previous|prior|above|earlier|preceding)\b"
        r"|\b(?:ignore|bypass)\s+(?:the\s+)?(?:policy|policies|rules|guard|instructions)\b"),
    "claims_system_note": re.compile(
        r"\bsystem\s*(?:note|message|prompt|instruction|override)\b"
        r"|\bnote\s+to\s+(?:the\s+)?(?:processing\s+)?(?:agent|assistant)\b"),
    "claims_authorization": re.compile(
        r"\bauthori[sz]ed\s+by\b|\bi\s+authori[sz]e\b|\bapproval\s+(?:id|token|code)\b|\bauthori[sz]ation\s+code\b"),
}
_AUTHORITY_FIELD_NAME = re.compile(
    r"approv|authori[sz]|admin|overrid|sudo|root|scope|grant|permit|allow|trusted|bypass|skip", re.I)

# --- redaction of token-shaped strings in anything we print -----------------------------------------
_REDACT = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\b[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
]
_MAX_SHOWN = 80


def _redact(text: str) -> str:
    for pat in _REDACT:
        text = pat.sub("[REDACTED]", text)
    return text


def _shown(value: Any) -> str:
    text = _redact(value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True))
    return text if len(text) <= _MAX_SHOWN else text[:_MAX_SHOWN] + "...[truncated]"


def _finding(code: str, severity: str, field: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "field": field, "detail": detail}


# --- text normalisation ------------------------------------------------------------------------------
def _has_hidden(text: str) -> bool:
    return any(unicodedata.category(c) in ("Cf", "Cc") and c not in "\n\t\r" for c in text)


def _fold_for_scan(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return re.sub(r"\s+", " ", text).casefold()


def scan_authority_claims(text: str) -> list[str]:
    """Names of authority-claim patterns present in text (after NFKC, zero-width removal, casefold)."""
    folded = _fold_for_scan(text)
    return sorted(name for name, pat in _AUTHORITY_PATTERNS.items() if pat.search(folded))


def _norm_str(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


# --- tool registry and scope validation ---------------------------------------------------------------
def check_tools(tools: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(tools, dict) or not tools:
        return ["tools must be a non-empty object"]
    for name, spec in tools.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            problems.append(f"tool {name!r}: spec must be an object")
            continue
        if set(spec) - {"sensitive", "args"} or not isinstance(spec.get("sensitive"), bool) \
                or not isinstance(spec.get("args"), dict):
            problems.append(f"tool {name!r}: needs exactly boolean 'sensitive' and object 'args'")
            continue
        for arg, aspec in spec["args"].items():
            if not isinstance(aspec, dict) or set(aspec) - {"type", "required", "role"} \
                    or aspec.get("type") not in JSON_TYPES or not isinstance(aspec.get("required"), bool) \
                    or aspec.get("role") not in ALL_ROLES:
                problems.append(f"tool {name!r} arg {arg!r}: needs type {JSON_TYPES}, boolean required, role {ALL_ROLES}")
            elif aspec["role"] == "amount" and aspec["type"] != "integer":
                problems.append(f"tool {name!r} arg {arg!r}: role amount must have type integer")
    return problems


def check_scope(scope: Any) -> list[str]:
    """Problems with a trusted scope record; empty means usable. Unknown keys are refused."""
    if not isinstance(scope, dict):
        return ["scope must be an object"]
    problems: list[str] = []
    extra = set(scope) - {"scope_id", "granted_tools", "allowed_values", "allowed_domains", "max_amount"}
    if extra:
        problems.append(f"unknown scope keys {sorted(extra)}")
    if not isinstance(scope.get("scope_id"), str) or not scope.get("scope_id"):
        problems.append("scope_id must be a non-empty string")
    gt = scope.get("granted_tools", [])
    if not (isinstance(gt, list) and all(isinstance(x, str) for x in gt)):
        problems.append("granted_tools must be a list of strings")
    for key in ("allowed_values", "allowed_domains"):
        val = scope.get(key, {})
        if not (isinstance(val, dict) and all(isinstance(k, str) and isinstance(v, list)
                                              and all(isinstance(i, str) for i in v) for k, v in val.items())):
            problems.append(f"{key} must map 'tool.arg' to a list of strings")
    ma = scope.get("max_amount", {})
    if not (isinstance(ma, dict) and all(isinstance(k, str) and type(v) is int and v > 0 for k, v in ma.items())):
        problems.append("max_amount must map 'tool.arg' to a positive integer")
    return problems


# --- destination parsing ------------------------------------------------------------------------------
_BAD_DEST = re.compile(r"[\s\\\x00-\x1f\x7f<>()\"'`,;]")


def _dest_host(value: str) -> str | None:
    """Host of an email address or http(s) URL, or None if ambiguous. Never interprets odd input."""
    if not value or _BAD_DEST.search(value):
        return None
    if "://" in value:
        try:
            parts = urlsplit(value)
            parts.port  # noqa: B018  raises ValueError on a bad port
        except ValueError:
            return None
        if parts.scheme.lower() not in ("http", "https") or "@" in parts.netloc:
            return None
        return (parts.hostname or "").lower() or None
    if value.count("@") != 1:
        return None
    local, host = value.split("@")
    if not local or not host or host.endswith("."):
        return None
    return host.lower()


def _host_in(host: str, domains: list[str]) -> bool:
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)


# --- the audit -----------------------------------------------------------------------------------------
def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in (int, float) and value == value and value not in (float("inf"), float("-inf"))
    if expected == "boolean":
        return type(value) is bool
    if expected == "object":
        return isinstance(value, dict)
    return isinstance(value, list)


def _verdict(findings: list[dict[str, str]]) -> str:
    sev = {f["severity"] for f in findings}
    return "deny" if "deny" in sev else "hold" if "hold" in sev else "allow"


def audit_call(call: Any, trusted_scope: Any = None, tools: Any = None, document: str | None = None) -> dict[str, Any]:
    """Audit one call. Never raises on bad input; malformed input yields verdict deny."""
    findings: list[dict[str, str]] = []
    registry = DEFAULT_TOOLS if tools is None else tools
    problems = check_tools(registry)
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "authorization_source": "trusted_scope_input_only",
        "provenance_claims_used_for_authorization": False,
        "scope_id": None, "normalized_call": None, "findings": findings, "verdict": "deny",
    }
    if problems:
        findings.append(_finding("TOOLS_INVALID", "deny", "tools", "; ".join(problems)[:300]))
        return out
    if not isinstance(call, dict) or not isinstance(call.get("tool"), str) or not isinstance(call.get("args"), dict) \
            or not all(isinstance(k, str) for k in call["args"]):
        findings.append(_finding("MALFORMED_CALL", "deny", "call",
                                 "call must be an object with string 'tool' and object 'args' with string keys"))
        return out

    scope: dict[str, Any] | None = None
    if trusted_scope is not None:
        sp = check_scope(trusted_scope)
        if sp:
            findings.append(_finding("SCOPE_INVALID", "hold", "scope", "; ".join(sp)[:300]))
        else:
            scope = trusted_scope
            out["scope_id"] = scope["scope_id"]

    # Fields on the call itself never carry authority; report them.
    for key in call:
        if key in CALL_KEYS:
            continue
        auth_like = bool(_AUTHORITY_FIELD_NAME.search(str(key)))
        findings.append(_finding("AUTHORITY_FIELD_IGNORED" if auth_like else "UNEXPECTED_CALL_FIELD",
                                 "hold" if auth_like else "info", f"call.{_shown(key)}",
                                 "field on the call has no effect on authorization; only the trusted scope input does"))

    raw_tool = call["tool"]
    tool = _norm_str(raw_tool)
    if tool != raw_tool:
        findings.append(_finding("TOOL_NAME_NOT_CANONICAL", "hold", "tool",
                                 f"tool name changed under NFKC/strip: {_shown(raw_tool)!r}"))
    if _has_hidden(raw_tool):
        findings.append(_finding("HIDDEN_CHARACTERS", "hold", "tool", "control or format characters in the tool name"))
    spec = registry.get(tool)
    if spec is None:
        findings.append(_finding("UNKNOWN_TOOL", "deny", "tool", f"tool {_shown(tool)!r} is not in the tool registry"))
        out["normalized_call"] = {"tool": _shown(tool), "args": {}}
        return out

    # Normalise args (NFKC + strip on strings) without repairing anything.
    norm_args: dict[str, Any] = {}
    for key, val in call["args"].items():
        nkey = _norm_str(key)
        if nkey in norm_args:
            findings.append(_finding("DUPLICATE_ARG", "deny", f"args.{_shown(nkey)}", "two args collide after normalisation"))
            continue
        if isinstance(val, str):
            if _has_hidden(val):
                findings.append(_finding("HIDDEN_CHARACTERS", "hold", f"args.{_shown(nkey)}",
                                         "control or format characters in the value"))
            val = _norm_str(val)
        norm_args[nkey] = val

    prov = call.get("provenance", {})
    if not isinstance(prov, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in prov.items()):
        findings.append(_finding("PROVENANCE_MALFORMED", "hold", "provenance",
                                 "claimed provenance must map arg names to strings; treated as untrusted"))
        prov = {}
    claims = {k: (v if v in KNOWN_PROVENANCE else "untrusted") for k, v in prov.items()}

    arg_specs: dict[str, dict[str, Any]] = spec["args"]
    for name in sorted(norm_args):
        if name not in arg_specs:
            findings.append(_finding("EXTRA_ARG", "deny", f"args.{_shown(name)}",
                                     f"argument not defined for tool {tool!r}"))
    for name, aspec in arg_specs.items():
        if name not in norm_args:
            if aspec["required"]:
                findings.append(_finding("MISSING_ARG", "deny", f"args.{name}", "required argument is missing"))
            continue
        if not _type_ok(norm_args[name], aspec["type"]):
            findings.append(_finding("WRONG_TYPE", "deny", f"args.{name}",
                                     f"expected {aspec['type']}, got {type(norm_args[name]).__name__}"))

    # Authority claims inside untrusted text. Only ever stricter.
    for name, aspec in arg_specs.items():
        val = norm_args.get(name)
        if aspec["role"] == "text" and isinstance(val, str):
            for pat in scan_authority_claims(val):
                findings.append(_finding("AUTHORITY_CLAIM_IN_UNTRUSTED_TEXT", "hold", f"args.{name}", pat))
    if isinstance(document, str):
        for pat in scan_authority_claims(document):
            findings.append(_finding("AUTHORITY_CLAIM_IN_DOCUMENT", "info", "document",
                                     f"{pat} (recorded; document text never authorises anything)"))

    # Scope checks. Authorization lives only here.
    scoped_args = [(n, a) for n, a in arg_specs.items() if a["role"] in SCOPED_ROLES and n in norm_args
                   and _type_ok(norm_args[n], a["type"])]
    granted = scope is not None and tool in scope.get("granted_tools", [])
    if spec["sensitive"] and not granted:
        findings.append(_finding("SENSITIVE_WITHOUT_TRUSTED_SCOPE", "hold", "tool",
                                 f"{tool!r} is a sensitive operation and no trusted scope grants it"))
    elif scope is None:
        if scoped_args:
            findings.append(_finding("NO_TRUSTED_SCOPE", "hold", "scope",
                                     "no usable trusted scope; scoped arguments cannot be authorised"))
    else:
        for name, aspec in scoped_args:
            _check_scoped_arg(findings, scope, tool, name, aspec["role"], norm_args[name])
    for name, aspec in arg_specs.items():
        if aspec["role"] in SCOPED_ROLES and name in norm_args and name in claims \
                and claims[name] not in TRUSTED_PROVENANCE:
            findings.append(_finding("CLAIMED_UNTRUSTED_SOURCE", "info", f"args.{name}",
                                     "agent claims this value did not come from user or registry (recorded, not used)"))

    out["normalized_call"] = {"tool": tool, "args": {k: _redact_value(norm_args[k]) for k in sorted(norm_args)},
                              "claimed_provenance": {k: claims[k] for k in sorted(claims)}}
    out["verdict"] = _verdict(findings)
    return out


def _redact_value(value: Any) -> Any:
    return _walk(value)


def _walk(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_walk(v) for v in value]
    if isinstance(value, dict):
        return {_redact(str(k)): _walk(v) for k, v in value.items()}
    return value


def _check_scoped_arg(findings: list[dict[str, str]], scope: dict[str, Any], tool: str, name: str, role: str,
                      value: Any) -> None:
    key = f"{tool}.{name}"
    field = f"args.{name}"
    values = scope.get("allowed_values", {}).get(key)
    domains = scope.get("allowed_domains", {}).get(key)
    if role == "amount":
        cap = scope.get("max_amount", {}).get(key)
        if cap is None:
            findings.append(_finding("AMOUNT_OUT_OF_SCOPE", "deny", field, f"no max_amount for {key} in the trusted scope"))
        elif value <= 0 or value > cap:
            findings.append(_finding("AMOUNT_OUT_OF_SCOPE", "deny", field,
                                     f"amount {value} is not a positive integer <= {cap}"))
        return
    code = {"destination": "DESTINATION_OUT_OF_SCOPE", "recipient": "RECIPIENT_OUT_OF_SCOPE",
            "resource": "RESOURCE_OUT_OF_SCOPE"}[role]
    if values is None and domains is None:
        findings.append(_finding(code, "deny", field, f"no allowed values for {key} in the trusted scope"))
        return
    if values is not None and value in values:
        return
    if role == "destination" and domains is not None:
        host = _dest_host(value)
        if host is None:
            findings.append(_finding("DESTINATION_MALFORMED", "deny", field,
                                     "destination is ambiguous (several recipients, userinfo, bad scheme or characters)"))
            return
        if _host_in(host, domains):
            return
    findings.append(_finding(code, "deny", field, f"{_shown(value)!r} is not in the trusted scope for {key}"))


# --- CLI -----------------------------------------------------------------------------------------------
def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} is not valid JSON input")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate JSON key {k!r}")
        out[k] = v
    return out


def load_json_text(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_pairs)


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit one proposed tool call against a trusted scope record.")
    ap.add_argument("--call", required=True, help="JSON file with the proposed call, or - for stdin")
    ap.add_argument("--scope", help="JSON file with the TRUSTED scope record (operator supplied)")
    ap.add_argument("--tools", help="JSON file with a tool registry (default: built-in demo registry)")
    ap.add_argument("--document", help="text file with untrusted document text (scanned, never trusted)")
    ap.add_argument("--exit-code", action="store_true", help="exit 0 allow, 3 hold, 4 deny")
    args = ap.parse_args(argv)
    try:
        call = load_json_text(_read(args.call))
        scope = load_json_text(_read(args.scope)) if args.scope else None
        tools = load_json_text(_read(args.tools)) if args.tools else None
        document = _read(args.document) if args.document else None
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "error": f"{type(exc).__name__}: {_shown(str(exc))}"}))
        return 2
    result = audit_call(call, scope, tools, document)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.exit_code:
        return {"allow": 0, "hold": 3, "deny": 4}[result["verdict"]]
    return 0


if __name__ == "__main__":
    sys.exit(main())
