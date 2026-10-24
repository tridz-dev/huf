"""Agent reply blocks (telegram-buttons / telegram-media): every documented shape and every model-written variant
is accepted and normalised into ONE internal form, or rejected with an error; nothing is dropped silently."""

from __future__ import annotations

import json
import re
import unittest
from types import SimpleNamespace

from huf.ai.gateway_adapters import telegram_agent_context as tac
from huf.ai.gateway_adapters import telegram_blocks as blocks
from huf.ai.gateway_adapters import telegram_buttons as tb
from huf.ai.gateway_adapters import telegram_media_reply as mr
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi

CHAT = 111
GW = SimpleNamespace(name="GW", provider="Telegram")


def btn(**kw):
	return {"inline_keyboard": [[{"text": "B", **kw}]]}


def first(spec):
	return spec["rows"][0][0]


class Cache(blocks.LocalCache):
	pass


class TestScan(unittest.TestCase):
	BODY = '{"inline_keyboard": [[{"text": "A", "callback_data": "a"}]]}'

	def test_fence_variants_are_live_and_fully_stripped(self):
		cases = {
			"backticks": f"Hi\n```telegram-buttons\n{self.BODY}\n```\nBye",
			"tildes": f"Hi\n~~~telegram-buttons\n{self.BODY}\n~~~\nBye",
			"json tag first": f"Hi\n```json telegram-buttons\n{self.BODY}\n```\nBye",
			"json tag after": f"Hi\n```telegram-buttons json\n{self.BODY}\n```\nBye",
			"mixed case": f"Hi\n```Telegram-Buttons\n{self.BODY}\n```\nBye",
			"trailing spaces": f"Hi\n```telegram-buttons  \n{self.BODY}\n```  \nBye",
			"crlf": f"Hi\r\n```telegram-buttons\r\n{self.BODY}\r\n```\r\nBye",
			"single line": f"Hi\n```telegram-buttons {self.BODY}```\nBye",
			"closing on body line": f"Hi\n```telegram-buttons\n{self.BODY}```\nBye",
			"underscore name": f"Hi\n```telegram_buttons\n{self.BODY}\n```\nBye",
			"after prose": f"Hi ```telegram-buttons\n{self.BODY}\n```\nBye",
		}
		for name, text in cases.items():
			with self.subTest(name):
				visible, found = blocks.scan(text)
				self.assertNotIn("telegram", visible.lower())
				self.assertNotIn("inline_keyboard", visible)
				self.assertTrue(visible.startswith("Hi"), visible)
				self.assertEqual(len(found.get(blocks.BUTTONS, [])), 1, found)
				spec, errors = tb.parse(found[blocks.BUTTONS])
				self.assertEqual(errors, [])
				self.assertEqual(first(spec)["callback"], "a")

	def test_unclosed_fence_at_end_of_truncated_reply(self):
		visible, found = blocks.scan(f"Answer.\n```telegram-buttons\n{self.BODY}")
		self.assertEqual(visible, "Answer.")
		self.assertEqual(len(found[blocks.BUTTONS]), 1)
		visible, found = blocks.scan('Answer.\n```telegram-media\n{"items": [{"type": "pho')
		self.assertEqual(visible, "Answer.")
		self.assertTrue(blocks.MEDIA in found and mr.parse(found[blocks.MEDIA])[1])

	def test_blocks_inside_code_samples_are_not_live(self):
		samples = {
			"four backticks": f"Example:\n````markdown\n```telegram-buttons\n{self.BODY}\n```\n````\nDone",
			"other fence": f"```python\n```telegram-buttons\n{self.BODY}\n```\n",
			"indented": f"Example:\n\n    ```telegram-buttons\n    {self.BODY}\n    ```\n\nDone",
			"tab indented": f"\t```telegram-buttons\n\t{self.BODY}\n\t```",
			"prose mention": "Use a ```telegram-buttons fence to add buttons.",
		}
		for name, text in samples.items():
			with self.subTest(name):
				visible, found = blocks.scan(text)
				self.assertEqual(found, {})
				self.assertIn("telegram-buttons", visible)

	def test_other_fences_and_text_untouched(self):
		text = "a\n```python\nprint(1)\n```\nb"
		self.assertEqual(blocks.scan(text), (text, {}))

	def test_both_blocks_in_one_reply(self):
		text = f'x\n```telegram-media\n{{"items": []}}\n```\ny\n```telegram-buttons\n{self.BODY}\n```'
		visible, found = blocks.scan(text)
		self.assertEqual(visible, "x\ny")
		self.assertEqual(set(found), {blocks.BUTTONS, blocks.MEDIA})

	def test_lenient_json(self):
		for body in (
			'{"a": [1, 2,], }',
			'{"a": [1, 2]}\n',
			'﻿{"a": [1, 2]}',
		):
			value, err = blocks.loads(body)
			self.assertEqual((value, err), ({"a": [1, 2]}, ""), body)
		self.assertEqual(blocks.loads('{"a": "x,]"}')[0], {"a": "x,]"})  # commas inside strings survive
		self.assertTrue(blocks.loads("{nope")[1])

	def test_parse_bool(self):
		errors: list[str] = []
		for raw, want in (
			("false", False),
			("true", True),
			("0", False),
			(1, True),
			(None, False),
			(False, False),
		):
			self.assertEqual(blocks.parse_bool(raw, "x", errors), want, raw)
		self.assertEqual(errors, [])
		self.assertFalse(blocks.parse_bool("maybe", "once", errors))
		self.assertTrue(errors)


