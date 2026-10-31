"""Phone masking, safe last-real-message samples, editor-only API, test-run kind that never sends."""

from __future__ import annotations

import json
import unittest
from unittest import mock

import frappe

if isinstance(frappe, mock.MagicMock):  # bench-less run: let @frappe.whitelist return the function itself
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)

from huf.ai.flow.gateways import samples_api  # noqa: E402
from huf.ai.flow.gateways.phone_mask import mask_numbers_in_text, mask_phone, mask_sample
from huf.ai.flow.support.trigger_sample import cap_node_samples


class _Throw(Exception):
	pass


def _throw(*args, **kwargs):
	raise _Throw(args[0] if args else "")


class TestPhoneMask(unittest.TestCase):
	def test_keeps_last_four(self):
		self.assertEqual(mask_phone("15550001111"), "****1111")
		self.assertEqual(mask_phone("+91 99999-11111"), "****1111")
		self.assertEqual(mask_phone("123"), "****")
		self.assertEqual(mask_phone(""), "")

	def test_text_numbers_masked_but_not_dates_or_short_numbers(self):
		self.assertEqual(mask_numbers_in_text("call me on +91 99999 11111 please"), "call me on ****1111 please")
		self.assertEqual(mask_numbers_in_text("order 12345 on 2026-01-15"), "order 12345 on 2026-01-15")
		self.assertEqual(mask_numbers_in_text("SKU1234567890"), "SKU1234567890")

	def test_id_fields_and_nested_values(self):
		out = mask_sample(
			{
				"sender_id": "15550001111", "wa_id": "15550001111", "telegram_user_id": 123456789, "text": "my number is 15550001111",
				"received_at": "2026-01-15 17:15:00", "contacts": [{"name": "Ravi", "phones": ["+91 99999 11111"]}], "is_room": False,
			}
		)
		self.assertEqual((out["sender_id"], out["wa_id"], out["telegram_user_id"]), ("****1111", "****1111", "****6789"))
		self.assertEqual(out["text"], "my number is ****1111")
		self.assertEqual(out["received_at"], "2026-01-15 17:15:00")
		self.assertEqual(out["contacts"][0]["phones"], ["****1111"])
		self.assertEqual(out["contacts"][0]["name"], "Ravi")
		self.assertFalse(out["is_room"])
		self.assertNotIn("15550001111", json.dumps(out))

	def test_pinned_chat_sample_is_masked_webhook_sample_is_not(self):
		chat = {"nodes": [{"type": "trigger.whatsapp", "_sample": {"sender_id": "15550001111"}}]}
		hook = {"nodes": [{"type": "trigger.webhook", "_sample": {"sender_id": "15550001111"}}]}
		self.assertTrue(cap_node_samples(chat))
		self.assertEqual(chat["nodes"][0]["_sample"]["sender_id"], "****1111")
		self.assertFalse(cap_node_samples(hook))


class TestSafeMessage(unittest.TestCase):
	def test_no_secrets_no_record_ids_masked(self):
		payload = {"text": "hi", "sender_id": "15550001111", "gateway_event": "GWE-1", "api_key": "abc", "attachments": ["f1"], "_trigger": {}}
		out = samples_api.safe_message(payload)
		self.assertEqual(out, {"text": "hi", "sender_id": "****1111", "api_key": "(hidden)"})


