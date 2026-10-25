"""Deterministic AP control engine. No LLM in here: same input, same verdict, every time.

Fails closed: anything unresolved or surprising becomes a HOLD.
"""
import re
import statistics
from dataclasses import dataclass, field, asdict

from . import config, db
from .extractor import Extraction
from .parser import ParsedEmail

SEVERITY_ORDER = {"info": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class Finding:
    rule: str
    severity: str          # info | medium | high | critical
    points: int
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass
class Verdict:
    verdict: str           # PASS | HOLD
    score: int
    severity: str
    vendor_id: int | None
    vendor_name: str | None
    vendor_match: str
    findings: list

    def to_dict(self):
        d = asdict(self)
        return d


# --------------------------------------------------------------------------- helpers
def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def skeleton(domain: str) -> str:
    """Collapse common visual confusables so 'acmeindustrlal' ~ 'acmeindustrial'."""
    s = domain.lower().replace("rn", "m").replace("vv", "w")
    return s.translate(str.maketrans({"0": "o", "1": "l", "i": "l", "5": "s", "3": "e"}))


def lookalike(sender_domain: str, official: list[str]) -> str | None:
    """Return a reason string if sender_domain imitates (but is not) an official domain."""
    sd = sender_domain.lower()
    for od in official:
        od = od.lower()
        if sd == od or sd.endswith("." + od):
            return None
    for od in official:
        od = od.lower()
        stem = od.split(".")[0]
        if skeleton(sd) == skeleton(od):
            return f"homoglyph match of {od}"
        if edit_distance(sd, od) <= config.LOOKALIKE_MAX_DISTANCE:
            return f"edit distance {edit_distance(sd, od)} from {od}"
        if len(stem) >= 5 and stem in sd.split(".")[0]:
            return f"contains official name '{stem}'"
    return None


def resolve_vendor(conn, email: ParsedEmail):
    """Return (vendor_row | None, how). Exact domain first, then name, then lookalike."""
    vendors = conn.execute("SELECT * FROM vendors").fetchall()
    for v in vendors:
        doms = [d.strip().lower() for d in v["domains"].split(",")]
        if email.sender_domain in doms or any(email.sender_domain.endswith("." + d) for d in doms):
            return v, "domain"
    hay = f"{email.sender_name} {email.text}".lower()
    for v in vendors:
        if v["name"].lower() in hay:
            return v, "name_in_text"
    best, best_d = None, 99
    for v in vendors:
        for d in v["domains"].split(","):
            dist = edit_distance(email.sender_domain, d.strip().lower())
            if dist < best_d:
                best, best_d = v, dist
    if best is not None and best_d <= 4:
        return best, "lookalike_domain"
    return None, "none"


def _norm_addr(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# --------------------------------------------------------------------------- engine
def evaluate(conn, email: ParsedEmail, ex: Extraction) -> Verdict:
    F: list[Finding] = []
    add = lambda rule, sev, pts, msg, **ev: F.append(Finding(rule, sev, pts, msg, ev))

    vendor, how = resolve_vendor(conn, email)
    vid = vendor["id"] if vendor else None
    domain_issue = False

    # ---- 0. prompt injection (always evaluated, independent of vendor)
    if ex.injection_hits:
        add("prompt_injection", "high", 50,
            "Email contains instructions aimed at an AI/automation system. Treated as hostile.",
            patterns=ex.injection_hits)

    if vendor is None:
        add("vendor_unknown", "high", 45, "Sender could not be matched to any vendor in the vendor master.",
            sender=email.sender_email)
        return _finish(F, None, None, how)

    if vendor["status"] != "active":
        add("vendor_inactive", "high", 45, f"Vendor status is '{vendor['status']}'.")

    official = [d.strip() for d in vendor["domains"].split(",")]

    # ---- 1. sender identity
    if how != "domain":
        domain_issue = True
        reason = lookalike(email.sender_domain, official)
        if reason:
            add("lookalike_domain", "critical", 70,
                f"Sender domain '{email.sender_domain}' imitates vendor domain ({reason}).",
                sender_domain=email.sender_domain, official=official)
        else:
            add("sender_domain_mismatch", "high", 45,
                f"Sender domain '{email.sender_domain}' is not an official domain of {vendor['name']}.",
                official=official)

    if email.reply_to_domain and email.reply_to_domain != email.sender_domain:
        domain_issue = True
        add("reply_to_mismatch", "high", 40,
            f"Reply-To domain '{email.reply_to_domain}' differs from sender domain.",
            reply_to=email.reply_to_email)

    ar = email.auth_results.lower()
    if not ar:
        add("no_auth_results", "medium", 15, "No Authentication-Results header; sender not verified.")
    else:
        failed = [k for k in ("spf", "dkim", "dmarc") if re.search(rf"{k}=(fail|softfail|none|permerror|temperror)", ar)]
        if failed:
            add("email_auth_failed", "high", 40, f"Email authentication failed: {', '.join(failed)}.",
                results=email.auth_results)

    trusted = [r["email"].lower() for r in conn.execute(
        "SELECT email FROM vendor_contacts WHERE vendor_id=? AND trusted=1", (vid,))]
    new_contact = email.sender_email not in trusted
    if new_contact:
        add("new_contact", "medium", 20, "Sender is not a known trusted contact for this vendor.",
            sender=email.sender_email)

    # ---- 2. bank details
    accounts = conn.execute("SELECT fingerprint,last4 FROM vendor_bank_accounts WHERE vendor_id=? AND active=1",
                            (vid,)).fetchall()
    bank_flag = False
    if ex.bank_account:
        fp = db.fingerprint(ex.bank_account)
        if fp not in {a["fingerprint"] for a in accounts}:
            bank_flag = True
            add("bank_account_mismatch", "critical", 70,
                "Bank account in the message does not match the verified account on file.",
                provided_last4=db.last4(ex.bank_account), on_file_last4=[a["last4"] for a in accounts])
    if ex.intent == "bank_change" and not bank_flag:
        bank_flag = True
        add("bank_change_requested", "critical", 70,
            "Message requests a change to payment/bank details (vendor-master change).")

    if ex.remit_address and vendor["remit_address"] and \
            _norm_addr(ex.remit_address) != _norm_addr(vendor["remit_address"]):
        add("remit_address_changed", "high", 45, "Remit-to address differs from the address on file.",
            provided=ex.remit_address, on_file=vendor["remit_address"])

    # ---- 3. urgency (amplifier only)
    urgent = bool(ex.urgency_hits)
    if urgent:
        add("payment_urgency", "medium", 15, "Message pressures for fast payment.", patterns=ex.urgency_hits)

    # ---- 4. combination: the classic BEC pattern
    if bank_flag and (domain_issue or new_contact or urgent or any(f.rule == "email_auth_failed" for f in F)):
        add("bank_change_with_risk_signals", "critical", 30,
            "Bank/remit change combined with sender, contact, auth or urgency red flags.")

    # ---- 5. invoice / PO checks
    if ex.invoice_number:
        dup = conn.execute("SELECT * FROM invoices WHERE vendor_id=? AND invoice_number=?",
                           (vid, ex.invoice_number)).fetchone()
        if dup:
            add("duplicate_invoice", "high", 55,
                f"Invoice {ex.invoice_number} was already received (status: {dup['status']}, "
                f"${dup['amount']:,.2f} on {dup['invoice_date']}).", invoice=ex.invoice_number)
    elif ex.intent == "invoice":
        add("invoice_number_missing", "medium", 15, "Could not find an invoice number.")

    if ex.po_number:
        po = conn.execute("SELECT * FROM purchase_orders WHERE po_number=?", (ex.po_number,)).fetchone()
        if not po:
            add("po_not_found", "high", 45, f"{ex.po_number} does not exist.")
        elif po["vendor_id"] != vid:
            add("po_vendor_mismatch", "high", 50, f"{ex.po_number} belongs to a different vendor.")
        else:
            if po["status"] != "open":
                add("po_closed", "high", 45, f"{ex.po_number} is {po['status']}.")
            if ex.amount is not None and ex.amount > po["amount"] * (1 + config.PO_TOLERANCE):
                add("amount_over_po", "high", 50,
                    f"Invoice ${ex.amount:,.2f} exceeds PO ${po['amount']:,.2f}.",
                    invoice_amount=ex.amount, po_amount=po["amount"])
    elif ex.intent == "invoice" and ex.invoice_number:
        add("no_po_reference", "medium", 15, "Invoice does not reference a PO.")

    hist = [r["amount"] for r in conn.execute(
        "SELECT amount FROM invoices WHERE vendor_id=? AND status='paid'", (vid,))]
    if ex.amount is not None and len(hist) >= 3:
        mean, mx = statistics.mean(hist), max(hist)
        sd = statistics.pstdev(hist)
        if ex.amount > mx * 1.5 and ex.amount > mean + 3 * sd:
            add("amount_outlier", "medium", 20,
                f"Amount ${ex.amount:,.2f} is far above this vendor's history (mean ${mean:,.0f}, max ${mx:,.0f}).")

    return _finish(F, vendor, vid, how)


def _finish(F, vendor, vid, how) -> Verdict:
    score = min(sum(f.points for f in F), 100)
    sev = max((f.severity for f in F), key=lambda s: SEVERITY_ORDER[s], default="info")
    hold = any(SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER["high"] for f in F) or score >= config.HOLD_SCORE
    return Verdict("HOLD" if hold else "PASS", score, sev, vid, vendor["name"] if vendor else None, how, F)
