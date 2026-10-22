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
		with patch.object(scope, "settings", return_value=conf(**over)), patch.object(
			scope, "current_chat", return_value=current
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
		with patch.object(scope.frappe, "db", SimpleNamespace(get_value=lambda *a, **k: {"agent_recipient_scope": "Everyone"})):
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


if __name__ == "__main__":
	unittest.main()
