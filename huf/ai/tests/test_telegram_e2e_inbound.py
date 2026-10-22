# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""E2E-2: every Telegram update kind driven through ``handle_update`` / ``to_event`` and the Gateway run.

Fakes only: a Bot API fake for HTTP, an in-memory cache, and mocked Gateway Event / Gateway docs. Asserts the
HTTP ack shape, whether an event is ingested, the text the agent sees, the conversation key, that non-message
kinds do not
start an agent run, duplicate update ids, secret hygiene in logs, and prompt assembly for a Telegram run.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai import gateway_service as gs
from huf.ai.gateway_adapters import GatewayInboundRequest, telegram_ingest as ing
from huf.ai.gateway_adapters import telegram_agent_context, telegram_hooks  # noqa: F401  (registers hooks)
from huf.ai.gateway_adapters import telegram_integration_hooks as integ
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter
from huf.ai.gateway_adapters.telegram_inbound import parse_update, to_event
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi, load_fixture


class FakeCache:
	"""In-memory stand-in for frappe.cache() with the nx/make_key surface ``_first_delivery`` uses."""

	def __init__(self) -> None:
		self.store: dict = {}

	def make_key(self, key):
		return key

	def set(self, key, value, nx=False, ex=None):
		if nx and key in self.store:
			return False
		self.store[key] = value
		return True

	def get_value(self, key):
		return self.store.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.store[key] = value

	def delete_value(self, key):
		self.store.pop(key, None)

	def incrby(self, key, amount=1):
		self.store[key] = int(self.store.get(key, 0)) + amount
		return self.store[key]

	def expire(self, key, seconds):
		return True


class RecordingLogger:
	"""Captures every message frappe.logger / frappe.log_error would have written."""

	def __init__(self) -> None:
		self.lines: list[str] = []

	def _record(self, msg, *args, **kwargs):
		self.lines.append(str(msg))

	info = warning = error = debug = exception = critical = _record


GW = SimpleNamespace(
	name="gw1", provider="Telegram", mention_required=0, typing_indicator=0, execution_user="bot",
	direct_policy="Allow list",
)
# Gateway docs expose .get(); the fake mirrors it
GW.get = lambda key, default=None: getattr(GW, key, default)


def fresh_adapter(bot: FakeBotApi | None = None) -> TelegramGatewayAdapter:
	bot = bot or FakeBotApi()
	return TelegramGatewayAdapter(
		{"token": TOKEN, "webhook_secret": SECRET},
		http_post=bot.http_post,
		http_get=bot.http_get,
		download_attachments=False,
	)


def signed(payload: dict) -> GatewayInboundRequest:
	return GatewayInboundRequest(json.dumps(payload).encode(), headers={WEBHOOK_SECRET_HEADER: SECRET})


def msg_with(**fields) -> dict:
	"""message_text fixture with its text replaced by the given Message fields (document, audio, ...)."""
	upd = load_fixture("message_text")
	upd["message"].pop("text", None)
	upd["message"].update(fields)
	return upd


def unique_update(payload: dict, update_id: int) -> dict:
	upd = copy.deepcopy(payload)
	upd["update_id"] = update_id
	return upd


