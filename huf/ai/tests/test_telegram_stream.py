"""Telegram streaming drafts: throttle, coalescing, draft_id, private-only, flood control, stop, failure safety."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from huf.ai.gateway_adapters import telegram_ingest
from huf.ai.gateway_adapters import telegram_stream as ts
from huf.ai.gateway_adapters.telegram_client import TelegramApiError, TelegramBotClient
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi

CHAT = 555


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)


class Clock:
	def __init__(self):
		self.t = 100.0

	def __call__(self):
		return self.t


def make_sender(api):
	return TelegramSender(TelegramBotClient(TOKEN, http_post=api.http_post, http_get=api.http_get))


def updater(api=None, clock=None, **kw):
	api = api or FakeBotApi()
	clock = clock or Clock()
	return ts.DraftUpdater(make_sender(api), CHAT, 7, clock=clock, **kw), api, clock


class TestDraftUpdater(unittest.TestCase):
	def test_throttle_and_coalescing(self):
		u, api, clock = updater()
		self.assertTrue(u.push("a"))
		clock.t += 0.2
		self.assertFalse(u.push("ab"))
		clock.t += 0.2
		self.assertFalse(u.push("abc"))
		self.assertEqual(len(api.of("sendMessageDraft")), 1)
		clock.t += 1.0
		self.assertTrue(u.flush())
		calls = api.of("sendMessageDraft")
		self.assertEqual(len(calls), 2)
		self.assertEqual(calls[-1]["payload"]["text"], "abc")  # only the newest text, deltas coalesced

	def test_identical_text_not_resent(self):
		u, api, clock = updater()
		u.push("same")
		clock.t += 5
		self.assertFalse(u.push("same"))
		self.assertEqual(len(api.of("sendMessageDraft")), 1)

	def test_draft_id_nonzero_and_stable(self):
		self.assertNotEqual(ts.draft_id_for("EVT-1"), 0)
		self.assertEqual(ts.draft_id_for("EVT-1"), ts.draft_id_for("EVT-1"))
		self.assertNotEqual(ts.draft_id_for("EVT-1"), ts.draft_id_for("EVT-2"))
		with self.assertRaises(ValueError):
			ts.DraftUpdater(None, CHAT, 0)
		u, api, clock = updater()
		u.push("a")
		clock.t += 2
		u.push("ab")
		ids = {c["payload"]["draft_id"] for c in api.of("sendMessageDraft")}
		self.assertEqual(ids, {7})

	def test_payload_params(self):
		u, api, _ = updater(thread_id=9, keep_on_stop=True)
		u.push("hi")
		p = api.last("sendMessageDraft")["payload"]
		self.assertEqual(
			(p["chat_id"], p["message_thread_id"], p["can_stop"], p["keep_on_stop"]), (CHAT, 9, True, True)
		)
		self.assertNotIn("parse_mode", p)

	def test_start_sends_empty_thinking(self):
		u, api, _ = updater()
		self.assertTrue(u.start())
		self.assertEqual(api.last("sendMessageDraft")["payload"]["text"], "")

	def test_long_text_tail_fits_limit(self):
		u, api, _ = updater()
		u.push("x" * 5000 + "END")
		text = api.last("sendMessageDraft")["payload"]["text"]
		self.assertEqual(len(text), 4096)
		self.assertTrue(text.endswith("END"))

	def test_flood_control_pauses_then_resumes(self):
		api = FakeBotApi()
		api.queue("sendMessageDraft", FakeBotApi.error("Too Many Requests", 429, retry_after=10))
		u, _, clock = updater(api)
		self.assertFalse(u.push("a"))
		self.assertFalse(u.disabled)
		clock.t += 5
		self.assertFalse(u.push("ab"))  # still inside retry_after
		self.assertEqual(len(api.of("sendMessageDraft")), 1)
		clock.t += 10
		self.assertTrue(u.push("abc"))
		self.assertEqual(api.last("sendMessageDraft")["payload"]["text"], "abc")

	def test_blocked_disables_and_errors_never_raise(self):
		api = FakeBotApi()
		api.queue("sendMessageDraft", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
		u, _, clock = updater(api)
		self.assertFalse(u.push("a"))
		self.assertTrue(u.disabled)
		clock.t += 5
		self.assertFalse(u.push("b"))
		self.assertEqual(len(api.of("sendMessageDraft")), 1)

	def test_repeated_errors_disable(self):
		api = FakeBotApi()
		api.queue("sendMessageDraft", *[FakeBotApi.error("Bad Request: boom", 400)] * 3)
		u, _, clock = updater(api)
		for i in range(3):
			clock.t += 2
			u.push(f"t{i}")
		self.assertTrue(u.disabled)


class TestEnabled(unittest.TestCase):
	def test_private_only_and_flag(self):
		on, off = {"telegram_streaming": 1}, {"telegram_streaming": 0}
		self.assertFalse(ts.streaming_enabled("private", {}))
		self.assertTrue(ts.streaming_enabled("private", on))
		self.assertFalse(ts.streaming_enabled("group", on))
		self.assertFalse(ts.streaming_enabled("supergroup", on))
		self.assertFalse(ts.streaming_enabled("channel", on))
		self.assertFalse(ts.streaming_enabled("private", off))

	def test_hook_follows_the_gateway_switch_not_site_config(self):
		from unittest import mock

		import huf.ai.gateway_adapters.telegram_stream_hooks as hooks

		event = SimpleNamespace(raw_payload={}, conversation_id="c", name="e")
		for flag, expect_none in ((0, True), (1, False)):
			gw = SimpleNamespace(name="gw", get=lambda k, d=None, f=flag: f if k == "telegram_streaming" else d)
			with (
				mock.patch("frappe.conf", {"huf_telegram_streaming": 1}, create=True),
				mock.patch("huf.ai.gateway_webhook.get_gateway_adapter"),
				mock.patch("huf.ai.gateway_webhook.event_contact_name"),
				mock.patch("huf.ai.gateway_adapters.telegram_pipeline.reply_target", return_value=(None, None)),
				mock.patch("huf.ai.gateway_adapters.telegram_pipeline.build_sender"),
				mock.patch.object(ts, "make_runner", return_value="runner"),
			):
				self.assertEqual(hooks.agent_runner(event, gw) is None, expect_none)

	def test_event_chat_type(self):
		ev = SimpleNamespace(raw_payload={"telegram_meta": {"chat_type": "group"}})
		self.assertEqual(ts.event_chat_type(ev), "group")
		self.assertEqual(ts.event_chat_type(SimpleNamespace(raw_payload={})), "private")


def fake_stream(chunks, hook=None):
	def factory(**kwargs):
		async def gen():
			for c in chunks:
				if hook:
					hook(c)
				yield c

		return gen()

	return factory


COMPLETE = {
	"type": "complete",
	"response": "final answer",
	"full_response": "final answer",
	"success": True,
	"agent_run_id": "RUN-1",
}
CHUNKS = [
	{"type": "run_started", "agent_run_id": "RUN-1"},
	{"type": "delta", "content": "hel", "full_response": "hel"},
	{"type": "delta", "content": "lo", "full_response": "hello"},
	COMPLETE,
]


class TestRunner(unittest.TestCase):
	def _runner(self, chunks, api=None, cache=None, hook=None, keep=False):
		api = api or FakeBotApi()
		cache = cache or FakeCache()
		clock = Clock()
		r = ts.make_runner(
			make_sender(api),
			CHAT,
			"EVT-1",
			"GW",
			thread_id=3,
			keep_on_stop=keep,
			cache=cache,
			stream_factory=fake_stream(chunks, hook),
			clock=clock,
			min_interval=0,
		)
		return r, api, cache

	def test_streams_then_returns_complete(self):
		r, api, cache = self._runner(CHUNKS)
		result = r(agent_name="a", prompt="p", now=True, external_id="x")
		self.assertEqual(result["response"], "final answer")
		texts = [c["payload"]["text"] for c in api.of("sendMessageDraft")]
		self.assertEqual(texts, ["", "hel", "hello"])
		self.assertEqual(
			{c["payload"]["draft_id"] for c in api.of("sendMessageDraft")}, {ts.draft_id_for("EVT-1")}
		)
		self.assertEqual(api.of("sendMessage"), [])  # final goes through the pipeline, not here
		self.assertEqual(cache.get_value(ts._key("GW", CHAT)) in ({}, None), True)

	def test_placeholder_keeps_typing_alive_until_real_text_is_shown(self):
		seen = []
		cache = FakeCache()

		def hook(chunk):
			seen.append(dict(ts.StreamState("GW", CHAT, cache).get()))

		r, _, _ = self._runner(CHUNKS, cache=cache, hook=hook)
		r(agent_name="a", prompt="p")
		self.assertTrue(seen[0].get("draft_id"))  # run_started: placeholder only
		self.assertFalse(seen[0].get("draft_text"))  # keepalive skip callback must stay False
		self.assertTrue(any(s.get("draft_text") for s in seen[1:]))

	def test_failing_drafts_never_lose_final(self):
		api = FakeBotApi()
		api.queue("sendMessageDraft", *[FakeBotApi.error("Bad Request", 400)] * 10)
		r, _, _ = self._runner(CHUNKS, api=api)
		self.assertEqual(r(agent_name="a", prompt="p")["response"], "final answer")

	def test_stream_error_chunk_marks_failure(self):
		r, _, _ = self._runner(
			[{"type": "run_started", "agent_run_id": "R"}, {"type": "error", "error": "boom"}]
		)
		out = r(agent_name="a", prompt="p")
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "boom")

	def test_stream_without_result(self):
		r, _, _ = self._runner([])
		self.assertFalse(r(agent_name="a", prompt="p")["success"])

	def test_stop_delivers_nothing(self):
		def hook(chunk):
			if chunk.get("full_response") == "hel":
				cache.set_value(
					ts._key("GW", CHAT), {**cache.get_value(ts._key("GW", CHAT)), "stopped": True}
				)

		cache = FakeCache()
		r, api, _ = self._runner(
			CHUNKS[:2]
			+ [{"type": "delta", "full_response": "hello"}, {"type": "error", "error": "Cancelled by user"}],
			cache=cache,
			hook=hook,
		)
		out = r(agent_name="a", prompt="p")
		self.assertEqual(out["response"], ts.NO_REPLY)
		texts = [c["payload"]["text"] for c in api.of("sendMessageDraft")]
		self.assertNotIn("hello", texts)  # no draft after the stop

	def test_stop_keep_on_stop_returns_partial(self):
		def hook(chunk):
			if chunk.get("full_response") == "hel":
				cache.set_value(
					ts._key("GW", CHAT), {**cache.get_value(ts._key("GW", CHAT)), "stopped": True}
				)

		cache = FakeCache()
		r, _, _ = self._runner(
			CHUNKS[:2] + [{"type": "error", "error": "Cancelled by user"}], cache=cache, hook=hook, keep=True
		)
		out = r(agent_name="a", prompt="p")
		self.assertTrue(out["success"])
		self.assertEqual(out["response"], "hel")


class TestStopHandler(unittest.TestCase):
	def _parsed(self, draft_id=7):
		return SimpleNamespace(
			kind="unsupported",
			chat_id=str(CHAT),
			raw={
				"update_id": 1,
				"stopped_message_generation": {"chat": {"id": CHAT, "type": "private"}, "draft_id": draft_id},
			},
		)

	def test_stop_marks_state_and_cancels_run(self):
		cache, cancelled = FakeCache(), []
		ts.StreamState("GW", CHAT, cache).update(draft_id=7, run_id="RUN-1", stopped=False)
		gw = SimpleNamespace(name="GW", execution_user=None)
		from unittest import mock

		with mock.patch("frappe.set_user"), mock.patch("frappe.session", SimpleNamespace(user="Guest")):
			out = ts.handle_stopped(gw, None, self._parsed(), None, cache=cache, cancel=cancelled.append)
		self.assertTrue(out["stopped"] and out["run_cancelled"])
		self.assertEqual(cancelled, ["RUN-1"])
		self.assertTrue(ts.StreamState("GW", CHAT, cache).stopped())

	def test_no_active_stream_and_stale_draft_ignored(self):
		cache = FakeCache()
		gw = SimpleNamespace(name="GW", execution_user=None)
		self.assertNotIn("stopped", ts.handle_stopped(gw, None, self._parsed(), None, cache=cache))
		ts.StreamState("GW", CHAT, cache).update(draft_id=8, run_id="R")
		out = ts.handle_stopped(gw, None, self._parsed(7), None, cache=cache, cancel=lambda r: 1 / 0)
		self.assertEqual(out["note"], "stale draft")
		self.assertFalse(ts.StreamState("GW", CHAT, cache).stopped())

	def test_cancel_failure_still_stops_stream(self):
		cache = FakeCache()
		ts.StreamState("GW", CHAT, cache).update(draft_id=7, run_id="R")
		gw = SimpleNamespace(name="GW", execution_user=None)
		from unittest import mock

		with mock.patch("frappe.set_user"), mock.patch("frappe.session", SimpleNamespace(user="Guest")):
			out = ts.handle_stopped(gw, None, self._parsed(), None, cache=cache, cancel=lambda r: 1 / 0)
		self.assertFalse(out["run_cancelled"])
		self.assertTrue(ts.StreamState("GW", CHAT, cache).stopped())

	def test_non_stop_update_returns_none(self):
		self.assertIsNone(ts.handle_stopped(SimpleNamespace(name="GW"), None, SimpleNamespace(raw={}), None))

	def test_registered_with_ingest(self):
		import huf.ai.gateway_adapters.telegram_stream_hooks

		self.assertIn("stopped_message_generation", telegram_ingest._UPDATE_HANDLERS)
		self.assertIn("unsupported", telegram_ingest._UPDATE_HANDLERS)


class TestBeforeSend(unittest.TestCase):
	def test_passes_parts_and_clears_state(self):
		cache = FakeCache()
		ts.StreamState("GW", CHAT, cache).update(draft_id=7)
		ev, gw = SimpleNamespace(conversation_id=str(CHAT)), SimpleNamespace(name="GW")
		self.assertEqual(ts.before_send(ev, gw, ["a", "b"], cache=cache), ["a", "b"])
		self.assertEqual(ts.StreamState("GW", CHAT, cache).get(), {})

	def test_never_raises(self):
		self.assertEqual(ts.before_send(object(), object(), ["x"]), ["x"])


if __name__ == "__main__":
	unittest.main()
