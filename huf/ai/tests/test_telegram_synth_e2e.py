# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""W17-SYNTH: synthesized Telegram updates posted through the REAL webhook entry point.

Every test builds a realistic Bot API 10.x update, signs the request with ``X-Telegram-Bot-Api-Secret-Token`` and calls
``huf.ai.gateway_webhook.handle_gateway_webhook`` (secret check, ``telegram_ingest.handle_update`` chain, the real
``gateway_service.ingest_gateway_event`` admission). Only the outbound Bot API client (``FakeBotApi``) and the agent LLM
run (``frappe.enqueue`` / ``_run_agent``) are mocked; persistence is an in-memory stand-in so the suite behaves the same
in the unit runner and on a site (update-id claims are cleared with the W10 isolation helpers).

Already covered completely elsewhere and therefore not duplicated here:
  * Guard captcha submit/wrong-answer/replay/3-strike decline: test_telegram_e2e_modes.TestJoinRequests
  * Agent-decided join JSON parsing and agent failure fallback: test_telegram_e2e_modes.TestJoinRequests
  * Business reply job (sends as owner, right removed before run, rate-limit downgrade): TestBusinessMode in e2e_modes
  * Cockpit nonce internals (single-use under threads, cross-user): test_telegram_e2e_admin.TestNonceReplay
  * initData / Mini App token internals and POST-only whitelist: test_telegram_miniapp(_api), e2e_admin.TestMiniAppParity
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
import time
import unittest
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlparse

import frappe

from huf.ai import gateway_service as gs
from huf.ai import telegram_admin as ta
from huf.ai import telegram_guard as tg
from huf.ai import telegram_send_scope as tg_scope
from huf.ai.gateway_adapters import (
	provider_hooks,
	telegram_buttons as tb,
	telegram_business as biz,
	telegram_business_agent as bagent,
	telegram_ingest as ing,
	telegram_inline as inline,
	telegram_pipeline as tp,
)
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.gateway_webhook import handle_gateway_webhook
from huf.ai.tests import telegram_fakes as fakes
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi
from huf.ai.tests.test_telegram_e2e_admin import (  # noqa: F401  (base classes are not collected as tests)
	ADMIN,
	CHAT,
	GW as ADMIN_GW,
	TG,
	TG2,
	E2EBase as AdminBase,
)
from huf.ai.tests.test_telegram_e2e_modes import FakeCache, init_data, load_all_hooks

GW_NAME = "gw1"
OWNER, CUST = 1001, 2002
_ORIGINAL_HANDLERS = dict(ing._UPDATE_HANDLERS)


def setUpModule():
	load_all_hooks()


def tearDownModule():
	ing._UPDATE_HANDLERS.clear()
	ing._UPDATE_HANDLERS.update(_ORIGINAL_HANDLERS)


# -- in-memory persistence for the real ingest path ------------------------------------------------------------------


class EventDoc:
	"""Stand-in Gateway Event row: insert/db_set record state like the real doc."""

	def __init__(self, data: dict, store: list) -> None:
		self.__dict__.update(data)
		self.name = f"EV-{len(store) + 1}"
		store.append(self)

	def insert(self, **_kw):
		return self

	def db_set(self, field, value=None, **_kw):
		self.__dict__.update(field if isinstance(field, dict) else {field: value})

	def get(self, key, default=None):
		return self.__dict__.get(key, default)


class FakeDb:
	def __init__(self, events: list) -> None:
		self.events = events

	def get_value(self, doctype, filters=None, fieldname=None, *a, **kw):
		if doctype == "Gateway Event" and isinstance(filters, dict) and "idempotency_key" in filters:
			for ev in self.events:
				if getattr(ev, "idempotency_key", None) == filters["idempotency_key"]:
					return ev.name
		return None

	def exists(self, *a, **kw):
		return None

	def commit(self):
		pass

	def rollback(self):
		pass


def make_gateway(**over):
	base = dict(
		name=GW_NAME, provider="Telegram", is_enabled=1, mention_required=0, typing_indicator=0,
		direct_policy="Allow list", room_policy="Open", room_sender_policy="Open", execution_user="bot.user@example.com",
		default_agent="Sec", telegram_business_policy="Observe", telegram_join_policy="Queue", telegram_guard_captcha=0,
		telegram_welcome_template=None, pairing_ttl_minutes=60, pairing_pending_limit=5,
	)
	base.update(over)
	gw = SimpleNamespace(**base)
	gw.get = lambda key, default=None: getattr(gw, key, default)
	return gw


class Posted:
	"""Result of one webhook post: the returned body plus the HTTP status the endpoint set (200 when untouched)."""

	def __init__(self, body, status):
		self.body, self.status = body, status

	def __getitem__(self, key):
		return self.body[key]

	def get(self, key, default=None):
		return (self.body or {}).get(key, default)