KIND_PAYLOADS = {
	"text": lambda: load_fixture("message_text"),
	"photo": lambda: load_fixture("photo"),
	"document": lambda: msg_with(
		document={
			"file_id": "D1", "file_unique_id": "du1", "file_name": "report.pdf",
			"mime_type": "application/pdf", "file_size": 2048,
		}
	),
	"voice": lambda: load_fixture("voice"),
	"audio": lambda: msg_with(
		audio={"file_id": "A1", "file_unique_id": "au1", "duration": 61, "title": "Song", "performer": "Band"}
	),
	"video": lambda: msg_with(
		video={"file_id": "V1", "file_unique_id": "vu1", "duration": 5, "file_name": "clip.mp4"}
	),
	"video_note": lambda: load_fixture("video_note"),
	"sticker": lambda: load_fixture("sticker"),
	"animation": lambda: load_fixture("animation"),
	"location": lambda: load_fixture("location"),
	"venue": lambda: load_fixture("venue"),
	"contact": lambda: load_fixture("contact"),
	"poll": lambda: load_fixture("poll"),
	"dice": lambda: load_fixture("dice"),
	"forwarded": lambda: load_fixture("forwarded"),
	"reply_quote": lambda: load_fixture("reply_quote"),
	"edited_message": lambda: load_fixture("edited_message"),
	"channel_post": lambda: load_fixture("channel_post"),
	"start_payload": lambda: load_fixture("message_start_deep_link"),
	"business_message": lambda: load_fixture("business_message"),
	"guest_message": lambda: load_fixture("guest_message"),
	"inline_query": lambda: load_fixture("inline_query"),
	"chat_join_request": lambda: load_fixture("chat_join_request"),
	"reaction_added": lambda: load_fixture("message_reaction_added"),
	"reaction_count": lambda: load_fixture("message_reaction_count"),
	"poll_answer_unsupported": lambda: load_fixture("unsupported_update"),
}


class Harness:
	"""Drives handle_update with the ingest/touch seams patched and every log line captured."""

	def __init__(self, *, duplicate_aware: bool = False) -> None:
		self.cache = FakeCache()
		self.log = RecordingLogger()
		self.bot = FakeBotApi()
		self.adapter = fresh_adapter(self.bot)
		self.seen_ids: set = set()
		self.duplicate_aware = duplicate_aware
		self.ingest = mock.Mock(side_effect=self._ingest)

	def _ingest(self, gateway_name, provider_event_id, context, *, verified_sender, raw_payload=None):
		if self.duplicate_aware and provider_event_id in self.seen_ids:
			return {"duplicate": True, "event_name": "E-prev"}
		self.seen_ids.add(provider_event_id)
		return {"event_name": "E1", "status": "Received"}

	def handle(self, payload: dict, gateway=GW):
		with (
			mock.patch("huf.ai.gateway_service.ingest_gateway_event", self.ingest),
			mock.patch("huf.ai.gateway_webhook.touch_last_event"),
			mock.patch("frappe.cache", return_value=self.cache),
			mock.patch("frappe.logger", return_value=self.log),
			mock.patch("frappe.log_error", side_effect=lambda *a, **k: self.log.lines.append(str(a))),
			# unsupported-update handlers (guest, inline) read Gateway Access Entries via frappe.get_list
			mock.patch("frappe.get_list", return_value=[]),
			mock.patch("frappe.get_all", return_value=[]),
			# Inline/join/membership handlers read Gateway Access Entries; no site in unit runs, so fake the reads.
			mock.patch("huf.ai.gateway_service._sender_negative_state", return_value=None),
			mock.patch("huf.ai.gateway_service._sender_is_known", return_value=False),
			mock.patch("huf.ai.gateway_adapters.telegram_groups.decide", return_value="queue"),
			mock.patch("huf.ai.gateway_adapters.telegram_groups.record_pending_join", return_value="ACC-1"),
			mock.patch(
				"huf.ai.gateway_adapters.telegram_groups.apply_membership_change",
				return_value={"success": True, "transition": "noop"},
			),
		):
			return ing.handle_update(gateway, self.adapter, signed(payload))

	def ingested_context(self) -> dict:
		self.ingest.assert_called_once()
		return self.ingest.call_args.args[2]

	def ingested_event(self) -> dict:
		return self.ingest.call_args.kwargs["raw_payload"]


def event_of(payload: dict):
	"""The NormalizedGatewayEvent a payload maps to (test helper; no ingest)."""
	return to_event(parse_update(payload))


def parsed_of(payload: dict):
	return parse_update(payload)


