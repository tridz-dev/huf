"""End-to-end Telegram mode tests: every hook module loaded in the real telegram_hooks import order, driven through
``telegram_ingest.handle_update`` with the in-memory Bot API fake and an in-memory cache. Fakes only, no network.

Covers inline mode, guest mode, join requests (queue / decline / agent / Guard captcha), my_chat_member membership,
Secretary (business) mode with policies and loop prevention, bot-to-bot loop guard, stopped_message_generation,
and the update-handler chain for the 'message', 'callback_query' and 'unsupported' keys.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlparse

from huf.ai import telegram_admin
from huf.ai import telegram_guard as tg
from huf.ai.gateway_adapters import (
	GatewayInboundRequest,
	provider_hooks,
	telegram_hooks,
)
from huf.ai.gateway_adapters import (
	telegram_business as biz,
)
from huf.ai.gateway_adapters import (
	telegram_business_agent as agent,
)
from huf.ai.gateway_adapters import (
	telegram_guest as guest,
)
from huf.ai.gateway_adapters import (
	telegram_ingest as ing,
)
from huf.ai.gateway_adapters import (
	telegram_inline as inline,
)
from huf.ai.gateway_adapters import (
	telegram_loop_guard as lg,
)
from huf.ai.gateway_adapters import (
	telegram_modes_hooks as mh,
)
from huf.ai.gateway_adapters import (
	telegram_stream as stream,
)
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi

OWNER = 1001
CUST = 2002
PROVIDER = "Telegram"
_ORIGINAL_HANDLERS = dict(ing._UPDATE_HANDLERS)


def hook_modules() -> list[str]:
	"""The hook modules in the exact order telegram_hooks.py imports them."""
	src = Path(telegram_hooks.__file__).read_text(encoding="utf-8")
	return re.findall(r"^import (huf\.ai\.gateway_adapters\.\w+_hooks)\b", src, re.M)


def load_all_hooks() -> list[str]:
	"""Rebuild the update-handler registry from scratch by re-running every hook module in import order."""
	ing._UPDATE_HANDLERS.clear()
	names = hook_modules()
	for name in names:
		importlib.reload(importlib.import_module(name))
	return names


def tearDownModule():
	ing._UPDATE_HANDLERS.clear()
	ing._UPDATE_HANDLERS.update(_ORIGINAL_HANDLERS)


class FakeCache:
	"""Covers get/set_value, the frappe Redis surface (make_key, set nx, incrby, expire) used by the hooks."""

	def __init__(self):
		self.d: dict = {}

	def make_key(self, key):
		return key

	def get_value(self, key):
		return self.d.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def delete_value(self, key):
		self.d.pop(key, None)

	def set(self, key, value, ex=None, nx=False):
		if nx and key in self.d:
			return False
		self.d[key] = value
		return True

	def incrby(self, key, amount=1):
		self.d[key] = int(self.d.get(key) or 0) + amount
		return self.d[key]

	def expire(self, key, ttl):
		return True


def init_data(user_id: int, token: str = TOKEN) -> str:
	"""Signed Telegram Mini App initData (WebAppData HMAC) for a fresh auth_date."""
	fields = {
		"auth_date": str(int(time.time())),
		"query_id": "AAH",
		"user": json.dumps({"id": user_id, "first_name": "U"}),
	}
	dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
	secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
	fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
	return urlencode(fields)


class GatewayDouble(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)


class E2EBase(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post,
			download_attachments=False,
		)
		self.gw = GatewayDouble(
			name="gw1",
			provider=PROVIDER,
			mention_required=0,
			direct_policy="Allow list",
			execution_user="bot.user@example.com",
			default_agent="Sec",
			is_enabled=1,
			telegram_business_policy="Observe",
			telegram_join_policy="Queue",
			room_policy="Open",
			telegram_guard_captcha=0,
			telegram_welcome_template=None,
		)
		self.handlers = load_all_hooks()
		self.ingest = self.patch(
			"huf.ai.gateway_service.ingest_gateway_event", return_value={"event_name": "E1"}
		)
		self.patch("huf.ai.gateway_webhook.touch_last_event")
		self.patch("frappe.cache", return_value=self.cache)
		self.patch("frappe.logger")
		self.enqueue = self.patch("frappe.enqueue")

	def patch(self, target, **kw):
		p = mock.patch(target, **kw)
		m = p.start()
		self.addCleanup(p.stop)
		return m

	def send(self, payload, gw=None):
		req = GatewayInboundRequest(json.dumps(payload).encode(), headers={WEBHOOK_SECRET_HEADER: SECRET})
		return ing.handle_update(gw or self.gw, self.adapter, req)

	def ingested_context(self, i=0):
		return self.ingest.call_args_list[i]


def msg(update_id, text="hi", sender=42, chat=None, **extra):
	chat = chat or {"id": 42, "type": "private"}
	body = {
		"message_id": update_id,
		"from": {"id": sender, "is_bot": False, "first_name": "Ann"},
		"chat": chat,
		"date": 1760000000,
		"text": text,
	}
	body.update(extra)
	return {"update_id": update_id, "message": body}


def group_msg(update_id, sender=42, text="hello", **extra):
	body = {
		"message_id": update_id,
		"from": {"id": sender, "is_bot": False, "first_name": "B"},
		"chat": {"id": -100, "type": "supergroup", "title": "Club"},
		"date": 1760000000,
		"text": text,
	}
	body.update(extra)
	return {"update_id": update_id, "message": body}


# -- inline mode ------------------------------------------------------------------------------------------------------


def inline_update(update_id=9001, sender=42, is_bot=False, query="weather"):
	return {
		"update_id": update_id,
		"inline_query": {
			"id": f"iq{update_id}",
			"query": query,
			"offset": "",
			"from": {"id": sender, "is_bot": is_bot, "first_name": "Ann"},
		},
	}


class TestInlineMode(E2EBase):
	def setUp(self):
		super().setUp()
		self.admitted = self.patch("huf.ai.gateway_service._has_access_entry", return_value=True)
		self.patch("huf.ai.gateway_service._sender_negative_state", return_value=None)
		self.patch("frappe.set_user")

	def test_unpaired_sender_gets_pair_answer_and_no_data(self):
		self.admitted.return_value = False
		result = self.send(inline_update())
		self.assertEqual(result["success"], True)
		payload = self.api.last("answerInlineQuery")["payload"]
		self.assertEqual(payload["results"][0]["id"], "pair")
		self.assertEqual(payload["cache_time"], 300)
		self.assertEqual(payload["button"]["start_parameter"], "pair")
		self.ingest.assert_not_called()

	def test_paired_sender_gets_resolver_results(self):
		result = self.send(inline_update())
		payload = self.api.last("answerInlineQuery")["payload"]
		self.assertEqual(result["handled"], "inline_query")
		self.assertEqual(len(payload["results"]), 1)
		self.assertTrue(payload["results"][0]["id"].startswith("ask-"))
		self.assertTrue(payload["is_personal"])
		self.assertEqual(payload["cache_time"], inline.DEFAULT_CACHE_TIME)

	def test_no_execution_user_means_empty_results_not_admin(self):
		for user in (None, "", "Administrator", "Guest"):
			with self.subTest(user=user):
				self.api.calls.clear()
				self.gw.execution_user = user
				self.send(inline_update(update_id=9100 + len(str(user))))
				self.assertEqual(self.api.last("answerInlineQuery")["payload"]["results"], [])

	def test_unknown_policy_is_treated_as_unpaired(self):
		self.gw.direct_policy = "Disabled"
		self.admitted.return_value = True
		self.send(inline_update())
		self.assertEqual(self.api.last("answerInlineQuery")["payload"]["results"][0]["id"], "pair")

	def test_bot_sender_is_ignored(self):
		result = self.send(inline_update(is_bot=True))
		self.assertEqual(result["note"], "bot sender ignored")
		self.assertEqual(self.api.of("answerInlineQuery"), [])

	def test_chosen_inline_result_recorded_only(self):
		payload = {
			"update_id": 9200,
			"chosen_inline_result": {"result_id": "ask-x", "from": {"id": 42}, "query": "secret query text"},
		}
		result = self.send(payload)
		self.assertEqual(result, {"success": True, "handled": "chosen_inline_result"})
		self.assertEqual(self.api.calls, [])
		self.ingest.assert_not_called()


# -- guest mode -------------------------------------------------------------------------------------------------------


def guest_update(update_id, guest_id=55, text="what is the price?", query_id="gq1"):
	return {
		"update_id": update_id,
		"guest_message": {
			"message_id": 3,
			"guest_query_id": query_id,
			"from": {"id": guest_id, "is_bot": False, "first_name": "Gus"},
			"chat": {"id": -500, "type": "supergroup"},
			"text": text,
		},
	}


class TestGuestMode(E2EBase):
	def test_open_policy_ingests_as_guest_conversation(self):
		self.gw.direct_policy = "Open"
		result = self.send(guest_update(7001))
		self.assertTrue(result["success"])
		self.ingest.assert_called_once()
		self.assertEqual(self.ingested_context().args[2]["conversation_id"], "guest:-500")
		meta = self.ingested_context().kwargs["raw_payload"]["telegram_meta"]
		self.assertEqual((meta["guest"], meta["guest_query_id"]), (True, "gq1"))
		self.assertEqual(self.api.of("answerGuestQuery"), [])

	def test_non_open_policy_denies_once_per_guest(self):
		for policy in ("Allow list", "Pairing", "Closed"):
			with self.subTest(policy=policy):
				self.cache.d.clear()
				self.api.calls.clear()
				self.gw.direct_policy = policy
				first = self.send(guest_update(7100 + len(policy)))
				second = self.send(guest_update(7200 + len(policy)))
				self.assertEqual(first["note"], "guests not allowed by gateway policy")
				self.assertEqual(second["note"], "guests not allowed by gateway policy")
				answers = self.api.of("answerGuestQuery")
				self.assertEqual(len(answers), 1)
				self.assertEqual(
					answers[0]["payload"]["result"]["input_message_content"]["message_text"],
					guest.DENIED_TEXT,
				)
		self.ingest.assert_not_called()

	def test_rate_limit_replies_once_and_stops_ingest(self):
		self.gw.direct_policy = "Open"
		results = [self.send(guest_update(7300 + i, guest_id=60)) for i in range(guest.PER_GUEST_LIMIT + 2)]
		self.assertEqual(self.ingest.call_count, guest.PER_GUEST_LIMIT)
		self.assertEqual(results[-1]["note"], "rate limited")
		answers = self.api.of("answerGuestQuery")
		self.assertEqual(len(answers), 1)
		self.assertEqual(
			answers[0]["payload"]["result"]["input_message_content"]["message_text"], guest.RATE_TEXT
		)

	def test_malformed_and_empty_guest_updates_are_dropped(self):
		self.gw.direct_policy = "Open"
		bad = guest_update(7400)
		del bad["guest_message"]["guest_query_id"]
		self.assertEqual(self.send(bad)["note"], "malformed guest message dropped")
		empty = guest_update(7401, text="   ")
		self.assertEqual(self.send(empty)["note"], "no text")
		self.ingest.assert_not_called()
		self.assertEqual(self.api.calls, [])


# -- join requests, Guard mode and membership ---------------------------------------------------------------------


def join_update(update_id=6001, user=42, query_id=""):
	jr = {
		"chat": {"id": -100123, "type": "supergroup", "title": "Club"},
		"from": {"id": user, "is_bot": False, "first_name": "Ann", "username": "ann"},
		"user_chat_id": user,
		"date": 1760000000,
		"bio": "hello",
	}
	if query_id:
		jr["query_id"] = query_id
	return {"update_id": update_id, "chat_join_request": jr}


class TestJoinRequests(E2EBase):
	def setUp(self):
		super().setUp()
		self.gate = SimpleNamespace(
			name="gw1",
			provider=PROVIDER,
			default_agent="Sec",
			telegram_join_policy="Queue",
			room_policy="Open",
			telegram_guard_captcha=0,
		)
		self.patch("huf.ai.telegram_guard._load_gateway", return_value=self.gate)
		self.patch("huf.ai.telegram_guard._client_for", return_value=self.adapter.client)
		self.patch("huf.ai.telegram_guard._cache", return_value=self.cache)
		self.patch("huf.ai.telegram_guard._rate_ok", return_value=True)
		self.pending = self.patch("huf.ai.gateway_adapters.telegram_groups.record_pending_join")

	def test_default_policy_queues_without_answering(self):
		result = self.send(join_update())
		self.assertEqual(result["decision"], "queue")
		self.pending.assert_called_once()
		self.assertEqual(self.api.calls, [])

	def test_decline_policy_declines_plain_request(self):
		self.gate.telegram_join_policy = "Decline"
		result = self.send(join_update())
		self.assertEqual(result["decision"], "decline")
		call = self.api.last("declineChatJoinRequest")["payload"]
		self.assertEqual((str(call["chat_id"]), call["user_id"]), ("-100123", 42))
		self.pending.assert_not_called()

	def test_decline_policy_with_guard_query_answers_within_window(self):
		self.gate.telegram_join_policy = "Decline"
		self.send(join_update(query_id="q-dec"))
		call = self.api.last("answerChatJoinRequestQuery")["payload"]
		self.assertEqual(call, {"chat_join_request_query_id": "q-dec", "result": "decline"})

	def test_agent_policy_queues_now_and_decides_later_from_agent_json(self):
		self.gate.telegram_join_policy = "Agent"
		result = self.send(join_update(query_id="q-agent"))
		self.assertEqual(result["decision"], "queue")
		self.assertEqual(self.api.last("answerChatJoinRequestQuery")["payload"]["result"], "queue")
		self.enqueue.assert_called_once()
		self.assertEqual(self.enqueue.call_args.args[0], "huf.ai.telegram_guard.resolve_agent_join")
		kwargs = self.enqueue.call_args.kwargs

		cases = {
			'{"decision": "approve", "reason": "fits"}': None,  # S1: an agent approve is downgraded to queue
			'```json\n{"decision": "approve"}\n```': None,
			'{"decision": "decline"}': "decline",
			"approve!": None,
			'{"decision": "approve", "extra": 1}': None,
		}
		for text, want in cases.items():
			with self.subTest(text=text):
				self.api.calls.clear()
				out = tg.resolve_agent_join(
					kwargs["gateway_name"], kwargs["ctx"], runner=lambda g, p, c, t=text: t
				)
				if want is None:
					self.assertEqual(out, "queue")
					self.assertEqual(
						self.api.of("approveChatJoinRequest") + self.api.of("declineChatJoinRequest"), []
					)
				else:
					self.assertEqual(out, want)
					method = "approveChatJoinRequest" if want == "approve" else "declineChatJoinRequest"
					self.assertEqual(self.api.last(method)["payload"]["user_id"], 42)

	def test_agent_failure_falls_back_to_queue(self):
		self.gate.telegram_join_policy = "Agent"
		self.send(join_update(query_id="q-fail"))
		self.api.calls.clear()  # the synchronous 'queue' answer is not the agent's doing
		kwargs = self.enqueue.call_args.kwargs

		def boom(*_a, **_k):
			raise RuntimeError("agent down")

		self.assertEqual(tg.resolve_agent_join(kwargs["gateway_name"], kwargs["ctx"], runner=boom), "queue")
		self.assertEqual(self.api.calls, [])

	def test_guard_captcha_required_defers_then_approves_on_correct_answer(self):
		self.gate.telegram_guard_captcha = 1
		self.patch("frappe.utils.get_url", return_value="https://huf.example.com")
		self.patch("huf.ai.telegram_guard._bot_token", return_value=TOKEN)
		self.patch(
			"huf.ai.telegram_guard.make_question",
			return_value={"kind": "math", "prompt": "What is 2 + 3?", "options": [], "answer": "5"},
		)
		result = self.send(join_update(query_id="q-guard"))
		self.assertEqual(result["decision"], "defer")
		self.assertEqual(self.api.of("answerChatJoinRequestQuery"), [])
		web = self.api.last("sendChatJoinRequestWebApp")["payload"]
		self.assertEqual(web["chat_join_request_query_id"], "q-guard")
		nonce = parse_qs(urlparse(web["web_app_url"]).query)["n"][0]

		self.assertFalse(tg.submit_answer("gw1", nonce, init_data(42), "4")["done"])
		done = tg.submit_answer("gw1", nonce, init_data(42), "5")
		self.assertEqual((done["ok"], done["done"]), (True, True))
		self.assertEqual(self.api.last("approveChatJoinRequest")["payload"]["user_id"], 42)
		self.assertEqual(self.api.of("answerChatJoinRequestQuery"), [])  # the query was spent by the web app
		with self.assertRaises(tg.GuardError):
			tg.submit_answer("gw1", nonce, init_data(42), "5")  # single use

	def test_guard_captcha_wrong_user_and_three_wrong_answers_decline(self):
		self.gate.telegram_guard_captcha = 1
		self.patch("frappe.utils.get_url", return_value="https://huf.example.com")
		self.patch("huf.ai.telegram_guard._bot_token", return_value=TOKEN)
		self.patch(
			"huf.ai.telegram_guard.make_question",
			return_value={"kind": "math", "prompt": "What is 2 + 3?", "options": [], "answer": "5"},
		)
		self.send(join_update(query_id="q-wrong"))
		nonce = parse_qs(
			urlparse(self.api.last("sendChatJoinRequestWebApp")["payload"]["web_app_url"]).query
		)["n"][0]
		with self.assertRaises(tg.GuardError):
			tg.submit_answer("gw1", nonce, init_data(99), "5")  # someone else's initData
		for _ in range(tg.MAX_ATTEMPTS):
			last = tg.submit_answer("gw1", nonce, init_data(42), "0")
		self.assertEqual((last["ok"], last["done"]), (False, True))
		self.assertEqual(self.api.last("declineChatJoinRequest")["payload"]["user_id"], 42)

	def test_guard_without_captcha_answers_queue_synchronously(self):
		self.gate.telegram_join_policy = "Queue"
		self.gate.telegram_guard_captcha = 0
		self.send(join_update(query_id="q-sync"))
		self.assertEqual(self.api.last("answerChatJoinRequestQuery")["payload"]["result"], "queue")
		self.assertEqual(self.api.of("sendChatJoinRequestWebApp"), [])

	def test_captcha_never_auto_approves_a_plain_join_request(self):
		self.gate.telegram_guard_captcha = 1
		result = self.send(join_update())  # no query_id: captcha cannot run, the human admins decide
		self.assertEqual(result["decision"], "queue")
		self.assertEqual(self.api.calls, [])


class TestMembership(E2EBase):
	def setUp(self):
		super().setUp()
		self.opt_out = self.patch("huf.ai.gateway_service._record_opt_out")
		self.opt_in = self.patch("huf.ai.gateway_service._record_opt_in")
		self.room_out = self.patch("huf.ai.gateway_service._record_room_opt_out")
		self.room_in = self.patch("huf.ai.gateway_service._record_room_opt_in")

	def group_membership(self, old, new, update_id):
		return {
			"update_id": update_id,
			"my_chat_member": {
				"chat": {"id": -100123, "type": "supergroup", "title": "Club"},
				"from": {"id": 42, "is_bot": False, "first_name": "Ann"},
				"date": 1760000000,
				"old_chat_member": {"status": old, "user": {"id": 777, "is_bot": True}},
				"new_chat_member": {"status": new, "user": {"id": 777, "is_bot": True}},
			},
		}

	def test_bot_removed_from_group_marks_chat_unsendable(self):
		result = self.send(self.group_membership("member", "left", 5001))
		self.assertTrue(result["success"])
		self.room_out.assert_called_once()
		self.assertEqual(str(self.room_out.call_args.args[1]), "-100123")
		self.opt_out.assert_not_called()
		self.ingest.assert_not_called()

	def test_bot_readded_to_group_restores_chat(self):
		self.send(self.group_membership("left", "member", 5002))
		self.room_in.assert_called_once()
		self.assertEqual(str(self.room_in.call_args.args[1]), "-100123")
		self.opt_in.assert_not_called()
		self.opt_out.assert_not_called()

	def test_private_block_marks_known_sender_unsendable_and_unknown_is_not_stored(self):
		payload = json.loads(
			(Path(__file__).parent / "fixtures" / "telegram" / "my_chat_member_blocked.json").read_text()
		)
		with mock.patch("huf.ai.gateway_service._sender_is_known", return_value=True):
			self.send(payload)
		self.assertEqual(self.opt_out.call_count, 1)
		with mock.patch("huf.ai.gateway_service._sender_is_known", return_value=False):
			self.send(payload | {"update_id": payload["update_id"] + 1})
		self.assertEqual(self.opt_out.call_count, 1)
		self.ingest.assert_not_called()

	def test_private_unblock_restores_sender(self):
		payload = json.loads(
			(Path(__file__).parent / "fixtures" / "telegram" / "my_chat_member_unblocked.json").read_text()
		)
		self.send(payload)
		self.assertEqual(str(self.opt_in.call_args.args[1]), str(payload["my_chat_member"]["from"]["id"]))


# -- Secretary (business) mode ------------------------------------------------------------------------------------


def connection(rights=None, enabled=True, update_id=3001):
	conn = {
		"id": "bc-1",
		"user": {"id": OWNER, "is_bot": False, "first_name": "Owner"},
		"user_chat_id": OWNER,
		"date": 1760000000,
		"is_enabled": enabled,
	}
	if rights is not None:
		conn["rights"] = rights
	return {"update_id": update_id, "business_connection": conn}


def biz_msg(update_id=3002, sender=CUST, text="Do you have stock?", kind="business_message", **extra):
	body = {
		"message_id": 7,
		"business_connection_id": "bc-1",
		"from": {"id": sender, "is_bot": False, "first_name": "Cust"},
		"chat": {"id": CUST, "type": "private"},
		"date": 1760000000,
		"text": text,
	}
	body.update(extra)
	return {"update_id": update_id, kind: body}


class TestBusinessMode(E2EBase):
	def setUp(self):
		super().setUp()
		self.gw.telegram_business_policy = "Observe"
		self.gw.provider = PROVIDER
		self.patch("huf.ai.gateway_adapters.telegram_business_agent._load_gateway", return_value=self.gw)
		self.patch("huf.ai.gateway_adapters.telegram_business_agent._adapter", return_value=self.adapter)
		self.run_agent = self.patch(
			"huf.ai.gateway_adapters.telegram_business_agent._run_agent",
			return_value={"success": True, "response": "Yes, we have stock."},
		)
		self.patch("huf.ai.gateway_adapters.telegram_business_agent._credential", return_value="")
		self.enqueue_mock = self.enqueue
		self.patch("frappe.logger")

	def connect(self, rights):
		self.send(connection(rights))

	def policy(self, value):
		self.gw.telegram_business_policy = value

	def test_ignore_policy_neither_observes_nor_runs(self):
		self.connect({"can_reply": True})
		self.policy("Ignore")
		result = self.send(biz_msg())
		self.assertEqual(result["note"], "policy ignore")
		self.assertEqual([o for o in biz.observations("gw1") if o["event"] != "connection"], [])
		self.enqueue_mock.assert_not_called()

	def test_observe_policy_records_and_never_answers(self):
		self.connect({"can_reply": True})
		self.policy("Observe")
		result = self.send(biz_msg())
		self.assertEqual(result["policy"], "observe")
		self.assertEqual(biz.observations("gw1")[-1]["event"], "message")
		self.enqueue_mock.assert_not_called()
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_draft_with_rights_enqueues_and_draft_goes_to_owner_only(self):
		self.connect({"can_reply": True})
		self.policy("Draft")
		result = self.send(biz_msg())
		self.assertEqual(result["note"], "draft queued")  # the job delivers the draft asynchronously
		self.enqueue_mock.assert_called_once()
		self.assertEqual(self.enqueue_mock.call_args.kwargs["mode"], "draft")
		out = agent.run_business_job(
			"gw1", "draft", "bc-1", str(CUST), "7", "3002", "Do you have stock?", "Cust"
		)
		self.assertEqual(out["result"], "draft")
		sent = self.api.of("sendMessage")[-1]["payload"]
		self.assertEqual(str(sent["chat_id"]), str(OWNER))
		self.assertNotIn("business_connection_id", sent)
		self.assertIn("Yes, we have stock.", sent["text"])

	def test_draft_or_reply_without_can_reply_downgrades_to_observe(self):
		for policy in ("Draft", "Reply"):
			with self.subTest(policy=policy):
				self.cache.d.clear()
				self.enqueue_mock.reset_mock()
				self.connect({"can_read_messages": True})
				self.policy(policy)
				result = self.send(biz_msg(update_id=3100 + len(policy)))
				self.assertEqual(result["policy"], "observe")
				self.enqueue_mock.assert_not_called()
		self.assertEqual(biz.observations("gw1")[-1]["note"], "")  # reply without right: plain observe

	def test_connection_without_any_rights_object_is_treated_as_no_rights(self):
		self.send(connection(None))
		self.policy("Reply")
		self.assertEqual(self.send(biz_msg())["policy"], "observe")
		self.enqueue_mock.assert_not_called()

	def test_reply_with_rights_queues_one_job_and_duplicates_do_not_requeue(self):
		self.connect({"can_reply": True})
		self.policy("Reply")
		result = self.send(biz_msg(update_id=3300))
		self.assertEqual(result["note"], "auto-reply queued")
		self.enqueue_mock.assert_called_once()
		self.assertEqual(self.enqueue_mock.call_args.kwargs["mode"], "reply")
		self.assertEqual(self.send(biz_msg(update_id=3300))["note"], "duplicate update ignored")
		self.assertEqual(self.enqueue_mock.call_count, 1)

	def test_reply_job_sends_as_owner_with_business_connection(self):
		self.connect({"can_reply": True})
		self.policy("Reply")
		self.send(biz_msg(update_id=3400))
		out = agent.run_business_job(
			"gw1", "reply", "bc-1", str(CUST), "7", "3400", "Do you have stock?", "Cust"
		)
		self.assertEqual(out["result"], "replied")
		sent = self.api.last("sendMessage")["payload"]
		self.assertEqual(sent["business_connection_id"], "bc-1")
		self.assertEqual(str(sent["chat_id"]), str(CUST))
		self.assertEqual(sent["text"], "Yes, we have stock.")

	def test_reply_job_blocked_when_right_removed_before_run(self):
		self.connect({"can_reply": True})
		self.policy("Reply")
		self.send(biz_msg(update_id=3500))
		self.send(connection({"can_reply": False}, update_id=3501))
		out = agent.run_business_job("gw1", "reply", "bc-1", str(CUST), "7", "3500", "hi", "Cust")
		self.assertEqual(out, {"result": "skipped", "reason": "no_reply_right"})
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_disabled_connection_observed_only(self):
		self.send(connection({"can_reply": True}, enabled=False))
		self.policy("Reply")
		result = self.send(biz_msg(update_id=3600))
		self.assertEqual(biz.observations("gw1")[-1]["note"], "connection_disabled")
		self.assertEqual(result["policy"], "observe")
		self.enqueue_mock.assert_not_called()

	def test_reply_is_downgraded_to_draft_when_rate_limited(self):
		self.connect({"can_reply": True})
		self.policy("Reply")
		for _ in range(agent.RATE_LIMIT):
			agent._rate_hit("gw1", "bc-1", str(CUST))
		self.send(biz_msg(update_id=3700))
		self.assertEqual(self.enqueue_mock.call_args.kwargs["mode"], "draft")

	def test_owner_own_bot_and_business_bot_messages_never_trigger_policy(self):
		self.connect({"can_reply": True})
		self.policy("Reply")
		bot_sender = biz_msg(update_id=3802, sender=555)
		bot_sender["business_message"]["from"]["is_bot"] = True
		cases = {
			"owner": biz_msg(update_id=3800, sender=OWNER),
			"business_bot": biz_msg(update_id=3801, sender_business_bot={"id": 999, "is_bot": True}),
			"bot_sender": bot_sender,
		}
		for name, payload in cases.items():
			with self.subTest(name=name):
				result = self.send(payload)
				self.assertEqual(result["policy"], "ignore")
		self.enqueue_mock.assert_not_called()

	def test_edited_business_message_never_triggers_reply(self):
		self.connect({"can_reply": True})
		self.policy("Reply")
		self.send(biz_msg(update_id=3900, kind="edited_business_message"))
		self.enqueue_mock.assert_not_called()
		self.assertEqual(biz.observations("gw1")[-1]["event"], "edit")


# -- bot-to-bot loop guard (ingest prefilter) ---------------------------------------------------------------------


def bot_msg(update_id, bot=9, chat=-100, text="ping"):
	return {
		"update_id": update_id,
		"message": {
			"message_id": update_id,
			"from": {"id": bot, "is_bot": True, "first_name": "B"},
			"chat": {"id": chat, "type": "supergroup", "title": "Club"},
			"date": 1760000000,
			"text": text,
		},
	}


class TestBotLoopGuard(E2EBase):
	def setUp(self):
		super().setUp()
		self.gw.telegram_bot_allowlist = "9"
		self.gw.telegram_bot_max_hops = 3
		self.patch("huf.ai.gateway_adapters.telegram_modes_hooks._bot_username", return_value="huf_bot")
		self.clock_guard = lambda cache, gw: lg.LoopGuard(
			cache, max_hops=int(gw.telegram_bot_max_hops), rate_cap=5, clock=lambda: 1000.0
		)

	def guard_with_clock(self):
		return mock.patch.object(lg.LoopGuard, "from_gateway", side_effect=self.clock_guard)

	def test_bot_not_in_allowlist_is_dropped_before_ingest(self):
		self.gw.telegram_bot_allowlist = ""
		result = self.send(bot_msg(4001))
		self.assertIn("allow-list", result["note"])
		self.ingest.assert_not_called()

	def test_own_bot_message_is_dropped_even_if_allowlisted(self):
		self.gw.telegram_bot_allowlist = TOKEN.split(":", 1)[0]
		result = self.send(bot_msg(4002, bot=int(TOKEN.split(":", 1)[0])))
		self.assertIn("own bot message", result["note"])
		self.ingest.assert_not_called()

	def test_hop_cap_stops_at_limit_and_human_message_resets(self):
		with self.guard_with_clock():
			results = [self.send(bot_msg(4100 + i)) for i in range(5)]
			self.assertIn("hop limit", results[3]["note"])
			self.assertIn("hop limit", results[4]["note"])
			self.assertEqual(self.ingest.call_count, 3)
			self.send(msg(4200, text="human here", sender=42, chat={"id": -100, "type": "supergroup"}))
			self.ingest.reset_mock()
			self.send(bot_msg(4201))
			self.ingest.assert_called_once()

	def test_rate_cap_applies_per_chat_and_bot(self):
		self.gw.telegram_bot_max_hops = 50
		with self.guard_with_clock():
			results = [self.send(bot_msg(4300 + i)) for i in range(6)]
		self.assertIn("rate cap", results[5]["note"])
		self.assertEqual(self.ingest.call_count, 5)

	def test_group_message_not_addressed_to_bot_is_dropped_when_mention_required(self):
		self.gw.mention_required = 1
		result = self.send(group_msg(4400, sender=42, text="hi everyone"))
		self.assertIn("not addressed", result["note"])
		self.ingest.assert_not_called()
		self.assertTrue(
			self.send(
				group_msg(
					4401,
					sender=42,
					text="hi @huf_bot",
					entities=[{"type": "mention", "offset": 3, "length": 8}],
				)
			)["success"]
		)
		self.ingest.assert_called_once()


# -- stopped_message_generation -----------------------------------------------------------------------------------


class TestStopGeneration(E2EBase):
	def test_stop_without_active_stream_is_acked(self):
		result = self.send({"update_id": 4500, "stopped_message_generation": {"chat": {"id": 5}}})
		self.assertEqual(result["note"], "no active stream")
		self.ingest.assert_not_called()

	def test_stop_marks_stream_and_cancels_agent_run(self):
		stream.StreamState("gw1", "5").update(draft_id=1, run_id="run-1")
		cancel = mock.Mock()
		self.patch("huf.ai.run_control.cancel_agent_run", new=cancel)
		self.patch("frappe.set_user")
		self.patch("frappe.session", new=SimpleNamespace(user="Administrator"))
		result = self.send(
			{"update_id": 4501, "stopped_message_generation": {"chat": {"id": 5}, "draft_id": 1}}
		)
		self.assertEqual((result["stopped"], result["run_cancelled"]), (True, True))
		cancel.assert_called_once_with("run-1")
		self.assertTrue(stream.StreamState("gw1", "5").stopped())
		self.ingest.assert_not_called()


# -- handler chain ------------------------------------------------------------------------------------------------


class TestHandlerChain(E2EBase):
	def test_registry_keeps_every_key_after_registering_all_modules(self):
		for key in (
			"message",
			"edited_message",
			"channel_post",
			"callback_query",
			"unsupported",
			"inline_query",
			"chosen_inline_result",
			"guest_message",
			"chat_join_request",
			"chat_member",
			"my_chat_member",
			"business_connection",
			"business_message",
			"edited_business_message",
			"deleted_business_messages",
			"stopped_message_generation",
		):
			with self.subTest(key=key):
				self.assertIn(key, ing._UPDATE_HANDLERS)
		self.assertIsNotNone(provider_hooks.get(PROVIDER, "guest_reply"))
		self.assertIsNotNone(provider_hooks.get(PROVIDER, "conversation_key"))

	def test_hook_import_order_matches_telegram_hooks(self):
		self.assertEqual(self.handlers[0], "huf.ai.gateway_adapters.telegram_pipeline_hooks")
		self.assertEqual(self.handlers[-1], "huf.ai.gateway_adapters.telegram_business_agent_hooks")
		# 'unsupported' chain order depends on this: groups (outermost) -> stream -> guest -> inline
		order = [
			self.handlers.index(f"huf.ai.gateway_adapters.telegram_{m}_hooks")
			for m in ("inline", "guest", "stream", "groups")
		]
		self.assertEqual(order, sorted(order))

	def test_message_chain_order_owner_then_admin_then_loop_guard_then_ingest(self):
		from huf.ai.gateway_adapters import telegram_business_agent as ba

		calls: list[str] = []
		with (
			mock.patch.object(ba, "handle_owner_message", side_effect=lambda *a, **k: calls.append("owner")),
			mock.patch.object(
				telegram_admin, "handle_message", side_effect=lambda *a, **k: calls.append("admin")
			),
			mock.patch.object(mh, "prefilter", side_effect=lambda *a, **k: calls.append("loopguard")),
		):
			result = self.send(msg(4600, text="plain question"))
		self.assertEqual(calls, ["owner", "admin", "loopguard"])
		self.assertTrue(result["success"])
		self.ingest.assert_called_once()

	def test_admin_command_short_circuits_before_loop_guard_and_ingest(self):
		from huf.ai.gateway_adapters import telegram_business_agent as ba

		calls: list[str] = []
		with (
			mock.patch.object(ba, "handle_owner_message", side_effect=lambda *a, **k: calls.append("owner")),
			mock.patch.object(
				telegram_admin,
				"handle_message",
				side_effect=lambda *a, **k: (calls.append("admin"), {"success": True, "handled": "admin"})[1],
			),
			mock.patch.object(mh, "prefilter", side_effect=lambda *a, **k: calls.append("loopguard")),
		):
			result = self.send(msg(4601, text="/status"))
		self.assertEqual(calls, ["owner", "admin"])
		self.assertEqual(result["handled"], "admin")
		self.ingest.assert_not_called()

	def test_owner_edit_short_circuits_admin_and_ingest(self):
		from huf.ai.gateway_adapters import telegram_business_agent as ba

		calls: list[str] = []
		with (
			mock.patch.object(
				ba,
				"handle_owner_message",
				side_effect=lambda *a, **k: (calls.append("owner"), {"success": True, "result": "approved"})[
					1
				],
			),
			mock.patch.object(
				telegram_admin, "handle_message", side_effect=lambda *a, **k: calls.append("admin")
			),
		):
			self.send(msg(4602, text="replacement text"))
		self.assertEqual(calls, ["owner"])
		self.ingest.assert_not_called()

	def test_callback_chain_admin_then_business_then_buttons(self):
		payload = {
			"update_id": 4700,
			"callback_query": {
				"id": "cb1",
				"from": {"id": 42, "is_bot": False, "first_name": "Ann"},
				"message": {
					"message_id": 5,
					"chat": {"id": 42, "type": "private"},
					"date": 1760000000,
					"text": "x",
				},
				"chat_instance": "1",
				"data": "plain-data",
			},
		}
		calls: list[str] = []
		with (
			mock.patch.object(
				telegram_admin,
				"handle_callback",
				side_effect=lambda *a, **k: (calls.append("admin"), None)[1],
			),
			mock.patch(
				"huf.ai.gateway_adapters.telegram_buttons.handle_callback",
				side_effect=lambda *a, **k: (calls.append("buttons"), {"action": "ignore", "reason": "spy"})[
					1
				],
			),
		):
			result = self.send(payload)
		self.assertEqual(calls, ["admin", "buttons"])
		self.assertEqual(result["ignored"], "callback_query")
		self.ingest.assert_not_called()

	def test_admin_callback_short_circuits_buttons(self):
		payload = {
			"update_id": 4701,
			"callback_query": {
				"id": "cb2",
				"from": {"id": 42, "is_bot": False, "first_name": "Ann"},
				"message": {
					"message_id": 5,
					"chat": {"id": 42, "type": "private"},
					"date": 1760000000,
					"text": "x",
				},
				"chat_instance": "1",
				"data": "adm:whatever",
			},
		}
		with (
			mock.patch.object(
				telegram_admin, "handle_callback", return_value={"success": True, "handled": "adm"}
			),
			mock.patch("huf.ai.gateway_adapters.telegram_buttons.handle_callback") as buttons,
		):
			result = self.send(payload)
		self.assertEqual(result["handled"], "adm")
		buttons.assert_not_called()

	def test_each_unsupported_kind_reaches_exactly_its_handler(self):
		self.patch("huf.ai.gateway_service._has_access_entry", return_value=True)
		self.patch("huf.ai.gateway_service._sender_negative_state", return_value=None)
		self.patch("frappe.set_user")
		self.patch(
			"huf.ai.telegram_guard._load_gateway",
			return_value=SimpleNamespace(
				name="gw1", provider=PROVIDER, telegram_join_policy="Decline", room_policy="Open"
			),
		)
		self.patch("huf.ai.telegram_guard._client_for", return_value=self.adapter.client)
		self.gw.direct_policy = "Open"
		cases = [
			("inline_query", inline_update(9500), "answerInlineQuery", False),
			(
				"chosen_inline_result",
				{"update_id": 9501, "chosen_inline_result": {"result_id": "r", "from": {"id": 42}}},
				None,
				False,
			),
			("guest_message", guest_update(9502), None, True),
			("chat_join_request", join_update(9503, query_id="q-9503"), "answerChatJoinRequestQuery", False),
			("stopped", {"update_id": 9504, "stopped_message_generation": {"chat": {"id": 5}}}, None, False),
			("unknown", {"update_id": 9505, "poll_answer": {"poll_id": "p"}}, None, False),
		]
		for name, payload, method, ingested in cases:
			with self.subTest(name=name):
				self.api.calls.clear()
				self.ingest.reset_mock()
				result = self.send(payload)
				self.assertIsNotNone(result)
				if method:
					self.assertEqual(len(self.api.of(method)), 1)
				else:
					self.assertEqual(self.api.calls, [])
				if ingested:
					self.ingest.assert_called_once()
				else:
					self.ingest.assert_not_called()

	def test_join_request_reaches_groups_handler_once_through_unsupported_chain(self):
		self.patch(
			"huf.ai.telegram_guard._load_gateway",
			return_value=SimpleNamespace(
				name="gw1", provider=PROVIDER, telegram_join_policy="Decline", room_policy="Open"
			),
		)
		self.patch("huf.ai.telegram_guard._client_for", return_value=self.adapter.client)
		result = self.send(join_update(9600, query_id="q-chain"))
		self.assertEqual(result["decision"], "decline")
		self.assertEqual(len(self.api.of("answerChatJoinRequestQuery")), 1)
		self.ingest.assert_not_called()


if __name__ == "__main__":
	unittest.main()
