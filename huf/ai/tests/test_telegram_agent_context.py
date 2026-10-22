"""Telegram agent context (WP-C): dynamic instructions by gateway flags, length cap, hook override and call compat."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from huf.ai.gateway_adapters import provider_hooks, telegram_agent_context as tac, telegram_buttons
from huf.ai.gateway_adapters import telegram_buttons_hooks

SECRET = "123456:SECRET-TOKEN-XYZ"


def gw(**kw):
	base = {"provider": "Telegram", "telegram_bot_token": SECRET, "voice_reply_mode": "Off"}
	base.update(kw)
	return SimpleNamespace(**base)


ALL_ON = dict(
	telegram_agent_allow_group_admin=1,
	telegram_agent_allow_business=1,
	telegram_agent_allow_profile=1,
	voice_reply_mode="Text and voice",
)


class TestCapabilities(unittest.TestCase):
	def test_defaults_all_off(self):
		caps = tac.capabilities(SimpleNamespace())
		self.assertFalse(caps["group_admin"])
		self.assertFalse(caps["business"])
		self.assertFalse(caps["profile"])
		self.assertFalse(caps["voice_reply"])
		self.assertEqual(caps["voice_reply_mode"], "Off")

	def test_flags_and_voice_mode_reflected(self):
		caps = tac.capabilities(gw(**ALL_ON))
		self.assertTrue(caps["group_admin"] and caps["business"] and caps["profile"])
		self.assertTrue(caps["voice_reply"])
		self.assertEqual(caps["voice_reply_mode"], "Text and voice")

	def test_capabilities_never_contain_secrets(self):
		caps = tac.capabilities(gw(**ALL_ON))
		self.assertNotIn(SECRET, repr(caps))
		self.assertFalse(any("token" in k for k in caps))


class TestBuildInstructions(unittest.TestCase):
	def test_reply_features_always_present(self):
		text = tac.build_instructions(gw())
		self.assertIn("```telegram-buttons", text)
		self.assertIn("```telegram-media", text)
		self.assertIn("list_templates", text)
		self.assertIn("Reactions and typing", text)

	def test_optional_sections_follow_flags(self):
		off = tac.build_instructions(gw())
		self.assertNotIn("telegram_admin", off)
		self.assertNotIn("Secretary", off)
		self.assertNotIn("Bot commands", off)
		self.assertNotIn("Voice replies are on", off)

		on = tac.build_instructions(gw(**ALL_ON))
		self.assertIn("telegram_admin tool: group moderation (requires confirm).", on)
		self.assertIn("Secretary/business actions", on)
		self.assertIn("Bot commands and profile", on)
		self.assertIn("Voice replies are on (Text and voice)", on)

	def test_only_one_flag_adds_only_its_section(self):
		text = tac.build_instructions(gw(telegram_agent_allow_business=1))
		self.assertIn("Secretary/business actions", text)
		self.assertNotIn("telegram_admin", text)

	def test_length_cap_with_everything_on(self):
		text = tac.build_instructions(gw(**ALL_ON))
		self.assertLessEqual(len(text), 1200)
		self.assertIn("```telegram-buttons", text)

	def test_no_secrets_in_text(self):
		text = tac.build_instructions(gw(**ALL_ON))
		self.assertNotIn(SECRET, text)
		self.assertNotIn("SECRET", text)

	def test_none_gateway_still_works(self):
		text = tac.build_instructions(None)
		self.assertIn("```telegram-buttons", text)
		self.assertLessEqual(len(text), 1200)

	def test_buttons_wording_reused(self):
		self.assertIn(telegram_buttons.AGENT_INSTRUCTIONS, tac.build_instructions(gw()))


class TestHookRegistration(unittest.TestCase):
	def test_context_hook_overrides_buttons_hook(self):
		from huf.ai.gateway_adapters import telegram_hooks  # noqa: F401  (import order registers hooks)

		fn = provider_hooks.get("Telegram", "agent_instructions")
		self.assertIsNotNone(fn)
		self.assertEqual(fn.__module__, "huf.ai.gateway_adapters.telegram_agent_context_hooks")
		self.assertNotEqual(fn, telegram_buttons_hooks.agent_instructions)

	def test_hook_accepts_gateway_and_legacy_no_arg(self):
		from huf.ai.gateway_adapters import telegram_agent_context_hooks as hooks

		self.assertIn("Secretary/business actions", hooks.agent_instructions(gw(**ALL_ON)))
		self.assertIn("```telegram-buttons", hooks.agent_instructions())

	def test_buttons_hook_accepts_optional_gateway(self):
		self.assertEqual(telegram_buttons_hooks.agent_instructions(), telegram_buttons.AGENT_INSTRUCTIONS)
		self.assertEqual(telegram_buttons_hooks.agent_instructions(gw()), telegram_buttons.AGENT_INSTRUCTIONS)

	def test_no_arg_fallback_pattern(self):
		# Mirrors the gateway_service call site for a hook that only takes no arguments.
		def legacy():
			return "legacy note"

		def call(hook, gateway):
			try:
				return hook(gateway)
			except TypeError:
				return hook()

		self.assertEqual(call(legacy, gw()), "legacy note")


if __name__ == "__main__":
	unittest.main()
