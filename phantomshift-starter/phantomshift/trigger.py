"""Autonomous inbox trigger: polls a local fixture directory, nobody has to prompt it.

Each *.json file in the inbox is one synthetic invoice. A file is identified by the sha256
of its bytes, so the same content is processed once, even if renamed or re-dropped, and
even across restarts, because the dedupe key lives in the event store (QUEUED events carry
dedupe_key=content hash, unique across the store).

Lifecycle recorded in the event store (see eventstore.py for the full state machine):
    QUEUED -> AGENT_STARTED -> [handler runs] -> ACTION_PROPOSED ...
    handler raises -> RETRY_SCHEDULED (exponential backoff) -> AGENT_STARTED (attempt n+1)
    attempts exhausted, unreadable file, or oversized file -> FAILED (operator-visible, never silent)

The handler is injected: `handler(job) -> dict | None`. It may append its own events to
job.store (ACTION_PROPOSED, POLICY_REPLAY, ...). If it returns while the incident is still
AGENT_STARTED, the trigger records ACTION_PROPOSED with {"recorded_by": "trigger"} so the
incident leaves the work queue; a real pipeline should record that event itself.

Restart safety: incidents left in QUEUED / RETRY_SCHEDULED are resumed. An AGENT_STARTED
incident from a different trigger instance is treated as a crashed attempt (it consumes an
attempt, so a poison file cannot crash-loop forever). Run ONE trigger per store.

Honest limits: this is a polling loop over a local directory standing in for the real inbox.
It is not the OpenClaw always-on agent (hackathon gate H01 stays NOT TESTED until the
OpenClaw agent drives it on the GB10). Write fixture files atomically (write a dot-file or
.tmp, then rename); names starting with "." or ending in ".tmp" are ignored.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .eventstore import (ACTION_PROPOSED, AGENT_STARTED, FAILED, QUEUED, RETRY_SCHEDULED, DuplicateEvent,
                         EventStore, IllegalTransition)

MAX_FILE_BYTES = 1_000_000


@dataclass
class Job:
    incident_id: str
    run_id: str
    attempt: int
    path: Path
    content_hash: str
    data: dict
    store: EventStore = field(repr=False)


class InboxTrigger:
    def __init__(self, inbox: str | Path, store: EventStore, *, max_attempts: int = 3,
                 backoff_base_s: float = 0.5, backoff_max_s: float = 30.0,
                 clock: Callable[[], float] = time.time, notify: Callable[[dict], None] | None = None,
                 meta: dict | None = None) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.inbox = Path(inbox)
        self.store = store
        self.max_attempts = max_attempts
        self.backoff_base_s, self.backoff_max_s = backoff_base_s, backoff_max_s
        self._clock = clock
        self._notify = notify
        self._meta = {k: v for k, v in (meta or {}).items() if k in ("policy_version", "model_id", "inference_server")}
        self.instance_id = uuid.uuid4().hex[:8]
        self.notify_errors: list[str] = []
        self.loop_errors: list[str] = []
        self._hash_cache: dict[tuple[str, int, int], str] = {}

    # ---- intake -------------------------------------------------------------------------------
    def _scan(self) -> list[tuple[Path, str, bytes | None, str]]:
        """(path, content_hash, raw|None, problem) for regular *.json files, sorted by name."""
        out = []
        if not self.inbox.is_dir():
            return out
        for p in sorted(self.inbox.iterdir()):
            if p.name.startswith(".") or p.suffix != ".json" or p.is_symlink() or not p.is_file():
                continue
            try:
                st = p.stat()
                if st.st_size > MAX_FILE_BYTES:
                    out.append((p, hashlib.sha256(f"oversize:{p.name}:{st.st_size}".encode()).hexdigest(), None,
                                f"file larger than {MAX_FILE_BYTES} bytes"))
                    continue
                raw = p.read_bytes()
            except OSError as exc:
                out.append((p, hashlib.sha256(f"unreadable:{p.name}".encode()).hexdigest(), None, f"unreadable: {exc}"))
                continue
            out.append((p, hashlib.sha256(raw).hexdigest(), raw, ""))
        return out

    def _enqueue_new(self, summary: dict) -> None:
        for path, chash, raw, problem in self._scan():
            if self.store.has_dedupe_key(chash):
                summary["duplicates"].append(path.name)
                continue
            incident_id = f"inc-{chash[:12]}"
            try:
                self.store.append(QUEUED, incident_id, dedupe_key=chash, **self._meta, payload={
                    "path": path.name, "content_hash": chash, "trigger_instance": self.instance_id,
                    "evidence": "fixture"})
            except DuplicateEvent:
                summary["duplicates"].append(path.name)
                continue
            summary["queued"].append(incident_id)
            if problem:
                self._fail(incident_id, problem, 0, summary)
                continue
            try:
                data = json.loads((raw or b"").decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("top-level JSON value must be an object")
            except (ValueError, UnicodeDecodeError) as exc:  # deterministic failure: do not retry
                self._fail(incident_id, f"invalid fixture file: {exc}", 0, summary)

    # ---- processing ---------------------------------------------------------------------------
    def _fail(self, incident_id: str, reason: str, attempts: int, summary: dict) -> None:
        ev = self.store.append(FAILED, incident_id, **self._meta, payload={
            "reason": reason[:500], "attempts": attempts, "operator_visible": True,
            "alert": f"PHANTOMSHIFT trigger FAILED for {incident_id}: {reason[:200]}"})
        summary["failed"].append(incident_id)
        if self._notify:
            try:
                self._notify(ev)
            except Exception as exc:  # noqa: BLE001  the alert is already in the store; keep going
                self.notify_errors.append(f"{type(exc).__name__}: {exc}")

    def _queued_info(self, incident_id: str) -> dict:
        hist = self.store.events(incident_id)
        q = hist[0]["payload"]
        return {"path": q["path"], "content_hash": q["content_hash"],
                "attempts": sum(1 for e in hist if e["state"] == AGENT_STARTED), "hist": hist}

    def _backoff(self, attempt: int) -> float:
        return min(self.backoff_base_s * (2 ** (attempt - 1)), self.backoff_max_s)

    def _process(self, incident_id: str, handler: Callable[[Job], Any], summary: dict) -> None:
        state = self.store.current_state(incident_id)
        info = self._queued_info(incident_id)
        attempts = info["attempts"]
        now = self._clock()
        if state == AGENT_STARTED:  # left over from another instance: crashed mid-run
            last = info["hist"][-1]
            if last["payload"].get("trigger_instance") == self.instance_id:
                return
            if attempts >= self.max_attempts:
                self._fail(incident_id, "trigger restarted mid-run and attempts are exhausted", attempts, summary)
                return
            self.store.append(RETRY_SCHEDULED, incident_id, **self._meta, payload={
                "attempt": attempts, "next_attempt_at": now, "error": "trigger restarted mid-run (crashed attempt)"})
            state = RETRY_SCHEDULED
        if state == RETRY_SCHEDULED:
            due = self.store.events(incident_id)[-1]["payload"]["next_attempt_at"]
            if now < due:
                return
        elif state != QUEUED:
            return
        path = self.inbox / info["path"]
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != info["content_hash"]:
                raise ValueError("fixture file changed after it was queued")
            data = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            self._fail(incident_id, f"fixture file unavailable: {exc}", attempts, summary)
            return
        attempt = attempts + 1
        run_id = uuid.uuid4().hex[:12]
        self.store.append(AGENT_STARTED, incident_id, run_id=run_id, **self._meta, payload={
            "attempt": attempt, "trigger_instance": self.instance_id, "started_at": now})
        job = Job(incident_id, run_id, attempt, path, info["content_hash"], data, self.store)
        try:
            result = handler(job)
        except Exception as exc:  # noqa: BLE001  handler failures are retried, then surfaced
            err = f"{type(exc).__name__}: {exc}"[:300]
            if self.store.current_state(incident_id) != AGENT_STARTED:
                try:
                    self._fail(incident_id, f"handler raised after advancing the incident: {err}", attempt, summary)
                except IllegalTransition:  # already in a state that cannot fail (e.g. terminal): surface, don't hide
                    msg = f"{incident_id}: handler raised after reaching a terminal state: {err}"
                    self.loop_errors.append(msg)
                    print(f"[trigger] {msg}", file=sys.stderr)
            elif attempt >= self.max_attempts:
                self._fail(incident_id, f"handler failed {attempt} times; last error: {err}", attempt, summary)
            else:
                delay = self._backoff(attempt)
                self.store.append(RETRY_SCHEDULED, incident_id, run_id=run_id, **self._meta, payload={
                    "attempt": attempt, "next_attempt_at": self._clock() + delay, "error": err, "backoff_s": delay})
                summary["retry_scheduled"].append(incident_id)
            return
        if self.store.current_state(incident_id) == AGENT_STARTED:
            self.store.append(ACTION_PROPOSED, incident_id, run_id=run_id, **self._meta, payload={
                "recorded_by": "trigger", "handler_result": result if _jsonable(result) else repr(result)[:200]})
        summary["processed"].append(incident_id)

    # ---- public API ---------------------------------------------------------------------------
    def run_once(self, handler: Callable[[Job], Any]) -> dict:
        """One poll: enqueue new files, then work every incident that is due. Returns a summary."""
        summary: dict[str, list] = {"queued": [], "processed": [], "retry_scheduled": [], "failed": [], "duplicates": []}
        self._enqueue_new(summary)
        for iid in self.store.incidents_in_states({QUEUED, RETRY_SCHEDULED, AGENT_STARTED}):
            self._process(iid, handler, summary)
        return summary

    def run_forever(self, handler: Callable[[Job], Any], interval: float, stop_event: threading.Event) -> int:
        """Poll until stop_event is set. Errors in a cycle are recorded and the loop continues."""
        cycles = 0
        while not stop_event.is_set():
            try:
                self.run_once(handler)
            except Exception as exc:  # noqa: BLE001  the loop must survive; the error is not hidden
                msg = f"{type(exc).__name__}: {exc}"
                self.loop_errors.append(msg)
                print(f"[trigger] cycle error: {msg}", file=sys.stderr)
            cycles += 1
            stop_event.wait(interval)
        return cycles


def _jsonable(v: Any) -> bool:
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False