class WebhookHarness:
	"""Mixin: wires ``handle_gateway_webhook`` to the fake Bot API and an in-memory event store."""

	def wire(self, gw=None, fallback_get_doc=None):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post, http_get=self.api.http_get, download_attachments=False,
		)
		self.gw = gw or make_gateway()
		self.fcache = FakeCache()
		if not hasattr(self, "cache"):
			self.cache = self.fcache
		self.events: list[EventDoc] = []
		self.created: list[dict] = []
		self.enqueued: list = []
		self._request = None
		fakes.isolate_update_dedup(self)
		fakes.set_local_flags(self, in_test=False)
		self._local("response", frappe._dict())
		self._local("form_dict", frappe._dict())
		self.fallback_get_doc = fallback_get_doc
		self.api.queue("getMe", {"ok": True, "result": {"id": 123456, "is_bot": True, "username": "huf_bot"}})

		def get_doc(*args, **kw):
			first = args[0] if args else None
			if isinstance(first, dict):
				dt = first.get("doctype")
				if dt == "Gateway Event":
					return EventDoc(first, self.events)
				if dt == "Gateway Access Entry":
					self.created.append(dict(first))
					return SimpleNamespace(name=f"GAE-{len(self.created)}", insert=lambda **k: SimpleNamespace(name=f"GAE-{len(self.created)}"))
			if first == "Gateway" and len(args) > 1 and args[1] == self.gw.name:
				return self.gw
			if first == "Agent":
				return SimpleNamespace(name=args[1])
			if self.fallback_get_doc is not None:
				return self.fallback_get_doc(*args, **kw)
			raise frappe.DoesNotExistError(str(args))

		self.patch("frappe.get_doc", side_effect=get_doc)
		self.patch("frappe.cache", return_value=self.fcache)
		self.patch("frappe.logger")
		self.patch("frappe.set_user")
		self.patch("frappe.utils.now_datetime", side_effect=datetime.now)  # no System Settings lookup on a site
		self.enqueue = self.patch("frappe.enqueue", side_effect=lambda *a, **k: self.enqueued.append((a, k)))
		self.patch("huf.ai.gateway_webhook.get_gateway_adapter", side_effect=lambda gw, name="": self.adapter)
		self.patch("huf.ai.gateway_webhook._ingest_rate_gate")
		self.patch("huf.ai.gateway_webhook.touch_last_event")
		self.patch("huf.ai.gateway_service._sender_rate_limit_reason", return_value=None)
		self.patch("huf.ai.gateway_service._handle_consent_event", return_value=None)
		self.patch("huf.ai.gateway_service._sender_negative_state", return_value=None)
		self.has_entry = self.patch("huf.ai.gateway_service._has_access_entry", return_value=True)
		self.route = self.patch(
			"huf.ai.gateway_service.resolve_gateway_route",
			return_value={"status": "Queued", "target_type": "Agent", "agent": "Sec", "binding": "b1"},
		)

	def patch(self, target, **kw):
		p = mock.patch(target, **kw)
		m = p.start()
		self.addCleanup(p.stop)
		return m

	def _patch_obj(self, obj, name, value):
		p = mock.patch.object(obj, name, value, create=True)
		p.start()
		self.addCleanup(p.stop)

	def _local(self, name, value):
		missing = object()
		old = getattr(frappe.local, name, missing)
		setattr(frappe.local, name, value)

		def restore():
			if old is missing:
				try:
					delattr(frappe.local, name)
				except Exception:
					pass
			else:
				setattr(frappe.local, name, old)

		self.addCleanup(restore)

	def post(self, payload, *, secret=SECRET, method="POST", gateway=GW_NAME) -> Posted:
		body = json.dumps(payload).encode()
		headers = {"Content-Type": "application/json"}
		if secret is not None:
			headers[WEBHOOK_SECRET_HEADER] = secret
		request = SimpleNamespace(
			args={"gateway_name": gateway}, headers=headers, method=method, content_length=len(body),
			get_data=lambda *a, **k: body,
		)
		self._patch_obj(frappe, "request", request)
		if getattr(self, "use_fake_db", True):
			self._patch_obj(frappe, "db", FakeDb(self.events))
		frappe.local.response = frappe._dict()
		out = handle_gateway_webhook()
		return Posted(out, frappe.local.response.get("http_status_code", 200))

	# observable outcomes
	def calls(self, method):
		return self.api.of(method)

	def queued_events(self):
		return [e for e in self.events if getattr(e, "status", "") == "Queued"]


# -- payload builders (Bot API 10.x shapes) ---------------------------------------------------------------------------


def _from(uid, first="Ann", is_bot=False, **extra):
	return {"id": uid, "is_bot": is_bot, "first_name": first, "language_code": "en", **extra}


def private_msg(update_id, text="hello", uid=42, **extra):
	message = {
		"message_id": update_id, "from": _from(uid), "chat": {"id": uid, "first_name": "Ann", "type": "private"},
		"date": int(time.time()), "text": text,
	}
	message.update(extra)
	return {"update_id": update_id, "message": message}


def group_msg(update_id, text="@huf_bot status?", uid=42, chat_id=-1001234, **extra):
	message = {
		"message_id": update_id, "from": _from(uid), "chat": {"id": chat_id, "title": "Team", "type": "supergroup"},
		"date": int(time.time()), "text": text,
		"entities": [{"type": "mention", "offset": 0, "length": 8}],
	}
	message.update(extra)
	return {"update_id": update_id, "message": message}


def inline_update(update_id, uid=42, query="weather"):
	return {"update_id": update_id, "inline_query": {
		"id": f"iq{update_id}", "from": _from(uid), "query": query, "offset": "", "chat_type": "sender",
	}}


def callback_update(update_id, data, *, uid=42, chat_id=None, label="Approve", cq_id=None, message_id=55):
	chat_id = uid if chat_id is None else chat_id
	return {"update_id": update_id, "callback_query": {
		"id": cq_id or f"cq{update_id}", "from": _from(uid), "chat_instance": "-1234567890", "data": data,
		"message": {
			"message_id": message_id, "date": int(time.time()), "chat": {"id": chat_id, "type": "private"},
			"from": _from(999, "Huf", is_bot=True), "text": "Pick",
			"reply_markup": {"inline_keyboard": [[{"text": label, "callback_data": data}]]},
		},
	}}


def membership_update(update_id, old, new, kind="my_chat_member", chat_id=-100123, subject=777, actor=42):
	return {"update_id": update_id, kind: {
		"chat": {"id": chat_id, "type": "supergroup", "title": "Club"}, "from": _from(actor), "date": int(time.time()),
		"old_chat_member": {"status": old, "user": _from(subject, "Huf", is_bot=(kind == "my_chat_member"))},
		"new_chat_member": {"status": new, "user": _from(subject, "Huf", is_bot=(kind == "my_chat_member"))},
	}}


def join_update(update_id, uid=42, query_id=""):
	jr = {
		"chat": {"id": -100123, "type": "supergroup", "title": "Club"}, "from": _from(uid, username="ann"),
		"user_chat_id": uid, "date": int(time.time()), "bio": "hello",
	}
	if query_id:
		jr["query_id"] = query_id
	return {"update_id": update_id, "chat_join_request": jr}


def guest_update(update_id, text="what is the price?", guest_id=55):
	return {"update_id": update_id, "guest_message": {
		"message_id": 3, "guest_query_id": f"gq{update_id}", "from": _from(guest_id, "Gus"),
		"chat": {"id": -500, "type": "supergroup"}, "text": text,
	}}


class SynthBase(WebhookHarness, unittest.TestCase):
	def setUp(self):
		self.wire()


