# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp reply pipeline (T6): format + split, typing/read, preview_url, error classification and
send-only retries, status ordering, ``last_event_at``, ``<NO_REPLY>`` and reaction skipping.

The end-to-end cases reuse the T9b harness (real webhook -> ingest -> ``process_gateway_event`` ->
adapter, with only the LLM and the Meta HTTP boundary faked) in both direct and bridge mode.
"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai import gateway_service, gateway_webhook
from huf.ai.gateway_adapters import whatsapp as wa
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_errors as we
from huf.ai.tests.test_whatsapp_e2e_agent import (
	PHONE_ID,
	SENDER,
	FakeMeta,
	_E2EMixin,
	_Resp,
	_text_msg,
)

RETRY_METHOD = "huf.ai.gateway_service.retry_gateway_reply"


def graph_error(code: int, status: int = 400, message: str = "boom") -> _Resp:
	return _Resp({"error": {"code": code, "message": message}}, status)


class ScriptedMeta(FakeMeta):
	"""FakeMeta whose next outbound message answers come from ``script`` (response or exception)."""

	script: list
	read_status: int

	def _record(self, method, url, body):
		if isinstance(body, (str, bytes)):
			try:
				body = json.loads(body)
			except ValueError:
				pass
		self.calls.append({"method": method, "url": url, "body": body})
		if self._is_read(self.calls[-1]):
			return _Resp({"success": True}, self.read_status)
		if self.script:
			item = self.script.pop(0)
			if isinstance(item, BaseException):
				raise item
			if item is not None:
				return item
		return _Resp({"messages": [{"id": f"wamid.OUT{len(self.sends())}"}]})


# --------------------------------------------------------------------------- pure adapter tests


class FakeHttp:
	def __init__(self, script=None):
		self.calls = []
		self.script = list(script or [])

	def __call__(self, url, *, json, headers, timeout):
		self.calls.append({"url": url, "json": json, "timeout": timeout})
		if self.script:
			item = self.script.pop(0)
			if isinstance(item, BaseException):
				raise item
			if item is not None:
				return item
		return _Resp({"messages": [{"id": f"wamid.P{len(self.calls)}"}]})


def make_adapter(http, **context):
	return wa.WhatsAppGatewayAdapter(
		{"phone_number_id": PHONE_ID, "access_token": "tok", "webhook_verify_token": "v", "app_secret": "s"},
		http_post=http,
		gateway_context=context or None,
	)


