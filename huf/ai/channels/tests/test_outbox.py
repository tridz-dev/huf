# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Channel outbox (H-W2-15): retry classes, backoff, blocked never retried (G2), names only (G4), one effect (G5)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.channels import outbox, token_binder

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


class TestOutbox(IntegrationTestCase):
	def setUp(self):
		self.bind = patch.object(token_binder, "bind", return_value={"1": SENTINEL}).start()
		patch.object(frappe.db, "commit").start()
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
		transport = FakeTransport([TimeoutError("timed out")])
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
		transport = FakeTransport([TimeoutError("t")] * outbox.MAX_ATTEMPTS)
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
		# a worker died after claiming: the row is left in Sending
		frappe.db.set_value(outbox.DOCTYPE, name, "status", "Sending")
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