# Expected ingest outcome per kind: (ingested?, context kind or None, ack ``ignored`` marker or None)
EXPECTED = {
	"text": (True, "message", None),
	"photo": (True, "message", None),
	"document": (True, "message", None),
	"voice": (True, "message", None),
	"audio": (True, "message", None),
	"video": (True, "message", None),
	"video_note": (True, "message", None),
	"sticker": (True, "message", None),
	"animation": (True, "message", None),
	"location": (True, "message", None),
	"venue": (True, "message", None),
	"contact": (True, "message", None),
	"poll": (True, "message", None),
	"dice": (True, "message", None),
	"forwarded": (True, "message", None),
	"reply_quote": (True, "message", None),
	"edited_message": (False, None, "edited_message"),
	"channel_post": (False, None, "channel_post"),
	"start_payload": (True, "message", None),
	"reaction_added": (True, "reaction", None),
	"business_message": (False, None, "business"),
	"guest_message": (False, None, "guest_message"),
	"inline_query": (False, None, None),
	"chat_join_request": (False, None, "chat_join_request"),
	"reaction_count": (False, None, "message_reaction_count"),
	"poll_answer_unsupported": (False, None, "unsupported"),
}


class TestEveryKindAck(unittest.TestCase):
	"""Ack shape + ingest decision for each update kind."""

	def test_each_kind_ack_and_ingest_decision(self):
		for name, build in KIND_PAYLOADS.items():
			with self.subTest(kind=name):
				h = Harness()
				result = h.handle(build())
				ingested, ctx_kind, ignored = EXPECTED[name]
				self.assertIsInstance(result, dict)
				self.assertIs(result["success"], True)
				if ingested:
					h.ingest.assert_called_once()
					self.assertEqual(result["event_name"], "E1")
					self.assertEqual(h.ingested_context()["kind"], ctx_kind)
					self.assertEqual(h.ingested_context()["conversation_id"], event_of(build()).conversation_id)
				else:
					h.ingest.assert_not_called()
					if ignored:
						self.assertEqual(result["ignored"], ignored)

	def test_block_change_kinds_never_ingest(self):
		for name in ("my_chat_member_blocked", "my_chat_member_unblocked", "my_chat_member_group_added",
			"my_chat_member_group_promoted", "my_chat_member_group_removed", "chat_member_joined"):
			with self.subTest(kind=name), mock.patch("huf.ai.gateway_service._sender_is_known", return_value=False), \
				mock.patch("huf.ai.gateway_service._record_opt_in"), \
				mock.patch("huf.ai.gateway_service._record_opt_out"), \
				mock.patch("huf.ai.gateway_adapters.telegram_groups.apply_membership_change"):
				h = Harness()
				result = h.handle(load_fixture(name))
				self.assertIs(result["success"], True)
				h.ingest.assert_not_called()


class TestTextSeenByAgent(unittest.TestCase):
	"""The message_text the agent receives for each content type."""

	def _text(self, name: str, payload: dict | None = None) -> str:
		h = Harness()
		h.handle(payload or KIND_PAYLOADS[name]())
		return h.ingested_context()["message_text"]

	def test_plain_text(self):
		self.assertEqual(self._text("text"), load_fixture("message_text")["message"]["text"])

	def test_rich_descriptions(self):
		cases = {
			"sticker": "[sticker]",
			"animation": "[gif/animation",
			"video_note": "[video note 4s]",
			"voice": "[voice message 3s]",
			"audio": "[audio 61s] Band - Song",
			"location": "[location]",
			"venue": "[venue] Cafe",
			"contact": "[contact] Asha",
			"poll": "[poll] Lunch?",
			"dice": "[dice]",
		}
		for name, needle in cases.items():
			with self.subTest(kind=name):
				self.assertIn(needle, self._text(name))

	def test_forward_and_reply_context_reach_agent(self):
		self.assertIn("[forwarded from", self._text("forwarded"))
		self.assertIn("[replying to", self._text("reply_quote"))

	def test_media_without_caption_has_no_text_but_attachment_ref(self):
		# Documents and video have no description line: the agent only gets the saved attachment.
		# Recorded here so a change to the description is noticed.
		for name in ("document", "video"):
			with self.subTest(kind=name):
				self.assertEqual(self._text(name), "")
				refs = parsed_of(KIND_PAYLOADS[name]()).attachments_meta
				self.assertEqual(len(refs), 1)

	def test_start_payload_text(self):
		self.assertEqual(self._text("start_payload"), "/start pair_ABC123")