class TestApi(unittest.TestCase):
	def setUp(self):
		patches = [
			mock.patch.object(samples_api.frappe, "throw", side_effect=_throw),
			mock.patch.object(samples_api, "_", lambda s: s),
			mock.patch.object(samples_api.frappe.db, "exists", return_value=True),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		self.node = {"id": "t1", "type": "trigger.whatsapp", "config": {"gateway": "Support"}}
		from huf.ai.flow.testrun import step_test as st

		for p in (mock.patch.object(st, "load_graph", return_value={"nodes": [self.node]}), mock.patch.object(st, "find_node", return_value=self.node)):
			p.start()
			self.addCleanup(p.stop)

	def test_non_editor_is_refused(self):
		with mock.patch.object(samples_api.frappe, "has_permission", return_value=False):
			for fn in (samples_api.get_last_gateway_message, samples_api.get_gateway_sample):
				with self.assertRaises(_Throw):
					fn("f1", "t1")

	def test_other_node_type_refused(self):
		self.node["type"] = "trigger.webhook"
		with mock.patch.object(samples_api.frappe, "has_permission", return_value=True), self.assertRaises(_Throw):
			samples_api.get_gateway_sample("f1", "t1")

	def test_last_message_masked_and_matches_channel(self):
		rows = [
			{"trigger_payload": json.dumps({"gateway": "Other", "sender_id": "999"}), "creation": "2026-01-02"},
			{"trigger_payload": json.dumps({"gateway": "Support", "sender_id": "15550001111", "text": "hi", "gateway_event": "E"}), "creation": "2026-01-01"},
		]
		with (
			mock.patch.object(samples_api.frappe, "has_permission", return_value=True),
			mock.patch.object(samples_api.frappe, "get_all", return_value=rows),
		):
			out = samples_api.get_last_gateway_message("f1", "t1")
		self.assertTrue(out["found"])
		self.assertEqual(out["sample"], {"gateway": "Support", "sender_id": "****1111", "text": "hi"})

	def test_no_gateway_or_no_run(self):
		with (
			mock.patch.object(samples_api.frappe, "has_permission", return_value=True),
			mock.patch.object(samples_api.frappe, "get_all", return_value=[]),
		):
			self.assertFalse(samples_api.get_last_gateway_message("f1", "t1")["found"])
			self.node["config"]["gateway"] = ""
			self.assertFalse(samples_api.get_last_gateway_message("f1", "t1")["found"])

	def test_gateway_write_permission_needed_for_real_messages(self):
		def perm(doctype, ptype=None, doc=None, **kw):
			return not (doctype == "Gateway" and ptype == "write")  # read alone is not enough

		with mock.patch.object(samples_api.frappe, "has_permission", side_effect=perm), self.assertRaises(_Throw):
			samples_api.get_last_gateway_message("f1", "t1")

	def test_sample_is_registry_example_and_masked(self):
		with (
			mock.patch.object(samples_api.frappe, "has_permission", return_value=True),
			mock.patch.object(samples_api.frappe.db, "get_value", return_value="WhatsApp"),
		):
			out = samples_api.get_gateway_sample("f1", "t1")
		self.assertFalse(out["real"])
		self.assertEqual(out["sample"]["gateway"], "Support")
		self.assertTrue(out["sample"]["sender_id"].startswith("****"))


class TestTestRunNeverSends(unittest.TestCase):
	def test_trigger_test_is_simulated_and_records_nothing(self):
		from huf.ai.flow.testrun import step_test_api as api

		node = {"id": "t1", "type": "trigger.telegram", "config": {"gateway": "Bot"}}
		with (
			mock.patch.object(samples_api.frappe.db, "get_value", return_value="Telegram"),
			mock.patch.object(api.st, "_success", side_effect=lambda node, data, started, **meta: {"data": data, **meta}),
			mock.patch.object(api, "clean_sample_input", side_effect=lambda x: {"input": x}),
			mock.patch.object(samples_api.frappe, "get_doc") as get_doc,
			mock.patch.object(samples_api.frappe, "enqueue") as enqueue,
		):
			out = api._test_trigger("f1", node, None)
			picked = api._test_trigger("f1", node, {"text": "hi", "sender_id": "15550001111"})
		self.assertEqual(out["mode"], "simulated")
		self.assertIn("Nothing is sent", out["summary"])
		self.assertEqual(picked["data"], {"text": "hi", "sender_id": "****1111"})
		get_doc.assert_not_called()  # no Gateway Event / Flow Run is created
		enqueue.assert_not_called()


if __name__ == "__main__":
	unittest.main()
