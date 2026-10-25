"""Append-only, hash-chained SQLite event store plus the incident state machine.

What this is: a local audit log. Every event is correlated by incident_id (and optionally
run_id, tool_proposal_id, policy_version, model_id, inference_server, message_id,
approval_actor), carries a JSON payload, and is chained to the previous row by sha256
(prev_hash -> hash). SQLite triggers RAISE on UPDATE and DELETE, so the normal code path
cannot rewrite history, and `verify()` recomputes the chain, checks that sequence numbers
are contiguous, that the triggers still exist, and re-validates every state transition.

What this is NOT: tamper-proof. Someone with write access to the file can drop the
triggers and rewrite the whole chain consistently, or truncate the tail. Detection of
that needs the head hash anchored somewhere else (pass `expected_head` to `verify()`).
Evidence label for everything written here is whatever the caller's payload says; this
module does not upgrade a fixture run into a live one.

State machine (per incident_id; the state of an incident is the state of its last event)
-------------------------------------------------------------------------------------
    QUEUED -> AGENT_STARTED -> ACTION_PROPOSED -> DENIED
                                               \\-> POLICY_REPLAY[candidate] -> PENDING_APPROVAL
    DENIED -> POLICY_REPLAY[candidate]            (held action, then candidate repairs are tested)
    PENDING_APPROVAL -> APPROVED | REJECTED | EXPIRED
    APPROVED -> POLICY_REPLAY[verification] -> VERIFIED | FAILED | ROLLED_BACK
    VERIFIED -> ROLLED_BACK ; FAILED -> ROLLED_BACK
    AGENT_STARTED -> RETRY_SCHEDULED -> AGENT_STARTED   (bounded retries, see trigger.py)
    any non-terminal state -> FAILED
    terminal: REJECTED, EXPIRED, ROLLED_BACK (DENIED is terminal unless a replay follows)

Deliberate deviations from the plain list in the task brief, all so the "no approval
before testing" rule is enforceable rather than a convention:
  * POLICY_REPLAY is recorded twice, distinguished by payload["phase"]:
      "candidate"    sandbox replay of the candidate policy BEFORE a human is asked.
      "verification" replay of the approved policy AFTER approval (live-mode re-check).
  * RETRY_SCHEDULED is an extra state so a failed attempt is an explicit, operator-visible
    event instead of a silent self-loop.

Context rules enforced on top of the transition table:
  * PENDING_APPROVAL needs the previous event to be POLICY_REPLAY[candidate] with
    payload.tested is True, and payload.digest (str) that binds the request.
  * APPROVED / REJECTED need approval_actor and payload.digest equal to the pending digest.
  * POLICY_REPLAY[verification] needs payload.verified (bool) and payload.digest equal to
    the approved digest; VERIFIED needs that replay to have verified is True.
  * FAILED needs payload.reason (never a silent failure).
  * RETRY_SCHEDULED needs payload attempt, next_attempt_at, error.
  * QUEUED is only legal as the first event of an incident; QUEUED may carry a dedupe_key,
    which is UNIQUE across the store (idempotent intake).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

DEFAULT_PATH = "artifacts/events.sqlite"
GENESIS = "0" * 64

QUEUED, AGENT_STARTED, RETRY_SCHEDULED = "QUEUED", "AGENT_STARTED", "RETRY_SCHEDULED"
ACTION_PROPOSED, DENIED, PENDING_APPROVAL = "ACTION_PROPOSED", "DENIED", "PENDING_APPROVAL"
APPROVED, REJECTED, EXPIRED = "APPROVED", "REJECTED", "EXPIRED"
POLICY_REPLAY, VERIFIED, FAILED, ROLLED_BACK = "POLICY_REPLAY", "VERIFIED", "FAILED", "ROLLED_BACK"

STATES = frozenset({QUEUED, AGENT_STARTED, RETRY_SCHEDULED, ACTION_PROPOSED, DENIED, PENDING_APPROVAL,
                    APPROVED, REJECTED, EXPIRED, POLICY_REPLAY, VERIFIED, FAILED, ROLLED_BACK})
TERMINAL = frozenset({REJECTED, EXPIRED, ROLLED_BACK})

# Base table. POLICY_REPLAY successors depend on its phase and are resolved in check_transition.
TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({QUEUED}),
    QUEUED: frozenset({AGENT_STARTED, FAILED}),
    AGENT_STARTED: frozenset({ACTION_PROPOSED, RETRY_SCHEDULED, FAILED}),
    RETRY_SCHEDULED: frozenset({AGENT_STARTED, FAILED}),
    ACTION_PROPOSED: frozenset({DENIED, POLICY_REPLAY, FAILED}),
    DENIED: frozenset({POLICY_REPLAY, FAILED}),
    POLICY_REPLAY: frozenset({PENDING_APPROVAL, VERIFIED, FAILED, ROLLED_BACK}),
    PENDING_APPROVAL: frozenset({APPROVED, REJECTED, EXPIRED, FAILED}),
    APPROVED: frozenset({POLICY_REPLAY, FAILED}),
    VERIFIED: frozenset({ROLLED_BACK}),
    FAILED: frozenset({ROLLED_BACK}),
    REJECTED: frozenset(), EXPIRED: frozenset(), ROLLED_BACK: frozenset(),
}
_AFTER_CANDIDATE = frozenset({PENDING_APPROVAL, FAILED})
_AFTER_VERIFICATION = frozenset({VERIFIED, FAILED, ROLLED_BACK})

META_FIELDS = ("run_id", "tool_proposal_id", "policy_version", "model_id", "inference_server",
               "message_id", "approval_actor", "dedupe_key")
_HASHED = ("seq", "ts", "incident_id", *META_FIELDS, "state", "payload", "prev_hash")

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    incident_id TEXT NOT NULL,
    run_id TEXT, tool_proposal_id TEXT, policy_version TEXT, model_id TEXT,
    inference_server TEXT, message_id TEXT, approval_actor TEXT, dedupe_key TEXT,
    state TEXT NOT NULL,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS events_incident ON events(incident_id, seq);
CREATE UNIQUE INDEX IF NOT EXISTS events_dedupe ON events(dedupe_key)
    WHERE dedupe_key IS NOT NULL AND state = '{QUEUED}';
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only: UPDATE forbidden'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only: DELETE forbidden'); END;
"""


