"""Fixture matrix for pure Telegram update parsing and event mapping."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters.telegram_inbound import parse_update, to_event
from huf.ai.tests.telegram_fakes import FIXTURE_DIR, load_fixture


def parsed(name):
	return parse_update(load_fixture(name))


class TestTelegramInbound(unittest.TestCase):
	def test_every_fixture_parses(self):
		# answer_* fixtures are expected API request payloads, not inbound updates.
		names = sorted(p.stem for p in FIXTURE_DIR.glob("*.json") if not p.stem.startswith("answer_"))
		self.assertGreaterEqual(len(names), 20)
		for name in names:
			with self.subTest(name):
				self.assertTrue(parsed(name).update_id)

	def test_text_message(self):
		p = parsed("message_text")
		self.assertEqual((p.kind, p.chat_id, p.sender_id, p.text, p.message_id), ("message", "111", "111", "hello bot", "10"))
		event = to_event(p)
		self.assertEqual(event.thread_id, "10")
		self.assertEqual(event.display_name, "@janedoe")
		self.assertFalse(event.is_room)

	def test_group_mention_and_room(self):
		p = parsed("message_group_mention")
		self.assertTrue(p.mentioned)
		self.assertEqual(p.mentions, ("@huf_bot",))
		self.assertTrue(to_event(p).is_room)

	def test_bot_command_strips_bot_suffix(self):
		p = parsed("message_bot_command")
		self.assertEqual(p.command, "help")
		self.assertTrue(p.mentioned)

	def test_start_deep_link_payload(self):
		p = parsed("message_start_deep_link")
		self.assertEqual((p.command, p.start_payload), ("start", "pair_ABC123"))
		self.assertEqual(parsed("message_bot_command").start_payload, "")

	def test_edited_message_flag(self):
		p = parsed("edited_message")
		self.assertTrue(p.edited)
		self.assertEqual(p.kind, "edited_message")
		self.assertEqual(to_event(p).message_text, "hello bot (edited)")

	def test_channel_post_uses_channel_as_sender(self):
		p = parsed("channel_post")
		self.assertTrue(p.is_channel)
		self.assertEqual((p.chat_id, p.sender_id), ("-1009999", "-1009999"))
		event = to_event(p)
		self.assertTrue(event.is_room)
		self.assertEqual(event.display_name, "News")

	def test_callback_query(self):
		p = parsed("callback_query")
		self.assertEqual((p.kind, p.callback_query_id, p.callback_data, p.text), ("callback_query", "cbq-1", "approve:42", "approve:42"))
		self.assertEqual((p.chat_id, p.message_id), ("111", "55"))
		self.assertEqual(to_event(p).raw_payload["callback_query"]["id"], "cbq-1")

	def test_reaction_added_and_removed(self):
		added = parsed("message_reaction_added")
		self.assertEqual(added.reactions_added, ("👍",))
		event = to_event(added)
		self.assertEqual((event.kind, event.reaction_emoji, event.reaction_to), ("reaction", "👍", "55"))
		removed = parsed("message_reaction_removed")
		self.assertEqual(removed.reactions_removed, ("👍",))
		self.assertEqual(to_event(removed).reaction_emoji, "")

	def test_non_event_updates_return_none(self):
		for name in ("message_reaction_count", "my_chat_member_blocked", "my_chat_member_unblocked", "unsupported_update"):
			with self.subTest(name):
				self.assertIsNone(to_event(parsed(name)))

	def test_my_chat_member_block_detection(self):
		self.assertTrue(parsed("my_chat_member_blocked").bot_blocked)
		self.assertFalse(parsed("my_chat_member_blocked").bot_unblocked)
		self.assertTrue(parsed("my_chat_member_unblocked").bot_unblocked)
		self.assertEqual(parsed("unsupported_update").kind, "unsupported")

	def test_location_contact_venue_poll_text(self):
		self.assertEqual(parsed("location").text, "[location] 12.97,77.59")
		self.assertEqual(parsed("location").content_kind, "location")
		self.assertIn("Asha K +911234567890", parsed("contact").text)
		venue = parsed("venue")
		self.assertEqual(venue.content_kind, "venue")
		self.assertIn("Cafe, 1 MG Road", venue.text)
		poll = parsed("poll")
		self.assertEqual(poll.content_kind, "poll")
		self.assertEqual(poll.text, "[poll] Lunch?: Pizza | Sushi")

	def test_media_kinds(self):
		cases = {"photo": "photo", "voice": "voice", "video_note": "video_note", "sticker": "sticker", "animation": "animation"}
		for name, kind in cases.items():
			with self.subTest(name):
				p = parsed(name)
				self.assertEqual(p.content_kind, "media")
				self.assertEqual([m["kind"] for m in p.attachments_meta], [kind])
		self.assertEqual(parsed("photo").attachments_meta[0]["file_id"], "big")
		self.assertEqual(parsed("photo").text, "look")
		self.assertEqual(parsed("animation").attachments_meta[0]["file_id"], "anim-id")

	def test_media_group_id(self):
		self.assertEqual(parsed("media_group_photo").media_group_id, "mg-77")
		self.assertEqual(parsed("message_text").media_group_id, "")

	def test_reply_and_forward_origin(self):
		p = parsed("reply_and_forward")
		self.assertEqual(p.reply_to_message_id, "69")
		self.assertEqual(p.forward_origin, {"type": "user", "sender_user_id": "333", "date": 1750000000})

	def test_forum_topic_thread(self):
		p = parsed("forum_topic_message")
		self.assertEqual(p.message_thread_id, "900")
		self.assertEqual(to_event(p).thread_id, p.message_id)  # reply anchor stays the message id

	def test_missing_identifiers_raise(self):
		with self.assertRaises(ValueError):
			to_event(parse_update({"update_id": 1, "message": {"message_id": 1, "chat": {}, "from": {}, "text": "x"}}))


class TestTelegramInboundTypedKinds(unittest.TestCase):
	def test_inline_query(self):
		p = parsed("inline_query")
		self.assertEqual((p.kind, p.inline_query_id, p.query_text, p.sender_id), ("inline_query", "iq-1", "weekly report", "111"))
		self.assertEqual((p.inline_offset, p.chat_type), ("", "sender"))
		self.assertIsNone(to_event(p))

	def test_chosen_inline_result(self):
		p = parsed("chosen_inline_result")
		self.assertEqual((p.kind, p.result_id, p.query_text, p.inline_message_id), ("chosen_inline_result", "ask-abc", "weekly report", "imid-1"))
		self.assertEqual(p.sender_id, "111")
		self.assertIsNone(to_event(p))

	def test_chat_join_request(self):
		p = parsed("chat_join_request")
		self.assertEqual((p.kind, p.chat_id, p.sender_id, p.join_user_chat_id, p.bio), ("chat_join_request", "-1001234", "777", "777", "hello"))
		p2 = parse_update({"update_id": 5, "chat_join_request": {"chat": {"id": -1, "type": "channel"}, "from": {"id": 9},
			"user_chat_id": 9, "query_id": "jq", "invite_link": {"invite_link": "https://t.me/+x"}}})
		self.assertEqual((p2.join_query_id, p2.invite_link), ("jq", "https://t.me/+x"))
		self.assertIsNone(to_event(p))

	def test_guest_message(self):
		p = parsed("guest_message")
		self.assertEqual((p.kind, p.guest_query_id, p.sender_id, p.chat_id), ("guest_message", "gq-abc123", "777", "-1009988"))
		self.assertEqual(p.text, "@mybot what is 2+2?")
		self.assertIsNone(to_event(p))

	def test_stopped_message_generation(self):
		p = parse_update({"update_id": 7, "stopped_message_generation": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42}, "draft_id": 3}})
		self.assertEqual((p.kind, p.chat_id, p.sender_id), ("stopped_message_generation", "42", "42"))
		self.assertIsNone(to_event(p))

	def test_poll_and_poll_answer(self):
		p = parse_update({"update_id": 8, "poll": {"id": "p1", "question": "Lunch?"}})
		self.assertEqual((p.kind, p.poll_id, p.text), ("poll", "p1", "Lunch?"))
		a = parse_update({"update_id": 9, "poll_answer": {"poll_id": "p1", "user": {"id": 5}, "option_ids": [0, 2]}})
		self.assertEqual((a.kind, a.poll_id, a.sender_id, a.poll_option_ids), ("poll_answer", "p1", "5", (0, 2)))
		self.assertIsNone(to_event(p))
		self.assertIsNone(to_event(a))

	def test_payment_kinds(self):
		for key in ("shipping_query", "pre_checkout_query"):
			with self.subTest(key):
				p = parse_update({"update_id": 10, key: {"id": "q", "from": {"id": 6}}})
				self.assertEqual((p.kind, p.sender_id), (key, "6"))
				self.assertIsNone(to_event(p))

	def test_unknown_still_unsupported(self):
		self.assertEqual(parsed("unsupported_update").kind, "unsupported")