# -- (7) transport: secret, duplicates, routing of edit / channel ----------------------------------------------------


class TestTransport(SynthBase):
	def test_secret_mismatch_missing_and_correct(self):
		for secret in ("wrong", "", SECRET + "x", None):
			with self.subTest(secret=secret):
				res = self.post(private_msg(100 + len(str(secret))), secret=secret)
				self.assertEqual(res.status, 401)
				self.assertFalse(res.body["success"])
		self.assertEqual(self.events, [])
		self.assertEqual(self.api.calls, [])
		ok = self.post(private_msg(150))
		self.assertEqual(ok.status, 200)
		self.assertEqual(len(self.queued_events()), 1)

	def test_responses_never_echo_credentials(self):
		blob = json.dumps(self.post(private_msg(160), secret="wrong").body) + json.dumps(self.post(private_msg(161)).body, default=str)
		self.assertNotIn(TOKEN, blob)
		self.assertNotIn(SECRET, blob)

	def test_unknown_gateway_and_disabled_gateway(self):
		self.assertEqual(self.post(private_msg(170), gateway="nope").status, 404)
		self.gw.is_enabled = 0
		self.assertEqual(self.post(private_msg(171)).status, 403)
		self.assertEqual(self.events, [])

	def test_duplicate_message_update_id_acked_once(self):
		first = self.post(private_msg(200, "ping"))
		second = self.post(private_msg(200, "ping"))
		self.assertTrue(first.get("success") and not first.get("duplicate"))
		self.assertTrue(second.get("duplicate"))
		self.assertEqual(len(self.events), 1)
		self.assertEqual(len([a for a, _k in self.enqueued if a[0] == "huf.ai.gateway_service.process_gateway_event"]), 1)

	def test_duplicate_handler_update_answers_once(self):
		self.gw.direct_policy = "Pairing"  # unpaired -> pair prompt; a Telegram redelivery must not answer twice
		self.has_entry.return_value = False
		self.post(inline_update(210))
		again = self.post(inline_update(210))
		self.assertEqual(again.get("note"), "duplicate update ignored")
		self.assertEqual(len(self.calls("answerInlineQuery")), 1)

	def test_edited_message_routes_as_its_own_event_with_the_edited_text(self):
		self.post(private_msg(220, "hi"))
		edited = {"update_id": 221, "edited_message": private_msg(0, "hi (edited)")["message"]
			| {"message_id": 220, "edit_date": int(time.time())}}
		res = self.post(edited)
		self.assertTrue(res.get("success"))
		self.assertEqual([e.message_text for e in self.events], ["hi", "hi (edited)"])
		self.assertIn("edited_message", self.events[-1].raw_payload)

	def test_channel_post_is_a_room_event_gated_by_room_policy(self):
		payload = {"update_id": 230, "channel_post": {
			"message_id": 7, "sender_chat": {"id": -1009999, "type": "channel", "title": "News"},
			"chat": {"id": -1009999, "type": "channel", "title": "News"}, "date": int(time.time()), "text": "Breaking",
		}}
		self.gw.room_policy = "Allow list"
		self.has_entry.return_value = False
		res = self.post(payload)
		self.assertEqual(res.status, 200)
		self.assertEqual(self.queued_events(), [])  # unapproved channel never reaches the agent
		self.assertEqual(self.events[-1].conversation_id, "-1009999")
		self.assertEqual(self.api.calls, [])
		self.has_entry.return_value = True
		self.post(payload | {"update_id": 231})
		self.assertEqual(len(self.queued_events()), 1)


# -- (1) inline mode ------------------------------------------------------------------------------------------------


class TestInline(SynthBase):
	def test_unpaired_gets_pair_prompt_with_cache_time(self):
		self.has_entry.return_value = False
		res = self.post(inline_update(300))
		self.assertEqual(res.get("handled"), "inline_query")
		payload = self.calls("answerInlineQuery")[-1]["payload"]
		self.assertEqual(payload["results"][0]["id"], "pair")
		self.assertEqual(payload["cache_time"], 300)
		self.assertEqual(payload["button"]["start_parameter"], "pair")
		self.assertEqual(self.events, [])

	def test_paired_gets_agent_answer_and_default_cache_time(self):
		res = self.post(inline_update(301))
		self.assertEqual(res.get("handled"), "inline_query")
		payload = self.calls("answerInlineQuery")[-1]["payload"]
		self.assertTrue(payload["results"][0]["id"].startswith("ask-"))
		self.assertTrue(payload["is_personal"])
		self.assertEqual(payload["cache_time"], inline.DEFAULT_CACHE_TIME)

	def test_chosen_inline_result_queues_one_feedback_job_and_never_a_gateway_event(self):
		chosen = {"update_id": 302, "chosen_inline_result": {
			"result_id": "ask-1", "from": _from(42), "query": "weather", "inline_message_id": "imid"}}
		res = self.post(chosen)
		self.assertEqual((res.get("handled"), res.get("note")), ("chosen_inline_result", "agent run queued"))
		jobs = [k for a, k in self.enqueued if a and a[0] == inline.JOB]
		self.assertEqual(len(jobs), 1)
		self.assertEqual(jobs[0]["inline_message_id"], "imid")
		self.assertEqual(self.post(chosen).get("note"), "duplicate update ignored")  # Telegram redelivery
		self.assertEqual(len([1 for a, _k in self.enqueued if a and a[0] == inline.JOB]), 1)
		self.assertEqual(self.events, [])
		self.assertEqual(self.api.calls, [])

	def test_chosen_inline_result_without_message_id_or_ask_prefix_is_recorded_only(self):
		for n, chosen in enumerate(({"result_id": "ask-1", "query": "weather"}, {"result_id": "pair", "query": "x",
				"inline_message_id": "i"})):
			res = self.post({"update_id": 310 + n, "chosen_inline_result": {"from": _from(42), **chosen}})
			self.assertEqual(res.body, {"success": True, "handled": "chosen_inline_result"})
		self.assertEqual(self.enqueued, [])
		self.assertEqual(self.api.calls, [])

	def _button(self, uid=42, update_id=320, feedback=False):
		if feedback:
			self.gw.telegram_inline_feedback_enabled = 1
		self.post(inline_update(update_id, uid=uid))
		kb = self.calls("answerInlineQuery")[-1]["payload"]["results"][0]["reply_markup"]["inline_keyboard"][0][0]
		return kb["text"], kb["callback_data"]

	def _press(self, update_id, data, uid=42, imid="imid-1"):
		return self.post({"update_id": update_id, "callback_query": {
			"id": f"cq{update_id}", "from": _from(uid), "inline_message_id": imid, "chat_instance": "ci", "data": data}})

	def _jobs(self):
		return [k for a, k in self.enqueued if a and a[0] == inline.JOB]

	def test_button_label_follows_feedback_flag(self):
		self.assertEqual(self._button()[0], inline.TAP_LABEL)
		self.assertEqual(self._button(update_id=321, feedback=True)[0], inline.WORKING_LABEL)

	def test_button_press_runs_answer_once_and_replay_is_a_noop(self):
		_label, data = self._button()
		res = self._press(322, data)
		self.assertEqual((res.get("handled"), res.get("note")), ("inline_callback", "agent run queued"))
		self.assertEqual(len(self._jobs()), 1)
		self.assertEqual(self._jobs()[0]["inline_message_id"], "imid-1")
		self.assertEqual(self._jobs()[0]["query"], "weather")
		self.assertEqual(self._press(323, data).get("note"), "already started")  # second tap, new update id
		self.assertEqual(self._press(322, data).get("note"), "duplicate update ignored")  # redelivery
		self.assertEqual(len(self._jobs()), 1)
		self.assertEqual(self.events, [])

	def test_press_after_chosen_inline_result_does_not_double_run(self):
		_label, data = self._button()
		self.post({"update_id": 324, "chosen_inline_result": {
			"result_id": "ask-1", "from": _from(42), "query": "weather", "inline_message_id": "imid-1"}})
		self.assertEqual(self._press(325, data).get("note"), "already started")
		self.assertEqual(len(self._jobs()), 1)
		self.assertTrue(inline.feedback_seen(self.gw.name))

	def test_forged_unsigned_or_foreign_press_is_refused(self):
		_label, data = self._button()
		for n, (d, uid) in enumerate(((data[:-1] + ("A" if data[-1] != "A" else "B"), 42), ("inl:wait", 42), (data, 99))):
			self.assertIn(self._press(330 + n, d, uid=uid).get("note"), ("bad signature", "expired or foreign"))
		self.assertEqual(self._jobs(), [])