class IllegalTransition(ValueError):
    """Raised when an event would break the state machine or a context rule."""


class DuplicateEvent(ValueError):
    """Raised when a QUEUED event reuses an existing dedupe_key (idempotent intake)."""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_row(row: dict) -> str:
    return hashlib.sha256(_canon({k: row[k] for k in _HASHED}).encode()).hexdigest()


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v)


def check_transition(history: list[dict], state: str, approval_actor: str | None = None,
                     payload: dict | None = None, operators: frozenset[str] | set[str] | None = None) -> None:
    """Pure validator. `history` is the incident's prior events (oldest first). Raises IllegalTransition.

    `operators` (optional): when not None, APPROVED / REJECTED must carry an approval_actor in this set.
    None keeps the legacy rule (any non-empty actor string); the store alone cannot know who is an operator."""
    payload = payload or {}
    if state not in STATES:
        raise IllegalTransition(f"unknown state {state!r}")
    last = history[-1] if history else None
    prev = last["state"] if last else None
    if prev == POLICY_REPLAY:
        allowed = _AFTER_CANDIDATE if (last["payload"] or {}).get("phase") == "candidate" else _AFTER_VERIFICATION
    else:
        allowed = TRANSITIONS.get(prev, frozenset())
    if state not in allowed:
        raise IllegalTransition(f"illegal transition {prev} -> {state}; allowed: {sorted(allowed) or 'none (terminal)'}")

    lp = (last["payload"] or {}) if last else {}
    if state == POLICY_REPLAY:
        phase = payload.get("phase")
        if phase == "candidate":
            if prev not in (ACTION_PROPOSED, DENIED):
                raise IllegalTransition("candidate POLICY_REPLAY must follow ACTION_PROPOSED or DENIED")
            if not isinstance(payload.get("tested"), bool):
                raise IllegalTransition("candidate POLICY_REPLAY needs payload.tested (bool)")
        elif phase == "verification":
            if prev != APPROVED:
                raise IllegalTransition("verification POLICY_REPLAY requires prior APPROVED")
            if not isinstance(payload.get("verified"), bool):
                raise IllegalTransition("verification POLICY_REPLAY needs payload.verified (bool)")
            if payload.get("digest") != _last_digest(history, APPROVED):
                raise IllegalTransition("verification replay digest differs from the approved digest")
        else:
            raise IllegalTransition("POLICY_REPLAY needs payload.phase in {'candidate','verification'}")
    elif state == PENDING_APPROVAL:
        if lp.get("phase") != "candidate" or lp.get("tested") is not True:
            raise IllegalTransition("approval requested before the candidate policy was tested")
        if not _is_str(payload.get("digest")):
            raise IllegalTransition("PENDING_APPROVAL needs payload.digest binding the request")
    elif state in (APPROVED, REJECTED):
        if not _is_str(approval_actor):
            raise IllegalTransition(f"{state} needs approval_actor")
        if operators is not None and approval_actor not in operators:
            raise IllegalTransition(f"{state} approval_actor is not in the configured operator allow-list")
        if payload.get("digest") != _last_digest(history, PENDING_APPROVAL):
            raise IllegalTransition(f"{state} digest differs from the pending approval digest")
    elif state == VERIFIED:
        if lp.get("phase") != "verification" or lp.get("verified") is not True:
            raise IllegalTransition("VERIFIED needs a preceding verification replay with verified=True")
    elif state == FAILED:
        if not _is_str(payload.get("reason")):
            raise IllegalTransition("FAILED needs payload.reason (failures are never silent)")
    elif state == RETRY_SCHEDULED:
        if not (type(payload.get("attempt")) is int and payload["attempt"] >= 0 and isinstance(payload.get("next_attempt_at"), (int, float))
                and _is_str(payload.get("error"))):
            raise IllegalTransition("RETRY_SCHEDULED needs payload attempt (non-negative int, not bool), next_attempt_at (number), error (str)")


