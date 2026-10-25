#!/usr/bin/env python3
"""Build and verify a redacted, hashed incident receipt.

Standalone, stdlib only, no network, no environment access, no clock (so output is reproducible).

A receipt bundles four things about one incident: REDACTED observations, a policy diff, an approval record
and test results. Token-shaped strings are replaced before anything is hashed, so a secret that appeared in
an observation never reaches the receipt or its digest. The digest is the SHA-256 of canonical JSON (sorted
keys, compact separators, ASCII, no NaN).

IMPORTANT, and repeated in every receipt: a SHA-256 hash is NOT a digital signature and NOT an immutable
log. It detects accidental or naive edits only. Anyone who can edit the receipt can recompute the digest.
For tamper evidence against an adversary, anchor the digest somewhere you do not control the write path of
(a signature, a signed commit, an external append-only store). This tool does none of that.

Usage:
    python3 incident_receipt.py build  --input incident.json [--redact-emails] [--out receipt.json]
    python3 incident_receipt.py verify --receipt receipt.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import Any

RECEIPT_VERSION = "agent-incident-receipt/1"
CANONICALIZATION = "json:sort_keys,compact_separators,ascii,no_nan"
NOTICE = ("A SHA-256 digest is NOT a digital signature and NOT an immutable log. It detects accidental or naive "
          "changes to this receipt only: anyone who can edit the receipt can also recompute the digest. For "
          "tamper evidence against an adversary, anchor the digest outside this tool (a signature, a signed "
          "commit or an external append-only store).")
SECTIONS = ("observations", "policy_diff", "approval", "test_results")
INPUT_KEYS = {"incident_id", "observations", "policy_diff", "policy_before", "policy_after", "approval",
              "test_results"}

# (kind, pattern, group-to-replace). Order matters: broad blocks first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I)),
    ("discord_token", re.compile(r"\b[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b")),
    ("openai_like_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws_secret_key", re.compile(r"(?i)(aws_secret_access_key[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9/+=]{40}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("secret_assignment", re.compile(
        r"(?i)\b((?:api[_-]?key|secret|token|passwd|password)[\"']?\s*[:=]\s*[\"']?)(?!\[REDACTED)[^\s\"',;]{8,}")),
]
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class ReceiptError(ValueError):
    """Malformed input or receipt."""


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


# --- redaction -----------------------------------------------------------------------------------------
def redact_text(text: str, counts: dict[str, int], emails: bool = False) -> str:
    for kind, pat in _PATTERNS:
        def _sub(m: re.Match[str], kind: str = kind) -> str:
            counts[kind] = counts.get(kind, 0) + 1
            prefix = m.group(1) if m.groups() else ""
            return f"{prefix}[REDACTED:{kind}]"
        text = pat.sub(_sub, text)
    if emails:
        def _email(m: re.Match[str]) -> str:
            counts["email"] = counts.get("email", 0) + 1
            return "[REDACTED:email]"
        text = _EMAIL.sub(_email, text)
    return text


def redact_value(value: Any, counts: dict[str, int], emails: bool = False) -> Any:
    """Redact strings in values AND dict keys, recursively. Non-string scalars pass through."""
    if isinstance(value, str):
        return redact_text(value, counts, emails)
    if isinstance(value, list):
        return [redact_value(v, counts, emails) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            nk = redact_text(str(k), counts, emails)
            while nk in out:
                nk += "#dup"
            out[nk] = redact_value(v, counts, emails)
        return out
    return value


def count_secret_shapes(value: Any) -> int:
    """How many token-shaped strings remain in value (used by verify as a warning, never by the digest)."""
    counts: dict[str, int] = {}
    redact_value(value, counts, False)
    return sum(counts.values())


# --- policy diff ----------------------------------------------------------------------------------------
def diff_policies(before: Any, after: Any) -> dict[str, Any]:
    """Top-level key diff of two policy objects: added, removed, changed {from, to}."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ReceiptError("policy_before and policy_after must both be objects")
    return {
        "added": {k: after[k] for k in sorted(set(after) - set(before))},
        "removed": {k: before[k] for k in sorted(set(before) - set(after))},
        "changed": {k: {"from": before[k], "to": after[k]} for k in sorted(set(before) & set(after)) if before[k] != after[k]},
    }


# --- build / verify -------------------------------------------------------------------------------------
def _digests(receipt_core: dict[str, Any]) -> tuple[dict[str, str], str]:
    section_digests = {name: sha256_of(receipt_core["sections"][name]) for name in SECTIONS}
    preimage = {"receipt_version": receipt_core["receipt_version"], "incident_id": receipt_core["incident_id"],
                "redaction": receipt_core["redaction"], "section_digests": section_digests}
    return section_digests, sha256_of(preimage)