# -- (2) callback_query: signed buttons and the admin Approve / Decline nonce flow --------------------------------


class TestSignedButtons(SynthBase):
	def signed(self, chat_id, payload="approve:42"):
		return self.adapter.sign_callback_data(tb.encode_payload(payload, once=False, edit=False), chat_id)

	def test_signed_button_answers_first_then_runs_agent_with_label(self):
		res = self.post(callback_update(400, self.signed(42)))
		self.assertTrue(res.get("success"))
		self.assertEqual(self.api.calls[0]["method"], "answerCallbackQuery")
		self.assertEqual(self.events[-1].status, "Queued")
		self.assertIn("[button: Approve]", self.events[-1].message_text)
		self.assertIn("callback_data: approve:42", self.events[-1].message_text)

	def test_tampered_or_foreign_chat_signature_is_answered_and_not_ingested(self):
		good = self.signed(42)
		tampered = good[:-3] + ("AAA" if not good.endswith("AAA") else "BBB")
		for n, data in enumerate((tampered, self.signed(999), "b:--:approve|AAAAAAAAAAAA")):
			with self.subTest(n=n):
				res = self.post(callback_update(410 + n, data))
				self.assertEqual(res.get("note"), "invalid_signature")
		self.assertEqual(self.events, [])
		self.assertEqual({c["method"] for c in self.api.calls}, {"answerCallbackQuery"})

	def test_same_callback_query_id_runs_once(self):
		data = self.signed(42)
		self.post(callback_update(420, data, cq_id="same"))
		res = self.post(callback_update(421, data, cq_id="same"))
		self.assertEqual(res.get("note"), "duplicate")
		self.assertEqual(len(self.queued_events()), 1)