def _last_digest(history: list[dict], state: str) -> Any:
    for ev in reversed(history):
        if ev["state"] == state:
            return (ev["payload"] or {}).get("digest")
    return None


class EventStore:
    def __init__(self, path: str | Path = DEFAULT_PATH, clock: Callable[[], float] = time.time,
                 operators: set[str] | frozenset[str] | None = None) -> None:
        """`operators`: optional allow-list of approval_actor values accepted for APPROVED/REJECTED
        (also enforced by verify()). Default None keeps the legacy behaviour: any non-empty actor string.
        The store cannot know who is a real operator; whoever constructs it must supply the list, and
        the caller that appends is still trusted to pass the authenticated actor."""
        if operators is not None:
            if isinstance(operators, (str, bytes)) or not all(_is_str(o) for o in operators):
                raise ValueError("operators must be a collection of non-empty strings")
            operators = frozenset(operators)
        self._operators = operators
        self.path = str(path)
        self._clock = clock
        self._lock = threading.RLock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # Create the schema only for a brand-new database. Never re-create triggers on an existing one:
        # a dropped trigger must stay visible to verify() instead of being silently repaired.
        if self._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone() is None:
            self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- writes -------------------------------------------------------------------------------
    def append(self, state: str, incident_id: str, *, payload: dict | None = None, **meta: Any) -> dict:
        """Validate the transition, chain the hash and insert. Returns the stored event."""
        if not _is_str(incident_id):
            raise ValueError("incident_id must be a non-empty string")
        unknown = set(meta) - set(META_FIELDS)
        if unknown:
            raise ValueError(f"unknown event fields: {sorted(unknown)}")
        for k, v in meta.items():
            if v is not None and not isinstance(v, str):
                raise ValueError(f"{k} must be a string or None")
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        payload = payload or {}
        try:
            payload_text = _canon(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"payload is not JSON-serialisable: {exc}") from exc
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                history = self._history(incident_id)
                check_transition(history, state, meta.get("approval_actor"), json.loads(payload_text),
                                 self._operators)
                tail = self._db.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
                row = {"seq": (tail["seq"] + 1) if tail else 1, "ts": round(float(self._clock()), 6),
                       "incident_id": incident_id, **{k: meta.get(k) for k in META_FIELDS},
                       "state": state, "payload": payload_text, "prev_hash": tail["hash"] if tail else GENESIS}
                row["hash"] = _hash_row(row)
                cols = ", ".join(row)
                self._db.execute(f"INSERT INTO events ({cols}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                if "dedupe_key" in str(exc):
                    raise DuplicateEvent(f"dedupe_key already queued: {meta.get('dedupe_key')!r}") from exc
                raise
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return {**row, "payload": json.loads(payload_text)}

    # ---- reads --------------------------------------------------------------------------------
    @staticmethod
    def _to_event(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        return d

    def _history(self, incident_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM events WHERE incident_id = ? ORDER BY seq", (incident_id,)).fetchall()
        return [self._to_event(r) for r in rows]

    def events(self, incident_id: str | None = None) -> list[dict]:
        with self._lock:
            if incident_id is not None:
                return self._history(incident_id)
            return [self._to_event(r) for r in self._db.execute("SELECT * FROM events ORDER BY seq")]

    def current_state(self, incident_id: str) -> str | None:
        with self._lock:
            h = self._history(incident_id)
            return h[-1]["state"] if h else None

    def has_dedupe_key(self, key: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM events WHERE state = ? AND dedupe_key = ?", (QUEUED, key)).fetchone() is not None

    def incidents_in_states(self, states: set[str] | frozenset[str]) -> list[str]:
        """incident_ids whose LAST event is in `states`, oldest first."""
        marks = ", ".join("?" * len(states))
        with self._lock:
            rows = self._db.execute(
                f"SELECT e.incident_id FROM events e WHERE e.seq = (SELECT MAX(seq) FROM events WHERE incident_id = e.incident_id) "
                f"AND e.state IN ({marks}) ORDER BY e.seq", tuple(sorted(states))).fetchall()
        return [r[0] for r in rows]

    def head(self) -> str:
        with self._lock:
            r = self._db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            return r["hash"] if r else GENESIS

    # ---- integrity ----------------------------------------------------------------------------
    def verify(self, expected_head: str | None = None) -> dict:
        """Recompute the whole chain. Returns {ok, events, head, errors}. Never raises on tamper."""
        errors: list[str] = []
        with self._lock:
            names = {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            for t in ("events_no_update", "events_no_delete"):
                if t not in names:
                    errors.append(f"append-only trigger {t} is missing")
            prev, expect_seq, n = GENESIS, 1, 0
            histories: dict[str, list[dict]] = {}
            for r in self._db.execute("SELECT * FROM events ORDER BY seq"):
                n += 1
                raw = dict(r)
                if raw["seq"] != expect_seq:
                    errors.append(f"seq gap: expected {expect_seq}, found {raw['seq']} (row deleted or inserted)")
                    expect_seq = raw["seq"]
                expect_seq += 1
                if raw["prev_hash"] != prev:
                    errors.append(f"seq {raw['seq']}: prev_hash does not match previous row")
                if _hash_row(raw) != raw["hash"]:
                    errors.append(f"seq {raw['seq']}: hash mismatch (row content was altered)")
                prev = raw["hash"]
                try:
                    ev = self._to_event(r)
                    h = histories.setdefault(ev["incident_id"], [])
                    check_transition(h, ev["state"], ev["approval_actor"], ev["payload"], self._operators)
                    h.append(ev)
                except (IllegalTransition, ValueError) as exc:
                    errors.append(f"seq {raw['seq']}: invalid state transition in stored data: {exc}")
            if expected_head is not None and expected_head != prev:
                errors.append("head hash differs from the externally anchored head (truncation or rewrite)")
            return {"ok": not errors, "events": n, "head": prev, "errors": errors}
