"""Durable event inbox/outbox with deduplication and transactional claim."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

DEFAULT_PATH = "artifacts/autopatch.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at REAL NOT NULL,
  UNIQUE(event_type, fingerprint)
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  payload TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS research_jobs (
  id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  fingerprint TEXT,
  payload TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_run_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  fingerprint TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL,
  record TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deployments (
  id TEXT PRIMARY KEY,
  finding_id TEXT NOT NULL,
  state TEXT NOT NULL,
  record TEXT NOT NULL,
  created_at REAL NOT NULL
);
"""


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_event(event_type: str, payload: dict) -> str:
    return hashlib.sha256(_canonical({"t": event_type, "p": payload}).encode()).hexdigest()[:32]


class AutopatchStore:
    def __init__(self, path: str | Path = DEFAULT_PATH, clock: Callable[[], float] = time.time) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def append_event(self, event_type: str, payload: dict) -> dict:
        fp = fingerprint_event(event_type, payload)
        now = self._clock()
        with self._lock, self._conn() as c:
            try:
                c.execute(
                    "INSERT INTO events(event_type, fingerprint, payload, created_at) VALUES (?,?,?,?)",
                    (event_type, fp, _canonical(payload), now),
                )
                inserted = True
            except sqlite3.IntegrityError:
                inserted = False
        return {"event_type": event_type, "fingerprint": fp, "inserted": inserted, "created_at": now}

    def list_events(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT event_type, fingerprint, payload, created_at FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"event_type": r["event_type"], "fingerprint": r["fingerprint"],
             "payload": json.loads(r["payload"]), "created_at": r["created_at"]}
            for r in rows
        ]

    def enqueue_outbox(self, channel: str, dedupe_key: str, payload: dict) -> dict:
        now = self._clock()
        with self._lock, self._conn() as c:
            try:
                c.execute(
                    "INSERT INTO outbox(channel, dedupe_key, payload, state, next_attempt_at, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (channel, dedupe_key, _canonical(payload), "pending", now, now),
                )
                ok = True
            except sqlite3.IntegrityError:
                ok = False
        return {"channel": channel, "dedupe_key": dedupe_key, "enqueued": ok}

    def claim_outbox(self, limit: int = 5) -> list[dict]:
        now = self._clock()
        claimed = []
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT id, channel, dedupe_key, payload, attempts FROM outbox "
                "WHERE state='pending' AND next_attempt_at<=? ORDER BY id LIMIT ?",
                (now, limit),
            ).fetchall()
            for r in rows:
                c.execute(
                    "UPDATE outbox SET state='claimed', attempts=attempts+1 WHERE id=?",
                    (r["id"],),
                )
                claimed.append({
                    "id": r["id"],
                    "channel": r["channel"],
                    "dedupe_key": r["dedupe_key"],
                    "payload": json.loads(r["payload"]),
                })
        return claimed

    def complete_outbox(self, outbox_id: int, *, ok: bool, backoff_s: float = 60.0) -> None:
        now = self._clock()
        with self._lock, self._conn() as c:
            if ok:
                c.execute("UPDATE outbox SET state='sent' WHERE id=?", (outbox_id,))
            else:
                c.execute(
                    "UPDATE outbox SET state='pending', next_attempt_at=? WHERE id=?",
                    (now + backoff_s, outbox_id),
                )

    def upsert_finding(self, record: dict) -> dict:
        fid = record["finding_id"]
        fp = record["fingerprint"]
        now = self._clock()
        body = _canonical(record)
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO findings(id, fingerprint, state, record, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET "
                "state=excluded.state, record=excluded.record, updated_at=excluded.updated_at",
                (fid, fp, record.get("state", "PROPOSED"), body, now, now),
            )
        return {"finding_id": fid, "fingerprint": fp, "state": record.get("state")}

    def get_finding_by_fingerprint(self, fp: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT record FROM findings WHERE fingerprint=?", (fp,)).fetchone()
        return json.loads(row["record"]) if row else None

    def list_findings(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT record, updated_at FROM findings ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            rec = json.loads(r["record"])
            rec["updated_at"] = r["updated_at"]
            out.append(rec)
        return out

    def schedule_research(self, fingerprint: str, payload: dict, delay_s: float = 0.0) -> str:
        jid = "job-" + uuid.uuid4().hex[:12]
        now = self._clock()
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO research_jobs(id, state, fingerprint, payload, attempts, next_run_at, updated_at) "
                "VALUES (?,?,?,?,0,?,?)",
                (jid, "queued", fingerprint, _canonical(payload), now + delay_s, now),
            )
        return jid

    def claim_research_jobs(self, limit: int = 1) -> list[dict]:
        now = self._clock()
        jobs = []
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT id, fingerprint, payload, attempts FROM research_jobs "
                "WHERE state IN ('queued','retry') AND next_run_at<=? ORDER BY next_run_at LIMIT ?",
                (now, limit),
            ).fetchall()
            for r in rows:
                c.execute(
                    "UPDATE research_jobs SET state='running', attempts=attempts+1, updated_at=? WHERE id=?",
                    (now, r["id"]),
                )
                jobs.append({
                    "job_id": r["id"],
                    "fingerprint": r["fingerprint"],
                    "payload": json.loads(r["payload"]),
                    "attempts": r["attempts"] + 1,
                })
        return jobs

    def finish_research_job(self, job_id: str, *, ok: bool, backoff_s: float = 300.0) -> None:
        now = self._clock()
        state = "done" if ok else "retry"
        next_at = now if ok else now + backoff_s
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE research_jobs SET state=?, next_run_at=?, updated_at=? WHERE id=?",
                (state, next_at, now, job_id),
            )
