"""Bot-to-bot loop guard: human reset, allow-list, hop cap, rate cap, own id, update dedupe, ingest filter."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters import telegram_loop_guard as lg
from huf.ai.gateway_adapters import telegram_modes_hooks as mh


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)


def guard(cache=None, **kw):
	return lg.LoopGuard(cache or FakeCache(), clock=lambda: 1000.0, **kw)


def check(g, bot="9", n=None, own="1", allow=("9",), chat=5, thread=None):
	return g.check_bot("gw", chat, thread, bot, own_id=own, allowlist=frozenset(allow), update_id=n)


class TestGuard(unittest.TestCase):
	def test_parse_allowlist(self):
		self.assertEqual(lg.parse_allowlist(" 1, @2;3\n4 ,"), frozenset({"1", "2", "3", "4"}))
		self.assertEqual(lg.parse_allowlist(None), frozenset())

	def test_sender_bot_id(self):
		self.assertEqual(lg.sender_bot_id({"from": {"id": 7, "is_bot": True}}), "7")
		self.assertEqual(lg.sender_bot_id({"from": {"id": 7}, "via_bot": {"id": 8}}), "8")
		self.assertEqual(lg.sender_bot_id({"from": {"id": 7}, "sender_business_bot": {"id": 6}}), "6")
		self.assertIsNone(lg.sender_bot_id({"from": {"id": 7, "is_bot": False}}))

	def test_not_in_allowlist_dropped(self):
		d = check(guard(), allow=())
		self.assertFalse(d.allow)
		self.assertIn("allow-list", d.reason)

	def test_own_id_never(self):
		self.assertFalse(check(guard(), bot="1", own="1", allow=("1",)).allow)

	def test_hop_cap_and_human_reset(self):
		g = guard(rate_cap=100)
		self.assertTrue(all(check(g, n=i).allow for i in range(3)))
		d = check(g, n=3)
		self.assertFalse(d.allow)
		self.assertIn("hop limit", d.reason)
		g.note_human("gw", 5)
		self.assertTrue(check(g, n=4).allow)

	def test_hops_are_per_thread(self):
		g = guard(max_hops=1, rate_cap=100)
		self.assertTrue(check(g, thread=1).allow)
		self.assertFalse(check(g, thread=1).allow)
		self.assertTrue(check(g, thread=2).allow)

	def test_rate_cap(self):
		g = guard(max_hops=99, rate_cap=2)
		self.assertTrue(check(g).allow)
		self.assertTrue(check(g).allow)
		self.assertIn("rate cap", check(g).reason)
		self.assertTrue(check(g, bot="10", allow=("9", "10")).allow)  # per chat+bot

	def test_rate_window_rolls(self):
		now = [1000.0]
		g = lg.LoopGuard(FakeCache(), max_hops=99, rate_cap=1, clock=lambda: now[0])
		self.assertTrue(check(g).allow)
		self.assertFalse(check(g).allow)
		now[0] += 61
		self.assertTrue(check(g).allow)

	def test_update_id_idempotent(self):
		g = guard(max_hops=1)
		self.assertTrue(check(g, n=1).allow)
		self.assertTrue(check(g, n=1).allow)  # replay does not consume another hop
		self.assertFalse(check(g, n=2).allow)
		self.assertFalse(check(g, n=2).allow)

	def test_credentials_overrides(self):
		g = lg.LoopGuard.from_credentials(FakeCache(), {"bot_max_hops": "5", "bot_rate_cap": "x"})
		self.assertEqual((g.max_hops, g.rate_cap), (5, lg.DEFAULT_RATE_CAP))


class TestPrefilter(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		p = mock.patch.object(mh, "_cache", return_value=self.cache)
		p.start()
		self.addCleanup(p.stop)
		self.gw = SimpleNamespace(name="gw", mention_required=0)
		self.adapter = SimpleNamespace(_token="1:abc")

	def parsed(self, msg, uid="u1", room=False):
		return SimpleNamespace(
			kind="message",
			raw={"message": msg},
			chat_id="5",
			update_id=uid,
			is_room=room,
			is_channel=False,
		)

	def run_filter(self, parsed, allow="9"):
		with mock.patch.object(mh, "_credentials", return_value={"bot_allowlist": allow}):
			return mh.prefilter(self.gw, self.adapter, parsed, None)

	def test_bot_dropped_unless_allowed(self):
		msg = {"from": {"id": 9, "is_bot": True}, "chat": {"id": 5}}
		self.assertIn("allow-list", self.run_filter(self.parsed(msg), allow="")["note"])
		self.assertIsNone(self.run_filter(self.parsed(msg, "u2"), allow="9"))

	def test_human_message_passes_and_resets(self):
		bot = {"from": {"id": 9, "is_bot": True}, "chat": {"id": 5}}
		for i in range(3):
			self.assertIsNone(self.run_filter(self.parsed(bot, f"b{i}")))
		self.assertIsNotNone(self.run_filter(self.parsed(bot, "b3")))
		self.assertIsNone(self.run_filter(self.parsed({"from": {"id": 42}, "chat": {"id": 5}}, "h")))
		self.assertIsNone(self.run_filter(self.parsed(bot, "b4")))

	def test_group_not_addressed_dropped_when_mention_required(self):
		self.gw.mention_required = 1
		msg = {
			"from": {"id": 42},
			"chat": {"id": 5, "type": "group"},
			"text": "hi @other",
			"entities": [{"type": "mention", "offset": 3, "length": 6}],
		}
		with mock.patch.object(mh, "_bot_username", return_value="huf_bot"):
			self.assertIn("not addressed", self.run_filter(self.parsed(msg, room=True))["note"])
			msg["text"] = "hi @huf_bot"
			msg["entities"][0]["length"] = 8
			self.assertIsNone(self.run_filter(self.parsed(msg, "u3", room=True)))

	def test_registered_for_message_kinds(self):
		for k in ("message", "edited_message", "channel_post"):
			self.assertIn(k, ing._UPDATE_HANDLERS)


if __name__ == "__main__":
	unittest.main()
