"""Verification cases: state machine, approval controls, tamper-evident audit log.

States:  OPEN -> AWAITING_VENDOR -> READY_FOR_APPROVAL -> APPROVED
                 (any non-terminal) -> REJECTED
"""
import hashlib
import json
from datetime import datetime, timezone

from . import config

TERMINAL = {"APPROVED", "REJECTED"}


class ControlError(Exception):
    """Raised when an action violates an AP control."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- audit log
def _hash(prev: str, ts: str, actor: str, action: str, detail: str, case_id: str) -> str:
    return hashlib.sha256("|".join([prev or "", case_id, ts, actor, action, detail]).encode()).hexdigest()


def add_event(conn, case_id: str, actor: str, action: str, detail: dict | None = None):
    detail_json = json.dumps(detail or {}, sort_keys=True, default=str)
    prev = conn.execute("SELECT hash FROM case_events ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = prev["hash"] if prev else ""
    ts = now()
    h = _hash(prev_hash, ts, actor, action, detail_json, case_id)
    conn.execute("INSERT INTO case_events(case_id,ts,actor,action,detail_json,prev_hash,hash) VALUES (?,?,?,?,?,?,?)",
                 (case_id, ts, actor, action, detail_json, prev_hash, h))


def verify_audit_chain(conn) -> tuple[bool, int | None]:
    """Re-compute the whole chain. Returns (ok, first_bad_event_id)."""
    prev = ""
    for r in conn.execute("SELECT * FROM case_events ORDER BY id"):
        expect = _hash(prev, r["ts"], r["actor"], r["action"], r["detail_json"], r["case_id"])
        if r["prev_hash"] != prev or r["hash"] != expect:
            return False, r["id"]
        prev = r["hash"]
    return True, None


# --------------------------------------------------------------------------- cases
def create_case(conn, message_pk: int, verdict) -> str:
    n = conn.execute("SELECT COUNT(*) c FROM cases").fetchone()["c"] + 1
    cid = f"CASE-{n:04d}"
    top = sorted(verdict.findings, key=lambda f: -f.points)[:3]
    summary = "; ".join(f.message for f in top)
    ts = now()
    conn.execute("INSERT INTO cases(id,message_pk,vendor_id,state,severity,risk_score,summary,created_at,updated_at)"
                 " VALUES (?,?,?,?,?,?,?,?,?)",
                 (cid, message_pk, verdict.vendor_id, "OPEN", verdict.severity, verdict.score, summary, ts, ts))
    add_event(conn, cid, "agent", "case_opened",
              {"score": verdict.score, "severity": verdict.severity,
               "rules": [f.rule for f in verdict.findings]})
    return cid


def get_case(conn, case_id: str):
    c = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not c:
        raise ControlError(f"No such case: {case_id}")
    return c


def _role(user: str) -> str | None:
    return config.USERS.get(user)


def _set_state(conn, case_id, state, **extra):
    cols = ", ".join(f"{k}=?" for k in extra)
    conn.execute(f"UPDATE cases SET state=?, updated_at=?{', ' + cols if cols else ''} WHERE id=?",
                 (state, now(), *extra.values(), case_id))


def start_verification(conn, case_id: str, user: str):
    """Human (or agent on a human's behalf) kicks off the out-of-band callback."""
    c = get_case(conn, case_id)
    if _role(user) is None:
        raise ControlError(f"Unknown user '{user}'.")
    if c["state"] != "OPEN":
        raise ControlError(f"Cannot start verification from state {c['state']}.")
    contact = trusted_contact(conn, c["vendor_id"])
    _set_state(conn, case_id, "AWAITING_VENDOR", verification_started_by=user)
    add_event(conn, case_id, user, "verification_started",
              {"callback_contact": contact["email"] if contact else None,
               "callback_phone": contact["phone"] if contact else None})
    return contact


def record_confirmation(conn, case_id: str, user: str, confirmed: bool, note: str = ""):
    """Log the result of the callback made to a TRUSTED contact from the vendor master."""
    c = get_case(conn, case_id)
    if _role(user) is None:
        raise ControlError(f"Unknown user '{user}'.")
    if c["state"] != "AWAITING_VENDOR":
        raise ControlError(f"Cannot record confirmation from state {c['state']}.")
    add_event(conn, case_id, user, "vendor_confirmation", {"confirmed": confirmed, "note": note})
    if confirmed:
        _set_state(conn, case_id, "READY_FOR_APPROVAL")
    else:
        _set_state(conn, case_id, "REJECTED")
        add_event(conn, case_id, user, "rejected", {"reason": "vendor denied the request"})


def approve(conn, case_id: str, user: str):
    c = get_case(conn, case_id)
    role = _role(user)
    if role not in config.APPROVER_ROLES:
        raise ControlError(f"{user} (role: {role}) is not allowed to approve.")
    if c["state"] != "READY_FOR_APPROVAL":
        raise ControlError(f"Cannot approve from state {c['state']}: vendor verification is required first.")
    if c["verification_started_by"] == user:
        raise ControlError("Segregation of duties: the approver must differ from the person who ran verification.")
    _set_state(conn, case_id, "APPROVED")
    add_event(conn, case_id, user, "approved", {})


def reject(conn, case_id: str, user: str, reason: str = ""):
    c = get_case(conn, case_id)
    if _role(user) is None:
        raise ControlError(f"Unknown user '{user}'.")
    if c["state"] in TERMINAL:
        raise ControlError(f"Case already {c['state']}.")
    _set_state(conn, case_id, "REJECTED")
    add_event(conn, case_id, user, "rejected", {"reason": reason})


# --------------------------------------------------------------------------- verification helpers
def trusted_contact(conn, vendor_id: int):
    """Callback target: ONLY from the vendor master, never from the suspicious message."""
    return conn.execute("SELECT * FROM vendor_contacts WHERE vendor_id=? AND trusted=1 ORDER BY id LIMIT 1",
                        (vendor_id,)).fetchone()


def draft_callback(conn, case_id: str) -> dict:
    c = get_case(conn, case_id)
    v = conn.execute("SELECT * FROM vendors WHERE id=?", (c["vendor_id"],)).fetchone()
    contact = trusted_contact(conn, c["vendor_id"])
    msg = conn.execute("SELECT * FROM messages WHERE id=?", (c["message_pk"],)).fetchone()
    # Phone only: a hacked vendor mailbox would happily confirm its own request by email.
    script = [
        f"Call ONLY: {contact['phone'] if contact else 'n/a'} (from vendor master, not from the email).",
        f"Ask for {contact['name'] if contact else 'the registered contact'}.",
        f"Ask: Did {v['name']} send a request about invoice payment or bank details ({msg['received_at']})?",
        "If a bank change was requested: ask them to read back the last four digits of the NEW account. "
        "Do not read out any details from the email.",
        "Record the result in AP Guard (confirm or deny).",
    ]
    return {"contact": contact["name"] if contact else None, "phone": contact["phone"] if contact else None,
            "call_script": script}
