# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Channel outbox (H-W2-15): retry classes, backoff, blocked never retried (G2), names only (G4), one effect (G5)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

from huf.ai.channels import guard, outbox, token_binder
from huf.ai.flow.testrun import gate
from huf.ai.gateway_adapters import whatsapp_bridge as bridge

SENTINEL = "zz-outbox-value-sentinel-91c2"
PHONE = "+15550001111"


def request(**over):
	base = {
		"step_key": "sk-" + frappe.generate_hash(length=10),
		"run_id": "run-x",
		"node_id": "send1",
		"member_key": "m-1",
		"channel": "whatsapp",
		"category": "service",
		"template": "hello_tpl",
		"recipient_ref": "{{trigger.phone}}",
		"token_names": ["1"],
	}
	return {**base, **over}


class FakeTransport:
	"""Records one effect per step key, like a provider honouring the idempotency token."""

	def __init__(self, errors=()):
		self.errors = list(errors)
		self.effects: dict[str, int] = {}

	def __call__(self, row, recipient, text, values):
		if self.errors:
			raise self.errors.pop(0)
		self.effects[row.step_key] = self.effects.get(row.step_key, 0) + 1
		return {"message_id": "wamid." + row.step_key}


def resolver(row):
	return PHONE, None


def connect_error():
	"""The connection was never opened, so nothing reached Meta."""
	reason = NewConnectionError(None, "Failed to establish a new connection")
	return requests.ConnectionError(MaxRetryError(None, "/messages", reason))


def bridge_error(cause=None, **payload):
	error = bridge.BridgeError({"success": False, "error": "send_failed", **payload})
	error.__cause__ = cause
	return error