class TestButtonShapes(unittest.TestCase):
	def ok(self, raw, **want):
		spec, errors = tb.validate(raw)
		self.assertIsNotNone(spec, errors)
		self.assertEqual(errors, [], raw)
		return spec

	def test_inline_buttons_normalise_to_one_form(self):
		cases = [
			({"callback_data": "x"}, {"callback": "x"}),
			({"callback": "x"}, {"callback": "x"}),
			({"url": "https://a.io"}, {"url": "https://a.io"}),
			({"web_app": {"url": "https://a.io"}}, {"web_app": {"url": "https://a.io"}}),
			({"web_app": "https://a.io"}, {"web_app": {"url": "https://a.io"}}),
			({"login_url": "https://a.io/l"}, {"login_url": {"url": "https://a.io/l"}}),
			(
				{
					"login_url": {
						"url": "https://a.io/l",
						"forward_text": "Go",
						"bot_username": "@my_bot",
						"request_write_access": True,
					}
				},
				{
					"login_url": {
						"url": "https://a.io/l",
						"forward_text": "Go",
						"bot_username": "my_bot",
						"request_write_access": True,
					}
				},
			),
			({"switch_inline_query": "q"}, {"switch_inline_query": "q"}),
			({"switch_inline_query": ""}, {"switch_inline_query": ""}),
			({"switch_inline_query_current_chat": "q"}, {"switch_inline_query_current_chat": "q"}),
			({"switch_inline": "q"}, {"switch_inline_query": "q"}),
			({"switch_inline": "q", "current_chat": True}, {"switch_inline_query_current_chat": "q"}),
			({"switch_inline": {"query": "q"}}, {"switch_inline_query": "q"}),
			(
				{"switch_inline": {"query": "q", "current_chat": True}},
				{"switch_inline_query_current_chat": "q"},
			),
			({"copy_text": {"text": "CODE"}}, {"copy_text": {"text": "CODE"}}),
			({"copy_text": "CODE"}, {"copy_text": {"text": "CODE"}}),
		]
		for given, want in cases:
			with self.subTest(given):
				for top in ("inline_keyboard", "rows"):
					spec = self.ok({top: [[{"text": "B", **given}]]})
					self.assertEqual(first(spec), {"text": "B", **want})

	def test_top_level_variants(self):
		row = [[{"text": "B", "callback_data": "x"}]]
		for raw in (
			{"inline_keyboard": row},
			{"rows": row},
			{"reply_markup": {"inline_keyboard": row}},
			row,  # bare list of rows
		):
			self.assertEqual(first(self.ok(raw))["callback"], "x")

	def test_reply_keyboard_native_and_ours(self):
		cells = [["A", {"text": "Phone", "request_contact": True}]]
		native = self.ok(
			{
				"keyboard": cells,
				"resize_keyboard": False,
				"one_time_keyboard": True,
				"input_field_placeholder": "pick",
				"is_persistent": True,
			}
		)
		ours = self.ok(
			{
				"reply_keyboard": {
					"rows": cells,
					"resize": False,
					"one_time": True,
					"placeholder": "pick",
					"persistent": True,
				}
			}
		)
		self.assertEqual(native, ours)
		self.assertEqual((native["resize"], native["one_time"], native["placeholder"]), (False, True, "pick"))
		self.assertEqual(native["rows"][0][1], {"text": "Phone", "request_contact": True})
		self.assertEqual(self.ok({"keyboard": cells})["resize"], True)
		self.assertEqual(self.ok({"reply_keyboard": cells})["rows"], native["rows"])

	def test_reply_keyboard_special_cells_are_kept(self):
		spec = self.ok(
			{
				"keyboard": [
					[
						{"text": "Poll", "request_poll": {"type": "quiz"}},
						{"text": "Any poll", "request_poll": True},
						{"text": "App", "web_app": {"url": "https://a.io"}},
						{"text": "Users", "request_users": {"request_id": 1, "user_is_bot": False}},
						{"text": "Chat", "request_chat": {"request_id": 2, "chat_is_channel": True}},
						{"text": "Where", "request_location": True},
					]
				]
			}
		)
		cells = spec["rows"][0]
		self.assertEqual(cells[0]["request_poll"], {"type": "quiz"})
		self.assertEqual(cells[1]["request_poll"], {})
		self.assertEqual(cells[2]["web_app"], {"url": "https://a.io"})
		self.assertEqual(cells[3]["request_users"], {"request_id": 1, "user_is_bot": False})
		self.assertEqual(cells[4]["request_chat"], {"request_id": 2, "chat_is_channel": True})
		self.assertTrue(cells[5]["request_location"])

	def test_remove_keyboard(self):
		self.assertEqual(self.ok({"remove_keyboard": True}), {"mode": "remove_keyboard"})

	def test_booleans_are_real_booleans(self):
		spec = self.ok(
			{"inline_keyboard": [[{"text": "B", "callback_data": "x"}]], "once": "false", "edit": "true"}
		)
		self.assertEqual((spec["once"], spec["edit"]), (False, True))
		spec, errors = tb.validate({**btn(callback_data="x"), "once": "perhaps"})
		self.assertFalse(spec["once"])
		self.assertTrue(any("once" in e for e in errors))

	def test_rejected_with_an_error(self):
		cases = {
			"two kinds": btn(callback_data="a", url="https://a.io"),
			"no kind": btn(),
			"no text": {"inline_keyboard": [[{"callback_data": "a"}]]},
			"callback too long": btn(callback_data="x" * (tb.MAX_ID_BYTES + 1)),
			"bad scheme": btn(url="javascript:alert(1)"),
			"http web_app": btn(web_app={"url": "http://a.io"}),
			"login without url": btn(login_url={"forward_text": "x"}),
			"copy too long": btn(copy_text={"text": "x" * 300}),
			"empty": {},
			"rows not list": {"rows": "x"},
			"remove false": {"remove_keyboard": False, "x": 1},
			"keyboard empty": {"keyboard": [[]]},
			"request_users no id": {"keyboard": [[{"text": "U", "request_users": {}}]]},
		}
		for name, raw in cases.items():
			with self.subTest(name):
				spec, errors = tb.validate(raw)
				self.assertTrue(errors, raw)
				self.assertIsNone(spec if name != "two kinds" else None)

	def test_unknown_fields_are_reported_not_ignored_silently(self):
		spec, errors = tb.validate({**btn(callback_data="x", color="red"), "layout": 3})
		self.assertIsNotNone(spec)
		self.assertTrue(any("color" in e for e in errors) and any("layout" in e for e in errors))

	def test_button_text_has_no_invented_cap(self):
		text = "T" * 200
		spec, errors = tb.validate({"inline_keyboard": [[{"text": text, "callback_data": "x"}]]})
		self.assertEqual((first(spec)["text"], errors), (text, []))

	def test_truncations_are_reported(self):
		row = [{"text": str(i), "callback_data": f"c{i}"} for i in range(9)]
		spec, errors = tb.validate({"inline_keyboard": [row]})
		self.assertEqual(len(spec["rows"][0]), 8)
		self.assertTrue(any("row 1" in e and "8" in e for e in errors))
		many = [[{"text": "a", "callback_data": f"c{r}{c}"} for c in range(8)] for r in range(14)]
		spec, errors = tb.validate({"inline_keyboard": many})
		self.assertEqual(sum(len(r) for r in spec["rows"]), tb.MAX_BUTTONS)
		self.assertTrue(any("too many buttons" in e for e in errors))

	def test_last_block_wins_but_is_reported(self):
		a, b = json.dumps(btn(callback_data="a")), json.dumps(btn(callback_data="b"))
		spec, errors = tb.parse([a, b])
		self.assertEqual(first(spec)["callback"], "b")
		self.assertTrue(any("2 telegram-buttons blocks" in e for e in errors))

	def test_trailing_comma_json(self):
		spec, errors = tb.validate('{"inline_keyboard": [[{"text": "B", "callback_data": "x",},],],}')
		self.assertEqual((first(spec)["callback"], errors), ("x", []))

	def test_markup_is_telegram_native(self):
		adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET}, http_post=FakeBotApi().http_post
		)
		sign = lambda p: adapter.sign_callback_data(p, CHAT)  # noqa: E731
		spec = self.ok(
			{
				"inline_keyboard": [
					[
						{"text": "c", "callback_data": "go"},
						{"text": "w", "web_app": "https://x.io/app"},
						{"text": "l", "login_url": {"url": "https://x.io/l", "request_write_access": True}},
						{"text": "s", "switch_inline": "q", "current_chat": True},
						{"text": "cp", "copy_text": "CODE"},
					]
				]
			}
		)
		row = tb.build_markup(spec, sign)["inline_keyboard"][0]
		self.assertLessEqual(len(row[0]["callback_data"].encode()), 64)
		self.assertEqual(row[1]["web_app"], {"url": "https://x.io/app"})
		self.assertEqual(row[2]["login_url"], {"url": "https://x.io/l", "request_write_access": True})
		self.assertEqual(row[3]["switch_inline_query_current_chat"], "q")
		self.assertEqual(row[4]["copy_text"], {"text": "CODE"})
		reply = tb.build_markup(self.ok({"keyboard": [["A"]], "is_persistent": True}), sign)
		self.assertTrue(reply["is_persistent"])


