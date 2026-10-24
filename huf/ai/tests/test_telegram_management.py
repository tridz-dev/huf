# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure helpers of telegram_management (no site, no network)."""

from __future__ import annotations

import unittest

from huf.ai.telegram_management import _safe_text, build_health, build_overview, credential_presence

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
		self.assertEqual(
			credential_presence({"token": "123:abc", "webhook_secret": ""}),
			{"token_present": True, "webhook_secret_present": False},
		)

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


class TestInlineFeedbackCheck(unittest.TestCase):
	def _row(self, **kw):
		return {**GW, "telegram_inline_enabled": 1, "telegram_inline_feedback_enabled": 0, **kw}

	def _check(self, row, seen=False):
		from unittest.mock import patch

		with patch("huf.ai.gateway_adapters.telegram_inline.feedback_seen", return_value=seen):
			h = build_health(row, OK, PASSING)
		return h, next((c for c in h["checks"] if c["id"] == "inline_feedback"), None)

	def test_warns_when_inline_on_and_feedback_unknown(self):
		h, c = self._check(self._row())
		self.assertFalse(c["ok"])
		self.assertEqual(c["hint"], "In BotFather send /setinlinefeedback and choose Enabled")
		self.assertEqual(h["health"], "healthy")  # warning only

	def test_clears_with_flag_or_observation(self):
		self.assertTrue(self._check(self._row(telegram_inline_feedback_enabled=1))[1]["ok"])
		self.assertTrue(self._check(self._row(), seen=True)[1]["ok"])

	def test_absent_when_inline_off(self):
		self.assertIsNone(self._check(self._row(telegram_inline_enabled=0))[1])
