# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram agent send scope and caps (fake DB/cache; no network)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai import telegram_send_scope as scope


class FakeCache:
	def __init__(self):
		self.store = {}

	def get_value(self, key):
		return self.store.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.store[key] = value


def conf(**over):
	base = {"scope": "Current contact", "allowlist": [], "per_run": 20, "per_day": 200}
	base.update(over)
	return base


class TestChatNormalisation(unittest.TestCase):
	def test_normalize(self):
		self.assertEqual(scope.normalize_chat(" 0123 "), "123")
		self.assertEqual(scope.normalize_chat("-1001234567890"), "-1001234567890")
		self.assertEqual(scope.normalize_chat("@MyChannel"), "@mychannel")
		self.assertEqual(scope.normalize_chat("not a chat"), "")
		self.assertEqual(scope.normalize_chat(None), "")

	def test_allowlist_parse(self):
		self.assertEqual(scope.parse_allowlist("1, @Chan;2\n1 junk!"), ["1", "@chan", "2"])
		self.assertEqual(scope.invalid_allowlist_entries("1 junk!"), ["junk!"])


class TestRecipientScope(unittest.TestCase):
	def check(self, recipient, current="111", **over):
		with (
			patch.object(scope, "settings", return_value=conf(**over)),
			patch.object(scope, "current_chat", return_value=current),
		):
			return scope.check_recipient("GW", "RUN", recipient)

	def test_current_chat_allowed(self):
		self.assertIsNone(self.check("111"))
		self.assertIsNone(self.check(111))

	def test_other_chat_denied_by_default(self):
		out = json.loads(self.check("222"))
		self.assertEqual(out["error"], "recipient_not_permitted")
		self.assertFalse(out["success"])

	def test_username_never_matches_numeric_current(self):
		self.assertIsNotNone(self.check("@someone"))

	def test_no_current_chat_denies_everything_but_any(self):
		self.assertIsNotNone(self.check("111", current=""))

	def test_allow_list(self):
		self.assertIsNone(self.check("222", scope="Allow-list", allowlist=["222"]))
		self.assertIsNotNone(self.check("333", scope="Allow-list", allowlist=["222"]))

	def test_approved_contacts(self):
		with patch.object(scope, "_is_approved", return_value=True):
			self.assertIsNone(self.check("222", scope="Approved contacts"))
		with patch.object(scope, "_is_approved", return_value=False):
			self.assertIsNotNone(self.check("222", scope="Approved contacts"))

	def test_any_number_still_rejects_garbage(self):
		self.assertIsNone(self.check("222", scope="Any number"))
		self.assertIsNotNone(self.check("../etc", scope="Any number"))

	def test_unknown_scope_fails_closed(self):
		with patch.object(
			scope.frappe,
			"db",
			SimpleNamespace(get_value=lambda *a, **k: {"agent_recipient_scope": "Everyone"}),
		):
			self.assertEqual(scope.settings("GW")["scope"], "Current contact")

	def test_settings_error_fails_closed(self):
		def boom(*a, **k):
			raise RuntimeError("db")

		with patch.object(scope.frappe, "db", SimpleNamespace(get_value=boom)):
			conf_ = scope.settings("GW")
		self.assertEqual(conf_["scope"], "Current contact")
		self.assertEqual(conf_["per_run"], scope.DEFAULT_PER_RUN)


