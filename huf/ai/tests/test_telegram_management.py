# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure helpers of telegram_management (no site, no network)."""

from __future__ import annotations

import unittest

from huf.ai.telegram_management import build_health, build_overview, credential_presence, _safe_text

GW = {"name": "TG-1", "is_enabled": 1, "last_event_at": "2026-01-01 10:00:00", "last_error": None}
OK = {"token_present": True, "webhook_secret_present": True}
PASSING = [
	{"id": "bot_reachable", "label": "a", "ok": True, "hint": ""},
	{"id": "webhook_url", "label": "b", "ok": True, "hint": ""},
	{"id": "webhook_allowed_updates", "label": "c", "ok": True, "hint": ""},
]


def _states(h):
	return {c["code"]: c["state"] for c in h["checklist"]}


class TestTelegramManagement(unittest.TestCase):
	def test_presence_masks_values(self):
		self.assertEqual(credential_presence({"token": "123:abc", "webhook_secret": ""}), {"token_present": True, "webhook_secret_present": False})

	def test_overview_has_no_secret_fields(self):
		out = build_overview(GW, OK, {"id": 1}, "", "https://x/y")
		self.assertNotIn("token", out)
		self.assertEqual(out["webhook_url"], "https://x/y")
		self.assertIsNone(out["last_error"])

	def test_healthy(self):
		h = build_health(GW, OK, PASSING)
		self.assertEqual(h["health"], "healthy")
		self.assertTrue(all(s == "done" for s in _states(h).values()))

	def test_not_set_up_without_token(self):
		h = build_health(GW, {"token_present": False, "webhook_secret_present": True}, [])
		self.assertEqual(h["health"], "not_set_up")

	def test_disabled(self):
		self.assertEqual(build_health({**GW, "is_enabled": 0}, OK, PASSING)["health"], "disabled")

	def test_rejected_token_blocks(self):
		checks = [{"id": "bot_reachable", "label": "a", "ok": False, "hint": "getMe failed"}]
		h = build_health(GW, OK, checks)
		self.assertEqual(h["health"], "blocked")
		self.assertEqual(_states(h)["bot_token"], "blocked")

	def test_webhook_problem_degrades(self):
		checks = PASSING[:1] + [{"id": "webhook_url", "label": "b", "ok": False, "hint": "x"}]
		self.assertEqual(build_health(GW, OK, checks)["health"], "degraded")

	def test_no_events_yet_is_not_set_up(self):
		self.assertEqual(build_health({**GW, "last_event_at": None}, OK, PASSING)["health"], "not_set_up")

	def test_safe_text_scrubs_secret(self):
		self.assertEqual(_safe_text("bad 123:SECRET end", {"token": "123:SECRET"}), "bad *** end")


if __name__ == "__main__":
	unittest.main()