class TestAdapterReplyFormatting(unittest.TestCase):
	def reply(self, text, **kw):
		from huf.ai.gateway_adapters.types import GatewayReply

		return GatewayReply(conversation_id="15559876543", text=text, reply_to_provider_message_id="wamid.in", **kw)

	def test_long_reply_is_split_in_order_fence_safe_and_quoted_once(self):
		code = "```python\n" + "\n".join(f"value_{i} = {i}" for i in range(450)) + "\n```"
		text = "a" * 3000 + "\n\n" + code + "\n\n" + "c" * 3000
		http = FakeHttp()
		delivery = make_adapter(http).send_reply(self.reply(text))
		bodies = [c["json"]["text"]["body"] for c in http.calls]
		self.assertGreaterEqual(len(bodies), 3)
		self.assertTrue(all(len(b) <= 4096 for b in bodies))
		self.assertTrue(bodies[0].startswith("a"))
		self.assertTrue(bodies[-1].endswith("c"))
		for body in bodies:
			self.assertEqual(body.count("```") % 2, 0, "a code fence was cut across parts")
		self.assertIn("context", http.calls[0]["json"])
		self.assertTrue(all("context" not in c["json"] for c in http.calls[1:]))
		self.assertEqual(delivery.provider_message_id, "wamid.P1")
		self.assertEqual(delivery.provider_response["message_ids"], [f"wamid.P{i}" for i in range(1, len(bodies) + 1)])

	def test_markdown_is_converted(self):
		http = FakeHttp()
		make_adapter(http).send_reply(self.reply("# Title\n**bold** and [site](https://example.com)"))
		body = http.calls[0]["json"]["text"]["body"]
		self.assertNotIn("**", body)
		self.assertNotIn("](", body)
		self.assertIn("*bold*", body)

	def test_part_two_is_not_sent_when_part_one_failed(self):
		http = FakeHttp([graph_error(130429, 429)])
		adapter = make_adapter(http)
		with self.assertRaises(ValueError):
			adapter.send_reply(self.reply("a" * 3000 + "\n\n" + "b" * 3000))
		self.assertEqual(len(http.calls), 1)

	def test_parts_error_reports_sent_and_remaining(self):
		http = FakeHttp([None, graph_error(500, 500)])
		with self.assertRaises(wa.WhatsAppPartsError) as ctx:
			make_adapter(http).send_text_parts("15559876543", ["one", "two", "three"], "wamid.in")
		err = ctx.exception
		self.assertEqual(err.sent_ids, ["wamid.P1"])
		self.assertEqual(err.remaining, ["two", "three"])
		self.assertTrue(wa.classify_send_exception(err)["retryable"])

	def test_preview_url_option_direct(self):
		for option, expected in (("On", True), ("Off", False), ("Default (off)", False), ("", False)):
			http = FakeHttp()
			make_adapter(http, preview_url=option).send_reply(self.reply("hello"))
			self.assertIs(http.calls[0]["json"]["text"]["preview_url"], expected, option)

	def test_preview_url_option_bridge_mode_passes_flag_to_direct_graph_post(self):
		adapter = make_adapter(FakeHttp(), whatsapp_account="acct", preview_url="On")
		with patch.object(wa, "bridge") as b:
			b.is_available.return_value = True
			b.send_text.return_value = {"success": True, "message_id": "wamid.b"}
			adapter._send_text_part("1555", "hi", None)
		self.assertIs(b.send_text.call_args.kwargs["preview_url"], True)
		self.assertTrue(b.send_text.call_args.kwargs["trusted"])

	def test_bridge_and_direct_send_identical_text_json(self):
		http = FakeHttp()
		make_adapter(http, preview_url="On").send_reply(self.reply("hello"))
		direct = http.calls[0]["json"]
		self.assertEqual(direct, bridge._text_payload("15559876543", "hello", "wamid.in", True))


class TestTypingIndicator(unittest.TestCase):
	def test_call_shape_and_timeout(self):
		http = FakeHttp()
		self.assertTrue(make_adapter(http).mark_read_typing("wamid.in"))
		call = http.calls[0]
		self.assertTrue(call["url"].endswith(f"/{PHONE_ID}/messages"))
		self.assertEqual(
			call["json"],
			{
				"messaging_product": "whatsapp",
				"status": "read",
				"message_id": "wamid.in",
				"typing_indicator": {"type": "text"},
			},
		)
		self.assertEqual(call["timeout"], 5)

	def test_failures_are_swallowed_and_not_retried(self):
		for item in (RuntimeError("down"), graph_error(500, 500), graph_error(190, 401)):
			http = FakeHttp([item])
			self.assertFalse(make_adapter(http).mark_read_typing("wamid.in"))
			self.assertEqual(len(http.calls), 1)

	def test_no_message_id_makes_no_call(self):
		http = FakeHttp()
		self.assertFalse(make_adapter(http).mark_read_typing(""))
		self.assertEqual(http.calls, [])


class TestSendErrorClassification(unittest.TestCase):
	def classify(self, item):
		http = FakeHttp([item])
		with self.assertRaises(Exception) as ctx:
			make_adapter(http)._graph_send({"to": "1"})
		return wa.classify_send_exception(ctx.exception)

	def test_rate_limit_is_retryable(self):
		cls = self.classify(graph_error(130429, 429))
		self.assertEqual((cls["code"], cls["retryable"]), (130429, True))

	def test_pair_rate_limit_waits_six_seconds(self):
		cls = self.classify(graph_error(131056))
		self.assertEqual(we.backoff_seconds(cls, 1), 6.0)

	def test_server_error_and_timeout_are_retryable(self):
		self.assertTrue(self.classify(graph_error(0, 503))["retryable"])
		import requests

		cls = self.classify(requests.exceptions.Timeout("timed out"))
		self.assertEqual((cls["kind"], cls["retryable"]), ("timeout", True))

	def test_permanent_codes(self):
		for code in (131047, 131026, 131048, 131049, 132001, 368, 190):
			self.assertFalse(self.classify(graph_error(code))["retryable"], code)


