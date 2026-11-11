# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""huf_gateway_delivery_status fires once per (provider_message_id, status) that actually advances."""

from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from huf.ai import gateway_webhook

GW = "gw-1"
WAMID = "wamid.T5"


class _Store:
	"""Stands in for frappe.db for one Gateway Event row."""

	def __init__(self, reply_status=""):
		self.row = {"name": "GE-1", "reply_status": reply_status}
		self.values = {}

	def get_value(self, doctype, filters, fields, as_dict=False):
		return dict(self.row)

	def set_value(self, doctype, name, values, update_modified=True):
		self.row.update(values)
		self.values.update(values)


class TestDeliveryStatusHook(IntegrationTestCase):
	def _run(self, statuses, store=None):
		store = store or _Store()
		with (
			patch.object(gateway_webhook.frappe, "db", store),
			patch.object(gateway_webhook, "fire_hook") as hook,
		):
			for s in statuses:
				gateway_webhook._update_reply_status(GW, {"id": WAMID, **s})
		return store, hook

	def test_sent_delivered_read_fires_three_times(self):
		_, hook = self._run([{"status": "sent"}, {"status": "delivered"}, {"status": "read"}])
		self.assertEqual(hook.call_count, 3)
		first = hook.call_args_list[0]
		self.assertEqual(first.args, ("huf_gateway_delivery_status",))
		self.assertEqual(
			first.kwargs,
			{
				"gateway": GW,
				"provider_message_id": WAMID,
				"status": "sent",
				"error_code": None,
				"error_title": None,
				"event_name": "GE-1",
			},
		)
		self.assertEqual([c.kwargs["status"] for c in hook.call_args_list], ["sent", "delivered", "read"])

	def test_replay_fires_nothing(self):
		store, _ = self._run([{"status": "sent"}, {"status": "delivered"}, {"status": "read"}])
		_, hook = self._run([{"status": "sent"}, {"status": "delivered"}, {"status": "read"}], store)
		self.assertEqual(hook.call_count, 0)

	def test_read_then_late_delivered_fires_only_read(self):
		_, hook = self._run([{"status": "read"}, {"status": "delivered"}])
		self.assertEqual([c.kwargs["status"] for c in hook.call_args_list], ["read"])

	def test_late_sent_after_failed_fires_nothing_new(self):
		_, hook = self._run([{"status": "failed", "errors": [{"code": 1, "title": "x"}]}, {"status": "sent"}])
		self.assertEqual([c.kwargs["status"] for c in hook.call_args_list], ["failed"])

	def test_failed_stores_code_and_joined_summary(self):
		errors = [{"code": 131026, "title": "Undeliverable"}, {"code": 131047, "message": "Re-engagement"}]
		store, hook = self._run([{"status": "failed", "errors": errors}])
		self.assertEqual(str(store.values["delivery_error_code"]), "131026")
		self.assertIn("131026", store.values["delivery_error"])
		self.assertIn("Undeliverable", store.values["delivery_error"])
		self.assertIn("131047", store.values["delivery_error"])
		self.assertEqual(hook.call_count, 1)
		self.assertEqual(hook.call_args.kwargs["error_code"], 131026)
		self.assertEqual(hook.call_args.kwargs["error_title"], "Undeliverable")
		# identical failed replay: nothing
		_, hook2 = self._run([{"status": "failed", "errors": errors}], store)
		self.assertEqual(hook2.call_count, 0)

	def test_raising_handler_does_not_break_update(self):
		store = _Store()
		with (
			patch.object(gateway_webhook.frappe, "db", store),
			patch("huf.ai.gateway_hooks.frappe.get_hooks", return_value=["x.y.z"]),
			patch("huf.ai.gateway_hooks.frappe.get_attr", side_effect=RuntimeError("boom")),
			patch("huf.ai.gateway_hooks.frappe.log_error") as log,
		):
			gateway_webhook._update_reply_status(GW, {"id": WAMID, "status": "delivered"})
		self.assertEqual(store.row["reply_status"], "delivered")
		self.assertTrue(log.called)