def build_receipt(incident: Any, redact_emails: bool = False) -> dict[str, Any]:
    if not isinstance(incident, dict):
        raise ReceiptError("incident input must be an object")
    extra = set(incident) - INPUT_KEYS
    if extra:
        raise ReceiptError(f"unknown input keys {sorted(extra)}")
    iid = incident.get("incident_id")
    if not isinstance(iid, str) or not _ID.match(iid):
        raise ReceiptError("incident_id must match [A-Za-z0-9._:-]{1,64}")
    if not isinstance(incident.get("observations"), list):
        raise ReceiptError("observations must be a list")
    if "policy_diff" in incident:
        if "policy_before" in incident or "policy_after" in incident:
            raise ReceiptError("give policy_diff or policy_before+policy_after, not both")
        policy_diff = incident["policy_diff"]
    elif "policy_before" in incident and "policy_after" in incident:
        policy_diff = diff_policies(incident["policy_before"], incident["policy_after"])
    else:
        raise ReceiptError("policy_diff (or policy_before and policy_after) is required")
    if not isinstance(policy_diff, dict):
        raise ReceiptError("policy_diff must be an object")
    approval = incident.get("approval", "MISSING")
    if approval == "MISSING" or not (approval is None or isinstance(approval, dict)):
        raise ReceiptError("approval must be an object, or null when no approval exists")
    if not isinstance(incident.get("test_results"), (dict, list)):
        raise ReceiptError("test_results must be an object or a list")

    counts: dict[str, int] = {}
    raw_sections = {"observations": incident["observations"], "policy_diff": policy_diff,
                    "approval": approval, "test_results": incident["test_results"]}
    sections = {name: redact_value(raw_sections[name], counts, redact_emails) for name in SECTIONS}
    core: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "incident_id": iid,
        "redaction": {"applied": True, "emails_redacted": bool(redact_emails),
                      "redactions_by_kind": {k: counts[k] for k in sorted(counts)}, "total": sum(counts.values())},
        "sections": sections,
    }
    try:
        section_digests, digest = _digests(core)
    except (TypeError, ValueError) as exc:  # non-JSON values or NaN
        raise ReceiptError(f"input is not canonical-JSON serialisable: {exc}") from exc
    return {**core, "hash_algorithm": "sha256", "canonicalization": CANONICALIZATION,
            "section_digests": section_digests, "digest": digest,
            "provenance_label": "sha256 over redacted content; NOT a signature; NOT an immutable log",
            "notice": NOTICE}


def verify_receipt(receipt: Any) -> dict[str, Any]:
    """Recompute section digests and the overall digest and compare with the claimed values."""
    result: dict[str, Any] = {"ok": False, "mismatches": [], "notice": NOTICE}
    try:
        if not isinstance(receipt, dict):
            raise ReceiptError("receipt must be an object")
        for key in ("receipt_version", "incident_id", "redaction", "sections", "section_digests", "digest"):
            if key not in receipt:
                raise ReceiptError(f"receipt is missing {key!r}")
        if receipt["receipt_version"] != RECEIPT_VERSION:
            raise ReceiptError(f"unsupported receipt_version {receipt['receipt_version']!r}")
        sections = receipt["sections"]
        if not isinstance(sections, dict) or set(sections) != set(SECTIONS):
            raise ReceiptError(f"sections must be exactly {list(SECTIONS)}")
        claimed_sections = receipt["section_digests"]
        if not isinstance(claimed_sections, dict):
            raise ReceiptError("section_digests must be an object")
        section_digests, digest = _digests(receipt)
    except (ReceiptError, TypeError, ValueError, KeyError) as exc:
        result["mismatches"].append(f"malformed: {str(exc)[:200]}")
        return result
    for name in SECTIONS:
        if claimed_sections.get(name) != section_digests[name]:
            result["mismatches"].append(f"section:{name}")
    if receipt["digest"] != digest:
        result["mismatches"].append("digest")
    result.update({"ok": not result["mismatches"], "claimed_digest": receipt["digest"], "recomputed_digest": digest,
                   "unredacted_secret_shapes": count_secret_shapes(sections)})
    return result


# --- CLI -------------------------------------------------------------------------------------------------
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
    ap = argparse.ArgumentParser(description="Build or verify a redacted, hashed incident receipt. "
                                             "A hash is NOT a digital signature and NOT an immutable log.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="redact, canonicalise and hash an incident bundle")
    b.add_argument("--input", required=True, help="incident JSON file, or - for stdin")
    b.add_argument("--redact-emails", action="store_true", help="also redact email addresses")
    b.add_argument("--out", help="also write the receipt to this path")
    v = sub.add_parser("verify", help="recompute the digest of a receipt")
    v.add_argument("--receipt", required=True, help="receipt JSON file, or - for stdin")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "build":
            out = build_receipt(load_json(args.input), args.redact_emails)
            text = json.dumps(out, indent=2, sort_keys=True)
            print(text)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(text + "\n")
            return 0
        res = verify_receipt(load_json(args.receipt))
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0 if res["ok"] else 1
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:300]}", "notice": NOTICE}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
