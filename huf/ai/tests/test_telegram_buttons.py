"""Telegram buttons: agent spec parse/validate/strip, markup per kind, callback flow (answer first, once/edit, dup, stale)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from huf.ai.gateway_adapters import telegram_buttons as tb
from huf.ai.gateway_adapters import telegram_inbound
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi

CHAT = 111
NOW = 1760000100.0


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)

	def delete_value(self, key):
		self.d.pop(key, None)


def block(obj) -> str:
	return "```telegram-buttons\n" + json.dumps(obj) + "\n```"


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post,
			http_get=self.api.http_get,
			download_attachments=False,
		)
		self.cache = FakeCache()
		self.sign = lambda p: self.adapter.sign_callback_data(p, CHAT)

	def callback_update(self, data, cqid="cq1", date=1760000000, label="Approve", message_id=55):
		return telegram_inbound.parse_update(
			{
				"update_id": 9,
				"callback_query": {
					"id": cqid,
					"from": {"id": CHAT, "is_bot": False, "first_name": "J"},
					"data": data,
					"message": {
						"message_id": message_id,
						"date": date,
						"chat": {"id": CHAT, "type": "private"},
						"reply_markup": {"inline_keyboard": [[{"text": label, "callback_data": data}]]},
					},
				},
			}
		)

	def press(self, spec, **kw):
		markup = tb.build_markup(tb.validate(spec)[0], self.sign)
		data = markup["inline_keyboard"][0][0]["callback_data"]
		parsed = self.callback_update(data, **kw.pop("upd", {}))
		payload = self.adapter.verify_callback_data(parsed.callback_data, parsed.chat_id)
		return parsed, tb.handle_callback(
			parsed, payload, self.adapter.sender, "GW", cache=self.cache, now=NOW, **kw
		)


class TestParse(unittest.TestCase):
	def test_extract_strips_and_validates(self):
		spec = {"rows": [[{"text": "Yes", "callback": "y"}]], "once": True}
		visible, parsed, errors = tb.extract("Sure?\n\n" + block(spec) + "\n")
		self.assertEqual(visible, "Sure?")
		self.assertEqual(parsed["mode"], "rows")
		self.assertTrue(parsed["once"])
		self.assertEqual(errors, [])

	def test_no_block_untouched(self):
		self.assertEqual(tb.extract("hello"), ("hello", None, []))

	def test_bad_json_stripped_no_spec(self):
		visible, spec, errors = tb.extract("Hi\n```telegram-buttons\n{nope\n```")
		self.assertEqual(visible, "Hi")
		self.assertIsNone(spec)
		self.assertTrue(errors)

	def test_limits(self):
		many = [[{"text": str(i), "callback": f"c{i}"} for i in range(20)] for _ in range(15)]
		spec, errors = tb.validate({"rows": many})
		self.assertTrue(any("Telegram allows" in e for e in errors))
		self.assertLessEqual(max(len(r) for r in spec["rows"]), tb.MAX_PER_ROW)
		self.assertLessEqual(sum(len(r) for r in spec["rows"]), tb.MAX_BUTTONS)

	def test_callback_id_size_and_kind_exclusivity(self):
		spec, errors = tb.validate(
			{
				"rows": [
					[
						{"text": "long", "callback": "x" * (tb.MAX_ID_BYTES + 1)},
						{"text": "both", "callback": "a", "url": "https://x.io"},
						{"text": "ok", "callback": "x" * tb.MAX_ID_BYTES},
					]
				]
			}
		)
		self.assertEqual([b["text"] for b in spec["rows"][0]], ["ok"])
		self.assertEqual(len([e for e in errors if "callback_data must be" in e or "exactly one" in e]), 2)

	def test_url_schemes(self):
		spec, _ = tb.validate(
			{
				"rows": [
					[
						{"text": "bad", "url": "javascript:alert(1)"},
						{"text": "wa", "web_app": "http://x.io"},
						{"text": "good", "url": "https://x.io"},
					]
				]
			}
		)
		self.assertEqual([b["text"] for b in spec["rows"][0]], ["good"])

	def test_empty_spec_rejected(self):
		self.assertIsNone(tb.validate({})[0])
		self.assertIsNone(tb.validate("[1]")[0])


class TestMarkup(Base):
	def test_each_kind(self):
		spec, _ = tb.validate(
			{
				"rows": [
					[
						{"text": "c", "callback": "go"},
						{"text": "u", "url": "https://x.io"},
						{"text": "w", "web_app": "https://x.io/app"},
						{"text": "s", "switch_inline": "q"},
						{"text": "s2", "switch_inline": "q", "current_chat": True},
						{"text": "cp", "copy_text": "CODE"},
						{"text": "l", "login_url": "https://x.io/login"},
					]
				]
			}
		)
		row = tb.build_markup(spec, self.sign)["inline_keyboard"][0]
		self.assertLessEqual(len(row[0]["callback_data"].encode()), 64)
		self.assertEqual(row[1]["url"], "https://x.io")
		self.assertEqual(row[2]["web_app"], {"url": "https://x.io/app"})
		self.assertEqual(row[3]["switch_inline_query"], "q")
		self.assertEqual(row[4]["switch_inline_query_current_chat"], "q")
		self.assertEqual(row[5]["copy_text"], {"text": "CODE"})
		self.assertEqual(row[6]["login_url"], {"url": "https://x.io/login"})

	def test_max_id_signed_fits_64(self):
		spec, _ = tb.validate(
			{"rows": [[{"text": "m", "callback": "é" * (tb.MAX_ID_BYTES // 2)}]], "once": True, "edit": True}
		)
		self.assertLessEqual(
			len(tb.build_markup(spec, self.sign)["inline_keyboard"][0][0]["callback_data"].encode()), 64
		)

	def test_reply_keyboard_and_remove(self):
		spec, _ = tb.validate(
			{
				"reply_keyboard": {
					"rows": [["A", {"text": "Me", "request_contact": True}]],
					"one_time": True,
					"placeholder": "pick",
				}
			}
		)
		m = tb.build_markup(spec, self.sign)
		self.assertTrue(m["one_time_keyboard"])
		self.assertTrue(m["resize_keyboard"])
		self.assertEqual(m["input_field_placeholder"], "pick")
		self.assertEqual(m["keyboard"][0][1], {"text": "Me", "request_contact": True})
		self.assertEqual(
			tb.build_markup(tb.validate({"remove_keyboard": True})[0], self.sign), {"remove_keyboard": True}
		)

	def test_pipeline_end_to_end_markup_on_last_part(self):
		long_text = "para.\n\n" * 1200
		spec = {"rows": [[{"text": "Yes", "callback": "y"}]]}
		parts = tp.make_parts(long_text + block(spec))
		self.assertTrue(all("telegram-buttons" not in p for p in parts))
		import unittest.mock as m

		event = SimpleNamespace(conversation_id=str(CHAT), name="EV1")
		with m.patch.object(tb, "_cache", return_value=self.cache):
			tp_parts = tp.make_parts(long_text + block(spec), tp.reply_scope(None, event))
			markup = tb.markup_for(event, None, "\n\n".join(tp_parts), signer=self.sign, cache=self.cache)
			retry = tb.markup_for(event, None, tp_parts[-1], signer=self.sign, cache=self.cache)
		self.assertIsNotNone(markup)
		self.assertIsNotNone(retry)
		sender = tp.build_sender(self.adapter)
		tp.send_parts_with(sender, CHAT, tp_parts, markup=markup)
		calls = self.api.of("sendMessage")
		self.assertNotIn("reply_markup", calls[0]["payload"])
		self.assertIn("reply_markup", calls[-1]["payload"])

	def test_buttons_only_gets_placeholder(self):
		with __import__("unittest.mock").mock.patch.object(tb, "_cache", return_value=self.cache):
			self.assertEqual(
				tp.make_parts(block({"rows": [[{"text": "a", "callback": "a"}]]})), [tb.PLACEHOLDER_TEXT]
			)


class TestCallback(Base):
	SPEC = {"rows": [[{"text": "Approve", "callback": "approve:42"}]]}

	def test_answer_first_then_ingest_with_label(self):
		_, d = self.press(self.SPEC)
		self.assertEqual(self.api.calls[0]["method"], "answerCallbackQuery")
		self.assertEqual(d["action"], "ingest")
		self.assertEqual(d["text"], "[button: Approve]\ncallback_data: approve:42")
		self.assertEqual(d["edit_message_id"], "")

	def test_answer_failure_does_not_block(self):
		self.api.queue("answerCallbackQuery", FakeBotApi.error("query is too old", 400))
		_, d = self.press(self.SPEC)
		self.assertEqual(d["action"], "ingest")

	def test_once_removes_keyboard_and_blocks_second_tap(self):
		spec = {**self.SPEC, "once": True}
		parsed, d = self.press(spec)
		self.assertEqual(d["action"], "ingest")
		self.assertEqual(
			[c["method"] for c in self.api.calls], ["answerCallbackQuery", "editMessageReplyMarkup"]
		)
		self.assertEqual(
			self.api.last("editMessageReplyMarkup")["payload"]["reply_markup"], {"inline_keyboard": []}
		)
		parsed2 = self.callback_update(parsed.callback_data, cqid="cq2")
		payload = self.adapter.verify_callback_data(parsed2.callback_data, parsed2.chat_id)
		d2 = tb.handle_callback(parsed2, payload, self.adapter.sender, "GW", cache=self.cache, now=NOW)
		self.assertEqual((d2["action"], d2["reason"]), ("ignore", "already_used"))
		self.assertEqual(self.api.last("answerCallbackQuery")["payload"]["text"], tb.MSG_USED)

	def test_duplicate_callback_query_id_ignored(self):
		parsed, d = self.press(self.SPEC)
		payload = self.adapter.verify_callback_data(parsed.callback_data, parsed.chat_id)
		d2 = tb.handle_callback(parsed, payload, self.adapter.sender, "GW", cache=self.cache, now=NOW)
		self.assertEqual(d2["reason"], "duplicate")
		self.assertEqual(d2["action"], "ignore")  # still answered so the spinner stops

	def test_stale_and_unknown_message_toast_no_run(self):
		_, d = (
			self.press(self.SPEC, upd={"date": 1760000000 - 49 * 3600}, now=None) if False else (None, None)
		)
		parsed = self.callback_update(
			self.sign(tb.encode_payload("x", once=False, edit=False)), date=1760000000 - 49 * 3600
		)
		d = tb.handle_callback(
			parsed,
			self.adapter.verify_callback_data(parsed.callback_data, parsed.chat_id),
			self.adapter.sender,
			"GW",
			cache=self.cache,
			now=NOW,
		)
		self.assertEqual((d["action"], d["reason"]), ("ignore", "stale"))
		self.assertEqual(self.api.calls[0]["payload"]["text"], tb.MSG_STALE)
		parsed = self.callback_update(
			self.sign(tb.encode_payload("x", once=False, edit=False)), date=0, cqid="cq9"
		)
		d = tb.handle_callback(parsed, "b:--:x", self.adapter.sender, "GW", cache=self.cache, now=NOW)
		self.assertEqual(d["reason"], "stale")

	def test_tampered_signature_answered_not_ingested(self):
		parsed = self.callback_update("b:--:approve|AAAAAAAAAAAA")
		payload = self.adapter.verify_callback_data(parsed.callback_data, parsed.chat_id)
		self.assertIsNone(payload)
		d = tb.handle_callback(parsed, payload, self.adapter.sender, "GW", cache=self.cache, now=NOW)
		self.assertEqual((d["action"], d["reason"]), ("ignore", "invalid_signature"))
		self.assertEqual(self.api.calls[0]["method"], "answerCallbackQuery")

	def test_wrong_chat_context_rejected(self):
		data = self.adapter.sign_callback_data("b:--:x", 999)
		self.assertIsNone(self.adapter.verify_callback_data(data, CHAT))

	def test_foreign_payload_passes_through(self):
		data = self.adapter.sign_callback_data("approve:42", CHAT)
		parsed = self.callback_update(data)
		d = tb.handle_callback(parsed, "approve:42", self.adapter.sender, "GW", cache=self.cache, now=NOW)
		self.assertEqual((d["action"], d["text"]), ("ingest", "approve:42"))


class TestEdit(Base):
	def event(self, edit_id):
		return SimpleNamespace(
			conversation_id=str(CHAT), raw_payload={"telegram_meta": {"edit_message_id": edit_id}}
		)

	def test_edit_decision_flag(self):
		_, d = self.press({**TestCallback.SPEC, "edit": True})
		self.assertEqual(d["edit_message_id"], "55")

	def test_try_edit_edits_in_place(self):
		sender = tp.build_sender(self.adapter)
		res = tb.try_edit(
			sender, self.event("55"), ["Done"], {"inline_keyboard": [[{"text": "x", "url": "https://x.io"}]]}
		)
		self.assertEqual(res.provider_message_id, "55")
		call = self.api.last("editMessageText")["payload"]
		self.assertEqual(call["message_id"], 55)
		self.assertIn("inline_keyboard", call["reply_markup"])
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_try_edit_falls_back(self):
		sender = tp.build_sender(self.adapter)
		self.assertIsNone(tb.try_edit(sender, self.event(""), ["x"], None))
		self.assertIsNone(tb.try_edit(sender, self.event("55"), ["a", "b"], None))
		self.assertIsNone(tb.try_edit(sender, self.event("55"), ["a"], {"remove_keyboard": True}))
		self.api.queue("editMessageText", FakeBotApi.error("message can't be edited", 400))
		self.assertIsNone(tb.try_edit(sender, self.event("55"), ["a"], None))


if __name__ == "__main__":
	unittest.main()


class TestNativeUrlShapes(unittest.TestCase):
	def test_web_app_and_login_url_accept_the_telegram_native_dict_shape(self):
		from huf.ai.gateway_adapters import telegram_buttons as tb

		for kind in ("web_app", "login_url"):
			for value in ("https://x.example/p?a=1", {"url": "https://x.example/p?a=1"}):
				spec, errors = tb.validate({"rows": [[{"text": "Open", kind: value}]]})
				self.assertEqual(errors, [], (kind, value))
				self.assertEqual(spec["rows"][0][0][kind], {"url": "https://x.example/p?a=1"})

	def test_native_shape_without_https_url_is_still_refused(self):
		from huf.ai.gateway_adapters import telegram_buttons as tb

		for bad in ({"url": "http://x.example"}, {"url": ""}, {"nope": 1}, {}):
			spec, errors = tb.validate({"rows": [[{"text": "Open", "web_app": bad}]]})
			self.assertIsNone(spec)
			self.assertTrue(errors)