class TestMediaShapes(unittest.TestCase):
	FILE_ID = "AgACAgIAAxkBAAIBQ2ZxYz_abcDEF123"

	def one(self, raw):
		items, errors = mr.validate(raw)
		return items, errors

	def test_file_locations_normalise(self):
		cases = [
			(
				{"type": "photo", "source": "url", "value": "https://a.io/a.png"},
				("url", "https://a.io/a.png"),
			),
			({"type": "photo", "media": "https://a.io/a.png"}, ("url", "https://a.io/a.png")),
			({"type": "photo", "url": "https://a.io/a.png"}, ("url", "https://a.io/a.png")),
			({"type": "photo", "photo": "https://a.io/a.png"}, ("url", "https://a.io/a.png")),
			({"type": "photo", "value": "/files/a.png"}, ("file_url", "/files/a.png")),
			({"type": "photo", "value": "/private/files/a.png"}, ("file_url", "/private/files/a.png")),
			({"type": "photo", "file_url": "/files/a.png"}, ("file_url", "/files/a.png")),
			({"type": "photo", "file_id": "short"}, ("file_id", "short")),
			({"type": "photo", "media": self.FILE_ID}, ("file_id", self.FILE_ID)),
			({"type": "photo", "value": self.FILE_ID}, ("file_id", self.FILE_ID)),
			({"photo": "https://a.io/a.png"}, ("url", "https://a.io/a.png")),  # no type: from the field name
			({"type": "photo", "media": {"url": "https://a.io/a.png"}}, ("url", "https://a.io/a.png")),
		]
		for entry, (source, value) in cases:
			for shape in (entry, {"items": [entry]}, [entry], {"media": [entry]}):
				with self.subTest(entry, shape=type(shape).__name__):
					items, errors = self.one(shape)
					self.assertEqual(errors, [])
					self.assertEqual(
						(items[0]["type"], items[0]["source"], items[0]["value"]), ("photo", source, value)
					)

	def test_type_aliases(self):
		for alias, kind in (
			("image", "photo"),
			("Image", "photo"),
			("picture", "photo"),
			("gif", "animation"),
			("videonote", "video_note"),
			("video-note", "video_note"),
			("file", "document"),
		):
			items, errors = self.one([{"type": alias, "media": "https://a.io/x"}])
			self.assertEqual((items[0]["type"], errors), (kind, []), alias)

	def test_rejected_with_an_error(self):
		cases = {
			"no media": {"type": "photo"},
			"ambiguous source": {"type": "photo", "value": "hello world"},
			"two locations": {"type": "photo", "url": "https://a.io/a", "file_id": "other"},
			"url source with path": {"type": "photo", "source": "url", "value": "/files/a.png"},
			"bad source": {"type": "photo", "source": "ftp", "value": "x"},
			"no type": {"media": "https://a.io/a"},
			"bad type": {"type": "bogus", "media": "https://a.io/a"},
			"not an object": "photo",
			"location range": {"type": "location", "latitude": 99, "longitude": 1},
			"venue no address": {"type": "venue", "latitude": 1, "longitude": 1, "title": "T"},
			"contact no name": {"type": "contact", "phone_number": "+1"},
			"poll 1 option": {"type": "poll", "question": "Q", "options": ["a"]},
			"dice unknown": {"type": "dice", "emoji": "🍎"},
			"quiz without answer": {"type": "quiz", "question": "Q", "options": ["a", "b"]},
			"quiz answer out of range": {
				"type": "quiz",
				"question": "Q",
				"options": ["a", "b"],
				"correct_option_id": 2,
			},
		}
		for name, entry in cases.items():
			with self.subTest(name):
				items, errors = self.one([entry])
				self.assertEqual(items, [], entry)
				self.assertTrue(errors, entry)

	def test_all_invalid_block_yields_errors_not_silence(self):
		items, errors = mr.parse(['{"items": [{"type": "photo"}, {"type": "bogus"}]}'])
		self.assertEqual(items, [])
		self.assertEqual(len(errors), 2)

	def test_poll_and_quiz(self):
		base = {"question": "Q?", "options": ["a", "b", {"text": "c"}]}
		cases = [
			({"type": "poll", **base}, {"quiz": None}),
			(
				{"type": "quiz", **base, "correct_option_id": 1, "explanation": "because", "open_period": 30},
				{"quiz": True, "correct_option_ids": [1], "explanation": "because", "open_period": 30},
			),
			(
				{"type": "poll", **base, "poll_type": "quiz", "correct_option_id": 0},
				{"quiz": True, "correct_option_ids": [0]},
			),
			(
				{"type": "poll", **base, "quiz": True, "correct_option_id": 2},
				{"quiz": True, "correct_option_ids": [2]},
			),
			(
				{"type": "poll", "value": {**base, "type": "quiz", "correct_option_ids": [0, 2]}},
				{"quiz": True, "correct_option_ids": [0, 2]},
			),
		]
		for entry, want in cases:
			with self.subTest(entry):
				items, errors = self.one([entry])
				self.assertEqual(errors, [])
				self.assertEqual(items[0]["type"], "poll")
				self.assertEqual(items[0]["options"], ["a", "b", "c"])
				for k, v in want.items():
					self.assertEqual(items[0].get(k), v)
		items, _ = self.one(
			[{"type": "poll", **base, "is_anonymous": "false", "allows_multiple_answers": True}]
		)
		self.assertEqual((items[0]["is_anonymous"], items[0]["allows_multiple_answers"]), (False, True))

	def test_dice_emoji_variants(self):
		for given, want in (
			("🎲", "🎲"),
			("🎯️", "🎯"),
			("⚽️", "⚽"),
			("🏀", "🏀"),
			("🎳️", "🎳"),
			("slots", "🎰"),
			(None, "🎲"),
		):
			entry = {"type": "dice"} if given is None else {"type": "dice", "emoji": given}
			items, errors = self.one([entry])
			self.assertEqual((items[0]["emoji"], errors), (want, []), given)

	def test_item_options_native_and_short_names(self):
		native = {
			"type": "photo",
			"media": "https://a.io/a.png",
			"has_spoiler": True,
			"show_caption_above_media": True,
			"disable_notification": True,
			"protect_content": True,
			"reply_to_message_id": 5,
			"message_thread_id": 7,
			"message_effect_id": "eff",
		}
		short = {
			"type": "photo",
			"media": "https://a.io/a.png",
			"has_spoiler": True,
			"show_caption_above_media": True,
			"silent": True,
			"protect": True,
			"reply_to": "5",
			"thread_id": 7,
			"effect": "eff",
		}
		a, ea = self.one([native])
		b, eb = self.one([short])
		self.assertEqual((ea, eb), ([], []))
		self.assertEqual(a, b)
		self.assertEqual(
			(a[0]["silent"], a[0]["protect"], a[0]["reply_to"], a[0]["thread_id"], a[0]["effect_id"]),
			(True, True, 5, 7, "eff"),
		)
		for kind in ("location", "contact", "poll", "dice"):  # options apply to text kinds too
			item = {
				"location": {"latitude": 1, "longitude": 2},
				"contact": {"phone_number": "+1", "first_name": "A"},
				"poll": {"question": "Q", "options": ["a", "b"]},
				"dice": {},
			}[kind]
			items, errors = self.one([{"type": kind, **item, "disable_notification": True}])
			self.assertEqual((items[0]["silent"], errors), (True, []), kind)

	def test_unsupported_flags_are_reported(self):
		items, errors = self.one([{"type": "document", "media": "https://a.io/a.pdf", "has_spoiler": True}])
		self.assertNotIn("has_spoiler", items[0])
		self.assertTrue(any("has_spoiler" in e for e in errors))
		items, errors = self.one([{"type": "sticker", "file_id": "s", "caption": "x"}])
		self.assertNotIn("caption", items[0])
		self.assertTrue(errors)

	def test_long_caption_is_kept_for_the_sender(self):
		items, errors = self.one([{"type": "photo", "media": "https://a.io/a", "caption": "c" * 3000}])
		self.assertEqual((len(items[0]["caption"]), errors), (3000, []))

	def test_limits_are_reported(self):
		items, errors = self.one([{"type": "photo", "media": f"https://a.io/{i}"} for i in range(11)])
		self.assertEqual(len(items), 10)
		self.assertTrue(any("11 items" in e for e in errors))
		poll = {"type": "poll", "question": "Q", "options": [str(i) for i in range(13)]}
		items, errors = self.one([poll])
		self.assertEqual(len(items[0]["options"]), 12)
		self.assertTrue(any("13 options" in e for e in errors))

	def test_several_media_blocks_are_merged(self):
		a = json.dumps({"items": [{"type": "photo", "media": "https://a.io/1"}]})
		b = json.dumps({"items": [{"type": "photo", "media": "https://a.io/2"}]})
		items, errors = mr.parse([a, b])
		self.assertEqual([i["value"] for i in items], ["https://a.io/1", "https://a.io/2"])
		self.assertEqual(errors, [])

	def test_trailing_comma_json(self):
		items, errors = mr.validate('{"items": [{"type": "photo", "media": "https://a.io/a",},],}')
		self.assertEqual((len(items), errors), (1, []))