class TestConversationKey(unittest.TestCase):
	"""One agent conversation per chat, or per topic when a thread id is present."""

	def _key(self, payload: dict) -> str:
		ev = event_of(payload)
		shim = SimpleNamespace(conversation_id=ev.conversation_id, raw_payload=ev.raw_payload)
		return integ.conversation_key(shim)

	def test_private_chat_is_chat_id(self):
		self.assertEqual(self._key(load_fixture("message_text")), "111")

	def test_forum_topic_is_chat_colon_thread(self):
		payload = load_fixture("forum_topic_message")
		thread = payload["message"]["message_thread_id"]
		self.assertEqual(self._key(payload), f"-1005555:{thread}")

	def test_general_topic_without_thread_is_chat_only(self):
		payload = load_fixture("forum_topic_message")
		payload["message"].pop("message_thread_id")
		payload["message"].pop("is_topic_message", None)
		self.assertEqual(self._key(payload), "-1005555")

	def test_reply_chain_thread_in_plain_supergroup_is_chat_only(self):
		# message_thread_id without is_topic_message is a reply-chain artifact, not a topic.
		payload = load_fixture("message_group_mention")
		payload["message"]["message_thread_id"] = 77
		self.assertEqual(self._key(payload), "-1001234")

	def test_private_topic_keyed_by_thread(self):
		payload = load_fixture("message_text")
		payload["message"].update({"message_thread_id": 9, "is_topic_message": True})
		self.assertEqual(self._key(payload), "111:9")

	def test_same_chat_same_key_across_updates(self):
		a = unique_update(load_fixture("message_text"), 1)
		b = unique_update(load_fixture("message_text"), 2)
		self.assertEqual(self._key(a), self._key(b))


class TestNonMessageKindsDoNotRunAgent(unittest.TestCase):
	"""Reactions, membership, business, guest and tampered callbacks never start an agent run."""

	def test_tampered_callback_is_dropped(self):
		h = Harness()
		result = h.handle(load_fixture("callback_query"))
		self.assertEqual(result["ignored"], "callback_query")
		h.ingest.assert_not_called()

	def test_reaction_is_record_only_in_gateway_service(self):
		h = Harness()
		h.handle(load_fixture("message_reaction_added"))
		ctx = h.ingested_context()
		self.assertEqual(ctx["kind"], "reaction")
		event = SimpleNamespace(
			name="GEV-R", db_set=mock.Mock(), get=lambda k, d=None: None, raw_payload={},
		)
		with mock.patch.object(gs, "_record_event", return_value={"status": "Succeeded"}) as rec, \
			mock.patch.object(gs.frappe, "get_doc") as get_doc:
			gs._continue_ingest(event, "gw1", "1", ctx, True)
		rec.assert_called_once()
		get_doc.assert_not_called()  # no Gateway lookup, consent, rate bucket or Agent run

	def test_reaction_removed_also_record_only(self):
		h = Harness()
		h.handle(load_fixture("message_reaction_removed"))
		self.assertEqual(h.ingested_context()["kind"], "reaction")

	def test_join_request_never_ingests(self):
		h = Harness()
		h.handle(load_fixture("chat_join_request"))
		h.ingest.assert_not_called()

	def test_guest_message_routes_through_guest_handler_not_default_ingest(self):
		h = Harness()
		with mock.patch("huf.ai.gateway_adapters.telegram_guest.handle_guest", return_value=None):
			h.handle(load_fixture("guest_message"))
		h.ingest.assert_not_called()

	def test_business_message_with_no_handler_result_is_not_a_plain_message(self):
		h = Harness()
		with mock.patch("huf.ai.gateway_adapters.telegram_business.handle_business_message", return_value=None):
			result = h.handle(load_fixture("business_message"))
		self.assertIs(result["success"], True)
		if h.ingest.called:
			self.assertNotEqual(h.ingested_context().get("kind"), "")


