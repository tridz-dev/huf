"""Rich inbound Telegram content: descriptive text for every content type, forward/reply context, media refs."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters.telegram_inbound import media_refs, parse_update, to_event
from huf.ai.tests.telegram_fakes import load_fixture


def text_of(name: str) -> str:
	return to_event(parse_update(load_fixture(name))).message_text


def with_message(**kw) -> dict:
	upd = load_fixture("message_text")
	upd["message"].pop("text", None)
	upd["message"].update(kw)
	return upd


class TestInboundRich(unittest.TestCase):
	def test_sticker(self):
		self.assertEqual(text_of("sticker"), "[sticker] 😀")

	def test_sticker_set_and_flavour(self):
		upd = with_message(
			sticker={
				"file_id": "s",
				"is_animated": False,
				"is_video": True,
				"emoji": "🔥",
				"set_name": "Pack1",
			}
		)
		self.assertEqual(to_event(parse_update(upd)).message_text, "[video sticker] 🔥 set: Pack1")

	def test_animated_sticker_uses_thumbnail(self):
		upd = with_message(
			sticker={
				"file_id": "tgs",
				"is_animated": True,
				"thumbnail": {"file_id": "th", "file_unique_id": "u"},
			}
		)
		refs = media_refs(upd["message"])
		self.assertEqual(
			(refs[0]["kind"], refs[0]["file_id"], refs[0]["mime_type"]), ("sticker", "th", "image/webp")
		)

	def test_animation_caption_kept(self):
		self.assertEqual(text_of("animation"), "lol\n[gif/animation 2s]")

	def test_video_note_and_voice(self):
		self.assertEqual(text_of("video_note"), "[video note 4s]")
		self.assertEqual(text_of("voice"), "[voice message 3s]")

	def test_audio_title_performer(self):
		upd = with_message(audio={"file_id": "a", "duration": 61, "title": "Song", "performer": "Band"})
		self.assertEqual(to_event(parse_update(upd)).message_text, "[audio 61s] Band - Song")

	def test_media_refs_cover_all_kinds(self):
		for name, kind in (
			("sticker", "sticker"),
			("animation", "animation"),
			("video_note", "video_note"),
			("voice", "voice"),
		):
			self.assertEqual([r["kind"] for r in parse_update(load_fixture(name)).attachments_meta], [kind])

	def test_venue_poll_dice(self):
		self.assertIn("[venue] Cafe, 1 MG Road", text_of("venue"))
		self.assertEqual(text_of("poll"), "[poll] Lunch?: Pizza | Sushi")
		self.assertEqual(text_of("dice"), "[dice] 🎯 6")

	def test_contact_and_live_location(self):
		self.assertIn("Asha K +911234567890", text_of("contact"))
		upd = with_message(location={"latitude": 1.5, "longitude": 2.5, "live_period": 600})
		self.assertEqual(
			to_event(parse_update(upd)).message_text, "[location] 1.5,2.5\n(live location, shared for 600s)"
		)

	def test_forwarded_origin(self):
		self.assertEqual(text_of("forwarded"), "[forwarded from Huf News (Admin)]\ncheck this out")

	def test_forwarded_user_and_hidden(self):
		self.assertTrue(text_of("reply_and_forward").startswith("[forwarded from Bob]"))
		upd = with_message(
			text="x", forward_origin={"type": "hidden_user", "sender_user_name": "Anon Z", "date": 1}
		)
		self.assertEqual(to_event(parse_update(upd)).message_text, "[forwarded from Anon Z]\nx")

	def test_reply_with_quote(self):
		self.assertEqual(text_of("reply_quote"), '[replying to Bob (@bobby): "ship on Friday"]\nagree')

	def test_reply_without_quote_uses_original_text(self):
		out = text_of("reply_and_forward")
		self.assertIn('[replying to Jane (@janedoe): "orig"]', out)
		self.assertTrue(out.endswith("re: that"))

	def test_reply_to_media_names_the_kind(self):
		upd = with_message(
			text="what is this?",
			reply_to_message={"message_id": 3, "chat": {"id": 111}, "voice": {"file_id": "v", "duration": 5}},
		)
		self.assertIn(
			'[replying to a message: "[voice message 5s]"]', to_event(parse_update(upd)).message_text
		)

	def test_command_text_not_prefixed(self):
		upd = load_fixture("message_bot_command")
		upd["message"]["reply_to_message"] = {"message_id": 3, "chat": {"id": 111}, "text": "old"}
		p = parse_update(upd)
		self.assertEqual(to_event(p).message_text, p.text)

	def test_web_app_data_checklist_and_text_link(self):
		upd = with_message(web_app_data={"button_text": "Order", "data": '{"a":1}'})
		self.assertIn("[web app data from Order]", to_event(parse_update(upd)).message_text)
		upd = with_message(
			checklist={
				"title": "Todo",
				"tasks": [{"id": 1, "text": "milk"}, {"id": 2, "text": "eggs", "completion_date": 5}],
			}
		)
		self.assertIn("[checklist] Todo: [ ] milk | [x] eggs", to_event(parse_update(upd)).message_text)
		upd = with_message(
			text="see docs",
			entities=[{"type": "text_link", "offset": 4, "length": 4, "url": "https://x.dev/d"}],
		)
		self.assertIn("[links] docs -> https://x.dev/d", to_event(parse_update(upd)).message_text)

	def test_game(self):
		upd = with_message(game={"title": "Tetris", "description": "d", "photo": []})
		self.assertIn("[game] Tetris", to_event(parse_update(upd)).message_text)

	def test_plain_text_and_entities_unchanged(self):
		self.assertEqual(text_of("message_text"), "hello bot")
		p = parse_update(load_fixture("message_group_mention"))
		self.assertEqual(p.mentions, ("@huf_bot",))
		self.assertEqual(to_event(p).message_text, p.text)


if __name__ == "__main__":
	unittest.main()