class TestSending(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post,
			http_get=self.api.http_get,
			download_attachments=False,
		)
		self.sender = tp.build_sender(self.adapter)

	def send(self, entries):
		items, errors = mr.validate(entries)
		self.assertEqual(errors, [])
		return mr.send_media_items(
			self.sender, CHAT, items, resolve_file=lambda u: ("f", b"x"), check_url=lambda u: (True, "")
		)

	def test_spoiler_survives_because_it_is_not_albumed(self):
		self.send(
			[
				{"type": "photo", "media": "https://a.io/1", "has_spoiler": True},
				{"type": "photo", "media": "https://a.io/2"},
				{"type": "photo", "media": "https://a.io/3"},
			]
		)
		first_call = self.api.of("sendPhoto")[0]["payload"]
		self.assertTrue(first_call["has_spoiler"])
		self.assertEqual(len(self.api.last("sendMediaGroup")["payload"]["media"]), 2)

	def test_plain_photos_still_album(self):
		self.send([{"type": "photo", "media": f"https://a.io/{i}"} for i in range(3)])
		self.assertEqual(len(self.api.of("sendMediaGroup")), 1)
		self.assertEqual(self.api.of("sendPhoto"), [])

	def test_over_long_caption_goes_alone_and_overflow_is_follow_up_text(self):
		self.send(
			[
				{"type": "photo", "media": "https://a.io/1", "caption": "w " * 800},
				{"type": "photo", "media": "https://a.io/2"},
			]
		)
		self.assertEqual(self.api.of("sendMediaGroup"), [])
		self.assertEqual(len(self.api.of("sendPhoto")), 2)
		self.assertTrue(self.api.of("sendMessage"))

	def test_options_reach_the_api(self):
		self.send(
			[
				{
					"type": "video",
					"media": "https://a.io/v",
					"silent": True,
					"protect": True,
					"reply_to": 9,
					"thread_id": 3,
					"effect": "5104841245755180586",
					"show_caption_above_media": True,
					"caption": "c",
				},
				{
					"type": "location",
					"latitude": 1,
					"longitude": 2,
					"disable_notification": True,
					"thread_id": 4,
				},
			]
		)
		video = self.api.last("sendVideo")["payload"]
		self.assertEqual(
			(video["disable_notification"], video["protect_content"], video["message_thread_id"]),
			(True, True, 3),
		)
		self.assertEqual(video["message_effect_id"], "5104841245755180586")
		self.assertTrue(video["show_caption_above_media"])
		self.assertEqual(video["reply_parameters"]["message_id"], 9)
		loc = self.api.last("sendLocation")["payload"]
		self.assertEqual((loc["disable_notification"], loc["message_thread_id"]), (True, 4))

	def test_quiz_payload(self):
		self.send(
			[
				{
					"type": "quiz",
					"question": "Q?",
					"options": ["a", "b"],
					"correct_option_id": 1,
					"explanation": "why",
					"open_period": 20,
					"is_anonymous": False,
				}
			]
		)
		poll = self.api.last("sendPoll")["payload"]
		self.assertEqual(poll["type"], "quiz")
		self.assertEqual(
			(poll["correct_option_id"], poll["explanation"], poll["open_period"]), (1, "why", 20)
		)
		self.assertFalse(poll["is_anonymous"])
		self.send([{"type": "poll", "question": "Q?", "options": ["a", "b"]}])
		self.assertNotIn("type", self.api.last("sendPoll")["payload"])

	def test_contact_vcard_and_dice(self):
		self.send(
			[
				{"type": "contact", "phone_number": "+1", "first_name": "A", "vcard": "BEGIN:VCARD"},
				{"type": "dice", "emoji": "🎯️"},
			]
		)
		self.assertEqual(self.api.last("sendContact")["payload"]["vcard"], "BEGIN:VCARD")
		self.assertEqual(self.api.last("sendDice")["payload"]["emoji"], "🎯")