class TestAdminApproveFlow(WebhookHarness, AdminBase):
	"""Agent proposes a state change -> signed Approve/Reject buttons -> the human's press arrives as a callback_query."""

	use_fake_db = False

	def setUp(self):
		AdminBase.setUp(self)
		self.fx_get_doc = frappe.get_doc
		gw = make_gateway(name=ADMIN_GW)
		self.wire(gw, fallback_get_doc=self.fx_get_doc)
		from huf.ai.tools import telegram_admin_tools as tool

		self.tool = tool
		self.owner = True
		for name, value in (
			("_make_client", lambda token, *, timeout=30: TelegramBotClient(
				token, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None)),
			("_token", lambda: TOKEN),
			("_gateway_token", lambda gateway: TOKEN),
			("_cache", lambda: self.cache),
			("_audit", lambda *a, **k: None),
			("_flag", lambda gw, group: True),
			("_cap_limit", lambda gw: 50),
			("_is_owner_run", lambda gw, chat: self.owner),
			("_is_paired_admin", lambda gw, uid: False),
			("_admin_bindings", lambda gw: [self.binding_row()]),
			("_callback_signer", lambda gw, chat: (lambda p: self.adapter.sign_callback_data(p, chat))),
		):
			p = mock.patch.object(tool, name, value)
			p.start()
			self.addCleanup(p.stop)
		for name, value in (
			("run_gateway", lambda: ADMIN_GW), ("effective_run_id", lambda: "run1"), ("current_chat", lambda r=None: CHAT),
			("check_recipient", lambda *a, **k: None), ("claim_send", lambda *a, **k: None),
			("release_send", lambda *a, **k: None),
		):
			p = mock.patch.object(tool.scope, name, value)
			p.start()
			self.addCleanup(p.stop)
		self.api.members = {}
		original = self.api.http_post

		def http_post(url, **kw):
			method = url.rsplit("/", 1)[-1]
			if method == "getMe":
				self.api.calls.append({"method": method, "payload": {}, "files": None, "url": url})
				return fakes.FakeResponse({"ok": True, "result": {"id": 999, "is_bot": True}})
			if method == "getChatMember":
				self.api.calls.append({"method": method, "payload": {}, "files": None, "url": url})
				return fakes.FakeResponse({"ok": True, "result": {"status": "administrator", "can_delete_messages": True,
					"can_restrict_members": True, "can_pin_messages": True, "can_change_info": True}})
			return original(url, **kw)

		self.api.http_post = http_post
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET}, http_post=http_post, http_get=self.api.http_get,
			download_attachments=False,
		)

	def binding_row(self):
		b = ta.get_binding(TG, ADMIN_GW, cache=self.cache)
		return dict(b)

	def bind_admin(self, tg=TG, chat=CHAT, user=ADMIN, role="Admin"):
		code = self.mint(user, role)
		res = self.post(private_msg(500 + int(tg), f"/start {code}", uid=int(tg), entities=[
			{"type": "bot_command", "offset": 0, "length": 6}]), gateway=ADMIN_GW)
		return res

	def request_action(self):
		with mock.patch.object(self.tool.scope, "current_chat", lambda r=None: CHAT):
			return json.loads(self.tool.handle_action(action="delete_message", message_id=3))

	def buttons(self):
		kb = self.api.last("sendMessage")["payload"]["reply_markup"]["inline_keyboard"][0]
		return {b["text"]: b["callback_data"] for b in kb}

	def press(self, data, uid=TG, update_id=None):
		update_id = update_id or (9000 + len(self.api.calls) + int(time.time() * 1000) % 100000)
		return self.post(callback_update(update_id, data, uid=int(uid), label="Approve"), gateway=ADMIN_GW)

	def setUpRequest(self):
		self.assertTrue(self.bind_admin().get("success"))
		with mock.patch.object(self.tool, "ALWAYS_HUMAN_APPROVAL", self.tool.ALWAYS_HUMAN_APPROVAL | {"delete_message"}):
			out = self.request_action()
		return out

	def test_approve_executes_once_and_replay_is_refused(self):
		out = self.setUpRequest()
		self.assertEqual(out["status"], "pending_human_approval", out)
		self.assertEqual(self.calls("deleteMessage"), [])
		approve = self.buttons()["Approve"]
		self.press(approve, update_id=9101)
		self.assertEqual(len(self.calls("deleteMessage")), 1)
		self.assertEqual(self.api.last("deleteMessage")["payload"]["message_id"], 3)
		self.press(approve, update_id=9102)  # replay of the same button
		self.press(approve, update_id=9103)
		self.assertEqual(len(self.calls("deleteMessage")), 1)

	def test_wrong_user_press_is_refused_and_does_not_burn_the_nonce(self):
		self.setUpRequest()
		approve = self.buttons()["Approve"]
		self.press(approve, uid=TG2, update_id=9111)
		self.assertEqual(self.calls("deleteMessage"), [])
		self.press(approve, update_id=9112)  # the real admin can still approve
		self.assertEqual(len(self.calls("deleteMessage")), 1)

	def test_decline_does_nothing(self):
		self.setUpRequest()
		reject = self.buttons()["Reject"]
		self.press(reject, update_id=9121)
		self.assertEqual(self.calls("deleteMessage"), [])
		self.press(self.buttons()["Approve"], update_id=9122)  # nonces are per-button: Approve after Reject still single use
		self.assertLessEqual(len(self.calls("deleteMessage")), 1)

	def test_agent_state_change_from_non_owner_chat_is_refused(self):
		self.assertTrue(self.bind_admin().get("success"))
		self.api.calls.clear()
		self.owner = False
		for action, kw in (("delete_message", {"message_id": 3}), ("ban", {"user_id": 5}), ("pin", {"message_id": 3})):
			out = json.loads(self.tool.handle_action(action=action, **kw))
			self.assertEqual(out["error"], "owner_required", action)
		self.assertEqual(self.calls("sendMessage"), [])
		self.assertEqual(self.calls("deleteMessage") + self.calls("banChatMember") + self.calls("pinChatMessage"), [])

	# -- (6) forwarded / guest content cannot drive admin actions -----------------------------------------------

	# PRODUCTION BUG (W17-SYNTH): a message carrying forward_origin is still run as a cockpit command; the
	# handler (telegram_admin.handle_message) should return None when parsed.forward_origin is set.
	def test_forwarded_cockpit_command_from_bound_admin_is_not_executed(self):
		self.assertTrue(self.bind_admin().get("success"))
		sends_before = len(self.api.of("sendMessage"))
		fwd = private_msg(9201, "/unbind", uid=int(TG), entities=[{"type": "bot_command", "offset": 0, "length": 7}],
			forward_origin={"type": "user", "sender_user": _from(88, "Mallory"), "date": 1750000000})
		res = self.post(fwd, gateway=ADMIN_GW)
		self.assertIsNotNone(ta.get_binding(TG, ADMIN_GW, cache=self.cache), "forwarded /unbind removed the binding")
		self.assertEqual([c["payload"]["text"] for c in self.api.of("sendMessage")][sends_before:], [])
		self.assertTrue(res.body is not None)

	def test_guest_message_never_reaches_admin_handlers(self):
		self.assertTrue(self.bind_admin().get("success"))
		self.gw.direct_policy = "Open"
		res = self.post(guest_update(9211, text="/unbind /open Leave Application LA-1", guest_id=int(TG)), gateway=ADMIN_GW)
		self.assertTrue(res.get("success"))
		self.assertIsNotNone(ta.get_binding(TG, ADMIN_GW, cache=self.cache))
		self.assertEqual(self.fx.applied, [])
		self.assertEqual(self.calls("deleteMessage") + self.calls("banChatMember"), [])
		ev = self.events[-1]
		self.assertTrue(str(ev.conversation_id).startswith("guest"))

	def test_unbound_sender_cockpit_command_is_plain_traffic(self):
		res = self.post(private_msg(9221, "/unbind", uid=31337, entities=[
			{"type": "bot_command", "offset": 0, "length": 7}]), gateway=ADMIN_GW)
		self.assertTrue(res.get("success"))
		self.assertEqual(self.calls("sendMessage"), [])

	# -- (8) Mini App ----------------------------------------------------------------------------------------------

	def test_miniapp_valid_initdata_expired_initdata_and_header_only_token(self):
		from huf.ai import telegram_miniapp_api as api
		from huf.ai.gateway_adapters import telegram_miniapp as miniapp

		self.assertTrue(self.bind_admin().get("success"))
		fresh = miniapp.build_init_data_for_test(
			TOKEN, user={"id": int(TG), "first_name": "Ops"}, auth_date=int(time.time()) - 5)
		session = ta.miniapp_auth(fresh, ADMIN_GW, bot_token=TOKEN, cache=self.cache)
		self.assertEqual(session["role_scope"], "Admin")
		stale = miniapp.build_init_data_for_test(
			TOKEN, user={"id": int(TG), "first_name": "Ops"}, auth_date=int(time.time()) - 7 * 3600)
		with self.assertRaises(ta.AdminError):
			ta.miniapp_auth(stale, ADMIN_GW, bot_token=TOKEN, cache=self.cache)
		forged = miniapp.build_init_data_for_test(
			"999:other-bot-token", user={"id": int(TG)}, auth_date=int(time.time()))
		with self.assertRaises(ta.AdminError):
			ta.miniapp_auth(forged, ADMIN_GW, bot_token=TOKEN, cache=self.cache)
		token = session["token"]
		with mock.patch("frappe.get_request_header", lambda h: token if h == api.TOKEN_HEADER else None):
			self.assertEqual(api.me().get("success", True) is not False, True)
		with mock.patch("frappe.get_request_header", lambda h: token if h == api.TOKEN_HEADER else None):
			refused = api.me(token=token)  # token in the URL/param is refused even beside a valid header
		self.assertFalse(refused.get("success"))
		with mock.patch("frappe.get_request_header", lambda h: None):
			self.assertFalse(api.me(token=token).get("success"))
		allowed = getattr(frappe, "allowed_http_methods_for_whitelisted_func", {})
		if allowed:
			for fn in (api.me, api.config, api.search, api.approvals, api.act_confirm, api.revoke_token):
				self.assertEqual(list(allowed.get(fn, [])), ["POST"], fn.__name__)