class TestCaps(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		patch.object(scope, "_cache", return_value=self.cache).start()
		self.addCleanup(patch.stopall)

	def claim(self, now, **over):
		with patch.object(scope, "settings", return_value=conf(**over)):
			return scope.claim_send("GW", "RUN", now=now)

	def test_per_run_cap(self):
		self.assertIsNone(self.claim(1000, per_run=2))
		self.assertIsNone(self.claim(1001, per_run=2))
		out = json.loads(self.claim(1002, per_run=2))
		self.assertEqual(out["error"], "send_cap_exceeded")
		self.assertEqual(out["cap"], "run")
		self.assertIsNone(out["retry_after"])

	def test_per_day_cap_with_retry_after(self):
		self.assertIsNone(self.claim(1000, per_day=2, per_run=0))
		self.assertIsNone(self.claim(2000, per_day=2, per_run=0))
		out = json.loads(self.claim(3000, per_day=2, per_run=0))
		self.assertEqual(out["cap"], "day")
		self.assertEqual(out["retry_after"], 1000 + scope.DAY_SECONDS - 3000)

	def test_day_window_rolls(self):
		self.assertIsNone(self.claim(1000, per_day=1, per_run=0))
		self.assertIsNone(self.claim(1000 + scope.DAY_SECONDS + 1, per_day=1, per_run=0))

	def test_zero_means_unlimited(self):
		for i in range(50):
			self.assertIsNone(self.claim(1000 + i, per_day=0, per_run=0))

	def test_release_frees_a_slot(self):
		self.assertIsNone(self.claim(1000, per_run=1))
		with patch.object(scope, "settings", return_value=conf(per_run=1)):
			scope.release_send("GW", "RUN")
		self.assertIsNone(self.claim(1001, per_run=1))

	def test_refused_claim_counts_nothing(self):
		self.claim(1000, per_run=1)
		self.claim(1001, per_run=1)
		self.assertEqual(len(self.cache.store[scope._run_key("GW", "RUN")]), 1)


class TestGatewayState(unittest.TestCase):
	def setUp(self):
		self.addCleanup(patch.stopall)
		self.flags = patch.object(
			scope.frappe, "flags", SimpleNamespace(huf_current_agent_run_id="R")
		).start()

	def lookups(self, channel, gateway_row):
		def get_value(doctype, name, fields=None, as_dict=False):
			if doctype == "Agent Run":
				return "C"
			if doctype == "Agent Conversation":
				return channel
			return gateway_row

		return patch.object(scope.frappe, "db", SimpleNamespace(get_value=get_value)).start()

	def test_no_run_is_none(self):
		scope.frappe.flags.huf_current_agent_run_id = None
		self.assertEqual(scope.gateway_state(), ("none", ""))

	def test_non_gateway_channel_is_none(self):
		self.lookups("desk", None)
		self.assertEqual(scope.gateway_state(), ("none", ""))

	def test_enabled_telegram(self):
		self.lookups("gateway:GW", {"provider": "Telegram", "is_enabled": 1})
		self.assertEqual(scope.gateway_state(), ("telegram", "GW"))

	def test_whatsapp_disabled_missing_are_invalid(self):
		for row in (
			{"provider": "WhatsApp", "is_enabled": 1},
			{"provider": "Telegram", "is_enabled": 0},
			None,
		):
			self.lookups("gateway:GW", row)
			self.assertEqual(scope.gateway_state()[0], "invalid")

	def test_db_error_is_invalid(self):
		def boom(*a, **k):
			raise RuntimeError("db down")

		patch.object(scope.frappe, "db", SimpleNamespace(get_value=boom)).start()
		self.assertEqual(scope.gateway_state()[0], "invalid")
		self.assertEqual(scope.run_gateway(), "")


class AtomicRedis:
	"""Thread-safe fake exposing the Redis counter API (the real client is atomic server-side)."""

	def __init__(self):
		import threading

		self.d, self.lock = {}, threading.Lock()

	def make_key(self, k):
		return "k:" + k

	def incrby(self, k, n):
		with self.lock:
			self.d[k] = self.d.get(k, 0) + n
			return self.d[k]

	def decrby(self, k, n):
		return self.incrby(k, -n)

	def expire(self, k, s):
		return True

	def ttl(self, k):
		return 100


class TestAtomicCaps(unittest.TestCase):
	def setUp(self):
		self.addCleanup(patch.stopall)

	def hammer(self, cache, **over):
		import threading

		results = []
		patch.object(scope, "_cache", return_value=cache).start()
		patch.object(scope, "settings", return_value=conf(**over)).start()

		def work():
			results.append(scope.claim_send("GW", "RUN"))

		threads = [threading.Thread(target=work) for _ in range(60)]
		[t.start() for t in threads]
		[t.join() for t in threads]
		return sum(1 for r in results if r is None)

	def test_redis_run_cap_never_exceeded(self):
		self.assertEqual(self.hammer(AtomicRedis(), per_run=7, per_day=0), 7)

	def test_redis_day_cap_never_exceeded(self):
		self.assertEqual(self.hammer(AtomicRedis(), per_run=0, per_day=11), 11)

	def test_fallback_lock_cap_never_exceeded(self):
		self.assertEqual(self.hammer(FakeCache(), per_run=5, per_day=0), 5)

	def test_redis_release_frees_slot(self):
		cache = AtomicRedis()
		patch.object(scope, "_cache", return_value=cache).start()
		patch.object(scope, "settings", return_value=conf(per_run=1)).start()
		self.assertIsNone(scope.claim_send("GW", "RUN"))
		self.assertIsNotNone(scope.claim_send("GW", "RUN"))
		scope.release_send("GW", "RUN")
		self.assertIsNone(scope.claim_send("GW", "RUN"))


class PipeRedis(AtomicRedis):
	def __init__(self, fail_after_incr=False):
		super().__init__()
		self.ttls, self.fail_after_incr = {}, fail_after_incr

	def pipeline(self, transaction=True):
		outer = self

		class P:
			def __init__(self):
				self.ops = []

			def set(self, k, v, nx=False, ex=None):
				self.ops.append(("set", k, v, nx, ex))

			def incrby(self, k, n):
				self.ops.append(("incr", k, n))

			def execute(self):
				out = []
				for op in self.ops:
					if op[0] == "set":
						if op[3] and op[1] in outer.d:
							out.append(None)
						else:
							outer.d[op[1]] = op[2]
							outer.ttls[op[1]] = op[4]
							out.append(True)
					else:
						out.append(outer.incrby(op[1], op[2]))
				return out

		return P()


class TestAtomicTtl(unittest.TestCase):
	def setUp(self):
		self.addCleanup(patch.stopall)

	def test_counter_always_created_with_ttl(self):
		c = PipeRedis()
		patch.object(scope, "_cache", return_value=c).start()
		patch.object(scope, "settings", return_value=conf(per_run=3, per_day=5)).start()
		self.assertIsNone(scope.claim_send("GW", "RUN"))
		self.assertTrue(c.ttls and all(v == scope.DAY_SECONDS for v in c.ttls.values()))

	def test_exception_after_incr_does_not_double_count(self):
		c = PipeRedis()
		real = c.ttl
		state = {"n": 0}

		def boom(k):
			raise RuntimeError("redis gone")

		c.ttl = boom
		cache = FakeCache()
		patch.object(scope, "_cache", return_value=c).start()
		# day cap of 1 reached on 2nd claim path: force failure after the run counter was incremented
		patch.object(scope, "settings", return_value=conf(per_run=5, per_day=1)).start()
		orig = scope._incr

		def flaky(cl, key):
			state["n"] += 1
			if state["n"] == 2:
				raise RuntimeError("boom")
			return orig(cl, key)

		patch.object(scope, "_incr", side_effect=flaky).start()
		scope.claim_send("GW", "RUN")  # falls back to list path
		run_counter = [v for k, v in c.d.items() if "RUN" in k]
		self.assertEqual(run_counter, [0])  # released before fallback


if __name__ == "__main__":
	unittest.main()