class TestMakePartsFeedback(unittest.TestCase):
	def setUp(self):
		blocks._LOCAL.d.clear()
		self.event = SimpleNamespace(conversation_id=str(CHAT), name="EV1", gateway="GW")
		self.scope = tp.reply_scope(GW, self.event)

	def media(self, obj):
		return "```telegram-media\n" + (obj if isinstance(obj, str) else json.dumps(obj)) + "\n```"

	def buttons(self, obj):
		return "```telegram-buttons\n" + (obj if isinstance(obj, str) else json.dumps(obj)) + "\n```"

	def test_invalid_blocks_are_reported_everywhere(self):
		text = "Done." + "\n" + self.media({"items": [{"type": "photo"}]}) + "\n" + self.buttons(btn())
		with self.assertLogs("huf.telegram.blocks", level="WARNING") as logs:
			parts = tp.make_parts(text, self.scope)
		self.assertEqual(parts, ["Done."])
		self.assertIn("media: photo", logs.output[0])
		self.assertIn("buttons:", logs.output[0])
		# (b) note on the Gateway Event
		calls = []
		ev = SimpleNamespace(db_set=lambda *a, **k: calls.append(a))
		blocks.attach_to_event(ev, self.scope)
		self.assertEqual(calls[0][0], "delivery_error")
		self.assertIn("Reply blocks: media: photo", calls[0][1])
		# (c) fed back to the agent exactly once, on its next run in this conversation
		line = tac.event_context(SimpleNamespace(conversation_id=str(CHAT), gateway="GW", raw_payload={}), GW)
		self.assertIn("Your last reply had invalid buttons/media: media: photo", line)
		self.assertIn("inline_keyboard", line)
		again = tac.event_context(
			SimpleNamespace(conversation_id=str(CHAT), gateway="GW", raw_payload={}), GW
		)
		self.assertNotIn("Your last reply", again)

	def test_feedback_is_per_conversation(self):
		tp.make_parts(self.media("{nope"), self.scope)
		other = tac.event_context(SimpleNamespace(conversation_id="999", gateway="GW", raw_payload={}), GW)
		self.assertNotIn("Your last reply", other)

	def test_clean_reply_records_nothing(self):
		with self.assertNoLogs("huf.telegram.blocks", level="WARNING"):
			tp.make_parts("Hello\n" + self.buttons(btn(callback_data="x")), self.scope)
		self.assertEqual(blocks.take_errors(self.scope), [])
		self.assertEqual(blocks.feedback_line("GW", str(CHAT)), "")

	def test_reply_that_would_be_empty_says_what_was_wrong(self):
		parts = tp.make_parts(self.media({"items": [{"type": "photo"}, {"type": "bogus"}]}), self.scope)
		self.assertEqual(len(parts), 1)
		self.assertIn("were invalid and not sent", parts[0])
		self.assertIn("photo", parts[0])
		parts = tp.make_parts(self.buttons("{broken"), self.scope)
		self.assertIn("invalid JSON", parts[0])

	def test_valid_buttons_without_text_keep_placeholder_and_media_only_stays_silent(self):
		self.assertEqual(
			tp.make_parts(self.buttons(btn(callback_data="x")), self.scope), [tb.PLACEHOLDER_TEXT]
		)
		parts = tp.make_parts(
			self.media({"items": [{"type": "photo", "media": "https://a.io/a"}]}), self.scope
		)
		self.assertTrue(mr.is_media_only(parts[0]))

	def test_partial_invalid_block_still_sends_the_valid_part(self):
		parts = tp.make_parts(
			"Look\n"
			+ self.media({"items": [{"type": "photo", "media": "https://a.io/a"}, {"type": "photo"}]}),
			self.scope,
		)
		self.assertEqual(parts, ["Look"])
		self.assertEqual(len(mr.take_items(parts, scope=self.scope)), 1)
		self.assertTrue(blocks.take_errors(self.scope))

	def test_fence_variants_never_leak_json_into_the_text(self):
		body = json.dumps(btn(callback_data="x"))
		for text in (
			f"Hi\n~~~telegram-buttons\n{body}\n~~~",
			f"Hi\n```json telegram-buttons\n{body}\n```",
			f"Hi\n```Telegram-Buttons\n{body}\n```",
			f"Hi\n```telegram-buttons\n{body}",
			f"Hi\n```telegram-buttons\n{body[:20]}",
		):
			with self.subTest(text):
				blocks._LOCAL.d.clear()
				parts = tp.make_parts(text, self.scope)
				self.assertEqual(parts, ["Hi"])

	def test_spoken_text_strips_every_variant(self):
		body = json.dumps(btn(callback_data="x"))
		self.assertEqual(tp.spoken_text(f"Hi\n~~~telegram-buttons\n{body}\n~~~\nthere"), "Hi\nthere")

	def test_keyboard_goes_on_the_real_text_not_the_failure_note(self):
		api = FakeBotApi()
		adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET}, http_post=api.http_post, http_get=api.http_get
		)
		sender = tp.build_sender(adapter)
		scope = self.scope
		parts = tp.make_parts(
			"Text\n"
			+ self.media({"items": [{"type": "photo", "media": "https://a.io/a"}]})
			+ "\n"
			+ self.buttons(btn(callback_data="x")),
			scope,
		)
		api.queue("sendPhoto", api.error("Bad Request: wrong file identifier", 400))
		markup = {"inline_keyboard": [[{"text": "B", "callback_data": "x"}]]}
		tp.send_parts_with(sender, CHAT, parts, markup=markup, media=True, scope=scope)
		msgs = api.of("sendMessage")
		self.assertEqual(len(msgs), 2)
		self.assertIn("reply_markup", msgs[0]["payload"])  # the real text
		self.assertNotIn("reply_markup", msgs[1]["payload"])  # the "Could not send" note
		self.assertIn("media not sent", "; ".join(blocks.take_errors(scope)))

	def test_markup_for_failure_is_not_silent(self):
		tp.make_parts("Hi\n" + self.buttons(btn(callback_data="x")), self.scope)

		def boom(payload):
			raise RuntimeError("signer down")

		self.assertIsNone(tb.markup_for(self.event, GW, "Hi", signer=boom))
		self.assertIn("could not be attached", " ".join(blocks.take_errors(self.scope)))

	def test_markup_survives_a_trailing_failure_note_on_retry(self):
		parts = tp.make_parts("Hi\n" + self.buttons(btn(callback_data="x")), self.scope)
		noted = "\n\n".join([*parts, mr.failure_note(["photo: boom"])])
		markup = tb.markup_for(self.event, GW, noted, signer=lambda p: p)
		self.assertEqual(markup["inline_keyboard"][0][0]["text"], "B")