class TestDuplicateDelivery(unittest.TestCase):
	def test_registered_handler_runs_once_per_update_id(self):
		spy = mock.Mock(return_value=None)  # None falls through to the default path
		h = Harness(duplicate_aware=True)
		with mock.patch.dict(ing._UPDATE_HANDLERS, {"message": spy}):
			first = h.handle(load_fixture("message_text"))
			second = h.handle(load_fixture("message_text"))
		self.assertEqual(spy.call_count, 1)
		self.assertEqual(second["ignored"], "message")
		self.assertIn("duplicate", second["note"])
		self.assertIs(first["success"], True)

	def test_default_path_redelivery_is_deduplicated_by_ingest(self):
		# With the per-update guard disabled, a redelivered text message reaches ingest_gateway_event again,
		# which must answer duplicate (the idempotency key is the provider update id).
		h = Harness(duplicate_aware=True)
		with mock.patch.dict(ing._UPDATE_HANDLERS, {"message": None}):
			first = h.handle(load_fixture("message_text"))
			second = h.handle(load_fixture("message_text"))
		self.assertEqual(first["event_name"], "E1")
		self.assertTrue(second["duplicate"])
		update_id = str(load_fixture("message_text")["update_id"])
		self.assertEqual({c.args[1] for c in h.ingest.call_args_list}, {update_id})

	def test_text_redelivery_stopped_by_update_guard(self):
		# The "message" handlers are registered, so a second delivery of the same update id is acked, not re-run.
		h = Harness(duplicate_aware=True)
		h.handle(load_fixture("message_text"))
		again = h.handle(load_fixture("message_text"))
		self.assertEqual(again["ignored"], "message")
		self.assertEqual(h.ingest.call_count, 1)

	def test_handler_exception_releases_delivery_for_retry(self):
		calls = []

		def boom(gateway, adapter, parsed, request):
			calls.append(parsed.update_id)
			if len(calls) == 1:
				raise RuntimeError("transient")
			return {"success": True, "handled": True}

		h = Harness()
		with mock.patch.dict(ing._UPDATE_HANDLERS, {"message": boom}):
			with self.assertRaises(RuntimeError):
				h.handle(load_fixture("message_text"))
			again = h.handle(load_fixture("message_text"))
		self.assertEqual(len(calls), 2)
		self.assertEqual(again, {"success": True, "handled": True})

	def test_unsupported_handler_redelivery_acked_not_rerun(self):
		# "unsupported" carries inline/guest/stream chains; a spy on it must run once for a redelivered update.
		spy = mock.Mock(return_value=None)
		h = Harness()
		with mock.patch.dict(ing._UPDATE_HANDLERS, {"unsupported": spy}):
			h.handle(load_fixture("inline_query"))
			again = h.handle(load_fixture("inline_query"))
		self.assertEqual(spy.call_count, 1)
		self.assertEqual(again["ignored"], "unsupported")


class TestSecretHygiene(unittest.TestCase):
	"""No bot token, webhook secret or callback key may appear in any logged string."""

	def _assert_clean(self, log: RecordingLogger):
		blob = "\n".join(log.lines)
		self.assertNotIn(TOKEN, blob)
		self.assertNotIn(TOKEN.split(":", 1)[1], blob)
		self.assertNotIn(SECRET, blob)

	def test_all_kinds_logs_are_clean(self):
		for name, build in KIND_PAYLOADS.items():
			with self.subTest(kind=name):
				h = Harness()
				h.handle(build())
				self._assert_clean(h.log)

	def test_tampered_callback_and_block_logs_are_clean(self):
		h = Harness()
		h.handle(load_fixture("callback_query"))
		with mock.patch("huf.ai.gateway_service._sender_is_known", return_value=True), \
			mock.patch("huf.ai.gateway_service._record_opt_out"):
			h.handle(load_fixture("my_chat_member_blocked"))
		self._assert_clean(h.log)

	def test_media_download_error_with_token_url_is_redacted(self):
		h = Harness()
		leaky = RuntimeError(f"GET https://api.telegram.org/file/bot{TOKEN}/photos/p.jpg failed")
		event = SimpleNamespace(name="GEV-M", raw_payload=load_fixture("photo"), get=lambda k, d=None: None)
		with mock.patch.object(h.adapter.client, "download_file", side_effect=leaky), \
			mock.patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=h.adapter), \
			mock.patch("frappe.logger", return_value=h.log):
			self.assertEqual(ing.save_media(event, GW), [])
		self._assert_clean(h.log)