# -- (3) rooms: bot added / first message / duplicate suppression / removal / migration ------------------------------


class TestRooms(SynthBase):
	def setUp(self):
		super().setUp()
		self.gw.room_policy = "Allow list"
		self.has_entry.return_value = False
		self.patch("huf.ai.gateway_service._new_unique_pairing_code", return_value="PAIR-1")
		self.patch("frappe.get_all", return_value=[])
		self.opt_in = self.patch("huf.ai.gateway_service._record_room_opt_in")
		self.opt_out = self.patch("huf.ai.gateway_service._record_room_opt_out")

	def pending(self):
		return [c for c in self.created if c.get("entry_type") == "Room"]

	def test_bot_added_to_group_creates_one_pending_room_entry(self):
		res = self.post(membership_update(600, "left", "member"))
		self.assertTrue(res.get("success"))
		self.opt_in.assert_called_once()
		rooms = self.pending()
		self.assertEqual(len(rooms), 1)
		self.assertEqual((rooms[0]["state"], rooms[0]["external_id"], rooms[0]["gateway"]), ("Pending", "-100123", GW_NAME))
		self.assertEqual(self.api.calls, [])  # never talks to an unapproved room

	def test_first_addressed_message_in_unknown_room_goes_pending_not_to_the_agent(self):
		res = self.post(group_msg(610))
		self.assertEqual(res.get("status"), "Rejected")
		self.assertEqual(len(self.pending()), 1)
		self.assertEqual(self.pending()[0]["external_id"], "-1001234")
		self.assertEqual(self.queued_events(), [])
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_unaddressed_chatter_in_unknown_room_creates_nothing(self):
		self.gw.mention_required = 0
		self.post(group_msg(611, text="just chatting", entities=[]))
		self.assertEqual(self.pending(), [])
		self.assertEqual(self.queued_events(), [])

	def test_approved_room_message_runs_the_agent_once(self):
		self.has_entry.return_value = True
		self.post(group_msg(620))
		self.assertEqual(len(self.queued_events()), 1)
		self.assertEqual(self.pending(), [])

	def test_duplicate_reply_suppressed_only_when_a_tool_already_sent_to_the_chat(self):
		event = SimpleNamespace(name="EV-1", sender_id="42", conversation_id="-1001234", db_set=lambda *a, **k: None)
		sent = []
		suppress = mock.patch.object(gs, "_suppress_reply", side_effect=lambda ev, run, note: {"suppressed": note})
		attempt = mock.patch.object(gs, "_attempt_reply_parts", side_effect=lambda *a: sent.append(a) or {"status": "Succeeded"})
		with suppress, attempt, \
			mock.patch.object(gs, "_reply_finished"), mock.patch.object(gs, "is_opted_out", return_value=False), \
			mock.patch.object(gs.provider_hooks, "get", return_value=None), \
			mock.patch.object(tp, "reply_scope", return_value=None):
			with mock.patch.object(tg_scope, "current_chat_texts", return_value=["Done, pinned it."]):
				out = gs._send_telegram_reply(event, self.gw, "run-1", "I pinned the message for you.")
			self.assertEqual(out, {"suppressed": tp.DUPLICATE_NOTE})
			self.assertEqual(sent, [])
			with mock.patch.object(tg_scope, "current_chat_texts", return_value=[]):
				out = gs._send_telegram_reply(event, self.gw, "run-2", "Here is your answer.")
			self.assertEqual(out["status"], "Succeeded")
			self.assertEqual(len(sent), 1)

	def test_bot_removed_opts_the_room_out_and_runs_nothing(self):
		res = self.post(membership_update(630, "member", "kicked"))
		self.assertTrue(res.get("success"))
		self.opt_out.assert_called_once()
		self.assertEqual(str(self.opt_out.call_args.args[1]), "-100123")
		self.assertEqual(self.pending(), [])
		self.assertEqual(self.events, [])

	def test_migration_drops_pending_duplicate_for_new_chat(self):
		from huf.ai.gateway_adapters import telegram_groups as groups

		dropped = self.patch("huf.ai.gateway_service._drop_pending_room", return_value=1)
		self.patch("huf.ai.gateway_service._live_room_entry", return_value={"name": "GAE-old"})
		real = {("Room", "-100123"): True}
		self.has_entry.side_effect = lambda gw, kind, ext: real.get((kind, str(ext)), False)
		old_doc = SimpleNamespace(state="Approved", display_label="Club", notes="", expires_at=None, approved_by="a@x.com")
		inner = self.fallback_get_doc
		self.fallback_get_doc = lambda *a, **k: old_doc if a[:2] == ("Gateway Access Entry", "GAE-old") else inner(*a, **k)
		self.patch("huf.ai.gateway_service._save_entry")
		self.assertTrue(groups.migrate_room(self.gw, "-100123", "-1001999888777"))
		dropped.assert_called_once_with(self.gw, "-1001999888777")
		# new entry already approved (race the other way): still removes the Pending duplicate
		dropped.reset_mock()
		real[("Room", "-1001999888777")] = True
		self.assertFalse(groups.migrate_room(self.gw, "-100123", "-1001999888777"))
		dropped.assert_called_once_with(self.gw, "-1001999888777")

	def test_migrate_to_chat_id_moves_the_approved_room(self):
		moves = []
		real = {("Room", "-100123"): True}
		self.has_entry.side_effect = lambda gw, kind, ext: real.get((kind, str(ext)), False)
		self.patch("huf.ai.gateway_service._live_room_entry", return_value={"name": "GAE-old"})
		old_doc = SimpleNamespace(db_set=lambda *a, **k: moves.append(("old", a)), state="Approved",
			display_label="Club", notes="", expires_at=None, approved_by="a@x.com")
		inner = self.fallback_get_doc
		self.fallback_get_doc = lambda *a, **k: old_doc if a[:2] == ("Gateway Access Entry", "GAE-old") else inner(*a, **k)
		saved = self.patch("huf.ai.gateway_service._save_entry")
		payload = {"update_id": 640, "message": {
			"message_id": 1, "from": _from(777), "chat": {"id": -100123, "type": "group", "title": "Club"},
			"date": int(time.time()), "migrate_to_chat_id": -1001999888777}}
		res = self.post(payload)
		self.assertEqual(res.get("note"), "migrated", res.body)
		new = [c for c in self.created if c.get("entry_type") == "Room"]
		self.assertEqual(len(new), 1)
		self.assertEqual((new[0]["external_id"], new[0]["state"]), ("-1001999888777", "Approved"))
		saved.assert_called_once()
		self.assertEqual(saved.call_args.args[1]["state"], gs.ENTRY_STATE_REVOKED)
		self.assertEqual(self.events, [])