class TestReplyStatusOrdering(unittest.TestCase):
	def test_ordering_table(self):
		wins = gateway_webhook._reply_status_wins
		self.assertTrue(wins("sent", "delivered"))
		self.assertTrue(wins("delivered", "read"))
		self.assertTrue(wins("read", "played"))
		self.assertFalse(wins("read", "delivered"))
		self.assertFalse(wins("delivered", "sent"))
		self.assertFalse(wins("delivered", "failed"))
		self.assertFalse(wins("read", "failed"))
		self.assertTrue(wins("sent", "failed"))
		self.assertTrue(wins("", "failed"))
		self.assertFalse(wins("failed", "sent"))  # the late-sent-after-failed regression
		self.assertTrue(wins("failed", "delivered"))
		self.assertTrue(wins("retrying", "sent"))


class TestWindowIgnoresReactions(unittest.TestCase):
	def test_reaction_never_opens_the_window(self):
		now = now_datetime()
		rows = [
			{
				"received_at": now - timedelta(minutes=1),
				"verified_sender": 1,
				"sender_id": SENDER,
				"raw_payload": {"kind": "reaction", "message": {"type": "reaction", "timestamp": "1"}},
			}
		]
		with patch.object(bridge.frappe, "get_all", return_value=rows):
			self.assertFalse(bridge.window_state("G", SENDER, now)["open"])

	def test_real_message_still_opens_it(self):
		now = now_datetime()
		rows = [
			{
				"received_at": now - timedelta(minutes=1),
				"verified_sender": 1,
				"sender_id": SENDER,
				"raw_payload": {"message": {"type": "text"}},
			}
		]
		with patch.object(bridge.frappe, "get_all", return_value=rows):
			self.assertTrue(bridge.window_state("G", SENDER, now)["open"])


# --------------------------------------------------------------------------- end to end


