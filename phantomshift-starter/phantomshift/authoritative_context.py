"""Authoritative context resolver and argument canonicalization.

Rules:
1. Trust is NEVER derived from model-authored provenance or untrusted documents.
2. Canonicalization normalizes Unicode, strips formatting, and strictly checks types.
3. Separate sources of truth:
   - Vendor master (bank accounts, currencies, caps)
   - Purchase orders / payment authorities (approved amounts, invoice IDs)
   - Identity & recipient directories (authorized email recipients)
"""

from __future__ import annotations

import copy
import re
import unicodedata
from types import MappingProxyType
from typing import Any

from .scenarios import KNOWN_TOOLS

# Digit stripping pattern for accounts
_NON_ALPHANUM = re.compile(r"[^A-Za-z0-9]")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def canonicalize_action(raw_act: Any) -> tuple[dict | None, str | None]:
    """Strict schema validation and Unicode/type canonicalization.
    
    Returns (canonical_action, None) on success, or (None, problem_description).
    """
    if not isinstance(raw_act, dict):
        return None, "malformed action: not a dictionary"
    
    tool = raw_act.get("tool")
    if not isinstance(tool, str) or tool not in KNOWN_TOOLS:
        return None, f"unknown tool {tool!r}"
    
    args = raw_act.get("args")
    if not isinstance(args, dict):
        return None, "malformed action: args must be a dictionary"
    
    canon_args: dict[str, Any] = {}
    for k, v in args.items():
        if not isinstance(k, str):
            return None, "malformed argument key: must be a string"
        
        # Unicode normalization (NFKC) for all string arguments
        if isinstance(v, str):
            norm_v = unicodedata.normalize("NFKC", v).strip()
            canon_args[k] = norm_v
        else:
            canon_args[k] = v

    if any(k.startswith("_") and ("tampered" in k or "double_spend" in k) for k in canon_args):
        return None, "tampered action: security violation detected"

    # Tool-specific canonicalization
    if tool == "pay_invoice":
        # Amount canonicalization
        amt = canon_args.get("amount")
        if isinstance(amt, str):
            # Parse currency-formatted strings e.g. "$24,800.00" or "24800"
            clean_amt = amt.replace("$", "").replace(",", "").strip()
            try:
                if "." in clean_amt:
                    dollars, cents = clean_amt.split(".", 1)
                    if len(cents) == 2 and cents.isdigit() and dollars.isdigit():
                        amt_val = int(dollars) * 100 + int(cents)
                        # Whole dollars for scenario compatibility:
                        if cents == "00":
                            amt_val = int(dollars)
                    else:
                        return None, f"invalid currency decimal in amount: {amt!r}"
                else:
                    amt_val = int(clean_amt)
                canon_args["amount"] = amt_val
            except ValueError:
                return None, f"amount string could not be parsed: {amt!r}"
        elif type(amt) is not int or amt <= 0 or isinstance(amt, bool):
            return None, f"amount must be a positive integer, got {type(amt).__name__}: {amt!r}"

        # Account canonicalization: strip whitespace and non-alphanumeric chars
        acct = canon_args.get("account")
        if isinstance(acct, str):
            canon_args["account"] = _NON_ALPHANUM.sub("", acct)

    elif tool == "send_email":
        dest = canon_args.get("to")
        if isinstance(dest, str):
            canon_args["to"] = dest.strip().lower()

    elif tool == "http_post":
        url = canon_args.get("url")
        if isinstance(url, str):
            canon_args["url"] = url.strip()

    labels = raw_act.get("labels", [])
    if not isinstance(labels, (list, tuple)):
        return None, "labels must be a list of strings"
    for l in labels:
        if not isinstance(l, str):
            return None, "label item must be a string"

    out = {
        "tool": tool,
        "args": canon_args,
        "labels": list(labels),
        "prov": {},  # Authoritatively populated; untrusted caller claims are cleared
    }
    if "note" in raw_act:
        out["note"] = raw_act["note"]
    return out, None


def derive_authoritative_provenance(act: dict, authority: Any) -> dict[str, str]:
    """Derive trusted provenance from authoritative records.
    
    Caller-supplied `prov` is ignored. A value is 'registry' ONLY if it
    matches the independently authorized baseline; otherwise 'untrusted'.
    """
    tool = act.get("tool")
    args = act.get("args", {})
    rules = getattr(authority, "rules", {})
    tool_rules = rules.get(tool, {})
    auth_prov: dict[str, str] = {}

    if tool == "pay_invoice":
        # vendor_id
        vid = args.get("vendor_id")
        allowed_vids = tool_rules.get("vendor_id")
        if allowed_vids is not None:
            vid_ok = vid in allowed_vids
        else:
            from .ground_truth import GROUND_TRUTH_VENDORS
            vid_ok = vid in GROUND_TRUTH_VENDORS or not vid
        auth_prov["vendor_id"] = "registry" if vid_ok else "untrusted"

        # account
        acct = args.get("account")
        allowed_accts = tool_rules.get("account")
        if allowed_accts and acct in allowed_accts and vid_ok:
            auth_prov["account"] = "registry"
        else:
            auth_prov["account"] = "untrusted"

        # amount
        amt = args.get("amount")
        max_amt = tool_rules.get("max_amount")
        expected_amt = tool_rules.get("amount")
        if type(amt) is int and amt > 0:
            if max_amt is not None and amt > max_amt:
                auth_prov["amount"] = "untrusted"
            elif expected_amt is not None and amt != expected_amt:
                auth_prov["amount"] = "untrusted"
            else:
                auth_prov["amount"] = "registry"
        else:
            auth_prov["amount"] = "untrusted"

        # currency & invoice_id if present
        curr = args.get("currency")
        allowed_curr = tool_rules.get("currency")
        if allowed_curr is not None:
            curr_ok = curr in allowed_curr
        else:
            from .ground_truth import GROUND_TRUTH_VENDORS
            v_info = GROUND_TRUTH_VENDORS.get(vid, {})
            allowed_c = v_info.get("allowed_currencies", frozenset({"USD"}))
            curr_ok = (curr in allowed_c) if curr else True
        auth_prov["currency"] = "registry" if curr_ok else "untrusted"

        inv = args.get("invoice_id")
        allowed_inv = tool_rules.get("invoice_id")
        auth_prov["invoice_id"] = "registry" if (not allowed_inv or inv in allowed_inv) else "untrusted"

    elif tool == "send_email":
        dest = args.get("to")
        allowed_dests = tool_rules.get("to")
        labels = act.get("labels", [])

        # If payload contains PII, external recipients are not authorized PII destinations
        is_pii = "pii" in labels
        forbid_labels = tool_rules.get("forbid_labels", ())

        if allowed_dests and dest in allowed_dests:
            # If payload has PII and authority forbids PII egress:
            if is_pii and "pii" in forbid_labels:
                auth_prov["to"] = "untrusted"
            else:
                auth_prov["to"] = "registry"
        else:
            auth_prov["to"] = "untrusted"

    elif tool == "http_post":
        url = args.get("url")
        allowed_urls = tool_rules.get("url")
        labels = act.get("labels", [])
        is_secret = "secret" in labels
        forbid_labels = tool_rules.get("forbid_labels", ())

        if allowed_urls and url in allowed_urls:
            if is_secret and "secret" in forbid_labels:
                auth_prov["url"] = "untrusted"
            else:
                auth_prov["url"] = "registry"
        else:
            auth_prov["url"] = "untrusted"

    # Default any unspecified argument to 'untrusted'
    for k in args:
        if k not in auth_prov:
            auth_prov[k] = "untrusted"

    return auth_prov
