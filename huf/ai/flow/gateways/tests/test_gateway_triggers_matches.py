# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Table tests for ``gateway_triggers.matches``: every registry param, no bench needed (pytest or unittest)."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.flow.gateways import gateway_triggers as gt
from huf.ai.flow.gateways.registry import get_registry

GW = SimpleNamespace(name="Support", provider="whatsapp")
TG = SimpleNamespace(name="Bot", provider="telegram")


def cfg(gateway="Support", **params):
	return {"gateway": gateway, "params": [{"key": k, "value": v} for k, v in params.items()]}


def msg(**over):
	base = {
		"gateway_event": "", "gateway": "Support", "provider": "whatsapp", "sender_id": "15550001111",
		"text": "Hi, where is my ORDER?", "message_type": "text", "kind": "message", "attachments": [],
		"is_room": False, "mentioned": False, "language": "",
	}
	base.update(over)
	return base


class TestMatches(unittest.TestCase):
	def ok(self, config, payload, gateway=GW, node_type="trigger.gateway"):
		got, reason = gt.matches(config, payload, gateway, node_type)
		self.assertTrue(got, reason)

	def no(self, config, payload, gateway=GW, node_type="trigger.gateway", reason=None):
		got, why = gt.matches(config, payload, gateway, node_type)
		self.assertFalse(got)
		if reason:
			self.assertEqual(why, reason)

	def test_every_registry_param_is_implemented_or_listed(self):
		keys = {p["key"] for spec in get_registry()["specs"].values() for p in spec["params"]}
		handled = {
			"only_senders", "message_kinds", "keywords", "starts_with", "chat_scope", "only_when_mentioned", "has_attachment",
			"language", "ignore_bots", "max_runs_per_sender_per_hour", "allow_parallel", "button_reply_ids", "button_payloads",
			"ad_tags", "first_message_only", "only_chats", "chat_kinds", "topics", "commands", "callback_prefixes",
			"include_edits", "include_channel_posts",
		}
		self.assertEqual(keys - handled, set())

	def test_channel_and_blank(self):
		self.ok(cfg(), msg())
		self.no(cfg(gateway=""), msg(), reason=gt.REASON_NO_CHANNEL)
		self.no(cfg(gateway="Other"), msg(), reason=gt.REASON_OTHER_CHANNEL)

	def test_dedicated_node_needs_its_provider(self):
		self.ok(cfg(), msg(), node_type="trigger.whatsapp")
		self.no(cfg(), msg(), node_type="trigger.telegram", reason=gt.REASON_OTHER_CHANNEL)
		self.ok(cfg("Bot"), msg(gateway="Bot", provider="telegram"), TG, "trigger.telegram")

	def test_empty_and_unknown_params_are_no_filter(self):
		self.ok(cfg(keywords=[], starts_with="", only_senders=None, message_kinds=[], mystery=["x"]), msg())

	def test_keywords_whole_word_case_insensitive(self):
		self.ok(cfg(keywords=["order"]), msg())
		self.ok(cfg(keywords=["refund", "Order"]), msg())
		self.no(cfg(keywords=["ord"]), msg(), reason="keywords")
		self.no(cfg(keywords=["order"]), msg(text="reorder please"))

	def test_starts_with(self):
		self.ok(cfg(starts_with="hi"), msg())
		self.no(cfg(starts_with="order"), msg())

	def test_only_senders_matches_ids_numbers_and_usernames(self):
		self.ok(cfg(only_senders=["+1 555 000 1111"]), msg())
		self.ok(cfg(only_senders=["asha_k"]), msg(username="Asha_K"))
		self.ok(cfg(only_senders=["@asha_k"]), msg(username="asha_k"))
		self.no(cfg(only_senders=["15559999999"]), msg())

	def test_message_kinds_and_attachment(self):
		self.ok(cfg(message_kinds=["text", "voice"]), msg())
		self.no(cfg(message_kinds=["voice"]), msg())
		self.no(cfg(has_attachment=True), msg())
		self.ok(cfg(has_attachment=True), msg(attachments=["/files/a.png"]))

	def test_chat_scope_and_mention(self):
		room = msg(is_room=True)
		self.no(cfg(chat_scope="direct"), room)
		self.ok(cfg(chat_scope="groups"), room)
		self.no(cfg(chat_scope="groups"), msg())
		self.no(cfg(only_when_mentioned=True), room, reason="not mentioned")
		self.ok(cfg(only_when_mentioned=True), msg(is_room=True, mentioned=True))
		self.ok(cfg(only_when_mentioned=True), msg())  # direct chats are not groups

	def test_language_matches_prefix(self):
		self.ok(cfg(language=["en"]), msg(language="en-US"))
		self.no(cfg(language=["hi"]), msg(language="en"))
		self.no(cfg(language=["hi"]), msg())

	def test_ignore_bots_default_on(self):
		self.no(cfg(), msg(sender_is_bot=True))
		self.ok(cfg(ignore_bots=False), msg(sender_is_bot=True))

	def test_buttons_and_ads(self):
		self.ok(cfg(button_reply_ids=["yes"]), msg(button_id="yes"))
		self.ok(cfg(button_reply_ids=["yes"]), msg(interactive_reply={"id": "yes", "title": "Yes"}))
		self.no(cfg(button_reply_ids=["yes"]), msg(button_id="no"))
		self.ok(cfg(button_payloads=["P1"]), msg(button_payload="P1"))
		self.ok(cfg(ad_tags=["spring"]), msg(referral_tag="spring"))
		self.ok(cfg(ad_tags=["ad1"]), msg(referral={"source_id": "ad1"}))
		self.no(cfg(ad_tags=["spring"]), msg())

	def test_first_message_only(self):
		with patch.object(gt, "_is_first_message", return_value=True):
			self.ok(cfg(first_message_only=True), msg())
		with patch.object(gt, "_is_first_message", return_value=False):
			self.no(cfg(first_message_only=True), msg(), reason="not the first message")
			self.ok(cfg(), msg())

	def test_telegram_filters(self):
		t = dict(gateway="Bot", provider="telegram")
		self.ok(cfg("Bot", only_chats=["-100"]), msg(telegram_chat_id="-100", **t), TG)
		self.ok(cfg("Bot", only_chats=["@team"]), msg(username="team", **t), TG)
		self.no(cfg("Bot", only_chats=["-100"]), msg(telegram_chat_id="1", **t), TG)
		self.ok(cfg("Bot", chat_kinds=["private"]), msg(telegram_chat_type="private", **t), TG)
		self.no(cfg("Bot", chat_kinds=["group"]), msg(telegram_chat_type="private", **t), TG)
		self.ok(cfg("Bot", topics=["7"]), msg(topic_id="7", **t), TG)
		self.no(cfg("Bot", topics=["7"]), msg(**t), TG)

	def test_commands_handle_bot_suffix(self):
		t = dict(gateway="Bot", provider="telegram")
		self.ok(cfg("Bot", commands=["start"]), msg(command="start", **t), TG)
		self.ok(cfg("Bot", commands=["/start"]), msg(text="/start@my_bot hello", **t), TG)
		self.ok(cfg("Bot", commands=["help"]), msg(command="/help@my_bot", **t), TG)
		self.no(cfg("Bot", commands=["start"]), msg(text="start", **t), TG)

	def test_callback_prefixes_and_kinds(self):
		t = dict(gateway="Bot", provider="telegram")
		self.ok(cfg("Bot", callback_prefixes=["buy:"]), msg(kind="callback", callback_data="buy:12", **t), TG)
		self.no(cfg("Bot", callback_prefixes=["buy:"]), msg(kind="callback", callback_data="x", **t), TG)
		self.no(cfg(), msg(kind="reaction"))
		self.ok(cfg(), msg(kind="callback"))

	def test_edits_and_channel_posts_off_by_default(self):
		self.no(cfg(), msg(edited=True), reason="edited message")
		self.ok(cfg(include_edits=True), msg(edited=True))
		self.no(cfg(), msg(is_channel_post=True))
		self.ok(cfg(include_channel_posts=True), msg(is_channel_post=True))


