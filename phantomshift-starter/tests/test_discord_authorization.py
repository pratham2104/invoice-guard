import unittest

from phantomshift.approval import config_digest
from phantomshift.discord_auth import ApprovalBinding, authorize_discord_event
from phantomshift.policies import CANDIDATES

GUILD, CHAN, OTHER_CHAN = "111111111111111111", "222222222222222222", "333333333333333333"
OP, OP2, STRANGER = "444444444444444444", "555555555555555555", "666666666666666666"
POLICY = {"guild_id": GUILD, "channel_ids": [CHAN], "user_ids": [OP, OP2]}
CFG = next(p for p in CANDIDATES if p["name"] == "context_bound")


def ev(**kw):
    base = {"id": "900000000000000001", "guild_id": GUILD, "channel_id": CHAN, "author": {"id": OP},
            "content": "hello", "timestamp": 1000.0}
    base.update(kw)
    return base


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class AuthorizeEventTests(unittest.TestCase):
    def reject(self, event, policy=POLICY, code=None):
        ok, why = authorize_discord_event(event, policy)
        self.assertFalse(ok, why)
        if code:
            self.assertTrue(why.startswith(code), why)

    def test_operator_in_allowed_guild_and_channel_ok(self):
        self.assertEqual(authorize_discord_event(ev(), POLICY), (True, "ok"))
        self.assertTrue(authorize_discord_event(ev(author={"id": OP2, "bot": False}), POLICY)[0])

    def test_wrong_user_rejected(self):
        self.reject(ev(author={"id": STRANGER}), code="unauthorized_author")

    def test_wrong_guild_rejected(self):
        self.reject(ev(guild_id="999999999999999999"), code="wrong_guild")

    def test_wrong_channel_rejected(self):
        self.reject(ev(channel_id=OTHER_CHAN), code="wrong_channel")

    def test_bot_author_rejected_even_if_allow_listed(self):
        self.reject(ev(author={"id": OP, "bot": True}), code="bot_author")
        self.reject(ev(author={"id": OP, "bot": "false"}), code="bot_author")  # malformed flag
        self.reject(ev(webhook_id="123456789"), code="bot_author")
        self.reject(ev(author={"id": OP, "system": True}), code="bot_author")

    def test_dm_rejected_unless_explicitly_allowed(self):
        dm = ev()
        del dm["guild_id"]
        del dm["channel_id"]
        self.reject(dm, code="dm_not_allowed")
        self.reject(dm, {**POLICY, "allow_dm": False}, code="dm_not_allowed")
        self.assertTrue(authorize_discord_event(dm, {**POLICY, "allow_dm": True})[0])
        dm_stranger = {**dm, "author": {"id": STRANGER}}
        self.reject(dm_stranger, {**POLICY, "allow_dm": True}, code="unauthorized_author")

    def test_ids_are_exact_string_matches(self):
        self.reject(ev(author={"id": int(OP)}), code="missing_field")
        self.reject(ev(author={"id": " " + OP}), code="missing_field")
        self.reject(ev(author={"id": OP + "0"}), code="unauthorized_author")
        self.reject(ev(guild_id=int(GUILD)), code="missing_field")
        self.reject(ev(channel_id=int(CHAN)), code="missing_field")
        self.reject(ev(author={"id": OP[:-1]}), code="unauthorized_author")

    def test_missing_fields_fail_closed(self):
        for field in ("author", "channel_id"):
            e = ev()
            del e[field]
            self.reject(e, code="missing_field")
        self.reject(ev(author={}), code="missing_field")
        self.reject(ev(author="someone"), code="missing_field")
        self.reject(ev(channel_id=""), code="missing_field")
        self.reject({}, code="missing_field")
        self.reject(None, code="bad_event")
        self.reject("not an event", code="bad_event")

    def test_reaction_style_event_uses_user_id(self):
        r = {"guild_id": GUILD, "channel_id": CHAN, "user_id": OP}
        self.assertTrue(authorize_discord_event(r, POLICY)[0])
        self.reject({**r, "user_id": STRANGER}, code="unauthorized_author")
        self.reject({**r, "author": {"id": OP}, "user_id": STRANGER}, code="author_mismatch")

    def test_bad_policy_fails_closed(self):
        for pol in (None, {}, {"guild_id": GUILD}, {**POLICY, "channel_ids": []}, {**POLICY, "user_ids": OP},
                    {**POLICY, "channel_ids": CHAN}, {**POLICY, "user_ids": [int(OP)]}, {**POLICY, "guild_id": 5},
                    {**POLICY, "allow_dm": "yes"}):
            self.reject(ev(), pol, code="bad_policy")


class ApprovalMessageTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.b = ApprovalBinding(POLICY, ttl_s=300, clock=self.clock, approval_channel_id=CHAN)
        self.req = self.b.request(CFG, replay_tested=True)
        self.n, self.d = self.req["nonce"], self.req["digest"]
        self._mid = 900000000000000100

    def msg(self, text=None, **kw):
        self._mid += 1
        text = text if text is not None else f"approve {self.n} {self.d}"
        return ev(id=str(self._mid), content=text, timestamp=self.clock.t + 1, **kw)

    def test_request_refused_before_replay_testing(self):
        with self.assertRaises(ValueError):
            self.b.request(CFG, replay_tested=False)
        with self.assertRaises(ValueError):
            self.b.request(CFG, replay_tested=1)  # truthy but not True
        self.assertEqual(self.req["reply_with"], f"approve {self.n} {self.d}")

    def test_valid_approval_then_activate_exact_config(self):
        r = self.b.verify_approval_message(self.msg())
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["state"], r["actor"], r["digest"]), ("approved", OP, self.d))
        self.assertEqual(self.d, config_digest(CFG))
        act = self.b.activate(self.n, CFG)
        self.assertTrue(act["ok"])
        tampered = {**CFG, "name": "evil"}
        self.assertFalse(self.b.activate(self.n, tampered)["ok"])

    def test_activate_before_approval_fails(self):
        self.assertFalse(self.b.activate(self.n, CFG)["ok"])

    def test_reject_verb_records_rejection(self):
        r = self.b.verify_approval_message(self.msg(f"reject {self.n} {self.d}"))
        self.assertTrue(r["ok"])
        self.assertEqual(r["state"], "rejected")
        self.assertFalse(self.b.activate(self.n, CFG)["ok"])

    def test_verb_assertion(self):
        r = self.b.verify_approval_message(self.msg(f"reject {self.n} {self.d}"), approve=True)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith("verb_mismatch"))

    def test_wrong_sender_guild_channel_bot_dm_rejected(self):
        for kw, code in (({"author": {"id": STRANGER}}, "unauthorized_author"),
                         ({"guild_id": "999999999999999999"}, "wrong_guild"),
                         ({"channel_id": OTHER_CHAN}, "wrong_channel"),
                         ({"author": {"id": OP, "bot": True}}, "bot_author")):
            r = self.b.verify_approval_message(self.msg(**kw))
            self.assertFalse(r["ok"], kw)
            self.assertTrue(r["reason"].startswith(code), r)
        dm = self.msg()
        del dm["guild_id"], dm["channel_id"]
        self.assertTrue(self.b.verify_approval_message(dm)["reason"].startswith("dm_not_allowed"))
        # none of those burned the nonce
        self.assertTrue(self.b.verify_approval_message(self.msg())["ok"])

    def test_allowed_channel_but_not_the_approvals_channel(self):
        pol = {**POLICY, "channel_ids": [CHAN, OTHER_CHAN]}
        b = ApprovalBinding(pol, clock=self.clock, approval_channel_id=CHAN)
        req = b.request(CFG, replay_tested=True)
        r = b.verify_approval_message(ev(id="900000000000000500", channel_id=OTHER_CHAN, timestamp=1001.0,
                                         content=f"approve {req['nonce']} {req['digest']}"))
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith("wrong_channel"))

    def test_mismatched_digest_rejected_and_does_not_burn_nonce(self):
        wrong = "0" * 64
        r = self.b.verify_approval_message(self.msg(f"approve {self.n} {wrong}"))
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith("digest_mismatch"))
        short = self.b.verify_approval_message(self.msg(f"approve {self.n} {self.d[:12]}"))  # prefix is not enough
        self.assertFalse(short["ok"])
        self.assertTrue(self.b.verify_approval_message(self.msg())["ok"])

    def test_unknown_nonce_and_garbage_text_rejected(self):
        self.assertTrue(self.b.verify_approval_message(self.msg(f"approve {'0'*16} {self.d}"))["reason"].startswith("unknown_nonce"))
        for text in ("yes", "approve", f"approve {self.n}", f"please approve {self.n} {self.d}",
                     f"approve {self.n} {self.d} extra", None, 5):
            e = self.msg()
            e["content"] = text
            self.assertFalse(self.b.verify_approval_message(e)["ok"], text)

    def test_replayed_nonce_rejected(self):
        self.assertTrue(self.b.verify_approval_message(self.msg())["ok"])
        r = self.b.verify_approval_message(self.msg())  # new message id, same nonce
        self.assertFalse(r["ok"])
        self.assertIn("already used", r["reason"])
        r = self.b.verify_approval_message(self.msg(f"reject {self.n} {self.d}"))  # cannot flip a decision either
        self.assertFalse(r["ok"])

    def test_replayed_message_id_rejected(self):
        e = self.msg()
        self.assertTrue(self.b.verify_approval_message(e)["ok"])
        r = self.b.verify_approval_message(e)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith("replayed_message"))

    def test_expired_nonce_rejected(self):
        self.clock.t += 301
        r = self.b.verify_approval_message(self.msg())
        self.assertFalse(r["ok"])
        self.assertIn("expired", r["reason"])
        self.assertFalse(self.b.activate(self.n, CFG)["ok"])

    def test_stale_future_and_missing_timestamp_rejected(self):
        old = self.msg()
        old["timestamp"] = 900.0                       # sent before the request was issued
        self.assertTrue(self.b.verify_approval_message(old)["reason"].startswith("stale_message"))
        fut = self.msg()
        fut["timestamp"] = self.clock.t + 3600
        self.assertTrue(self.b.verify_approval_message(fut)["reason"].startswith("future_message"))
        none = self.msg()
        del none["timestamp"]
        self.assertTrue(self.b.verify_approval_message(none)["reason"].startswith("missing_field"))
        iso = self.msg()
        iso["timestamp"] = "1970-01-01T00:16:41+00:00"  # 1001.0 epoch
        self.assertTrue(self.b.verify_approval_message(iso)["ok"])

    def test_missing_message_id_rejected(self):
        e = self.msg()
        del e["id"]
        self.assertFalse(self.b.verify_approval_message(e)["ok"])

    def test_digest_is_case_normalised_but_otherwise_exact(self):
        r = self.b.verify_approval_message(self.msg(f"APPROVE {self.n.upper()} {self.d.upper()}"))
        self.assertTrue(r["ok"], r)

    def test_each_request_has_its_own_nonce_and_digest(self):
        other_cfg = next(p for p in CANDIDATES if p["name"] != "context_bound")
        req2 = self.b.request(other_cfg, replay_tested=True)
        self.assertNotEqual(req2["nonce"], self.n)
        r = self.b.verify_approval_message(self.msg(f"approve {req2['nonce']} {self.d}"))  # digest of the other request
        self.assertTrue(r["reason"].startswith("digest_mismatch"))

    def test_binding_construction_validates_policy_and_channel(self):
        with self.assertRaises(ValueError):
            ApprovalBinding({})
        with self.assertRaises(ValueError):
            ApprovalBinding(POLICY, approval_channel_id=OTHER_CHAN)


if __name__ == "__main__":
    unittest.main()
