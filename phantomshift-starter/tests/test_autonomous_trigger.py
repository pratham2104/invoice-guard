import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from phantomshift.eventstore import (ACTION_PROPOSED, AGENT_STARTED, APPROVED, DENIED, FAILED, PENDING_APPROVAL,
                                     POLICY_REPLAY, QUEUED, REJECTED, RETRY_SCHEDULED, ROLLED_BACK, VERIFIED,
                                     DuplicateEvent, EventStore, IllegalTransition)
from phantomshift.trigger import InboxTrigger


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


D = "a" * 64


def walk_to_pending(store, iid="i1"):
    store.append(QUEUED, iid)
    store.append(AGENT_STARTED, iid, run_id="r1")
    store.append(ACTION_PROPOSED, iid, tool_proposal_id="tp1")
    store.append(POLICY_REPLAY, iid, policy_version="context_bound", payload={"phase": "candidate", "tested": True})
    store.append(PENDING_APPROVAL, iid, message_id="m1", payload={"digest": D})


class EventStoreStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore(":memory:")
        self.addCleanup(self.store.close)

    def test_happy_path_verifies_and_records_correlation_fields(self):
        walk_to_pending(self.store)
        self.store.append(APPROVED, "i1", approval_actor="op-1", message_id="m2", payload={"digest": D})
        self.store.append(POLICY_REPLAY, "i1", model_id="m", inference_server="127.0.0.1:8000",
                          payload={"phase": "verification", "verified": True, "digest": D})
        self.store.append(VERIFIED, "i1")
        self.assertEqual(self.store.current_state("i1"), VERIFIED)
        evs = self.store.events("i1")
        self.assertEqual(evs[5]["approval_actor"], "op-1")
        self.assertEqual(evs[6]["inference_server"], "127.0.0.1:8000")
        self.assertTrue(all(e["ts"] > 0 for e in evs))
        r = self.store.verify()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["events"], 8)
        self.assertEqual(r["head"], self.store.head())

    def assert_illegal(self, *args, **kw):
        n = len(self.store.events())
        with self.assertRaises(IllegalTransition):
            self.store.append(*args, **kw)
        self.assertEqual(len(self.store.events()), n, "illegal event must not be stored")

    def test_must_start_with_queued_and_queued_only_once(self):
        self.assert_illegal(AGENT_STARTED, "i1")
        self.store.append(QUEUED, "i1")
        self.assert_illegal(QUEUED, "i1")
        self.assert_illegal(ACTION_PROPOSED, "i1")  # skipped AGENT_STARTED

    def test_approval_before_testing_is_illegal(self):
        for s in (QUEUED, AGENT_STARTED, ACTION_PROPOSED):
            self.store.append(s, "i1")
        self.assert_illegal(APPROVED, "i1", approval_actor="op-1", payload={"digest": D})
        self.assert_illegal(PENDING_APPROVAL, "i1", payload={"digest": D})  # untested candidate

    def test_pending_requires_tested_true_and_digest(self):
        for s in (QUEUED, AGENT_STARTED, ACTION_PROPOSED):
            self.store.append(s, "i1")
        self.store.append(POLICY_REPLAY, "i1", payload={"phase": "candidate", "tested": False})
        self.assert_illegal(PENDING_APPROVAL, "i1", payload={"digest": D})
        self.store.append(FAILED, "i1", payload={"reason": "candidate failed replay"})
        self.store.append(QUEUED, "i2")
        for s in (AGENT_STARTED, ACTION_PROPOSED):
            self.store.append(s, "i2")
        self.store.append(POLICY_REPLAY, "i2", payload={"phase": "candidate", "tested": True})
        self.assert_illegal(PENDING_APPROVAL, "i2", payload={})  # no digest binding

    def test_approval_needs_actor_and_matching_digest(self):
        walk_to_pending(self.store)
        self.assert_illegal(APPROVED, "i1", payload={"digest": D})
        self.assert_illegal(APPROVED, "i1", approval_actor="op-1", payload={"digest": "b" * 64})
        self.assert_illegal(REJECTED, "i1", approval_actor="op-1", payload={})

    def test_verification_replay_must_follow_approval_with_same_digest(self):
        walk_to_pending(self.store)
        self.assert_illegal(POLICY_REPLAY, "i1", payload={"phase": "verification", "verified": True, "digest": D})
        self.store.append(APPROVED, "i1", approval_actor="op-1", payload={"digest": D})
        self.assert_illegal(POLICY_REPLAY, "i1", payload={"phase": "verification", "verified": True, "digest": "c" * 64})
        self.store.append(POLICY_REPLAY, "i1", payload={"phase": "verification", "verified": False, "digest": D})
        self.assert_illegal(VERIFIED, "i1")  # replay said verified=False
        self.store.append(ROLLED_BACK, "i1")

    def test_terminal_states_and_failed_reason(self):
        walk_to_pending(self.store)
        self.store.append(REJECTED, "i1", approval_actor="op-1", payload={"digest": D})
        self.assert_illegal(APPROVED, "i1", approval_actor="op-1", payload={"digest": D})
        self.assert_illegal(FAILED, "i1", payload={"reason": "x"})
        self.store.append(QUEUED, "i2")
        self.assert_illegal(FAILED, "i2")  # failures are never silent: reason required
        self.assert_illegal(FAILED, "i2", payload={"reason": ""})
        self.store.append(FAILED, "i2", payload={"reason": "boom"})
        self.store.append(ROLLED_BACK, "i2")

    def test_denied_then_candidate_replay_and_unknown_state(self):
        for s in (QUEUED, AGENT_STARTED, ACTION_PROPOSED, DENIED):
            self.store.append(s, "i1")
        self.assert_illegal(PENDING_APPROVAL, "i1", payload={"digest": D})
        self.store.append(POLICY_REPLAY, "i1", payload={"phase": "candidate", "tested": True})
        self.assert_illegal("BOGUS", "i1")
        self.assert_illegal(POLICY_REPLAY, "i1", payload={"phase": "nope"})

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            self.store.append(QUEUED, "")
        with self.assertRaises(ValueError):
            self.store.append(QUEUED, "i1", payload={"x": object()})
        with self.assertRaises(ValueError):
            self.store.append(QUEUED, "i1", bogus_field="x")
        with self.assertRaises(ValueError):
            self.store.append(QUEUED, "i1", run_id=5)

    def test_dedupe_key_unique_for_queued(self):
        self.store.append(QUEUED, "i1", dedupe_key="k")
        self.assertTrue(self.store.has_dedupe_key("k"))
        with self.assertRaises(DuplicateEvent):
            self.store.append(QUEUED, "i2", dedupe_key="k")
        self.assertIsNone(self.store.current_state("i2"))


class EventStoreIntegrityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(Path(self._tmp.name) / "sub" / "events.sqlite")
        self.store = EventStore(self.path)
        walk_to_pending(self.store)
        self.head = self.store.head()
        self.store.close()

    def raw(self):
        c = sqlite3.connect(self.path)
        self.addCleanup(c.close)
        return c

    def test_update_and_delete_raise(self):
        c = self.raw()
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("UPDATE events SET payload = '{}' WHERE seq = 1")
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("DELETE FROM events WHERE seq = 1")
        with EventStore(self.path) as s:
            self.assertTrue(s.verify()["ok"])
            self.assertEqual(len(s.events()), 5)

    def test_persists_across_reopen(self):
        with EventStore(self.path) as s:
            self.assertEqual(s.current_state("i1"), PENDING_APPROVAL)
            self.assertEqual(s.head(), self.head)

    def test_payload_tamper_detected(self):
        c = self.raw()
        c.execute("DROP TRIGGER events_no_update")
        c.execute("UPDATE events SET payload = '{\"digest\":\"evil\"}' WHERE seq = 5")
        c.commit()
        with EventStore(self.path) as s:
            r = s.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("hash mismatch" in e for e in r["errors"]))
        self.assertTrue(any("trigger" in e for e in r["errors"]))

    def test_deleted_middle_row_detected(self):
        c = self.raw()
        c.execute("DROP TRIGGER events_no_delete")
        c.execute("DELETE FROM events WHERE seq = 3")
        c.commit()
        with EventStore(self.path) as s:
            r = s.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("seq gap" in e or "prev_hash" in e for e in r["errors"]))

    def test_tail_truncation_detected_with_anchored_head(self):
        c = self.raw()
        c.execute("DROP TRIGGER events_no_delete")
        c.execute("DELETE FROM events WHERE seq = 5")
        c.execute("CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'x'); END")
        c.commit()
        with EventStore(self.path) as s:
            self.assertFalse(s.verify(expected_head=self.head)["ok"])

    def test_recomputed_hash_still_caught_by_chain(self):
        # attacker edits a middle row AND fixes that row's hash: the next row's prev_hash exposes it
        import hashlib
        from phantomshift.eventstore import _HASHED, _canon
        c = self.raw()
        c.row_factory = sqlite3.Row
        c.execute("DROP TRIGGER events_no_update")
        row = dict(c.execute("SELECT * FROM events WHERE seq = 2").fetchone())
        row["payload"] = '{"forged":true}'
        row["hash"] = hashlib.sha256(_canon({k: row[k] for k in _HASHED}).encode()).hexdigest()
        c.execute("UPDATE events SET payload=?, hash=? WHERE seq=2", (row["payload"], row["hash"]))
        c.commit()
        with EventStore(self.path) as s:
            r = s.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("prev_hash" in e for e in r["errors"]))


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.inbox = root / "inbox"
        self.inbox.mkdir()
        self.db = str(root / "events.sqlite")
        self.clock = Clock()
        self.store = EventStore(self.db, clock=self.clock)
        self.addCleanup(self.store.close)
        self.calls = []

    def drop(self, name, obj):
        (self.inbox / name).write_text(json.dumps(obj))

    def trigger(self, store=None, **kw):
        return InboxTrigger(self.inbox, store or self.store, clock=self.clock, backoff_base_s=1.0, **kw)

    def ok_handler(self, job):
        self.calls.append(job)
        return {"seen": job.data.get("invoice_id")}

    def test_processes_new_file_without_prompting_and_records_events(self):
        t = self.trigger()
        self.assertEqual(t.run_once(self.ok_handler)["processed"], [])
        self.drop("inv-1.json", {"invoice_id": "INV-1", "amount": 10})  # appears later; nobody calls anything
        s = t.run_once(self.ok_handler)
        self.assertEqual(len(s["processed"]), 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].data["invoice_id"], "INV-1")
        iid = s["processed"][0]
        states = [e["state"] for e in self.store.events(iid)]
        self.assertEqual(states, [QUEUED, AGENT_STARTED, ACTION_PROPOSED])
        self.assertTrue(all(e["ts"] == 1000.0 for e in self.store.events(iid)))
        self.assertEqual(self.store.events(iid)[1]["run_id"], self.calls[0].run_id)
        self.assertTrue(self.store.verify()["ok"])

    def test_same_content_processed_once_even_renamed(self):
        t = self.trigger()
        self.drop("a.json", {"invoice_id": "INV-1"})
        self.drop("b.json", {"invoice_id": "INV-1"})
        s = t.run_once(self.ok_handler)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(s["duplicates"]), 1)
        t.run_once(self.ok_handler)
        self.drop("c.json", {"invoice_id": "INV-1"})
        t.run_once(self.ok_handler)
        self.assertEqual(len(self.calls), 1)
        self.drop("d.json", {"invoice_id": "INV-2"})
        t.run_once(self.ok_handler)
        self.assertEqual(len(self.calls), 2)

    def test_restart_idempotency_via_event_store(self):
        self.drop("a.json", {"invoice_id": "INV-1"})
        self.trigger().run_once(self.ok_handler)
        self.store.close()
        store2 = EventStore(self.db, clock=self.clock)
        self.addCleanup(store2.close)
        s = self.trigger(store2).run_once(self.ok_handler)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(s["queued"], [])
        self.assertEqual(s["duplicates"], ["a.json"])

    def test_crash_mid_run_is_resumed_after_restart_and_counts_an_attempt(self):
        class Crash(BaseException):
            pass

        def crashing(job):
            raise Crash()

        self.drop("a.json", {"invoice_id": "INV-1"})
        with self.assertRaises(Crash):
            self.trigger().run_once(crashing)
        iid = self.store.incidents_in_states({AGENT_STARTED})[0]
        t2 = self.trigger()  # new instance id: treats the dangling AGENT_STARTED as a crashed attempt
        s = t2.run_once(self.ok_handler)
        self.assertEqual(s["processed"], [iid])
        self.assertEqual(self.calls[0].attempt, 2)
        states = [e["state"] for e in self.store.events(iid)]
        self.assertEqual(states, [QUEUED, AGENT_STARTED, RETRY_SCHEDULED, AGENT_STARTED, ACTION_PROPOSED])

    def test_retry_with_backoff_then_failed_operator_visible(self):
        alerts = []
        t = self.trigger(max_attempts=3, notify=alerts.append)
        self.drop("a.json", {"invoice_id": "INV-1"})

        def boom(job):
            self.calls.append(job.attempt)
            raise RuntimeError("model server unreachable")

        s = t.run_once(boom)
        self.assertEqual(len(s["retry_scheduled"]), 1)
        t.run_once(boom)  # backoff not elapsed: no new attempt
        self.assertEqual(self.calls, [1])
        self.clock.t += 1.0   # backoff_base 1s
        s = t.run_once(boom)
        self.assertEqual(self.calls, [1, 2])
        self.assertEqual(len(s["retry_scheduled"]), 1)
        self.clock.t += 1.5   # second backoff is 2s: not yet
        t.run_once(boom)
        self.assertEqual(self.calls, [1, 2])
        self.clock.t += 0.5
        s = t.run_once(boom)
        self.assertEqual(self.calls, [1, 2, 3])
        self.assertEqual(len(s["failed"]), 1)
        iid = s["failed"][0]
        self.assertEqual(self.store.current_state(iid), FAILED)
        last = self.store.events(iid)[-1]
        self.assertTrue(last["payload"]["operator_visible"])
        self.assertEqual(last["payload"]["attempts"], 3)
        self.assertIn("unreachable", last["payload"]["reason"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["state"], FAILED)
        # no further attempts and no resurrection by re-dropping the same content
        self.clock.t += 1000
        self.drop("again.json", {"invoice_id": "INV-1"})
        t.run_once(boom)
        self.assertEqual(self.calls, [1, 2, 3])
        self.assertTrue(self.store.verify()["ok"])

    def test_retry_then_success(self):
        t = self.trigger(max_attempts=3)
        self.drop("a.json", {"invoice_id": "INV-1"})
        outcomes = [RuntimeError("flaky"), None]

        def flaky(job):
            o = outcomes.pop(0)
            if o:
                raise o
            return {"ok": True}

        t.run_once(flaky)
        self.clock.t += 1.0
        s = t.run_once(flaky)
        self.assertEqual(len(s["processed"]), 1)
        self.assertEqual(self.store.current_state(s["processed"][0]), ACTION_PROPOSED)

    def test_invalid_json_fails_immediately_and_visibly(self):
        (self.inbox / "bad.json").write_text("{not json")
        self.drop("list.json", [1, 2])
        s = self.trigger().run_once(self.ok_handler)
        self.assertEqual(len(s["failed"]), 2)
        self.assertEqual(self.calls, [])
        ev = self.store.events(s["failed"][0])[-1]
        self.assertTrue(ev["payload"]["operator_visible"])

    def test_notify_errors_do_not_hide_failure(self):
        def bad_notify(ev):
            raise OSError("discord down")

        t = self.trigger(notify=bad_notify)
        (self.inbox / "bad.json").write_text("nope")
        s = t.run_once(self.ok_handler)
        self.assertEqual(self.store.current_state(s["failed"][0]), FAILED)
        self.assertEqual(len(t.notify_errors), 1)

    def test_ignores_dotfiles_tmp_nonjson_and_symlinks(self):
        (self.inbox / ".partial.json").write_text("{}")
        (self.inbox / "x.tmp").write_text("{}")
        (self.inbox / "notes.txt").write_text("{}")
        outside = Path(self._tmp.name) / "outside.json"
        outside.write_text('{"invoice_id": "secret"}')
        (self.inbox / "link.json").symlink_to(outside)
        s = self.trigger().run_once(self.ok_handler)
        self.assertEqual(s["queued"], [])
        self.assertEqual(self.calls, [])

    def test_handler_advancing_incident_is_respected(self):
        def pipeline(job):
            job.store.append(ACTION_PROPOSED, job.incident_id, run_id=job.run_id, payload={"by": "pipeline"})
            job.store.append(DENIED, job.incident_id, run_id=job.run_id)

        self.drop("a.json", {"invoice_id": "INV-1"})
        s = self.trigger().run_once(pipeline)
        self.assertEqual(self.store.current_state(s["processed"][0]), DENIED)
        self.trigger().run_once(pipeline)  # not re-run
        self.assertEqual(len(self.store.events()), 4)

    def test_run_forever_stops_and_survives_cycle_errors(self):
        stop = threading.Event()
        t = self.trigger()
        real = t.run_once
        state = {"n": 0}

        def flaky_run_once(handler):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("transient scan error")
            return real(handler)

        t.run_once = flaky_run_once
        self.drop("a.json", {"invoice_id": "INV-1"})

        def handler(job):
            self.calls.append(job)
            stop.set()

        cycles = t.run_forever(handler, 0.01, stop)
        self.assertGreaterEqual(cycles, 2)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(t.loop_errors), 1)

    def test_max_attempts_validated(self):
        with self.assertRaises(ValueError):
            self.trigger(max_attempts=0)


if __name__ == "__main__":
    unittest.main()