class TestInstructionsMatchValidators(unittest.TestCase):
	TEXTS = (tb.AGENT_INSTRUCTIONS, tac.MEDIA_TEXT)
	ACCEPTED = tb.ACCEPTED_KEYS | mr.ACCEPTED_KEYS
	PROSE = {"telegram_admin"}

	def tokens(self, text):
		return set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text))

	def test_every_underscore_name_in_the_instructions_is_accepted_by_a_validator(self):
		for text in self.TEXTS:
			unknown = {t for t in self.tokens(text) if t not in self.ACCEPTED} - self.PROSE
			self.assertEqual(unknown, set(), text[:40])

	def test_every_documented_type_and_kind_is_listed(self):
		joined = " ".join(self.TEXTS)
		for name in (*mr.FILE_TYPES, *mr.TEXT_TYPES, *tb.BUTTON_KINDS, "quiz", "remove_keyboard", "keyboard"):
			self.assertIn(name, joined, name)
		for field in (
			"has_spoiler",
			"show_caption_above_media",
			"open_period",
			"correct_option_id",
			"explanation",
		):
			self.assertIn(field, joined, field)

	def test_fields_in_the_examples_survive_validation(self):
		example = json.loads(
			re.search(
				r"\{\"inline_keyboard\".*?\}\]\],\"once\":true\}",
				tb.AGENT_INSTRUCTIONS.replace("https://...", "https://x.io"),
			).group(0)
		)
		spec, errors = tb.validate(example)
		self.assertEqual(errors, [])
		self.assertTrue(spec["once"])
		reply = json.loads(re.search(r"\{\"keyboard\".*?\"\.\.\.\"\}", tb.AGENT_INSTRUCTIONS).group(0))
		spec, errors = tb.validate(reply)
		self.assertEqual(errors, [])

	def test_texts_fit_the_budget(self):
		everything = SimpleNamespace(
			telegram_agent_allow_group_admin=1,
			telegram_agent_allow_business=1,
			telegram_agent_allow_profile=1,
			voice_reply_mode="Text and voice",
		)
		self.assertLessEqual(len(tac.build_instructions(everything)), tac.MAX_CHARS)
		self.assertLessEqual(tac.MAX_CHARS, 2000)
		self.assertIn("```telegram-media", tac.build_instructions(everything))

	def test_no_stale_claims(self):
		admin = tac.FLAG_TEXT[tac.FLAG_GROUP_ADMIN]
		self.assertNotIn("confirm", admin)
		self.assertIn("bound admin chat", admin)
		self.assertIn("human Approve", admin)
		self.assertNotIn("topic", tac.TOOL_TEXT.lower())
		self.assertNotIn("reactions are recorded", tac.MEDIA_TEXT)
		self.assertFalse(hasattr(mr, "AGENT_INSTRUCTIONS"))


if __name__ == "__main__":
	unittest.main()