# -- (4) join requests and welcomes --------------------------------------------------------------------------------


class TestJoinAndWelcome(SynthBase):
	def setUp(self):
		super().setUp()
		self.gate = self.gw
		self.patch("huf.ai.telegram_guard._load_gateway", return_value=self.gate)
		self.patch("huf.ai.telegram_guard._client_for", return_value=self.adapter.client)
		self.patch("huf.ai.telegram_guard._cache", return_value=self.cache)
		self.patch("huf.ai.telegram_guard._rate_ok", return_value=True)
		fakes.isolate_admin_cache(self, ta, self.cache)
		self.pending = self.patch("huf.ai.gateway_adapters.telegram_groups.record_pending_join")

	def test_queue_policy_records_pending_and_answers_queue(self):
		res = self.post(join_update(700, query_id="q1"))
		self.assertEqual(res.get("decision"), "queue")
		self.pending.assert_called_once()
		self.assertEqual(self.api.last("answerChatJoinRequestQuery")["payload"]["result"], "queue")
		self.assertEqual(self.calls("approveChatJoinRequest"), [])

	def test_agent_policy_never_auto_approves(self):
		self.gate.telegram_join_policy = "Agent"
		res = self.post(join_update(710, query_id="q2"))
		self.assertEqual(res.get("decision"), "queue")
		self.assertEqual(self.calls("approveChatJoinRequest"), [])
		kwargs = [k for a, k in self.enqueued if a and a[0] == "huf.ai.telegram_guard.resolve_agent_join"][0]
		out = tg.resolve_agent_join(kwargs["gateway_name"], kwargs["ctx"], runner=lambda g, p, c: '{"decision": "approve"}')
		self.assertEqual(out, "queue")
		self.assertEqual(self.calls("approveChatJoinRequest"), [])

	def test_guard_captcha_issues_challenge_and_defers(self):
		self.gate.telegram_guard_captcha = 1
		self.patch("frappe.utils.get_url", return_value="https://huf.example.com")
		self.patch("huf.ai.telegram_guard._bot_token", return_value=TOKEN)
		self.patch("huf.ai.telegram_guard.make_question",
			return_value={"kind": "math", "prompt": "What is 2 + 3?", "options": [], "answer": "5"})
		res = self.post(join_update(720, query_id="q-guard"))
		self.assertEqual(res.get("decision"), "defer")
		web = self.api.last("sendChatJoinRequestWebApp")["payload"]
		self.assertEqual(web["chat_join_request_query_id"], "q-guard")
		nonce = parse_qs(urlparse(web["web_app_url"]).query)["n"][0]
		self.assertTrue(nonce)
		self.assertEqual(self.calls("approveChatJoinRequest") + self.calls("answerChatJoinRequestQuery"), [])
		self.assertTrue(tg.submit_answer(GW_NAME, nonce, init_data(42), "5")["done"])
		self.assertEqual(self.api.last("approveChatJoinRequest")["payload"]["user_id"], 42)

	def test_join_request_for_unadmitted_room_is_ignored(self):
		self.gate.room_policy = "Disabled"
		res = self.post(join_update(730, query_id="q3"))
		self.assertEqual(res.get("decision"), "ignore")
		self.pending.assert_not_called()
		self.assertEqual(self.api.calls, [])

	def test_chat_member_welcome_is_capped_per_chat(self):
		self.gate.telegram_welcome_template = "Welcome"
		sent = []
		fake_mod = SimpleNamespace(send_template=lambda *a, **k: sent.append(a) or {})
		with mock.patch.dict(sys.modules, {"huf.ai.telegram_templates": fake_mod}), \
			mock.patch("huf.ai.telegram_templates", fake_mod, create=True):
			for n in range(tg.WELCOME_CHAT_CAP + 5):
				self.post(membership_update(800 + n, "left", "member", kind="chat_member", subject=5000 + n, actor=9))
		self.assertEqual(len(sent), tg.WELCOME_CHAT_CAP)

	def test_chat_member_welcome_requires_admitted_room(self):
		self.gate.telegram_welcome_template = "Welcome"
		self.gate.room_policy = "Disabled"
		sent = []
		fake_mod = SimpleNamespace(send_template=lambda *a, **k: sent.append(a) or {})
		with mock.patch.dict(sys.modules, {"huf.ai.telegram_templates": fake_mod}), \
			mock.patch("huf.ai.telegram_templates", fake_mod, create=True):
			self.post(membership_update(790, "left", "member", kind="chat_member", subject=5999, actor=9))
		self.assertEqual(sent, [])