class _PipelineMixin(_E2EMixin):
	def _begin(self):
		self._start()
		self.meta.__class__ = ScriptedMeta
		self.meta.script = []
		self.meta.read_status = 200
		sleep = patch.object(gateway_service, "_sleep", lambda s: None)
		sleep.start()
		self.addCleanup(sleep.stop)
		epoch = patch.object(gateway_service, "_epoch", lambda: 1000.0)
		epoch.start()
		self.addCleanup(epoch.stop)

	# helpers
	def _reply_with(self, text):
		self.run_mock.side_effect = lambda **kw: {"response": text, "agent_run_id": "fake-run-x"}

	def _inbound(self, wamid):
		self.assertTrue(self._post(_text_msg(wamid))["success"])
		return self._event_name(wamid)

	def _retries(self):
		calls = [c for c in frappe.enqueue.call_args_list if c.args and c.args[0] == RETRY_METHOD]
		frappe.enqueue.reset_mock()
		return [c.kwargs for c in calls]

	def _run_retry(self, kwargs, due=True):
		kw = {k: v for k, v in kwargs.items() if k not in ("queue", "timeout", "enqueue_after_commit")}
		if due:
			kw["not_before"] = None
		try:
			return gateway_service.retry_gateway_reply(**kw)
		finally:
			frappe.set_user("Administrator")

	def _drain_retries(self):
		results = []
		while True:
			pending = self._retries()
			if not pending:
				return results
			for kw in pending:
				results.append(self._run_retry(kw))

	def _set_gateway(self, **values):
		frappe.db.set_value("Gateway", self.gateway.name, values)

	# ---- formatting + split
	def test_long_reply_is_three_ordered_parts_quote_on_first_only(self):
		self._reply_with("a" * 3000 + "\n\n" + "b" * 3000 + "\n\n" + "c" * 3000)
		name = self._inbound("wamid.L1")
		self._process(name)
		event = self._event(name)
		self.assertEqual(event.status, "Succeeded", event.error_message)
		sends = self.meta.sends()
		self.assertEqual(len(sends), 3, self.meta.calls)
		bodies = [s["body"]["text"]["body"] for s in sends]
		self.assertEqual([b[0] for b in bodies], ["a", "b", "c"])
		self.assertEqual(sends[0]["body"]["context"]["message_id"], "wamid.L1")
		self.assertTrue(all("context" not in s["body"] for s in sends[1:]))
		self.assertEqual(event.reply_message_id, "wamid.OUT1")
		self.assertEqual(event.reply_status, "sent")
		self.assertEqual(self.run_mock.call_count, 1)

	def test_markdown_is_converted_before_sending(self):
		self._reply_with("**Hello** there")
		name = self._inbound("wamid.M1")
		self._process(name)
		self.assertEqual(self.meta.sends()[0]["body"]["text"]["body"], "*Hello* there")

	# ---- typing
	def test_typing_call_precedes_the_run_and_the_reply(self):
		name = self._inbound("wamid.T1")
		self._process(name)
		reads = self.meta.reads()
		self.assertEqual(len(reads), 1)
		self.assertEqual(
			reads[0]["body"],
			{
				"messaging_product": "whatsapp",
				"status": "read",
				"message_id": "wamid.T1",
				"typing_indicator": {"type": "text"},
			},
		)
		self.assertEqual(self.meta.calls[0], reads[0])
		self.assertEqual(self._event(name).status, "Succeeded")

	def test_typing_can_be_disabled_per_gateway(self):
		self._set_gateway(typing_indicator=0)
		name = self._inbound("wamid.T2")
		self._process(name)
		self.assertEqual(self.meta.reads(), [])
		self.assertEqual(len(self.meta.sends()), 1)

	def test_typing_failure_does_not_block_the_reply(self):
		self.meta.read_status = 500
		name = self._inbound("wamid.T3")
		self._process(name)
		self.assertEqual(self._event(name).status, "Succeeded")
		self.assertEqual(len(self.meta.sends()), 1)

	# ---- preview_url
	def test_preview_url_default_and_on(self):
		name = self._inbound("wamid.PV1")
		self._process(name)
		self.assertIs(self.meta.sends()[0]["body"]["text"]["preview_url"], False)
		self._set_gateway(preview_url="On")
		name = self._inbound("wamid.PV2")
		self._process(name)
		self.assertIs(self.meta.sends()[1]["body"]["text"]["preview_url"], True)

	# ---- retry matrix
	def test_rate_limit_retries_up_to_four_attempts_then_fails_without_rerunning_the_agent(self):
		self.meta.script = [graph_error(130429, 429) for _ in range(4)]
		name = self._inbound("wamid.R1")
		out = self._process(name)
		self.assertEqual(out["status"], "Running")
		self.assertEqual(self._event(name).reply_status, "retrying")
		retries = self._retries()
		self.assertEqual(len(retries), 1)
		self.assertEqual(retries[0]["attempt"], 2)
		delay = retries[0]["not_before"] - 1000.0
		self.assertTrue(1.6 <= delay <= 2.4, delay)
		self._run_retry(retries[0])
		retries = self._retries()
		self.assertEqual(retries[0]["attempt"], 3)
		self._run_retry(retries[0])
		retries = self._retries()
		self.assertEqual(retries[0]["attempt"], 4)
		self._run_retry(retries[0])
		self.assertEqual(self._retries(), [])
		event = self._event(name)
		self.assertEqual(event.status, "Failed")
		self.assertTrue(event.delivery_error.startswith("gave up after 4 attempts:"), event.delivery_error)
		self.assertEqual(len(self.meta.sends()), 4)
		self.assertEqual(self.run_mock.call_count, 1)  # the paid-for run is never repeated

	def test_retry_max_attempts_setting_is_honoured(self):
		self._set_gateway(retry_max_attempts=2)
		self.meta.script = [graph_error(130429, 429) for _ in range(5)]
		name = self._inbound("wamid.R2")
		self._process(name)
		self._drain_retries()
		self.assertEqual(self._event(name).status, "Failed")
		self.assertEqual(len(self.meta.sends()), 2)
		self.assertIn("gave up after 2 attempts", self._event(name).delivery_error)

	def test_pair_rate_limit_waits_six_seconds(self):
		self.meta.script = [graph_error(131056)]
		name = self._inbound("wamid.R3")
		self._process(name)
		retries = self._retries()
		self.assertEqual(retries[0]["not_before"], 1006.0)

	def test_server_error_then_success_delivers_once(self):
		self.meta.script = [graph_error(0, 503)]
		name = self._inbound("wamid.R4")
		self._process(name)
		self._drain_retries()
		event = self._event(name)
		self.assertEqual(event.status, "Succeeded", event.error_message)
		self.assertEqual(event.reply_status, "sent")
		self.assertTrue(event.reply_message_id)
		self.assertEqual(len(self.meta.sends()), 2)  # one rejected + one accepted
		self.assertEqual(self.run_mock.call_count, 1)

	def test_timeout_is_retried(self):
		import requests

		self.meta.script = [requests.exceptions.Timeout("timed out")]
		name = self._inbound("wamid.R5")
		out = self._process(name)
		self.assertEqual(out["reply_status"], "retrying")
		self._drain_retries()
		self.assertEqual(self._event(name).status, "Succeeded")

	def test_permanent_error_fails_immediately_without_retry(self):
		self.meta.script = [graph_error(131026)]
		name = self._inbound("wamid.R6")
		out = self._process(name)
		self.assertEqual(out["status"], "Failed")
		self.assertEqual(self._retries(), [])
		event = self._event(name)
		self.assertEqual(event.status, "Failed")
		self.assertEqual(event.reply_status, "failed")
		self.assertIn("undeliverable", event.delivery_error)
		self.assertEqual(self.run_mock.call_count, 1)

	def test_double_delivery_of_the_retry_job_sends_once(self):
		self.meta.script = [graph_error(0, 503)]
		name = self._inbound("wamid.R7")
		self._process(name)
		kw = self._retries()[0]
		first = self._run_retry(kw)
		second = self._run_retry(kw)
		self.assertEqual(first["status"], "Succeeded")
		self.assertTrue(second.get("skipped"))
		self.assertEqual(len(self.meta.sends()), 2)

	def test_retry_job_claim_blocks_a_concurrent_duplicate(self):
		self.meta.script = [graph_error(0, 503)]
		name = self._inbound("wamid.R8")
		self._process(name)
		kw = self._retries()[0]
		frappe.cache().set(f"huf_gw_reply_retry:{name}", 1, ex=60)  # one in-flight retry per event, whatever the attempt
		self.addCleanup(frappe.cache().delete_value, f"huf_gw_reply_retry:{name}")
		self.assertTrue(self._run_retry(kw).get("skipped"))
		self.assertEqual(len(self.meta.sends()), 1)

	def test_retry_not_yet_due_hops_back_onto_the_queue(self):
		self.meta.script = [graph_error(0, 503)]
		name = self._inbound("wamid.R9")
		self._process(name)
		kw = self._retries()[0]
		out = self._run_retry(kw, due=False)
		self.assertTrue(out.get("deferred"))
		self.assertEqual(len(self.meta.sends()), 1)
		self.assertEqual(len(self._retries()), 1)

	def test_failure_in_part_two_resumes_with_the_remaining_part_only(self):
		self._reply_with("a" * 3000 + "\n\n" + "b" * 3000)
		self.meta.script = [None, graph_error(0, 500)]
		name = self._inbound("wamid.R10")
		self._process(name)
		kw = self._retries()[0]
		self.assertEqual(len(kw["parts_remaining"]), 1)
		self.assertTrue(kw["parts_remaining"][0].startswith("b"))
		self._run_retry(kw)
		sends = self.meta.sends()
		self.assertEqual(len(sends), 3)  # part 1, part 2 (rejected), part 2 again
		self.assertTrue(sends[2]["body"]["text"]["body"].startswith("b"))
		self.assertNotIn("context", sends[2]["body"])
		event = self._event(name)
		self.assertEqual(event.status, "Succeeded")
		self.assertEqual(event.reply_message_id, "wamid.OUT1")
		self.assertEqual(event.reply_status, "sent")

	# ---- window closed (race) handling
	def test_graph_131047_without_fallback_template_fails_without_retry(self):
		self.meta.script = [graph_error(131047, 400, "Re-engagement message")]
		name = self._inbound("wamid.W1")
		out = self._process(name)
		self.assertEqual(out["status"], "Failed")
		self.assertEqual(self._retries(), [])
		self.assertEqual(len(self.meta.sends()), 1)
		self.assertIn("24 hours", self._event(name).delivery_error)

	# ---- failed run
	def test_error_reply_text_takes_precedence_and_is_sent_once_per_event(self):
		self._set_fallback_text("credential apology")
		self._set_gateway(error_reply_text="Sorry, try again later.")
		self._fail_run(error="x", error_kind="rate_limited")
		first, second = self._inbound("wamid.F1"), self._inbound("wamid.F2")
		for name in (first, second):  # the once-only claim is per event, so a re-run must not resend
			key = f"huf_gw_fallback_reply:{name}:error"
			frappe.cache().delete_value(key)
			self.addCleanup(frappe.cache().delete_value, key)
		out1 = self._process(first)
		out2 = self._process(second)
		self.assertTrue(out1["fallback_sent"])
		self.assertTrue(out2["fallback_sent"])
		self.assertFalse(gateway_service._send_fallback_once(self._event(first), self.gateway))
		sends = self.meta.sends()
		self.assertEqual(len(sends), 2)
		self.assertEqual({s["body"]["text"]["body"] for s in sends}, {"Sorry, try again later."})

	def test_failed_run_sends_only_the_default_apology_once(self):
		self._fail_run(error="x", error_kind="rate_limited")
		name = self._inbound("wamid.F3")
		key = f"huf_gw_fallback_reply:{name}:error"
		frappe.cache().delete_value(key)
		self.addCleanup(frappe.cache().delete_value, key)
		out = self._process(name)
		self.assertEqual(out["status"], "Failed")
		sends = self.meta.sends()
		self.assertEqual(len(sends), 1)
		self.assertIn("something went wrong", sends[0]["body"]["text"]["body"])

	# ---- NO_REPLY / opt-out / reactions
	def test_no_reply_sentinel_sends_nothing_and_succeeds(self):
		for i, text in enumerate(("<NO_REPLY>", "  <no_reply>\n")):
			self._reply_with(text)
			name = self._inbound(f"wamid.N{i}")
			self._process(name)
			event = self._event(name)
			self.assertEqual(event.status, "Succeeded")
			self.assertEqual(event.reply_status, "suppressed")
		self.assertEqual(self.meta.sends(), [])

	def test_sentinel_inside_text_is_an_ordinary_reply(self):
		self._reply_with("I will say <NO_REPLY> later")
		name = self._inbound("wamid.N9")
		self._process(name)
		self.assertEqual(len(self.meta.sends()), 1)

	def test_sender_who_opts_out_during_the_run_gets_no_reply(self):
		name = self._inbound("wamid.O1")
		entry = frappe.get_all(
			"Gateway Access Entry",
			filters={"gateway": self.gateway.name, "external_id": SENDER},
			pluck="name",
		)[0]

		def opt_out_mid_run(**kwargs):
			frappe.db.set_value("Gateway Access Entry", entry, "state", gateway_service.ENTRY_STATE_OPTED_OUT)
			return {"response": "late answer", "agent_run_id": "fake-run-x"}

		self.run_mock.side_effect = opt_out_mid_run
		self._process(name)
		event = self._event(name)
		self.assertEqual((event.status, event.reply_status), ("Succeeded", "suppressed"))
		self.assertEqual(self.meta.sends(), [])

	def test_reaction_records_without_a_run(self):
		reaction = {
			"from": "+1 555 987 6543",
			"id": "wamid.X1",
			"type": "reaction",
			"reaction": {"message_id": "wamid.prev", "emoji": "\U0001F44D"},
		}
		self.assertTrue(self._post(reaction)["success"])
		name = self._event_name("wamid.X1")
		out = self._process(name)
		event = self._event(name)
		self.assertEqual(event.status, "Recorded")  # ingest records a reaction; processing leaves it alone
		self.assertEqual(event.error_message, "reaction_recorded: no run")
		self.assertEqual(out["status"], "Recorded")
		self.assertEqual(self.run_mock.call_count, 0)
		self.assertEqual(self.meta.calls, [])

	# ---- status webhooks / last_event_at
	def test_status_webhooks_never_downgrade_and_store_played(self):
		name = self._inbound("wamid.S1")
		self._process(name)
		wamid = self._event(name).reply_message_id
		update = gateway_webhook._update_reply_status
		for state, expected in (
			("delivered", "delivered"),
			("sent", "delivered"),
			("read", "read"),
			("delivered", "read"),
			("failed", "read"),
			("played", "played"),
		):
			update(self.gateway.name, {"id": wamid, "status": state})
			self.assertEqual(self._event(name).reply_status, expected, state)

	def test_late_sent_does_not_resurrect_a_failed_status(self):
		name = self._inbound("wamid.S2")
		self._process(name)
		wamid = self._event(name).reply_message_id
		update = gateway_webhook._update_reply_status
		update(self.gateway.name, {"id": wamid, "status": "failed", "errors": [{"code": 131026, "title": "undeliverable"}]})
		self.assertEqual(self._event(name).reply_status, "failed")
		update(self.gateway.name, {"id": wamid, "status": "sent"})
		self.assertEqual(self._event(name).reply_status, "failed")

	def test_last_event_at_written_on_ingest_and_throttled(self):
		self.assertFalse(frappe.db.get_value("Gateway", self.gateway.name, "last_event_at"))
		self._inbound("wamid.E1")
		first = frappe.db.get_value("Gateway", self.gateway.name, "last_event_at")
		self.assertTrue(first)
		recent = now_datetime() - timedelta(seconds=30)
		self._set_gateway(last_event_at=recent)
		self._inbound("wamid.E2")
		self.assertEqual(frappe.db.get_value("Gateway", self.gateway.name, "last_event_at"), recent)
		old = now_datetime() - timedelta(seconds=120)
		self._set_gateway(last_event_at=old)
		self._inbound("wamid.E3")
		self.assertGreater(frappe.db.get_value("Gateway", self.gateway.name, "last_event_at"), old)