class TestOutbox(IntegrationTestCase):
	def setUp(self):
		self.bind = patch.object(token_binder, "bind", return_value={"1": SENTINEL}).start()
		patch.object(frappe.db, "commit").start()
		self.recheck = patch.object(outbox, "_blocked_now", return_value=None, create=True).start()
		self.addCleanup(patch.stopall)

	def deliver(self, name, transport):
		return outbox.deliver(name, transport=transport, resolver=resolver)

	def row(self, name):
		return frappe.get_doc(outbox.DOCTYPE, name)

	def due(self, name):
		frappe.db.set_value(outbox.DOCTYPE, name, "next_attempt_at", add_to_date(now_datetime(), seconds=-1))

	def test_classes(self):
		self.assertEqual(outbox.classify({"retryable": True}), outbox.TRANSIENT)
		self.assertEqual(outbox.classify({"retryable": False}), outbox.PERMANENT)
		self.assertEqual(outbox.classify("frequency_capped"), outbox.BLOCKED)
		self.assertEqual(outbox.classify(token_binder.TokenUnbound(["1"])), outbox.BLOCKED)
		err = outbox.delivery_error(ValueError(f"boom {PHONE} {SENTINEL}"))
		self.assertEqual(set(err), {"class", "code", "kind"})
		self.assertNotIn(PHONE, str(err))
		self.assertNotIn(SENTINEL, str(err))

	def test_transient_retried_with_backoff_then_succeeds(self):
		name = outbox.enqueue(request(), deliver_now=False)
		transport = FakeTransport([connect_error()])
		self.assertEqual(self.deliver(name, transport), "Retrying")
		row = self.row(name)
		self.assertEqual(row.error_class, outbox.TRANSIENT)
		self.assertGreater(row.next_attempt_at, now_datetime())
		self.assertIsNone(self.deliver(name, transport), "not due yet: no attempt")
		self.due(name)
		self.assertEqual(self.deliver(name, transport), "Sent")
		self.assertEqual(transport.effects, {row.step_key: 1})
		self.assertEqual(self.row(name).attempts, 2)

	def test_transient_exhausted_is_final(self):
		name = outbox.enqueue(request(), deliver_now=False)
		transport = FakeTransport([connect_error() for _ in range(outbox.MAX_ATTEMPTS)])
		for _ in range(outbox.MAX_ATTEMPTS - 1):
			self.assertEqual(self.deliver(name, transport), "Retrying")
			self.due(name)
		self.assertEqual(self.deliver(name, transport), "Failed")
		self.assertEqual(self.row(name).error_code, outbox.RETRY_EXHAUSTED)

	def test_permanent_not_retried(self):
		name = outbox.enqueue(request(), deliver_now=False)
		transport = FakeTransport([PermissionError("no")])
		self.assertEqual(self.deliver(name, transport), "Failed")
		self.assertEqual(self.row(name).error_class, outbox.PERMANENT)
		self.assertIsNone(self.deliver(name, transport))
		self.assertEqual(transport.effects, {})

	def test_blocked_at_delivery_is_final(self):
		name = outbox.enqueue(request(), deliver_now=False)
		self.bind.side_effect = token_binder.TokenUnbound(["1"])
		transport = FakeTransport()
		self.assertEqual(self.deliver(name, transport), "Blocked")
		self.bind.side_effect = None
		self.assertIsNone(self.deliver(name, transport), "a block is never retried (G2)")
		self.assertEqual(self.row(name).status, "Blocked")
		self.assertEqual(transport.effects, {})

	def test_blocked_is_never_enqueued(self):
		"""Only an allowed send reaches enqueue: the outbox has no path that turns a block into a row."""
		before = frappe.db.count(outbox.DOCTYPE)
		with self.assertRaises(outbox.LiteralRecipient):
			outbox.enqueue(request(recipient_ref=PHONE), deliver_now=False)
		with self.assertRaises(ValueError):
			outbox.enqueue(request(step_key=""), deliver_now=False)
		self.assertEqual(frappe.db.count(outbox.DOCTYPE), before)

	def test_redelivery_same_step_key_one_effect(self):
		req = request()
		name = outbox.enqueue(req, deliver_now=False)
		self.assertEqual(outbox.enqueue(req, deliver_now=False), name, "same step key, same row")
		transport = FakeTransport()
		self.assertEqual(self.deliver(name, transport), "Sent")
		self.assertIsNone(self.deliver(name, transport), "re-delivered job: already sent")
		self.assertEqual(transport.effects, {req["step_key"]: 1})

	def test_row_holds_names_only(self):
		name = outbox.enqueue(request(), deliver_now=False)
		self.deliver(name, FakeTransport())
		dumped = frappe.as_json(self.row(name).as_dict())
		self.assertNotIn(SENTINEL, dumped)
		self.assertNotIn(PHONE, dumped)
		self.assertIn('"1"', self.row(name).token_names)

	def test_delivery_status_callback(self):
		name = outbox.enqueue(request(), deliver_now=False)
		self.deliver(name, FakeTransport())
		row = self.row(name)
		outbox.on_delivery_status(provider_message_id=row.provider_message_id, status="delivered")
		self.assertEqual(self.row(name).delivery_status, "delivered")
		outbox.on_delivery_status(provider_message_id=None, status=None)  # never raises

	def test_ambiguous_outcomes_are_final(self):
		dropped = requests.ConnectionError(ProtocolError("Connection aborted.", ConnectionResetError()))
		cases = [
			requests.ReadTimeout("Read timed out."),
			dropped,
			bridge_error(requests.ReadTimeout("Read timed out."), kind="timeout", retryable=True),
			bridge_error(dropped, kind="server", retryable=True),
			bridge_error(KeyError("messages"), message="Unexpected response from WhatsApp."),
			bridge_error(kind="server", retryable=True, message="HTTP 502"),
			bridge_error(graph_code=2, kind="server", retryable=True),
		]
		for error in cases:
			name = outbox.enqueue(request(), deliver_now=False)
			self.assertEqual(self.deliver(name, FakeTransport([error])), "Failed", repr(error))
			self.assertEqual(self.row(name).error_class, outbox.AMBIGUOUS, repr(error))
			self.assertIsNone(self.deliver(name, FakeTransport()))

	def test_provably_unsent_is_retried(self):
		for error in (
			requests.ConnectTimeout("connect timed out"),
			bridge_error(connect_error(), kind="server", retryable=True),
			bridge_error(graph_code=130429, kind="rate_limited", retryable=True),
			bridge_error(graph_code=131016, kind="server", retryable=True),
		):
			name = outbox.enqueue(request(), deliver_now=False)
			self.assertEqual(self.deliver(name, FakeTransport([error])), "Retrying", repr(error))

	def test_stale_sending_is_final_and_a_fresh_one_is_left_alone(self):
		name = outbox.enqueue(request(), deliver_now=False)
		frappe.db.set_value(outbox.DOCTYPE, name, "status", "Sending")
		transport = FakeTransport()
		self.assertIsNone(self.deliver(name, transport), "another worker may still be sending")
		self.assertEqual(self.row(name).status, "Sending")
		old = add_to_date(now_datetime(), minutes=-11)
		frappe.db.set_value(outbox.DOCTYPE, name, "modified", old, update_modified=False)
		self.assertEqual(self.deliver(name, transport), "Failed")
		self.assertEqual(self.row(name).error_class, outbox.AMBIGUOUS)
		self.assertEqual(transport.effects, {})

	def test_block_found_at_delivery_is_final(self):
		self.recheck.return_value = outbox.GATEWAY_DISABLED
		name = outbox.enqueue(request(), deliver_now=False)
		transport = FakeTransport()
		self.assertEqual(self.deliver(name, transport), "Blocked")
		self.assertEqual(self.row(name).error_code, outbox.GATEWAY_DISABLED)
		self.assertEqual(transport.effects, {})

	def test_window_closed_at_delivery_parks_without_spending_an_attempt(self):
		self.recheck.return_value = datetime.now(timezone.utc) + timedelta(hours=2)
		name = outbox.enqueue(request(), deliver_now=False)
		transport = FakeTransport()
		self.assertEqual(self.deliver(name, transport), "Retrying")
		row = self.row(name)
		self.assertEqual(row.attempts, 0)
		self.assertGreater(row.next_attempt_at, add_to_date(now_datetime(), minutes=110))
		self.assertEqual(transport.effects, {})