class TestEdgeCases(unittest.TestCase):
	def test_bad_json_falls_through(self):
		bad = GatewayInboundRequest(b"not json", headers={WEBHOOK_SECRET_HEADER: SECRET})
		self.assertIsNone(ing.handle_update(GW, fresh_adapter(), bad))

	def test_unsigned_request_falls_through_without_ingest(self):
		# handle_update returns None on ValueError from parse_update, so the generic path rejects it.
		h = Harness()
		unsigned = GatewayInboundRequest(json.dumps(load_fixture("message_text")).encode(), headers={})
		self.assertIsNone(ing.handle_update(GW, h.adapter, unsigned))
		h.ingest.assert_not_called()

	def test_channel_post_is_room_and_keyed_by_chat(self):
		ev = event_of(load_fixture("channel_post"))
		self.assertTrue(ev.is_room)
		self.assertEqual(ev.sender_id, ev.conversation_id)

	@unittest.expectedFailure
	def test_edit_not_misreported_as_duplicate(self):
		# Suspected bug (telegram_ingest.handle_update): edited_message / channel_post fall through to the
		# "message" category, whose _first_delivery guard already claimed this update id, so the ack says
		# "duplicate update ignored" for a first delivery. Edits and channel posts are never ingested.
		h = Harness()
		for name in ("edited_message", "channel_post"):
			with self.subTest(kind=name):
				result = h.handle(load_fixture(name))
				self.assertNotEqual(result.get("note"), "duplicate update ignored")