class TestWhatsAppReplyPipelineDirect(_PipelineMixin, IntegrationTestCase):
	USE_BRIDGE = False

	def setUp(self):
		self._begin()

	def test_graph_131047_uses_the_fallback_template(self):
		self._set_gateway(fallback_template="e2e_fallback")
		self.meta.script = [graph_error(131047, 400, "Re-engagement message")]
		name = self._inbound("wamid.W2")
		self._process(name)
		sends = self.meta.sends()
		self.assertEqual([s["body"]["type"] for s in sends], ["text", "template"])
		self.assertEqual(sends[1]["body"]["template"]["name"], "e2e_fallback")
		event = self._event(name)
		self.assertEqual(event.status, "Succeeded", event.error_message)
		self.assertEqual(event.error_message, gateway_service.WHATSAPP_FALLBACK_NOTE)
		self.assertEqual(self._retries(), [])


class TestWhatsAppReplyPipelineBridge(_PipelineMixin, IntegrationTestCase):
	USE_BRIDGE = True

	def setUp(self):
		if not bridge.is_available():
			self.skipTest("frappe_whatsapp is not installed on this site")
		self._begin()

	def test_agent_reply_is_posted_once_and_mirrored_with_the_wamid(self):
		self._reply_with("a" * 3000 + "\n\n" + "b" * 3000)
		name = self._inbound("wamid.B1")
		self._process(name)
		self.assertEqual(len(self.meta.sends()), 2)
		rows = frappe.get_all(
			"WhatsApp Message",
			filters={"type": "Outgoing", "whatsapp_account": self.account.name},
			fields=["message_id", "status"],
			order_by="creation asc",
		)
		self.assertEqual([r.message_id for r in rows], ["wamid.OUT1", "wamid.OUT2"])
		self.assertTrue(all(r.status == "Success" for r in rows))

	def test_bridge_graph_failure_is_classified_and_retried(self):
		self.meta.script = [graph_error(130429, 429)]
		name = self._inbound("wamid.B2")
		out = self._process(name)
		self.assertEqual(out["reply_status"], "retrying")
		self._drain_retries()
		self.assertEqual(self._event(name).status, "Succeeded")
		self.assertEqual(
			frappe.db.count("WhatsApp Message", {"type": "Outgoing", "whatsapp_account": self.account.name}), 1
		)