class TestRateCap(unittest.TestCase):
	def test_cap_value(self):
		self.assertEqual(gt.rate_cap_of(None), 30)
		self.assertEqual(gt.rate_cap_of(""), 30)
		self.assertEqual(gt.rate_cap_of(5), 5)
		self.assertEqual(gt.rate_cap_of("x"), 30)

	def test_over_cap_blocks_with_reason(self):
		with patch.object(gt, "over_rate_cap", return_value=True) as counted:
			got, reason = gt.matches(cfg(max_runs_per_sender_per_hour=3), msg(), GW, flow_id="F1")
		self.assertEqual((got, reason), (False, gt.REASON_RATE_LIMIT))
		counted.assert_called_once_with("F1", "Support", "15550001111", 3)

	def test_filters_are_checked_before_the_counter(self):
		with patch.object(gt, "over_rate_cap") as counted:
			got, _ = gt.matches(cfg(keywords=["refund"]), msg(), GW, flow_id="F1")
		self.assertFalse(got)
		counted.assert_not_called()

	def test_off_when_zero_or_no_sender(self):
		self.assertFalse(gt.over_rate_cap("F", "G", "s", 0))
		self.assertFalse(gt.over_rate_cap("F", "G", "", 5))

	def test_counter_over_cap_with_fake_cache(self):
		counts = {}

		class Cache:
			def incr(self, key):
				counts[key] = counts.get(key, 0) + 1
				return counts[key]

			def expire(self, key, ttl):
				pass

		with patch("frappe.cache", return_value=Cache()):
			results = [gt.over_rate_cap("F", "G", "s", 2) for _ in range(3)]
			other = gt.over_rate_cap("F", "G", "someone-else", 2)
		self.assertEqual(results, [False, False, True])
		self.assertFalse(other)


if __name__ == "__main__":
	unittest.main()