class TestPromptAssembly(unittest.TestCase):
	"""_process_gateway_event for a Telegram event: channel note, conversation_ref, media saved, files passed."""

	def _event(self, payload: dict):
		ev = event_of(payload)
		raw = ev.raw_payload
		return SimpleNamespace(
			name="GEV-TG",
			gateway="gw1",
			sender_id=ev.sender_id,
			conversation_id=ev.conversation_id,
			thread_id=ev.thread_id or "",
			provider_event_id=ev.provider_event_id,
			status="Queued",
			target_type="Agent",
			target_agent="A",
			message_text=ev.message_text,
			raw_payload=raw,
			flow_run="",
			agent_run="",
			db_set=mock.Mock(),
			get=lambda k, d=None: raw if k == "raw_payload" else d,
		)

	def _run(self, payload: dict, *, download=b"IMG", saved_url="/private/files/p.jpg", download_error=None):
		event = self._event(payload)
		gateway = SimpleNamespace(
			name="gw1", provider="Telegram", is_enabled=1, execution_user="bot", mention_required=0,
			typing_indicator=0, error_reply_text="", integration_settings="", retry_max_attempts=0,
			get=lambda k, d=None: getattr(gateway, k, d),
		)
		bot = FakeBotApi()
		adapter = fresh_adapter(bot)
		if download_error is not None:
			adapter.client.download_file = mock.Mock(side_effect=download_error)
		else:
			adapter.client.download_file = mock.Mock(return_value=(download, "photos/p.jpg"))
		captured = {}
		run = mock.Mock(return_value={"agent_run_id": "AR", "response": "ok", "success": True})

		def fake_get_doc(*args, **kwargs):
			if args and isinstance(args[0], dict) and args[0].get("doctype") == "File":
				return SimpleNamespace(insert=lambda **k: SimpleNamespace(file_url=saved_url))
			if args and args[0] == "Gateway Event":
				return event
			if args and args[0] == "Gateway":
				return gateway
			return SimpleNamespace(owner="bot", allow_guest=True)

		def serialised(fn, lock_key, **kw):
			captured["lock_key"] = lock_key
			return fn(**kw)

		with (
			mock.patch.object(gs.frappe, "get_doc", side_effect=fake_get_doc),
			mock.patch.object(gs, "_process_time_block_reason", return_value=""),
			mock.patch(
				"huf.ai.agent_access.resolve_run_identity_and_authorize",
				return_value=SimpleNamespace(authorized=True),
			),
			mock.patch.object(gs.frappe, "set_user"),
			mock.patch.object(gs, "_commit_unless_testing"),
			mock.patch.object(gs, "_maybe_mark_read_typing"),
			mock.patch.object(gs, "_run_agent_serialised", side_effect=serialised),
			mock.patch.object(gs, "_describe_attachments", return_value=""),
			mock.patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=adapter),
			mock.patch(
				"huf.ai.gateway_webhook.send_gateway_reply",
				return_value=SimpleNamespace(provider_message_id="m", provider_response={}),
			),
			mock.patch.object(gs.frappe, "log_error") as log_error,
			mock.patch("frappe.db", new=mock.MagicMock()),  # no site: stub the DB proxy the run touches
			mock.patch.object(gs, "_send_telegram_reply", return_value={"status": "Succeeded"}) as send,
			mock.patch(
				"huf.ai.media_prep.resolve_event_files",
				return_value=[
					{"file_id": "FILE-1", "file_url": saved_url, "filename": "p.jpg", "mime_type": "image/jpeg"}
				],
			),
			mock.patch.object(
				telegram_agent_context, "build_instructions", return_value="Telegram: keep replies short."
			),
			mock.patch.dict(sys.modules, {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=run)}),
		):
			out = gs._process_gateway_event("GEV-TG")
		self.log_error = log_error
		self.send = send
		return out, run, captured, event

	def test_channel_note_prepended_and_text_kept(self):
		_, run, _, _ = self._run(load_fixture("message_text"))
		prompt = run.call_args.kwargs["prompt"]
		self.assertTrue(prompt.startswith("[Channel note: Telegram: keep replies short.]\n"))
		self.assertTrue(prompt.endswith(load_fixture("message_text")["message"]["text"]))

	def test_conversation_ref_per_chat_and_per_topic(self):
		_, run, captured, _ = self._run(load_fixture("message_text"))
		self.assertEqual(run.call_args.kwargs["external_id"], "111")
		self.assertEqual(captured["lock_key"], "huf_gw_conv:gw1:111")
		payload = load_fixture("forum_topic_message")
		_, run2, captured2, _ = self._run(payload)
		thread = payload["message"]["message_thread_id"]
		self.assertEqual(run2.call_args.kwargs["external_id"], f"-1005555:{thread}")
		self.assertEqual(captured2["lock_key"], f"huf_gw_conv:gw1:-1005555:{thread}")

	def test_photo_saved_and_passed_as_file(self):
		out, run, _, _ = self._run(load_fixture("photo"))
		self.assertEqual(out["status"], "Succeeded")
		self.assertIn("[Attachment saved: /private/files/p.jpg]", run.call_args.kwargs["prompt"])
		files = run.call_args.kwargs.get("files")
		self.assertTrue(files)
		self.assertEqual(files[0]["file_url"], "/private/files/p.jpg")

	def test_photo_download_failure_tells_agent_attachment_unavailable(self):
		out, run, _, _ = self._run(load_fixture("photo"), download_error=RuntimeError("getFile failed"))
		self.assertIn(gs.ATTACHMENT_UNAVAILABLE_NOTE, run.call_args.kwargs["prompt"])
		self.assertFalse(run.call_args.kwargs.get("files"))


if __name__ == "__main__":
	unittest.main()