# -- (5) Secretary / business mode ---------------------------------------------------------------------------------


def connection_update(update_id, rights=None, enabled=True, conn_id="bc-1"):
	conn = {"id": conn_id, "user": _from(OWNER, "Owner"), "user_chat_id": OWNER, "date": int(time.time()), "is_enabled": enabled}
	if rights is not None:
		conn["rights"] = rights
	return {"update_id": update_id, "business_connection": conn}


def business_msg(update_id, text="Do you have stock?", conn_id="bc-1", **extra):
	message = {
		"message_id": 7, "business_connection_id": conn_id, "from": _from(CUST, "Cust"),
		"chat": {"id": CUST, "first_name": "Cust", "type": "private"}, "date": int(time.time()), "text": text,
	}
	message.update(extra)
	return {"update_id": update_id, "business_message": message}


class TestBusiness(SynthBase):
	def setUp(self):
		super().setUp()
		self.patch("huf.ai.gateway_adapters.telegram_business_agent._load_gateway", return_value=self.gw)
		self.patch("huf.ai.gateway_adapters.telegram_business_agent._adapter", return_value=self.adapter)
		self.patch("huf.ai.gateway_adapters.telegram_business_agent._credential", return_value="")
		self.agent_calls = []

	def run_agent(self, **_kw):
		self.agent_calls.append(_kw)
		return {"success": True, "response": "Yes, we have stock."}

	def test_draft_mode_goes_to_owner_only_and_reply_mode_sends_as_owner(self):
		self.gw.telegram_business_policy = "Draft"
		self.post(connection_update(900, {"can_reply": True}))
		res = self.post(business_msg(901))
		self.assertEqual(res.get("note"), "draft queued")
		job = [(a, k) for a, k in self.enqueued if a and "run_business_job" in str(a[0])][0][1]
		self.assertEqual(job["mode"], "draft")
		with mock.patch.object(bagent, "_run_agent", return_value={"success": True, "response": "Yes, we have stock."}):
			out = bagent.run_business_job("gw1", "draft", "bc-1", str(CUST), "7", "901", "Do you have stock?", "Cust")
		self.assertEqual(out["result"], "draft")
		sent = self.api.last("sendMessage")["payload"]
		self.assertEqual(str(sent["chat_id"]), str(OWNER))
		self.assertNotIn("business_connection_id", sent)
		self.assertEqual(self.queued_events(), [])  # the business path never creates a Gateway Event run

		self.gw.telegram_business_policy = "Reply"
		self.api.calls.clear()
		self.enqueued.clear()
		res = self.post(business_msg(902))
		self.assertEqual(res.get("note"), "auto-reply queued")
		with mock.patch.object(bagent, "_run_agent", return_value={"success": True, "response": "Yes, we have stock."}):
			out = bagent.run_business_job("gw1", "reply", "bc-1", str(CUST), "7", "902", "hi", "Cust")
		self.assertEqual(out["result"], "replied")
		sent = self.api.last("sendMessage")["payload"]
		self.assertEqual((sent["business_connection_id"], str(sent["chat_id"])), ("bc-1", str(CUST)))

	def test_secretary_run_gets_no_tools_and_state_is_restored(self):
		self.gw.telegram_business_policy = "Reply"
		self.post(connection_update(910, {"can_reply": True}))
		seen = {}

		def serialised(run, **kw):
			seen["allowlist"] = getattr(frappe.local, bagent.TOOL_ALLOWLIST_ATTR, "missing")
			return {"success": True, "response": "ok"}

		ident = SimpleNamespace(authorized=True, reason="")
		with mock.patch("huf.ai.agent_access.resolve_run_identity_and_authorize", return_value=ident), \
			mock.patch.object(gs, "_run_agent_serialised", side_effect=serialised):
			out = bagent._run_agent(self.gw, "bc-1", str(CUST), "prompt", "idem")
		self.assertEqual(seen["allowlist"], [])
		self.assertTrue(out["success"])
		self.assertIsNone(getattr(frappe.local, bagent.TOOL_ALLOWLIST_ATTR, None))

	def test_unknown_connection_is_ignored(self):
		self.gw.telegram_business_policy = "Reply"
		res = self.post(business_msg(920, conn_id="bc-unknown"))
		self.assertEqual(self.enqueued, [])
		self.assertEqual(self.api.of("sendMessage"), [])
		self.assertEqual(self.queued_events(), [])
		self.assertIsNotNone(res.body)

	def test_missing_reply_right_downgrades_to_observe(self):
		self.gw.telegram_business_policy = "Reply"
		self.post(connection_update(930, {"can_read_messages": True}))
		res = self.post(business_msg(931))
		self.assertEqual(res.get("policy"), "observe")
		self.assertEqual(self.enqueued, [])
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_owner_and_bot_messages_never_trigger_the_secretary(self):
		self.gw.telegram_business_policy = "Reply"
		self.post(connection_update(940, {"can_reply": True}))
		owner = business_msg(941)
		owner["business_message"]["from"] = _from(OWNER, "Owner")
		bot = business_msg(942)
		bot["business_message"]["from"] = _from(555, "Bot", is_bot=True)
		for payload in (owner, bot):
			self.assertEqual(self.post(payload).get("policy"), "ignore")
		self.assertEqual(self.enqueued, [])


if __name__ == "__main__":
	unittest.main()