class TestDeliveryRecheck(IntegrationTestCase):
	"""The guard chain as delivery re-runs it: everything but the cap claim."""

	def setUp(self):
		self.live = patch.object(gate, "is_live", return_value=True).start()
		self.enabled = 1
		real = frappe.db.get_value

		def get_value(doctype, *args, **kwargs):
			if doctype == "Gateway":
				return self.enabled
			return real(doctype, *args, **kwargs)

		patch.object(frappe.db, "get_value", side_effect=get_value).start()
		patch.object(frappe, "get_doc", return_value=SimpleNamespace(flow_id="f", flow_version="1")).start()
		patch.object(guard, "BUILTIN_STEPS", [("consent", self.step)]).start()
		patch.object(guard.guard_steps, "window_resolvers", return_value=[]).start()
		patch.object(guard, "_hook_paths", return_value=[]).start()
		self.cap = patch.object(guard.guard_steps, "apply_caps").start()
		self.addCleanup(patch.stopall)
		self.verdict = {"allow": True}
		self.seen = []

	def step(self, req):
		self.seen.append(req)
		return self.verdict

	def check(self):
		row = SimpleNamespace(
			gateway="g", channel="whatsapp", category="marketing", member_key="m", template="t",
			token_names='["1"]', header=None,  # noqa: S106
			run_id="r", node_id="n", step_key="k",
		)
		return outbox._blocked_now(row, PHONE)

	def test_allows_without_claiming_a_cap(self):
		self.assertIsNone(self.check())
		self.assertEqual(self.seen[0]["recipient"], PHONE)
		self.assertTrue(self.seen[0]["live"])
		self.cap.assert_not_called()

	def test_blocks(self):
		self.verdict = {"allow": False, "reason": "no_opt_in"}
		self.assertEqual(self.check(), "no_opt_in")
		self.verdict = None
		self.assertEqual(self.check(), "hook_error")
		self.live.return_value = False
		self.assertEqual(self.check(), outbox.NOT_LIVE)
		self.enabled = 0
		self.assertEqual(self.check(), outbox.GATEWAY_DISABLED)

	def test_app_hook_blocks(self):
		with patch.object(guard, "_hook_paths", return_value=["app.hook"]), patch.object(
			frappe, "get_attr", return_value=lambda req: {"allow": False, "reason": "freq_cap"}
		):
			self.assertEqual(self.check(), "freq_cap")

	def test_transport_passes_the_step_key(self):
		row = SimpleNamespace(
			channel="whatsapp", gateway="g", template="t", token_names="[]", header=None,  # noqa: S106
			language=None, run_id="r", step_key="sk-1",
		)
		with patch("huf.ai.whatsapp.management._send_authority", return_value=None), patch.object(
			bridge, "send_template", return_value={}
		) as send:
			outbox.whatsapp_transport(row, PHONE, None, {})
		self.assertEqual(send.call_args.kwargs["opaque_ref"], "sk-1")
