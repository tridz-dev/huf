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

	def test_off_when_inline_off(self):
		c = self._check(self._row(telegram_inline_enabled=0))[1]
		self.assertEqual((c["state"], c["ok"], c["hint"]), ("off", True, ""))


class TestFeatureRows(unittest.TestCase):
	def _states(self, row, bot):
		from unittest.mock import patch

		with patch("huf.ai.gateway_adapters.telegram_inline.feedback_seen", return_value=False):
			h = build_health({**GW, **row}, OK, PASSING, None, bot, None, "huf.example.com")
		return h, {c["id"]: c["state"] for c in h["checks"]}

	def test_warn_rows_never_degrade_health(self):
		row = {"telegram_inline_enabled": 1, "room_policy": "Open", "mention_required": 0}
		h, states = self._states(row, {})
		self.assertEqual(states["inline_mode"], "warn")
		self.assertEqual(states["group_privacy"], "warn")
		self.assertEqual(states["join_groups"], "warn")
		self.assertEqual(h["health"], "healthy")
		self.assertTrue(all(c["state"] in ("pass", "warn", "off") for c in h["checks"]))

	def test_feature_flags_from_settings(self):
		from huf.ai.telegram_management import feature_flags

		off = feature_flags({"room_policy": "Disabled", "telegram_inline_enabled": 0})
		self.assertFalse(any(off.values()))
		on = feature_flags(
			{
				"room_policy": "Open",
				"mention_required": 0,
				"direct_policy": "Open",
				"telegram_business_policy": "Draft",
				"telegram_join_policy": "Agent",
			}
		)
		self.assertTrue(all(on.values()))
		self.assertFalse(feature_flags({"room_policy": "Open", "mention_required": 1})["group_open"])
		self.assertTrue(feature_flags({"telegram_guard_captcha": "Emoji"})["join_requests"])
		self.assertTrue(feature_flags({"telegram_agent_allow_business": 1})["business"])

	def test_failed_readiness_still_degrades(self):
		bad = [{"id": "webhook_url", "label": "x", "ok": False, "hint": "h"}]
		h = build_health(GW, OK, bad)
		self.assertEqual(h["health"], "degraded")
		self.assertEqual(next(c for c in h["checks"] if c["id"] == "webhook_url")["state"], "fail")
